"""Offline acceptance tests: real API-shaped payloads, no network or OAuth."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from spark_google_mcp import GoogleReader, headers, local_window, mail_importance
from spark_sync import IntegrationSync


class GoogleReaderTests(unittest.TestCase):
    def reader(self, account="owner@example.com"):
        value = GoogleReader.__new__(GoogleReader)
        value.account = account
        return value

    def test_ist_midnight_window_is_bounded(self):
        utc = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
        day, tomorrow, after_tomorrow = local_window(utc)
        self.assertEqual(str(day.date()), "2026-10-21")
        self.assertEqual((tomorrow-day).total_seconds(), 86400)
        self.assertEqual((after_tomorrow-tomorrow).total_seconds(), 86400)

    def test_mail_priority_is_preview_based_not_claimed_as_truth(self):
        self.assertEqual(mail_importance("Urgent: payment failed", "", False)[0], "urgent")
        self.assertEqual(mail_importance("Contract approval", "", False)[0], "action")
        self.assertEqual(mail_importance("Hi", "", True)[0], "review")
        self.assertEqual(mail_importance("Hi", "", False)[0], "fyi")
        self.assertEqual(headers({"payload":{"headers":[{"name":"Subject","value":"Hello"}]}}),
                         {"subject":"Hello"})

    def test_read_mail_contains_real_metadata_and_account_specific_source_link(self):
        reader = self.reader()
        commands = []
        def fake(cmd, params):
            commands.append((cmd, params))
            if cmd[-1] == "getProfile":
                return {"emailAddress":"owner@example.com"}
            if cmd[-1] == "list":
                return {"messages":[{"id":"abcdef123", "threadId":"thread123"},
                                    {"id":"bcdef2345", "threadId":"thread234"}]}
            if cmd[-1] == "get":
                subject = "Urgent: payment failed" if params["id"] == "abcdef123" else "Daily digest"
                return {"id":params["id"], "threadId":"thread123" if params["id"]=="abcdef123" else "thread234",
                        "labelIds":["INBOX","UNREAD"] if params["id"]=="abcdef123" else ["INBOX"],
                        "snippet":"Please check account",
                        "payload":{"headers":[{"name":"Subject","value":subject},
                                              {"name":"From","value":"Sender <sender@example.org>"}]}}
            raise AssertionError(cmd)
        reader._run = fake
        answer = reader.read("gmail", "briefing")
        self.assertTrue(answer["ok"])
        msgs = answer["data"]["messages"]
        self.assertEqual(msgs[0]["priority"],"urgent")
        self.assertEqual(msgs[1]["priority"],"fyi")
        self.assertIn("authuser=owner@example.com",msgs[0]["url"])
        self.assertEqual(msgs[0]["reply_status"],"not_verified")
        self.assertEqual(len([cmd for cmd,p in commands if cmd[-1]=="get"]),2)
        self.assertIn("after:", commands[1][1]["q"])

    def test_account_mismatch_fails_closed_before_reading_mail(self):
        reader=self.reader()
        seen=[]
        def fake(command, params):
            seen.append(command)
            return {"emailAddress":"other@example.com"}
        reader._run=fake
        response=reader.read("gmail","briefing")
        self.assertFalse(response["ok"])
        self.assertEqual(response["state"],"account_mismatch")
        self.assertEqual(len(seen),1)

    def test_calendar_event_overlap_detected_from_real_event_boundaries(self):
        reader=self.reader()
        def fake(command, params):
            if command[-1]=="getProfile":return {"emailAddress":"owner@example.com"}
            return {"items":[
                {"id":"a","summary":"Meeting A","start":{"dateTime":"2026-10-21T09:00:00+05:30"},"end":{"dateTime":"2026-10-21T10:00:00+05:30"}},
                {"id":"b","summary":"Meeting B","start":{"dateTime":"2026-10-21T09:30:00+05:30"},"end":{"dateTime":"2026-10-21T10:30:00+05:30"}}]}
        reader._run=fake
        result=reader.read("google-calendar","briefing")
        self.assertTrue(result["ok"])
        self.assertTrue(all(e["overlap"] for e in result["data"]["events"]))

    def test_drive_review_is_only_a_candidate(self):
        reader=self.reader()
        def fake(command,params):
            if command[-1]=="getProfile":return {"emailAddress":"owner@example.com"}
            return {"files":[{"id":"1","name":"TANSAM NDA draft","webViewLink":"https://drive.google.com/file/d/1/view"},
                             {"id":"2","name":"Bike photo"}]}
        reader._run=fake
        result=reader.read("google-drive","briefing")
        self.assertTrue(result["data"]["files"][0]["review_candidate"])
        self.assertFalse(result["data"]["files"][1]["review_candidate"])

    def test_api_error_never_returns_successful_empty_result(self):
        reader=self.reader()
        reader._run=lambda *_: (_ for _ in ()).throw(ValueError("401 private detail"))
        result=reader.read("gmail","briefing")
        self.assertFalse(result["ok"])
        self.assertNotIn("private detail",json.dumps(result))


class Hub:
    def list(self):
        return [{"name":service,"configured":True,
                 "read_tools":["google_daily_briefing","google_list_items"]}
                for service in ("gmail","google-calendar","google-drive")]
    async def execute(self,service,action,args):
        assert args["name"]=="google_daily_briefing"
        payload={"gmail":{"source":"gmail","date":datetime.now(timezone.utc).astimezone(
                         timezone(timedelta(hours=5, minutes=30))).date().isoformat(),
                         "messages":[{"id":"x","priority":"urgent","subject":"Payment failure"}]},
                 "google-calendar":{"source":"google-calendar","events":[{"title":"Meeting"}]},
                 "google-drive":{"source":"google-drive","files":[{"name":"NDA","review_candidate":True}]}}
        return {"content":[{"type":"text","text":json.dumps(
            {"ok":True,"account":"owner@example.com","data":payload[service]})}]}


class BriefingSyncTests(unittest.TestCase):
    def test_only_briefing_tools_scheduled_and_snapshots_are_labeled(self):
        with tempfile.TemporaryDirectory() as tmp:
            sync=IntegrationSync(tmp,Hub(),clock=lambda:datetime.now(timezone.utc).timestamp())
            plan=sync.plan()
            self.assertEqual(len(plan),4)  # three services + connections
            self.assertTrue(all(s!="gmail" or t=="google_daily_briefing" for s,t,_ in plan))
            async def run():
                # Do not call Connections (it also invokes a separate diagnostic source).
                for service,tool,_ in plan[:3]:
                    value=await sync.pull(service,tool)
                    assert value["ok"]
                    body=json.dumps(value)
                    with sync.db() as db:
                        db.execute("INSERT INTO snapshots(id,service,tool,mode,body,last_success,state) VALUES(?,?,?,?,?,?,?)",
                                   (service+'/'+tool,service,tool,'data',body,sync.clock(),'current'))
            asyncio.run(run())
            result=sync.briefing()
            self.assertEqual(result["attention_count"],1)
            self.assertEqual(len(result["events"]),1)
            self.assertEqual(len(result["documents"]),1)
            self.assertEqual(result["sources"]["gmail"]["state"],"current")
            self.assertEqual(result["mode"],"cached Google reads, not live")


if __name__=="__main__":
    unittest.main()
