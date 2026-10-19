import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
import asyncio
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_rea import ReaClient, ReaError, validate_schema_references


class SchemaPolicyTests(unittest.TestCase):
    def test_schema_validation_never_fetches_remote_or_local_file_references(self):
        for reference in ('https://example.com/schema','file:///private.json'):
            with self.assertRaises(ReaError):validate_schema_references({'type':'object','properties':{'x':{'$ref':reference}}})
        validate_schema_references({'$defs':{'value':{'type':'string'}},'properties':{'x':{'$ref':'#/$defs/value'}}})


@unittest.skipUnless(importlib.util.find_spec("mcp") and importlib.util.find_spec("jsonschema"), "Optional MCP client dependencies unavailable")
class ReaTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_closes_owned_transport_instead_of_finishing_a_hidden_call(self):
        client=ReaClient(sys.executable,[str(Path(__file__).parent/'fixtures'/'rea_mcp_server.py')],{'SPARK_TEST_MCP_SLOW':'1'})
        try:
            await client.request('rea_discover',{})
            call=asyncio.create_task(client.request('rea_call',{'name':'wait_for_test','arguments':{'seconds':3}}))
            await asyncio.sleep(.1)
            call.cancel()
            with self.assertRaises(asyncio.CancelledError):await call
            self.assertTrue(client.worker.done())
        finally:await client.close()

    async def asyncSetUp(self):
        self.environment = patch.dict(os.environ, {
            "SPARK_REA_COMMAND": sys.executable,
            "SPARK_REA_ARGS": json.dumps([str(Path(__file__).parent / "fixtures" / "rea_mcp_server.py")]),
        })
        self.environment.start()
        self.client = ReaClient()

    async def asyncTearDown(self):
        await self.client.close()
        self.environment.stop()

    async def test_discovery_and_calls_retain_server_state(self):
        catalog = await self.client.request("rea_discover", {})
        self.assertEqual({t["name"] for t in catalog}, {"increment", "read_counter"})
        result = await self.client.request("rea_call", {"name": "increment", "arguments": {"amount": 7}})
        self.assertFalse(result.get("isError", False))
        result = await self.client.request("rea_call", {"name": "read_counter", "arguments": {}})
        self.assertEqual(result["content"][0]["text"], "7")

    async def test_schema_and_unknown_tool_rejection_do_not_lose_session(self):
        await self.client.request("rea_discover", {})
        for name, arguments in (("missing", {}), ("increment", {}), ("increment", {"amount": "bad"})):
            with self.assertRaises(ReaError):
                await self.client.request("rea_call", {"name": name, "arguments": arguments})
        result = await self.client.request("rea_call", {"name": "read_counter", "arguments": {}})
        self.assertEqual(result["content"][0]["text"], "0")

    async def test_failed_start_reports_error_and_can_reconnect(self):
        os.environ["SPARK_REA_COMMAND"] = "spark-nonexistent-mcp-executable"
        with self.assertRaises(ReaError):
            await self.client.request("rea_discover", {})
        os.environ["SPARK_REA_COMMAND"] = sys.executable
        catalog = await self.client.request("rea_discover", {})
        self.assertEqual(len(catalog), 2)


if __name__ == "__main__":
    unittest.main()
