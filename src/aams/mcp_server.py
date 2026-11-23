"""Local MCP stdio adapter for the model-neutral AAMS store."""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import BeliefProposal, EpistemicState, Evidence, EvidenceStatus, MemoryFormation
from .contracts import MemoryKind
from .recall import CognitiveMemory, CognitiveNeed, Entity
from .storage import AccessContext, SQLiteMemoryStore, StoreIntegrityError, VersionConflict
from .storage import WriteConflict

PROTOCOL_VERSION = "2026-07-28"
MAX_FRAME_BYTES = 256 * 1024
Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Timestamp = Annotated[str, Field(min_length=20, max_length=40)]
Text = Annotated[str, Field(min_length=1, max_length=4096)]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FormInput(ToolInput):
    request_key: Identifier
    text: Text
    source_actor: Identifier
    source_locator: Annotated[str, Field(min_length=1, max_length=512)]
    observed_at: Timestamp
    kind: MemoryKind = MemoryKind.EXPERIENCE


class RetrievalInput(ToolInput):
    recorded_as_of: Timestamp | None = None
    effective_at: Timestamp | None = None
    max_depth: Annotated[int, Field(strict=True, ge=0, le=1)] = 1
    max_bytes: Annotated[int, Field(strict=True, ge=128, le=65536)] = 16384


class RecallInput(RetrievalInput):
    query: Annotated[str, Field(max_length=1024)] = ""
    entity: Entity | None = None
    identifier: Identifier | None = None
    kinds: Annotated[list[MemoryKind], Field(max_length=7)] = Field(default_factory=list)
    max_items: Annotated[int, Field(strict=True, ge=1, le=100)] = 10


class ExplainInput(RetrievalInput):
    entity: Entity
    identifier: Identifier


class ReviseInput(ToolInput):
    belief_id: Identifier
    expected_revision: Identifier | None
    proposition: Text
    state: Literal["inferred", "hypothetical", "contested", "superseded", "rejected"]
    rationale: Text
    valid_from: Timestamp
    valid_until: Timestamp | None = None
    support_ids: Annotated[list[Identifier], Field(max_length=32)] = Field(default_factory=list)
    refute_ids: Annotated[list[Identifier], Field(max_length=32)] = Field(default_factory=list)
    confidence_basis: Text | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _success(value: dict) -> types.CallToolResult:
    return types.CallToolResult(
        structuredContent=value, content=[types.TextContent(type="text", text=json.dumps(value))]
    )


def _error(code: str) -> types.CallToolResult:
    return types.CallToolResult(
        isError=True,
        structuredContent={"code": code},
        content=[types.TextContent(type="text", text=code)],
    )


def build_server(store: SQLiteMemoryStore, access: AccessContext) -> Server:
    memory = CognitiveMemory(store)

    def form(args: FormInput) -> dict:
        key = json.dumps([access.scope, access.principal, args.request_key])
        token = sha256(key.encode()).hexdigest()
        payload = args.text.encode()
        recorded_at = store.ingestion_time(access, args.request_key) or _now()
        record = Evidence(
            "ev-" + token,
            access.scope,
            args.source_actor,
            args.source_locator,
            access.principal,
            args.observed_at,
            recorded_at,
            EvidenceStatus.UNVERIFIED,
            payload,
            "sha256:" + sha256(payload).hexdigest(),
        )
        formation = MemoryFormation(
            "fm-" + token,
            access.scope,
            args.kind,
            (record.evidence_id,),
            access.principal,
            record.recorded_at,
            EpistemicState.OBSERVED,
        )
        try:
            store.ingest(access, args.request_key, formation, (record,))
        except WriteConflict:
            # A concurrent process may have committed this key after the first read.
            winner_time = store.ingestion_time(access, args.request_key)
            if winner_time is None or winner_time == recorded_at:
                raise
            retry_record = Evidence(
                record.evidence_id,
                record.scope,
                record.source_actor,
                record.source_locator,
                record.producer,
                record.observed_at,
                winner_time,
                record.status,
                record.payload,
                record.digest,
            )
            retry_formation = MemoryFormation(
                formation.formation_id,
                formation.scope,
                formation.kind,
                formation.evidence_ids,
                formation.producer,
                winner_time,
                formation.epistemic_state,
            )
            store.ingest(access, args.request_key, retry_formation, (retry_record,))
        return {"formation_id": formation.formation_id, "evidence_id": record.evidence_id}

    def recall(args: RecallInput) -> dict:
        fields = args.model_dump(exclude={"kinds"})
        return memory.recall(access, CognitiveNeed(**fields, kinds=tuple(args.kinds)))

    def explain(args: ExplainInput) -> dict:
        return memory.explain(access, CognitiveNeed(**args.model_dump()))

    def revise(args: ReviseInput) -> dict:
        proposal = BeliefProposal(
            args.proposition,
            EpistemicState(args.state),
            args.rationale,
            args.valid_from,
            args.valid_until,
            tuple(args.support_ids),
            tuple(args.refute_ids),
            args.confidence_basis,
        )
        revision = store.revise(access, args.belief_id, args.expected_revision, proposal)
        return asdict(revision)

    handlers = {
        "memory_form": (FormInput, form, "Store a reported observation and its original text."),
        "memory_recall": (RecallInput, recall, "Find scoped memory by query or exact identity."),
        "memory_explain": (
            ExplainInput,
            explain,
            "Explain a scoped memory through its provenance.",
        ),
        "memory_revise": (
            ReviseInput,
            revise,
            "Append a belief revision with scoped evidence links.",
        ),
    }
    definitions = [
        types.Tool(name=name, description=description, inputSchema=model.model_json_schema())
        for name, (model, _, description) in handlers.items()
    ]

    async def list_tools(_context, _params):
        return types.ListToolsResult(tools=definitions)

    async def call_tool(_context, params):
        entry = handlers.get(params.name)
        if entry is None:
            return _error("UNKNOWN_TOOL")
        model, handler, _ = entry
        try:
            arguments = model.model_validate(
                params.arguments if params.arguments is not None else {}
            )
            return _success(await asyncio.to_thread(handler, arguments))
        except PermissionError:
            return _error("ACCESS_DENIED")
        except VersionConflict:
            return _error("VERSION_CONFLICT")
        except WriteConflict:
            return _error("WRITE_CONFLICT")
        except (ValidationError, ValueError):
            return _error("INVALID_INPUT")
        except StoreIntegrityError:
            return _error("STORE_ERROR")

    return Server("aams", version="0.1.0", on_list_tools=list_tools, on_call_tool=call_tool)


class _BoundedInput:
    """Provide the SDK with complete newline-delimited frames of bounded size."""

    async def __aiter__(self):
        while True:
            frame = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_FRAME_BYTES + 1)
            if not frame:
                return
            if len(frame) > MAX_FRAME_BYTES or not frame.endswith(b"\n"):
                print("AAMS closed stdio after an oversized or incomplete frame.", file=sys.stderr)
                return
            yield frame


async def _serve(server: Server) -> None:
    async with stdio_server(stdin=_BoundedInput()) as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve AAMS over MCP stdio")
    parser.add_argument("--db", required=True, help="Path to the local SQLite database")
    parser.add_argument("--principal", required=True, help="Host-assigned principal")
    parser.add_argument("--scope", required=True, help="Host-assigned scope")
    parser.add_argument("--write", action="store_true", help="Grant writes to this process")
    args = parser.parse_args()
    access = AccessContext(args.principal, args.scope, args.write)
    asyncio.run(_serve(build_server(SQLiteMemoryStore(args.db), access)))


if __name__ == "__main__":
    main()
