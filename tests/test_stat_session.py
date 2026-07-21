import json
import logging
import os
import tempfile
import unittest
from unittest.mock import patch

from core.observe import observer
from core.observe.stat_session import StatSession

SESSION_META_KEYS = {
    "type",
    "fileCreatedAtMs",
    "user",
    "project",
    "habVersion",
    "host",
}
HOST_KEYS = {
    "platform",
    "system",
    "release",
    "machine",
    "pythonVersion",
    "nodeIP",
    "cicdEnv",
}
INVOCATION_KEYS = {
    "type",
    "option",
    "invTSMs",
    "durationMs",
    "cpuUsagePercent",
    "argv",
    "exitCode",
    "downloads",
    "downloadTimeByDependency",
    "downloadTimeStats",
    "cacheStats",
}


def _read_events(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class StatSessionTests(unittest.TestCase):
    def setUp(self):
        observer.reset_download_profiling()

    def test_writes_habitat_session_and_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "habitat_session.jsonl")
            session = StatSession(path, ["sync", "."], "sync")
            session.start()
            observer.record_download_task(
                7, {"kind": "http", "url": "https://example.test/a", "bytes": 3}
            )
            observer.record_cache_access("http", True)
            session.finish(0)

            meta, invocation = _read_events(path)

        self.assertEqual(set(meta), SESSION_META_KEYS)
        self.assertEqual(set(meta["host"]), HOST_KEYS)
        self.assertEqual(set(invocation), INVOCATION_KEYS)
        self.assertEqual(invocation["type"], "invocation")
        self.assertEqual(invocation["option"], "sync")
        self.assertEqual(invocation["argv"], ["sync", "."])
        self.assertEqual(invocation["exitCode"], 0)
        self.assertEqual(invocation["downloads"][0]["durationMs"], 7)
        self.assertEqual(invocation["cacheStats"]["hit"], 1)

    def test_start_replaces_an_existing_session_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "habitat_session.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"type":"stale"}\n')

            session = StatSession(path, ["deps", "."], "deps")
            session.start()
            session.finish(1, RuntimeError("boom"))

            events = _read_events(path)

        self.assertEqual(
            [event["type"] for event in events],
            ["session_meta", "invocation"],
        )
        self.assertEqual(events[-1]["exitCode"], 1)
        self.assertEqual(
            events[-1]["exceptions"],
            [{"type": "RuntimeError", "message": "boom"}],
        )

    def test_captures_warning_log_using_habitat_event_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "habitat_session.jsonl")
            session = StatSession(path, ["sync", "."], "sync")
            session.start()
            logging.warning("warning from habitat")
            session.finish(0)

            warning_event = _read_events(path)[-1]

        self.assertEqual(
            set(warning_event),
            {"type", "invTSMs", "path", "tail", "truncated", "sizeBytes"},
        )
        self.assertEqual(warning_event["type"], "warn_error_log")
        self.assertIn("warning from habitat", warning_event["tail"])

    def test_reads_project_metadata_from_command_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "target")
            os.makedirs(target)
            with open(os.path.join(target, ".habitat"), "w", encoding="utf-8") as f:
                f.write(
                    "solutions = [{"
                    "'name': '.', "
                    "'url': 'https://github.com/example/target.git'"
                    "}]\n"
                )

            path = os.path.join(tmp, "habitat_session.jsonl")
            session = StatSession(path, ["sync", target], "sync", root_dir=target)
            session.start()
            session.finish(0)

            metadata = _read_events(path)[0]

        self.assertEqual(metadata["project"], "example/target")

    def test_rejects_statistics_generation_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.observe.stat_session.platform.system", return_value="Windows"):
                session = StatSession(os.path.join(tmp, "stats.jsonl"), [], "sync")
                with self.assertRaisesRegex(RuntimeError, "Linux and macOS"):
                    session.start()


if __name__ == "__main__":
    unittest.main()
