"""Unit tests for src.shared.observability."""

import json
import time
from unittest.mock import MagicMock

from src.shared.observability import Timer, get_request_id, log_event


class TestTimer:
    def test_elapsed_ms_is_positive(self) -> None:
        with Timer() as t:
            time.sleep(0.001)
        assert t.elapsed_ms > 0

    def test_elapsed_ms_is_float(self) -> None:
        with Timer() as t:
            pass
        assert isinstance(t.elapsed_ms, float)

    def test_measures_at_least_sleep_duration(self) -> None:
        with Timer() as t:
            time.sleep(0.05)
        assert t.elapsed_ms >= 40  # generous lower bound


class TestLogEvent:
    def _capture(self, level: str, event_name: str, **kwargs) -> dict:
        mock_logger = MagicMock()
        log_event(mock_logger, level, event_name, **kwargs)
        call_args = getattr(mock_logger, level).call_args
        return json.loads(call_args.args[0])

    def test_outputs_valid_json_with_event_name(self) -> None:
        data = self._capture("info", "test_event", foo="bar")
        assert data["event"] == "test_event"
        assert data["foo"] == "bar"

    def test_calls_correct_log_level(self) -> None:
        mock_logger = MagicMock()
        log_event(mock_logger, "warning", "some_event")
        mock_logger.warning.assert_called_once()
        mock_logger.info.assert_not_called()

    def test_never_logs_key_named_secret(self) -> None:
        data = self._capture("info", "ev", secret="mysecret", hits=5)
        assert "secret" not in data

    def test_never_logs_key_named_credential(self) -> None:
        data = self._capture("info", "ev", credential="abc", x=1)
        assert "credential" not in data

    def test_never_logs_key_named_token(self) -> None:
        data = self._capture("info", "ev", token="abc123", count=3)
        assert "token" not in data

    def test_safe_kwargs_are_included(self) -> None:
        data = self._capture("info", "ev", latency_ms=42, hits=5)
        assert data["latency_ms"] == 42
        assert data["hits"] == 5


class TestGetRequestId:
    def test_returns_id_from_event(self) -> None:
        event = {"requestContext": {"requestId": "abc-123"}}
        assert get_request_id(event) == "abc-123"

    def test_returns_non_empty_string_when_no_request_context(self) -> None:
        result = get_request_id({})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_non_empty_string_when_event_is_empty(self) -> None:
        result = get_request_id({})
        assert result != ""

    def test_returns_non_empty_string_when_request_context_missing_id(self) -> None:
        result = get_request_id({"requestContext": {}})
        assert isinstance(result, str)
        assert len(result) > 0
