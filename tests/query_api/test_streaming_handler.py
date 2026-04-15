"""Unit tests for the streaming query Lambda handler.

Tests drive _generate_events() directly, bypassing the Runtime API HTTP layer,
so no actual streaming infrastructure is needed.
"""

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.query_api.streaming_handler import _generate_events


def _event(
    repo_id: str = "abc",
    question: str = "What does foo do?",
    history: list | None = None,
    api_key: str = "",
) -> dict:
    """Build a minimal Lambda Function URL event."""
    body: dict = {"question": question}
    if history is not None:
        body["history"] = history
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    return {
        "rawPath": f"/repos/{repo_id}/query",
        "headers": headers,
        "body": json.dumps(body),
        "isBase64Encoded": False,
    }


def _ready_table() -> MagicMock:
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"repo_id": "abc", "status": "ready", "error": None}
    }
    return mock_table


class TestAuth:
    def test_rejects_missing_key_when_api_key_configured(self) -> None:
        with patch("src.query_api.streaming_handler._API_KEY", "secret"):
            events = list(_generate_events(_event(api_key="")))
        assert events == [{"type": "error", "error": "Unauthorized"}]

    def test_rejects_wrong_key(self) -> None:
        with patch("src.query_api.streaming_handler._API_KEY", "secret"):
            events = list(_generate_events(_event(api_key="wrong")))
        assert events == [{"type": "error", "error": "Unauthorized"}]

    def test_allows_correct_key(self) -> None:
        mock_table = _ready_table()
        chunks_json = json.dumps([{"source": "a.py", "chunk_index": 0, "text": "hi"}]).encode()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: chunks_json)}
        mock_s3vectors = MagicMock()
        mock_s3vectors.query_vectors.return_value = {"vectors": [{"key": "0"}]}

        with (
            patch("src.query_api.streaming_handler._API_KEY", "secret"),
            patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo,
            patch("src.query_api.streaming_handler._s3vectors", mock_s3vectors),
            patch("src.query_api.streaming_handler._s3", mock_s3),
            patch("src.query_api.streaming_handler.embed_text", return_value=np.zeros(1024, dtype="float32")),
            patch("src.query_api.streaming_handler.generate_answer_streaming", return_value=iter(["ok"])),
        ):
            mock_dynamo.Table.return_value = mock_table
            events = list(_generate_events(_event(api_key="secret")))

        assert events[0]["type"] == "sources"

    def test_no_auth_check_when_api_key_not_set(self) -> None:
        mock_table = _ready_table()
        chunks_json = json.dumps([{"source": "a.py", "chunk_index": 0, "text": "hi"}]).encode()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: chunks_json)}
        mock_s3vectors = MagicMock()
        mock_s3vectors.query_vectors.return_value = {"vectors": [{"key": "0"}]}

        with (
            patch("src.query_api.streaming_handler._API_KEY", ""),
            patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo,
            patch("src.query_api.streaming_handler._s3vectors", mock_s3vectors),
            patch("src.query_api.streaming_handler._s3", mock_s3),
            patch("src.query_api.streaming_handler.embed_text", return_value=np.zeros(1024, dtype="float32")),
            patch("src.query_api.streaming_handler.generate_answer_streaming", return_value=iter(["ok"])),
        ):
            mock_dynamo.Table.return_value = mock_table
            events = list(_generate_events(_event(api_key="")))

        assert events[0]["type"] == "sources"


class TestPathParsing:
    def test_invalid_path_returns_error(self) -> None:
        event = _event()
        event["rawPath"] = "/wrong"
        events = list(_generate_events(event))
        assert events == [{"type": "error", "error": "invalid path — expected /repos/{repo_id}/query"}]

    def test_missing_repo_id_returns_error(self) -> None:
        event = _event()
        event["rawPath"] = "/repos//query"
        events = list(_generate_events(event))
        assert events[0]["type"] == "error"


