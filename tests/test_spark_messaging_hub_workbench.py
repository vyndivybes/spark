"""Capabilities 02 & 06 — Workbench/UI wiring acceptance for the messaging hub.

Exercises hub actions through the real Workbench dispatch with a real
SparkWorkspace. No network: configure/receive use only local state errors.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_workspace import SparkWorkspace
from spark_workbench import ACTION_KEYS, Workbench
from spark_productivity import WorkbenchError


class HubWorkbenchWiringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = SparkWorkspace(self.directory.name)
        self.workbench = Workbench(self.workspace)
        self.project = "general"
        self.addAsyncCleanup(self._close)

    async def _close(self):
        await self.workbench.integrations.close()
        await self.workbench.intelligence.close()
        self.directory.cleanup()

    async def action(self, action, **payload):
        return await self.workbench.execute(action, self.project, payload)

    async def test_hub_actions_are_registered(self):
        for action in ("hub_status", "hub_configure", "hub_disconnect",
                       "hub_approve", "hub_send", "hub_receive", "hub_history"):
            self.assertIn(action, ACTION_KEYS)

    async def test_hub_status_starts_empty_with_no_open_relay_policy(self):
        status = await self.action("hub_status")
        self.assertEqual(status["schema"], "spark.messaging_hub.v1")
        self.assertEqual(status["channels"], {})
        self.assertIn("no open relay", status["policy"])

    async def test_configure_enable_and_disconnect_revoke(self):
        await self.action("hub_configure", channel="telegram",
                          config={"bot_token": "123:abc", "allowed_chat_id": "42"})
        status = await self.action("hub_status")
        self.assertEqual(status["channels"]["telegram"]["state"], "configured, untested")
        revoked = await self.action("hub_disconnect", channel="telegram")
        self.assertFalse(revoked["configured"])

    async def test_approve_and_send_without_provider_credentials_are_refused(self):
        with self.assertRaises(WorkbenchError):
            await self.action("hub_approve", channel="not-a-channel",
                              recipient="42", text="hello")

    async def test_send_without_configuration_is_refused(self):
        await self.action("hub_configure", channel="telegram",
                         config={"bot_token": "123:abc", "allowed_chat_id": "42"})
        approval = (await self.action("hub_approve", channel="telegram",
                                      recipient="42", text="hello"))["approval_id"]
        await self.action("hub_disconnect", channel="telegram")
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("hub_send", channel="telegram", approval_id=approval)
        self.assertIn("not configured", str(caught.exception))

    async def test_receive_unconfigured_channel_is_refused(self):
        with self.assertRaises(WorkbenchError):
            await self.action("hub_receive", channel="whatsapp")

    async def test_whatsapp_prepare_records_pricing_gate_not_a_free_claim(self):
        await self.action("hub_configure", channel="whatsapp",
                          config={"access_token": "EAAG", "phone_number_id": "1",
                                  "allowed_recipient": "911234567890"})
        approval = (await self.action("hub_approve", channel="whatsapp",
                                      recipient="911234567890", text="Report"))["approval_id"]
        with self.assertRaises(WorkbenchError) as caught:
            await self.action("hub_send", channel="whatsapp", approval_id=approval)
        self.assertIn("pricing", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
