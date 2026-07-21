import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from core.observe.events import close_jsonl


class MainLoggingTests(unittest.TestCase):
    def tearDown(self):
        close_jsonl()

    def test_log_jsonl_writes_structured_events_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "events.jsonl")
            sys.modules["coloredlogs"] = types.SimpleNamespace(install=lambda *args, **kwargs: None)
            from core.main import main

            with patch(
                "sys.argv",
                [
                    "hab",
                    "--log-jsonl",
                    path,
                    "sync",
                    "/path/that/does/not/exist",
                    "--compatible",
                ],
            ):
                main()

            self.assertTrue(os.path.exists(path))

    def test_stat_output_writes_habitat_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "habitat_session.jsonl")
            sys.modules["coloredlogs"] = types.SimpleNamespace(install=lambda *args, **kwargs: None)
            from core.main import main

            with patch(
                "sys.argv",
                [
                    "hab",
                    "--stat-output",
                    path,
                    "sync",
                    "/path/that/does/not/exist",
                    "--compatible",
                ],
            ):
                main()

            with open(path, encoding="utf-8") as f:
                events = [json.loads(line) for line in f]

        self.assertEqual(events[0]["type"], "session_meta")
        self.assertEqual(events[1]["type"], "invocation")
        self.assertEqual(events[1]["option"], "sync")
        self.assertEqual(events[1]["exitCode"], 0)

    def test_stat_output_and_event_log_must_use_different_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "output.jsonl")
            sys.modules["coloredlogs"] = types.SimpleNamespace(install=lambda *args, **kwargs: None)
            from core.main import main

            with patch(
                "sys.argv",
                [
                    "hab",
                    "--log-jsonl",
                    path,
                    "--stat-output",
                    path,
                    "sync",
                    "/path/that/does/not/exist",
                    "--compatible",
                ],
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()

        self.assertEqual(ctx.exception.code, 2)

    def test_stat_output_records_interrupted_command_as_failed(self):
        def interrupt(coro):
            coro.close()
            raise KeyboardInterrupt

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "habitat_session.jsonl")
            sys.modules["coloredlogs"] = types.SimpleNamespace(install=lambda *args, **kwargs: None)
            from core.main import main

            with patch(
                "sys.argv",
                [
                    "hab",
                    "--stat-output",
                    path,
                    "sync",
                    "/path/that/does/not/exist",
                    "--compatible",
                ],
            ), patch("core.main.asyncio.run", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    main()

            with open(path, encoding="utf-8") as f:
                events = [json.loads(line) for line in f]

        self.assertEqual(events[1]["type"], "invocation")
        self.assertEqual(events[1]["exitCode"], 1)
