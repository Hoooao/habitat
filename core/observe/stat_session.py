import json
import logging
import os
import platform
import re
import subprocess
import time
from pathlib import Path

from core.__version__ import __version__
from core.components.solution import load_solutions
from core.observe import observer
from core.settings import DEFAULT_CONFIG_FILE_NAME
from core.utils import git_root_dir

_MAX_WARNING_BYTES = 128 * 1024


def _append_jsonl(path, event):
    with open(str(path), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        f.write("\n")


def _git_config(key):
    try:
        return subprocess.check_output(
            ["git", "config", "--get", key], stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _user_info():
    name = _git_config("user.name") or os.environ.get("HABITAT_USERNAME", "").strip()
    email = _git_config("user.email")
    if name or email:
        return {"name": name, "email": email}
    return {"name": "unknown", "email": "unknown"}


def _current_project(root_dir=None):
    try:
        root_dir = os.path.abspath(str(root_dir or git_root_dir()))
        solution_file = os.path.join(root_dir, DEFAULT_CONFIG_FILE_NAME)
        solutions = load_solutions(
            root_dir,
            solution_file,
            ignore_non_existing=True,
            enable_version_checking=False,
        )
        if not solutions:
            return "unknown_project"
        url = getattr(solutions[0], "url", None)
        if not isinstance(url, str) or not url.strip():
            return "unknown_project"
        match = re.search(r"[:/]([^/]+/[^/]+?)(\.git)?$", url.strip())
        return match.group(1) if match else "unknown_project"
    except Exception:
        return "unknown_project"


def _host_info():
    values = (
        ("platform", platform.platform),
        ("system", platform.system),
        ("release", platform.release),
        ("machine", platform.machine),
        ("pythonVersion", platform.python_version),
        ("nodeIP", lambda: os.environ.get("NODE_IP", "").strip()),
        ("cicdEnv", lambda: os.environ.get("HABITAT_CICD_ENV", "").strip().lower()),
    )
    info = {}
    for key, provider in values:
        try:
            info[key] = provider()
        except Exception:
            info[key] = "unknown"
    return info


def _session_meta(root_dir=None):
    return {
        "type": "session_meta",
        "fileCreatedAtMs": int(time.time() * 1000),
        "user": _user_info(),
        "project": _current_project(root_dir),
        "habVersion": str(__version__),
        "host": _host_info(),
    }


class _WarningCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.lines = []
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    def emit(self, record):
        try:
            self.lines.append(self.format(record))
        except Exception:
            self.handleError(record)

    def snapshot(self):
        if not self.lines:
            return None
        content = ("\n".join(self.lines) + "\n").encode("utf-8", errors="replace")
        size_bytes = len(content)
        tail = content[-_MAX_WARNING_BYTES:]
        return {
            "type": "warn_error_log",
            "invTSMs": int(time.time() * 1000),
            "path": "",
            "tail": tail.decode("utf-8", errors="replace"),
            "truncated": size_bytes > _MAX_WARNING_BYTES,
            "sizeBytes": size_bytes,
        }


class StatSession:
    def __init__(self, output_path, argv, option, root_dir=None):
        self.output_path = Path(output_path).expanduser()
        self.argv = list(argv)
        self.option = str(option or "")
        self.root_dir = root_dir
        self._started = False
        self._finished = False
        self._start_ns = 0
        self._start_ts_ms = 0
        self._cpu_start_s = 0.0
        self._warning_handler = _WarningCaptureHandler()

    def start(self):
        if platform.system() not in ("Linux", "Darwin"):
            raise RuntimeError("statistics generation currently supports Linux and macOS only")
        if self._started:
            return

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.output_path.exists():
            self.output_path.unlink()
        _append_jsonl(self.output_path, _session_meta(self.root_dir))

        observer.reset_download_profiling()
        logging.getLogger().addHandler(self._warning_handler)
        self._start_ns = time.perf_counter_ns()
        self._start_ts_ms = int(time.time() * 1000)
        self._cpu_start_s = time.process_time()
        self._started = True

    def finish(self, exit_code, exception=None):
        if not self._started or self._finished:
            return
        self._finished = True
        logging.getLogger().removeHandler(self._warning_handler)

        duration_ms = int((time.perf_counter_ns() - self._start_ns) / 1_000_000)
        cpu_usage_percent = None
        if duration_ms > 0:
            cpu_used_s = time.process_time() - self._cpu_start_s
            cpu_usage_percent = round((cpu_used_s / (duration_ms / 1000.0)) * 100.0, 2)

        invocation = {
            "type": "invocation",
            "option": self.option,
            "invTSMs": self._start_ts_ms,
            "durationMs": duration_ms,
            "cpuUsagePercent": cpu_usage_percent,
            "argv": self.argv,
            "exitCode": int(exit_code),
            "downloads": observer.get_all_download_tasks_sorted(),
            "downloadTimeByDependency": observer.get_download_time_by_dependency(),
            "downloadTimeStats": observer.get_download_time_stats(),
            "cacheStats": observer.get_cache_stats(),
        }
        if int(exit_code) != 0 and exception is not None:
            invocation["exceptions"] = [
                {"type": type(exception).__name__, "message": str(exception)}
            ]
        exception_dependencies = observer.get_exception_dependencies()
        if int(exit_code) != 0 and exception_dependencies:
            invocation["exceptionDependencies"] = exception_dependencies

        _append_jsonl(self.output_path, invocation)
        warning_event = self._warning_handler.snapshot()
        if warning_event is not None:
            _append_jsonl(self.output_path, warning_event)


__all__ = ["StatSession"]
