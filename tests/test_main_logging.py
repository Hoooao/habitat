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
