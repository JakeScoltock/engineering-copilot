"""Structured logging and timing helpers for Lambda functions."""

import json
import time
import uuid


class Timer:
    """Context manager for timing a block of code.

    Usage::
        with Timer() as t:
            do_work()
        print(t.elapsed_ms)
    """

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        self._end = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        end = getattr(self, "_end", None) or time.perf_counter()
        return (end - self._start) * 1000


def log_event(logger, level: str, event_name: str, **kwargs) -> None:
    """Emit a single structured JSON log line via *logger*.

    Sensitive key names (secret, credential, token) are intentionally
    excluded so they are never accidentally logged.
    """
    _BLOCKED = {"secret", "credential", "token"}
    safe = {k: v for k, v in kwargs.items() if k.lower() not in _BLOCKED}
    payload = json.dumps({"event": event_name, **safe})
    getattr(logger, level)(payload)


def get_request_id(event: dict) -> str:
    """Return the API Gateway requestId, or a short UUID if not present."""
    try:
        return event["requestContext"]["requestId"]
    except (KeyError, TypeError):
        return str(uuid.uuid4())[:8]
