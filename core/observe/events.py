import json
import time
from threading import RLock

_LOCK = RLock()
_SEQ = 0
_EVENTS = []
_JSONL_FILE = None


def _now_ms():
    return int(time.time() * 1000)


def reset_events():
    global _SEQ
    global _EVENTS
    with _LOCK:
        _SEQ = 0
        _EVENTS = []


def open_jsonl(path):
    global _JSONL_FILE
    with _LOCK:
        close_jsonl()
        _JSONL_FILE = open(path, "a", encoding="utf-8")


def close_jsonl():
    global _JSONL_FILE
    with _LOCK:
        if _JSONL_FILE is None:
            return
        _JSONL_FILE.close()
        _JSONL_FILE = None


def record_event(event_type, **fields):
    global _SEQ
    with _LOCK:
        _SEQ += 1
        event = {
            "seq": _SEQ,
            "ts": _now_ms(),
            "event": str(event_type),
        }
        event.update({k: v for k, v in fields.items() if v is not None})
        _EVENTS.append(event)
        if _JSONL_FILE is not None:
            _JSONL_FILE.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            _JSONL_FILE.write("\n")
            _JSONL_FILE.flush()
        return dict(event)


def get_events(event_type=None):
    with _LOCK:
        if event_type is None:
            return [dict(event) for event in _EVENTS]
        return [dict(event) for event in _EVENTS if event.get("event") == event_type]
