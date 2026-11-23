import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from aams.demo import OBSERVATION, local_client, run_demo
from aams.mcp_server import PROTOCOL_VERSION


class MCPTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "mcp.sqlite3"

    async def test_executable_restart_workflow(self):
        result = await run_demo(self.path)
        self.assertEqual(result["protocol"], PROTOCOL_VERSION)
        self.assertEqual(result["observation_after_restart"], OBSERVATION["text"])
        self.assertEqual(result["prior_belief"], "Rainfall was 12 mm.")
        self.assertEqual(result["provenance_roles"], ["support", "refute"])

    async def test_schemas_and_nonleaking_errors(self):
        async with local_client(self.path, "writer", "weather", write=True) as client:
            tools = {item.name: item.input_schema for item in (await client.list_tools()).tools}
            self.assertFalse(tools["memory_form"]["additionalProperties"])
            self.assertIn("expected_revision", tools["memory_revise"]["required"])
            for name, args, code in (
                ("memory_form", {**OBSERVATION, "scope": "forged"}, "INVALID_INPUT"),
                ("memory_form", {**OBSERVATION, "text": "x" * 4097}, "INVALID_INPUT"),
                ("missing_tool", {}, "UNKNOWN_TOOL"),
            ):
                result = await client.call_tool(name, args)
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content, {"code": code})
            await client.call_tool("memory_form", OBSERVATION)
            conflict = await client.call_tool("memory_form", {**OBSERVATION, "text": "mismatch"})
            self.assertEqual(conflict.structured_content, {"code": "WRITE_CONFLICT"})

    async def test_modern_wire_validation(self):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "aams.mcp_server",
            "--db",
            os.fspath(self.path),
            "--principal",
            "test",
            "--scope",
            "weather",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        meta = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": {"name": "wire-test", "version": "1"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }

        async def request(number, method, params):
            frame = {"jsonrpc": "2.0", "id": number, "method": method, "params": params}
            process.stdin.write(json.dumps(frame).encode() + b"\n")
            await process.stdin.drain()
            reply = json.loads(await asyncio.wait_for(process.stdout.readline(), 10))
            self.assertEqual(reply["id"], number)
            return reply

        try:
            discovery = await request(1, "server/discover", {"_meta": meta})
            self.assertIn(PROTOCOL_VERSION, discovery["result"]["supportedVersions"])
            missing = await request(2, "tools/list", {})
            self.assertIn("error", missing)
            unsupported = await request(
                3,
                "tools/list",
                {"_meta": {**meta, "io.modelcontextprotocol/protocolVersion": "2039-01-01"}},
            )
            self.assertEqual(unsupported["error"]["code"], -32022)
            process.stdin.write(b"{invalid json}\n")
            await process.stdin.drain()
            tools = await request(4, "tools/list", {"_meta": meta})
            self.assertEqual(len(tools["result"]["tools"]), 4)
        finally:
            process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()
        self.assertEqual(process.returncode, 0)
