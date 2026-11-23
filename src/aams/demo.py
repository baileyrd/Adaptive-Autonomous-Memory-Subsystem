"""Exercise the AAMS stdio workflow with the pinned MCP SDK client."""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from .mcp_server import PROTOCOL_VERSION

OBSERVED_AT = "2026-01-12T09:00:00Z"
OBSERVATION = {
    "request_key": "station-reading",
    "text": "Rain gauge recorded 12 mm.",
    "source_actor": "station-1",
    "source_locator": "station:1/gauge/1",
    "observed_at": OBSERVED_AT,
}


def local_client(path: Path, principal: str, scope: str, *, write: bool = False) -> Client:
    args = ["-m", "aams.mcp_server", "--db", str(path), "--principal", principal, "--scope", scope]
    if write:
        args.append("--write")
    env = {"PYTHONPATH": os.environ["PYTHONPATH"]} if "PYTHONPATH" in os.environ else None
    return Client(
        StdioServerParameters(command=sys.executable, args=args, env=env),
        mode="auto",
        read_timeout_seconds=10,
    )


async def _call(client: Client, tool: str, arguments: dict) -> dict:
    result = await client.call_tool(tool, arguments)
    if result.is_error or result.structured_content is None:
        raise RuntimeError(f"{tool} failed: {result.structured_content}")
    return result.structured_content


async def _collect(path: Path) -> dict:
    async with local_client(path, "collector", "weather", write=True) as collector:
        tools = {tool.name for tool in (await collector.list_tools()).tools}
        if collector.protocol_version != PROTOCOL_VERSION or tools != {
            "memory_form",
            "memory_recall",
            "memory_explain",
            "memory_revise",
        }:
            raise RuntimeError("Unexpected MCP version or tools")
        observation = await _call(collector, "memory_form", OBSERVATION)
        if await _call(collector, "memory_form", OBSERVATION) != observation:
            raise RuntimeError("Replay changed observation identity")

    return observation


async def _analyze(path: Path, observation: dict) -> dict:
    async with local_client(path, "analyst", "weather", write=True) as analyst:
        packet = await _call(
            analyst,
            "memory_recall",
            {"entity": "formation", "identifier": observation["formation_id"]},
        )
        citation = packet["items"][0]["citations"][0]
        preview = citation["preview"]
        digest = "sha256:" + sha256(OBSERVATION["text"].encode()).hexdigest()
        if preview != OBSERVATION["text"] or citation["digest"] != digest:
            raise RuntimeError("Reopened process returned unexpected evidence")
        proposal = {
            "belief_id": "weather-assessment",
            "expected_revision": None,
            "proposition": "Rainfall was 12 mm.",
            "state": "inferred",
            "rationale": "Initial gauge reading.",
            "valid_from": OBSERVED_AT,
            "support_ids": [observation["evidence_id"]],
        }
        first = await _call(analyst, "memory_revise", proposal)
        correction = await _call(
            analyst,
            "memory_form",
            {
                **OBSERVATION,
                "request_key": "calibration-record",
                "source_locator": "station:1/calibration/1",
                "text": "Gauge calibration was overdue.",
            },
        )
        latest = await _call(
            analyst,
            "memory_revise",
            {
                **proposal,
                "expected_revision": first["revision_id"],
                "proposition": "Rainfall was reported as 12 mm; calibration is uncertain.",
                "state": "contested",
                "rationale": "Calibration record conflicts with the assumption.",
                "refute_ids": [correction["evidence_id"]],
            },
        )
        target = {"entity": "belief", "identifier": proposal["belief_id"]}
        current = (await _call(analyst, "memory_explain", target))["items"][0]
        past = (
            await _call(
                analyst, "memory_recall", {**target, "recorded_as_of": first["recorded_at"]}
            )
        )["items"][0]
        if (
            current["revision_id"] != latest["revision_id"]
            or past["revision_id"] != first["revision_id"]
        ):
            raise RuntimeError("Belief history did not reconstruct")
        if [edge["role"] for edge in current["citations"]] != ["support", "refute"]:
            raise RuntimeError("Explanation omitted supporting or refuting evidence")

    return {
        "protocol": PROTOCOL_VERSION,
        "observation_after_restart": preview,
        "observation_digest_verified": True,
        "prior_belief": past["proposition"],
        "current_belief": current["proposition"],
        "provenance_roles": [edge["role"] for edge in current["citations"]],
    }


async def _check_denial(path: Path) -> dict:
    target = {"entity": "belief", "identifier": "weather-assessment"}
    async with local_client(path, "visitor", "other") as visitor:
        denied = await _call(visitor, "memory_explain", target)
        missing = await _call(visitor, "memory_explain", {**target, "identifier": "unknown"})
        write = await visitor.call_tool("memory_form", OBSERVATION)
        if (
            denied != missing
            or denied["items"]
            or write.structured_content != {"code": "ACCESS_DENIED"}
        ):
            raise RuntimeError("Expected scope and write restrictions")
    return {"out_of_scope": denied, "write_denial": write.structured_content}


async def _run_phase(path: Path, phase: str, inputs: dict) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "aams.demo",
        "--phase",
        phase,
        "--db",
        str(path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(json.dumps(inputs).encode()), 30)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(
            f"Demo client phase {phase} failed with exit status {process.returncode}"
        )
    return json.loads(output)


async def run_demo(path: Path) -> dict:
    observation = await _run_phase(path, "collect", {})
    result = await _run_phase(path, "analyze", observation)
    return {**result, **(await _run_phase(path, "check-denial", {}))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("collect", "analyze", "check-denial"), help=argparse.SUPPRESS
    )
    parser.add_argument("--db", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.phase is None:
        with tempfile.TemporaryDirectory(prefix="aams-demo-") as directory:
            result = asyncio.run(run_demo(Path(directory) / "memory.db"))
    else:
        if args.db is None:
            parser.error("--phase requires --db")
        data = json.load(sys.stdin)
        if args.phase == "collect":
            result = asyncio.run(_collect(args.db))
        elif args.phase == "analyze":
            result = asyncio.run(_analyze(args.db, data))
        else:
            result = asyncio.run(_check_denial(args.db))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