class TestRepoValidation:
    def test_unknown_repo_returns_error(self) -> None:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            events = list(_generate_events(_event()))

        assert events == [{"type": "error", "error": "repo abc not found"}]

    def test_repo_not_ready_returns_error(self) -> None:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"repo_id": "abc", "status": "pending", "error": None}
        }

        with patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            events = list(_generate_events(_event()))

        assert events[0]["type"] == "error"
        assert "not ready" in events[0]["error"]
        assert "pending" in events[0]["error"]


class TestInputValidation:
    def test_empty_question_returns_error(self) -> None:
        mock_table = _ready_table()
        with patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            events = list(_generate_events(_event(question="   ")))
        assert events == [{"type": "error", "error": "question must not be empty"}]

    def test_question_too_long_returns_error(self) -> None:
        mock_table = _ready_table()
        with patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            events = list(_generate_events(_event(question="x" * 2001)))
        assert events[0]["type"] == "error"
        assert "2000" in events[0]["error"]


class TestHappyPath:
    def test_yields_sources_deltas_done(self) -> None:
        mock_table = _ready_table()
        chunks = [{"source": "main.py", "chunk_index": 0, "text": "def foo(): pass"}]
        chunks_json = json.dumps(chunks).encode()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: chunks_json)}
        mock_s3vectors = MagicMock()
        mock_s3vectors.query_vectors.return_value = {"vectors": [{"key": "0"}]}

        with (
            patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo,
            patch("src.query_api.streaming_handler._s3vectors", mock_s3vectors),
            patch("src.query_api.streaming_handler._s3", mock_s3),
            patch("src.query_api.streaming_handler.embed_text", return_value=np.zeros(1024, dtype="float32")),
            patch("src.query_api.streaming_handler.generate_answer_streaming", return_value=iter(["Hello", " world"])),
        ):
            mock_dynamo.Table.return_value = mock_table
            events = list(_generate_events(_event()))

        assert events[0] == {"type": "sources", "sources": [{"file": "main.py", "chunk_index": 0}]}
        assert events[1] == {"type": "delta", "text": "Hello"}
        assert events[2] == {"type": "delta", "text": " world"}
        assert events[3] == {"type": "done", "answer": "Hello world"}

    def test_no_hits_yields_empty_sources_and_done(self) -> None:
        mock_table = _ready_table()
        mock_s3vectors = MagicMock()
        mock_s3vectors.query_vectors.return_value = {"vectors": []}

        with (
            patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo,
            patch("src.query_api.streaming_handler._s3vectors", mock_s3vectors),
            patch("src.query_api.streaming_handler.embed_text", return_value=np.zeros(1024, dtype="float32")),
        ):
            mock_dynamo.Table.return_value = mock_table
            events = list(_generate_events(_event()))

        assert events == [
            {"type": "sources", "sources": []},
            {"type": "done", "answer": "No relevant content found."},
        ]

    def test_history_forwarded_to_generate_answer_streaming(self) -> None:
        mock_table = _ready_table()
        chunks = [{"source": "a.py", "chunk_index": 0, "text": "content"}]
        chunks_json = json.dumps(chunks).encode()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: chunks_json)}
        mock_s3vectors = MagicMock()
        mock_s3vectors.query_vectors.return_value = {"vectors": [{"key": "0"}]}
        history = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
        ]

        with (
            patch("src.query_api.streaming_handler._dynamodb") as mock_dynamo,
            patch("src.query_api.streaming_handler._s3vectors", mock_s3vectors),
            patch("src.query_api.streaming_handler._s3", mock_s3),
            patch("src.query_api.streaming_handler.embed_text", return_value=np.zeros(1024, dtype="float32")),
            patch("src.query_api.streaming_handler.generate_answer_streaming", return_value=iter(["ok"])) as mock_gen,
        ):
            mock_dynamo.Table.return_value = mock_table
            list(_generate_events(_event(history=history)))

        # Third positional arg is history (question, context, history, bedrock_client)
        passed_history = mock_gen.call_args[0][2]
        assert len(passed_history) == 2
        assert passed_history[0].role == "user"
        assert passed_history[0].content == "First question"
        assert passed_history[1].role == "assistant"
