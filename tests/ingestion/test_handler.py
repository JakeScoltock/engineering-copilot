"""Unit tests for the ingestion Lambda handler."""

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from botocore.exceptions import ClientError

from src.ingestion.handler import (
    _ensure_vector_bucket,
    _ingest,
    _reset_index,
    lambda_handler,
)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "op")


def _make_table():
    mock_table = MagicMock()
    mock_dynamo = MagicMock()
    mock_dynamo.Table.return_value = mock_table
    return mock_table, mock_dynamo


class TestLambdaHandler:
    def test_routes_sqs_record_to_ingest(self) -> None:
        event = {"Records": [{"body": json.dumps({"repo_id": "abc", "github_url": "https://github.com/foo/bar"})}]}
        with patch("src.ingestion.handler._ingest") as mock_ingest:
            lambda_handler(event, None)
        mock_ingest.assert_called_once_with(repo_id="abc", github_url="https://github.com/foo/bar")

    def test_processes_multiple_records(self) -> None:
        event = {
            "Records": [
                {"body": json.dumps({"repo_id": "a", "github_url": "https://github.com/foo/a"})},
                {"body": json.dumps({"repo_id": "b", "github_url": "https://github.com/foo/b"})},
            ]
        }
        with patch("src.ingestion.handler._ingest") as mock_ingest:
            lambda_handler(event, None)
        assert mock_ingest.call_count == 2


class TestIngest:
    def _patches(self, chunks, embeddings):
        mock_table, mock_dynamo = _make_table()
        mock_s3 = MagicMock()
        mock_s3vectors = MagicMock()
        fake_chunk = MagicMock()
        fake_chunk.model_dump.return_value = {"source": "a.py", "chunk_index": 0, "text": "t"}

        ctx = [
            patch("src.ingestion.handler._dynamodb", mock_dynamo),
            patch("src.ingestion.handler._s3", mock_s3),
            patch("src.ingestion.handler._s3vectors", mock_s3vectors),
            patch("src.ingestion.handler.fetch_repo", return_value=[MagicMock()]),
            patch("src.ingestion.handler.chunk_documents", return_value=chunks),
            patch("src.ingestion.handler.embed_texts", return_value=embeddings),
        ]
        return mock_table, mock_s3, mock_s3vectors, ctx

    def test_happy_path_sets_ready_status(self) -> None:
        chunks = [MagicMock(text="t", source="a.py", chunk_index=0)]
        chunks[0].model_dump.return_value = {"source": "a.py", "chunk_index": 0, "text": "t"}
        embeddings = np.zeros((1, 1536), dtype="float32")
        mock_table, _, _, ctx = self._patches(chunks, embeddings)

        with (ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[5]):
            _ingest("repo-1", "https://github.com/foo/bar")

        call_kwargs = mock_table.update_item.call_args.kwargs
        assert call_kwargs["ExpressionAttributeValues"][":s"] == "ready"

    def test_exception_sets_failed_status(self) -> None:
        mock_table, mock_dynamo = _make_table()

        with (
            patch("src.ingestion.handler._dynamodb", mock_dynamo),
            patch("src.ingestion.handler._s3", MagicMock()),
            patch("src.ingestion.handler._s3vectors", MagicMock()),
            patch("src.ingestion.handler.fetch_repo", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError),
        ):
            _ingest("repo-1", "https://github.com/foo/bar")

        call_kwargs = mock_table.update_item.call_args.kwargs
        assert call_kwargs["ExpressionAttributeValues"][":s"] == "failed"

    def test_chunks_json_written_to_s3(self) -> None:
        chunks = [MagicMock(text="t", source="a.py", chunk_index=0)]
        chunks[0].model_dump.return_value = {"source": "a.py", "chunk_index": 0, "text": "t"}
        embeddings = np.zeros((1, 1536), dtype="float32")
        mock_table, mock_s3, _, ctx = self._patches(chunks, embeddings)

        with (ctx[0], ctx[1], ctx[2], ctx[3], ctx[4], ctx[5]):
            _ingest("repo-1", "https://github.com/foo/bar")

        call_kwargs = mock_s3.put_object.call_args.kwargs
        assert call_kwargs["Key"] == "repos/repo-1/chunks.json"

    def test_chunk_cap_truncates_before_embedding(self) -> None:
        from src.ingestion.handler import _MAX_CHUNKS

        mock_table, mock_dynamo = _make_table()
        chunks = [MagicMock(text=f"t{i}", source="a.py", chunk_index=i) for i in range(_MAX_CHUNKS + 50)]
        for c in chunks:
            c.model_dump.return_value = {"source": "a.py", "chunk_index": 0, "text": "t"}
        embeddings = np.zeros((_MAX_CHUNKS, 1536), dtype="float32")

        with (
            patch("src.ingestion.handler._dynamodb", mock_dynamo),
            patch("src.ingestion.handler._s3", MagicMock()),
            patch("src.ingestion.handler._s3vectors", MagicMock()),
            patch("src.ingestion.handler.fetch_repo", return_value=[MagicMock()]),
            patch("src.ingestion.handler.chunk_documents", return_value=chunks),
            patch("src.ingestion.handler.embed_texts", return_value=embeddings) as mock_embed,
        ):
            _ingest("repo-1", "https://github.com/foo/bar")

        texts_passed = mock_embed.call_args.args[0]
        assert len(texts_passed) == _MAX_CHUNKS


class TestEnsureVectorBucket:
    def test_creates_bucket(self) -> None:
        mock_s3vectors = MagicMock()
        with patch("src.ingestion.handler._s3vectors", mock_s3vectors):
            _ensure_vector_bucket()
        mock_s3vectors.create_vector_bucket.assert_called_once()

    def test_ignores_conflict_exception(self) -> None:
        mock_s3vectors = MagicMock()
        mock_s3vectors.create_vector_bucket.side_effect = _client_error("ConflictException")
        with patch("src.ingestion.handler._s3vectors", mock_s3vectors):
            _ensure_vector_bucket()  # should not raise

    def test_reraises_other_exceptions(self) -> None:
        mock_s3vectors = MagicMock()
        mock_s3vectors.create_vector_bucket.side_effect = _client_error("AccessDenied")
        with patch("src.ingestion.handler._s3vectors", mock_s3vectors):
            with pytest.raises(ClientError):
                _ensure_vector_bucket()


class TestResetIndex:
    def test_deletes_then_creates_index(self) -> None:
        mock_s3vectors = MagicMock()
        with patch("src.ingestion.handler._s3vectors", mock_s3vectors):
            _reset_index("repo-1")
        mock_s3vectors.delete_index.assert_called_once()
        mock_s3vectors.create_index.assert_called_once()

    def test_ignores_not_found_on_delete(self) -> None:
        mock_s3vectors = MagicMock()
        mock_s3vectors.delete_index.side_effect = _client_error("NotFoundException")
        with patch("src.ingestion.handler._s3vectors", mock_s3vectors):
            _reset_index("repo-1")  # should not raise
        mock_s3vectors.create_index.assert_called_once()

    def test_reraises_other_delete_errors(self) -> None:
        mock_s3vectors = MagicMock()
        mock_s3vectors.delete_index.side_effect = _client_error("AccessDenied")
        with patch("src.ingestion.handler._s3vectors", mock_s3vectors):
            with pytest.raises(ClientError):
                _reset_index("repo-1")
