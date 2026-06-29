import json
import os
import tempfile
import unittest

from core.lifecycle import TaskResult, TaskTerminalStatus
from core.observe import observer
from core.observe.events import close_jsonl, get_events, open_jsonl, record_event, reset_events
from core.observe.summary import format_execution_summary


class ObserveEventsTests(unittest.TestCase):
    def setUp(self):
        observer.reset_download_profiling()

    def tearDown(self):
        close_jsonl()

    def test_event_store_records_sequence_and_filters_by_type(self):
        first = record_event("alpha", dep="a")
        second = record_event("beta", dep="b")

        self.assertEqual(first["seq"] + 1, second["seq"])
        self.assertEqual([e["event"] for e in get_events()], ["alpha", "beta"])
        self.assertEqual(get_events("beta"), [second])

        reset_events()
        self.assertEqual(get_events(), [])

    def test_event_store_writes_jsonl_when_sink_is_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "events.jsonl")
            open_jsonl(path)
            record_event("alpha", dep="a")
            record_event("beta", dep="b")
            close_jsonl()

            with open(path) as f:
                lines = [json.loads(line) for line in f]

        self.assertEqual([line["event"] for line in lines], ["alpha", "beta"])

    def test_observer_records_lifecycle_download_and_cache_events(self):
        observer.record_lifecycle_result(
            TaskResult("dep", dep_type="action", status=TaskTerminalStatus.SUCCEEDED)
        )
        observer.record_download_task(7, {"kind": "http", "url": "u", "bytes": 3})
        observer.record_cache_access("http", True)

        events = get_events()
        self.assertEqual(
            [event["event"] for event in events],
            ["task.completed", "download.completed", "cache.checked"],
        )
        self.assertEqual(observer.get_lifecycle_results()[0]["name"], "dep")
        self.assertEqual(observer.get_all_download_tasks_sorted()[0]["url"], "u")
        self.assertEqual(observer.get_cache_stats()["hit"], 1)
        self.assertEqual(events[0]["dep"], "dep")
        self.assertEqual(events[0]["status"], "succeeded")
        self.assertEqual(events[1]["durationMs"], 7)
        self.assertTrue(events[2]["hit"])

    def test_summary_formats_counts_failures_skips_and_slowest_tasks(self):
        self.assertEqual(format_execution_summary([]), [])
        events = [
            {
                "event": "task.completed",
                "dep": "a",
                "depType": "action",
                "status": "failed",
                "durationMs": 31,
                "errorMessage": "boom",
            },
            {
                "event": "task.completed",
                "dep": "b",
                "depType": "action",
                "status": "skipped",
                "durationMs": 1,
                "reason": "upstream_failed",
                "required": ["a"],
            },
            {
                "event": "task.completed",
                "dep": "c",
                "depType": "git",
                "status": "succeeded",
                "durationMs": 120,
            },
        ]

        lines = format_execution_summary(events)

        self.assertIn("Execution summary: succeeded=1 failed=1 skipped=1 cancelled=0", lines)
        self.assertIn("Failed tasks: a (boom)", lines)
        self.assertIn("Skipped tasks: b (upstream_failed: a)", lines)
        self.assertIn("Slowest tasks: c 120ms, a 31ms, b 1ms", lines)


if __name__ == "__main__":
    unittest.main()
