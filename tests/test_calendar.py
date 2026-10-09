import json
import unittest
from datetime import date
from types import SimpleNamespace

from app.agent.conversation import Conversation
from app.graph.workflow import _answer_from_calendar, build_graph, empty_state
from app.mcp.calendar import (
    ALLOW,
    MISSING,
    NOT_ALLOWED,
    Calendar,
    calendar_request,
    day_range,
    events_from_tool_text,
    week_range,
)
from tests.test_phase2 import FakeLLM, FakeMessage


def _settings(client_json="", url="https://calendarmcp.googleapis.com/mcp/v1"):
    return SimpleNamespace(
        google_client_json=client_json, calendar_mcp_url=url
    )


class FakeCalendar:
    def __init__(self, text=""):
        self.calls = []
        self.text = text

    def call(self, action, arguments):
        self.calls.append((action, arguments))
        return self.text


class FakeAuth:
    def __init__(self, refresh="refresh-token", access="access-token"):
        self.refresh = refresh
        self.access = access

    def load_refresh_token(self, path):
        return self.refresh

    def refresh_access_token(self, client_json, refresh):
        return self.access if refresh == "refresh-token" else ""


class RouterTests(unittest.TestCase):
    def test_tomorrow_maps_to_tomorrow_range(self):
        action, args = calendar_request(
            "What's on my calendar tomorrow?", today=date(2026, 10, 8)
        )
        self.assertEqual(action, "list_events")
        self.assertEqual(args["startTime"], "2026-10-09T00:00:00")
        self.assertEqual(args["endTime"], "2026-10-10T00:00:00")

    def test_today_is_the_default(self):
        action, args = calendar_request(
            "What do I have on my calendar?", today=date(2026, 10, 8)
        )
        self.assertEqual(action, "list_events")
        self.assertEqual(args["startTime"], "2026-10-08T00:00:00")

    def test_this_week_spans_monday(self):
        start, end = week_range(date(2026, 10, 8))
        self.assertEqual(start, "2026-10-05T00:00:00")
        self.assertEqual(end, "2026-10-12T00:00:00")

    def test_day_range_has_no_utc_offset(self):
        start, end = day_range(date(2026, 10, 8))
        self.assertNotIn("Z", start + end)
        self.assertNotIn("+", start + end)

    def test_search_finds_a_topic(self):
        action, args = calendar_request("When is my dentist appointment?")
        self.assertEqual(action, "search_events")
        self.assertEqual(args["query"], "dentist appointment")

    def test_calendars_list(self):
        self.assertEqual(
            calendar_request("List my calendars"), ("list_calendars", {})
        )

    def test_free_time_uses_suggest(self):
        action, _args = calendar_request("Am I free tomorrow afternoon?")
        self.assertEqual(action, "suggest_time")

    def test_fact_is_not_a_calendar_question(self):
        self.assertEqual(
            calendar_request("What is the capital of Japan?"), ("", {})
        )


class ParseTests(unittest.TestCase):
    def test_titles_and_times(self):
        payload = json.dumps(
            {
                "items": [
                    {
                        "summary": "Standup",
                        "start": {"dateTime": "2026-10-09T09:00:00"},
                    },
                    {"summary": "Lunch", "start": {"date": "2026-10-09"}},
                ]
            }
        )
        self.assertEqual(
            events_from_tool_text(payload),
            ["Standup at 2026-10-09T09:00:00", "Lunch at 2026-10-09"],
        )

    def test_bad_payload_lists_nothing(self):
        self.assertEqual(events_from_tool_text("not json"), [])


class ClientTests(unittest.TestCase):
    def test_write_tool_is_refused(self):
        calendar = Calendar(_settings("client.json"))
        self.assertEqual(calendar.call("create_event", {}), NOT_ALLOWED)

    def test_missing_sign_in(self):
        calendar = Calendar(_settings(""))
        self.assertEqual(
            calendar.call("list_events", {"pageSize": 10}), MISSING
        )

    def test_missing_refresh_token(self):
        calendar = Calendar(_settings("client.json"))
        calendar._auth = FakeAuth(refresh="")
        self.assertEqual(
            calendar.call("list_events", {"pageSize": 10}), MISSING
        )

    def test_failed_refresh_needs_sign_in(self):
        calendar = Calendar(_settings("client.json"))
        calendar._auth = FakeAuth(refresh="stale", access="")
        self.assertEqual(
            calendar.call("list_events", {"pageSize": 10}), MISSING
        )

    def test_allow_list_has_no_writes(self):
        self.assertNotIn("create_event", ALLOW)
        self.assertNotIn("update_event", ALLOW)
        self.assertNotIn("delete_event", ALLOW)
        self.assertNotIn("respond_to_event", ALLOW)

    def test_refused_token_needs_sign_in(self):
        from app.mcp.client import McpError

        calendar = Calendar(_settings("client.json"))
        calendar._auth = FakeAuth()

        class RefusingClient:
            def call_tool(self, name, arguments):
                raise McpError("The access token was refused.")

            def close(self):
                return None

        calendar.client = RefusingClient()
        self.assertEqual(
            calendar.call("list_events", {"pageSize": 10}), MISSING
        )


if __name__ == "__main__":
    unittest.main()

class GraphTests(unittest.TestCase):
    def test_tomorrow_calls_calendar_once(self):
        calendar = FakeCalendar(
            json.dumps(
                {
                    "items": [
                        {
                            "summary": "Standup",
                            "start": {"dateTime": "2026-10-09T09:00:00"},
                        }
                    ]
                }
            )
        )

        class SummaryModel:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                return FakeMessage("You have Standup at 9 AM tomorrow.")

        graph = build_graph(
            SummaryModel(), Conversation(), calendar=calendar
        )
        result = graph.invoke(
            empty_state("What's on my calendar tomorrow?")
        )
        self.assertEqual(calendar.calls[0][0], "list_events")
        self.assertEqual(
            result["response"], "You have Standup at 9 AM tomorrow."
        )

    def test_empty_day_says_so(self):
        calendar = FakeCalendar(json.dumps({"items": []}))
        spoken = _answer_from_calendar(
            calendar,
            FakeLLM(FakeMessage("unused")),
            "What's on my calendar today?",
            "list_events",
            {},
        )
        self.assertEqual(spoken, "You have nothing scheduled there.")

    def test_sign_in_message_passes_through(self):
        calendar = FakeCalendar(MISSING)
        spoken = _answer_from_calendar(
            calendar, None, "What's on my calendar today?", "list_events", {}
        )
        self.assertEqual(spoken, MISSING)

    def test_fact_does_not_call_calendar(self):
        calendar = FakeCalendar("should not be used")
        message = FakeMessage("Tokyo is the capital of Japan.")
        graph = build_graph(
            FakeLLM(message), Conversation(), calendar=calendar
        )
        result = graph.invoke(empty_state("What is the capital of Japan?"))
        self.assertEqual(calendar.calls, [])
        self.assertEqual(result["response"], "Tokyo is the capital of Japan.")


