import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.components import dependency_group
from core.components.action_dependency import ActionDependency
from core.components.dependency_group import DependencyGroup
from core.exceptions import HabitatException
from core.fetchers.local_fetcher import LocalFetcher
from core.lifecycle import TaskResult, TaskTerminalStatus
from core.observe import observer


class InMemoryGroup(DependencyGroup):
    type = "solution"
    source_attributes = []
    source_stamp_attributes = []

    async def up_to_date(self):
        return False


def _options():
    return SimpleNamespace(force=False, strict=False)


def _lifecycle_statuses():
    results = observer.get_lifecycle_results()
    assert len({item["name"] for item in results}) == len(results)
    return {item["name"]: item["status"] for item in results}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        observer.reset_download_profiling()

    def test_skip_propagates_through_required_action_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = InMemoryGroup(Path(tmp), {"name": "root"})
            a = ActionDependency(
                Path(tmp),
                {"name": "a", "commands": ["python3 -c 'raise SystemExit(7)'"]},
                parent=group,
            )
            b = ActionDependency(
                Path(tmp),
                {
                    "name": "b",
                    "commands": ["python3 -c 'open(\"b-ran\", \"w\").write(\"bad\")'"],
                    "require": ["a"],
                },
                parent=group,
            )
            c = ActionDependency(
                Path(tmp),
                {
                    "name": "c",
                    "commands": ["python3 -c 'open(\"c-ran\", \"w\").write(\"bad\")'"],
                    "require": ["b"],
                },
                parent=group,
            )
            group.children.extend([a, b, c])

            with self.assertRaises(HabitatException) as ctx:
                asyncio.run(group.fetch_children(tmp, _options()))

            self.assertIn("a", str(ctx.exception))
            self.assertIn("b", str(ctx.exception))
            self.assertIn("c", str(ctx.exception))
            self.assertFalse(os.path.exists(os.path.join(tmp, "b-ran")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "c-ran")))
            statuses = _lifecycle_statuses()
            self.assertEqual(statuses["a"], "failed")
            self.assertEqual(statuses["b"], "skipped")
            self.assertEqual(statuses["c"], "skipped")

    def test_required_action_runs_after_upstream_action_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = InMemoryGroup(Path(tmp), {"name": "root"})
            a = ActionDependency(
                Path(tmp),
                {"name": "a", "commands": ["python3 -c 'open(\"a-ran\", \"w\").write(\"ok\")'"]},
                parent=group,
            )
            b = ActionDependency(
                Path(tmp),
                {
                    "name": "b",
                    "commands": ["python3 -c 'open(\"b-ran\", \"w\").write(\"ok\")'"],
                    "require": ["a"],
                },
                parent=group,
            )
            group.children.extend([a, b])

            asyncio.run(group.fetch_children(tmp, _options()))

            self.assertTrue(os.path.exists(os.path.join(tmp, "a-ran")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "b-ran")))
            statuses = _lifecycle_statuses()
            self.assertEqual(statuses["a"], "succeeded")
            self.assertEqual(statuses["b"], "succeeded")

    def test_waiting_child_records_failed_result_when_requirement_times_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = InMemoryGroup(Path(tmp), {"name": "root"})
            child = ActionDependency(
                Path(tmp),
                {"name": "child", "commands": [], "require": ["missing"]},
                parent=group,
            )
            original_timeout = dependency_group.MAX_DEPENDENCY_WAIT_TIME
            dependency_group.MAX_DEPENDENCY_WAIT_TIME = 0.001

            async def run_child():
                event = group.event_manager.register_consumer("missing")
                await dependency_group.fetch_child(
                    child,
                    tmp,
                    _options(),
                    events=[event],
                )

            try:
                with self.assertRaises(HabitatException):
                    asyncio.run(run_child())
            finally:
                dependency_group.MAX_DEPENDENCY_WAIT_TIME = original_timeout

            result = group.event_manager.get_results()["child"]
            self.assertEqual(result.status, TaskTerminalStatus.FAILED)
            self.assertEqual(result.reason, "require_timeout")

    def test_local_fetcher_rejects_failed_reference_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = InMemoryGroup(Path(tmp), {"name": "root"})
            reference = ActionDependency(
                Path(tmp),
                {"name": "reference", "commands": []},
                parent=group,
            )
            component = ActionDependency(
                Path(tmp),
                {"name": "component", "commands": []},
                parent=group,
            )
            group.produce_event(
                "reference",
                TaskResult("reference", status=TaskTerminalStatus.FAILED, reason="test"),
            )
            fetcher = LocalFetcher(component, reference)

            with self.assertRaises(HabitatException):
                asyncio.run(fetcher.fetch(tmp, _options()))


if __name__ == "__main__":
    unittest.main()
