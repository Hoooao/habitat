import logging
from collections import Counter

from core.observe.events import get_events


def _short_error(event):
    text = str(event.get("errorMessage") or event.get("errorType") or "").strip()
    if not text:
        return ""
    return text.replace("\n", " ")[:160]


def _format_required(event):
    required = event.get("required") or []
    if isinstance(required, (list, tuple)):
        return ", ".join(str(item) for item in required)
    return str(required)


def format_execution_summary(events=None, slow_limit=5):
    events = list(get_events() if events is None else events)
    tasks = [event for event in events if event.get("event") == "task.completed"]
    if not tasks:
        return []

    counts = Counter(task.get("status") for task in tasks)
    lines = [
        "Execution summary: succeeded=%d failed=%d skipped=%d cancelled=%d"
        % (
            counts.get("succeeded", 0),
            counts.get("failed", 0),
            counts.get("skipped", 0),
            counts.get("cancelled", 0),
        )
    ]

    failed = [task for task in tasks if task.get("status") == "failed"]
    if failed:
        items = []
        for task in failed:
            error = _short_error(task)
            dep = task.get("dep") or task.get("name")
            items.append(f"{dep} ({error})" if error else str(dep))
        lines.append("Failed tasks: " + ", ".join(items))

    skipped = [task for task in tasks if task.get("status") == "skipped"]
    if skipped:
        items = []
        for task in skipped:
            dep = task.get("dep") or task.get("name")
            reason = str(task.get("reason") or "skipped")
            required = _format_required(task)
            detail = f"{reason}: {required}" if required else reason
            items.append(f"{dep} ({detail})")
        lines.append("Skipped tasks: " + ", ".join(items))

    slowest = sorted(
        tasks,
        key=lambda task: int(task.get("durationMs") or 0),
        reverse=True,
    )[:slow_limit]
    if slowest:
        lines.append(
            "Slowest tasks: "
            + ", ".join(
                "%s %sms" % (task.get("dep") or task.get("name"), int(task.get("durationMs") or 0))
                for task in slowest
            )
        )

    return lines


def render_execution_summary(events=None):
    lines = format_execution_summary(events)
    for line in lines:
        logging.info(line)
    return lines
