# Copyright 2024 The Lynx Authors. All rights reserved.
# Licensed under the Apache License Version 2.0 that can be found in the
# LICENSE file in the root directory of this source tree.

import logging
import time
from enum import Enum

from core.observe.observer import record_lifecycle_result


class TaskTerminalStatus(Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


def _now_ms():
    return int(time.time() * 1000)


class TaskResult:
    def __init__(
        self,
        name,
        dep_type="unknown",
        status=None,
        start_ts_ms=None,
        end_ts_ms=None,
        reason="",
        error_type="",
        error_message="",
        required=None,
        target_dir="",
    ):
        if status is None:
            raise ValueError("TaskResult status is required")
        self.name = str(name)
        self.dep_type = str(dep_type or "unknown")
        self.status = status
        self.start_ts_ms = start_ts_ms if start_ts_ms is not None else _now_ms()
        self.end_ts_ms = end_ts_ms
        self.reason = str(reason or "")
        self.error_type = str(error_type or "")
        self.error_message = str(error_message or "")
        self.required = list(required or [])
        self.target_dir = str(target_dir or "")

    @property
    def duration_ms(self):
        if self.end_ts_ms is None:
            return 0
        return max(0, int(self.end_ts_ms) - int(self.start_ts_ms))

    def to_dict(self):
        return {
            "name": self.name,
            "depType": self.dep_type,
            "status": self.status.value,
            "startTS": self.start_ts_ms,
            "endTS": self.end_ts_ms,
            "durationMs": self.duration_ms,
            "reason": self.reason,
            "errorType": self.error_type,
            "errorMessage": self.error_message,
            "required": list(self.required),
            "targetDir": self.target_dir,
        }


class TaskLifecycleRecorder:
    def __init__(self, name, dep_type="unknown", target_dir="", required=None):
        self.name = str(name)
        self.dep_type = str(dep_type or "unknown")
        self.target_dir = str(target_dir or "")
        self.required = list(required or [])
        self.start_ts_ms = _now_ms()

    def running(self):
        logging.info(
            "RUNNING dep=%s type=%s target=%s",
            self.name,
            self.dep_type,
            self.target_dir,
        )

    def succeeded(self):
        result = self._finish(TaskTerminalStatus.SUCCEEDED)
        logging.info(
            "SUCCEEDED dep=%s type=%s durationMs=%s",
            result.name,
            result.dep_type,
            result.duration_ms,
        )
        record_lifecycle_result(result)
        return result

    def failed(self, exc=None, reason=""):
        result = self._finish(
            TaskTerminalStatus.FAILED,
            reason=reason,
            error_type=type(exc).__name__ if exc else "",
            error_message=str(exc) if exc else "",
        )
        logging.error(
            "FAILED dep=%s type=%s durationMs=%s error=%s",
            result.name,
            result.dep_type,
            result.duration_ms,
            result.error_message,
        )
        record_lifecycle_result(result)
        return result

    def skipped(self, reason="", required=None):
        result = self._finish(
            TaskTerminalStatus.SKIPPED,
            reason=reason,
            required=list(required or self.required),
        )
        logging.warning(
            "SKIPPED dep=%s type=%s reason=%s require=%s",
            result.name,
            result.dep_type,
            result.reason,
            ",".join(result.required),
        )
        record_lifecycle_result(result)
        return result

    def cancelled(self, reason=""):
        result = self._finish(TaskTerminalStatus.CANCELLED, reason=reason)
        logging.warning(
            "CANCELLED dep=%s type=%s reason=%s",
            result.name,
            result.dep_type,
            result.reason,
        )
        record_lifecycle_result(result)
        return result

    def _finish(
        self,
        status,
        reason="",
        error_type="",
        error_message="",
        required=None,
    ):
        return TaskResult(
            self.name,
            dep_type=self.dep_type,
            status=status,
            start_ts_ms=self.start_ts_ms,
            end_ts_ms=_now_ms(),
            reason=reason,
            error_type=error_type,
            error_message=error_message,
            required=list(required or self.required),
            target_dir=self.target_dir,
        )
