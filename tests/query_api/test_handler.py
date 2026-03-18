"""Unit tests for the query-api Lambda handler."""

import json
from unittest.mock import MagicMock, patch

import numpy as np

from src.query_api.handler import lambda_handler


def _event(
    method: str,
    resource: str,
    body: dict | None = None,
    path_params: dict | None = None,
) -> dict:
    return {
        "httpMethod": method,
        "resource": resource,
        "path": resource,
        "pathParameters": path_params,
        "body": json.dumps(body) if body else None,
    }


class TestRouting:
    def test_health_returns_200(self) -> None:
        resp = lambda_handler(_event("GET", "/health"), None)
        assert resp["statusCode"] == 200
        assert json.loads(resp["body"])["status"] == "ok"

    def test_unknown_route_returns_404(self) -> None:
        resp = lambda_handler(_event("DELETE", "/unknown"), None)
        assert resp["statusCode"] == 404


class TestCreateRepo:
    def test_returns_202_for_valid_url(self) -> None:
        mock_table = MagicMock()
        mock_sqs = MagicMock()

        with (
            patch("src.query_api.handler._dynamodb") as mock_dynamo,
            patch("src.query_api.handler._sqs", mock_sqs),
        ):
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("POST", "/repos", body={"github_url": "https://github.com/octocat/Hello-World"}),
                None,
            )

        assert resp["statusCode"] == 202
        body = json.loads(resp["body"])
        assert "repo_id" in body
        assert body["status"] == "pending"

    def test_writes_job_to_dynamodb(self) -> None:
        mock_table = MagicMock()
        mock_sqs = MagicMock()

        with (
            patch("src.query_api.handler._dynamodb") as mock_dynamo,
            patch("src.query_api.handler._sqs", mock_sqs),
        ):
            mock_dynamo.Table.return_value = mock_table
            lambda_handler(
                _event("POST", "/repos", body={"github_url": "https://github.com/octocat/Hello-World"}),
                None,
            )

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args.kwargs["Item"]
        assert item["status"] == "pending"
        assert item["github_url"] == "https://github.com/octocat/Hello-World"

    def test_enqueues_sqs_message(self) -> None:
        mock_table = MagicMock()
        mock_sqs = MagicMock()

        with (
            patch("src.query_api.handler._dynamodb") as mock_dynamo,
            patch("src.query_api.handler._sqs", mock_sqs),
        ):
            mock_dynamo.Table.return_value = mock_table
            lambda_handler(
                _event("POST", "/repos", body={"github_url": "https://github.com/octocat/Hello-World"}),
                None,
            )

        mock_sqs.send_message.assert_called_once()
        msg = json.loads(mock_sqs.send_message.call_args.kwargs["MessageBody"])
        assert msg["github_url"] == "https://github.com/octocat/Hello-World"
        assert "repo_id" in msg

    def test_returns_400_when_url_missing(self) -> None:
        resp = lambda_handler(_event("POST", "/repos", body={}), None)
        assert resp["statusCode"] == 400

    def test_returns_400_for_invalid_github_url(self) -> None:
        resp = lambda_handler(
            _event("POST", "/repos", body={"github_url": "https://gitlab.com/foo/bar"}),
            None,
        )
        assert resp["statusCode"] == 400

    def test_returns_400_for_malformed_json_body(self) -> None:
        event = _event("POST", "/repos")
        event["body"] = "{not valid json"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    def test_returns_500_and_rolls_back_when_sqs_fails(self) -> None:
        mock_table = MagicMock()
        mock_sqs = MagicMock()
        mock_sqs.send_message.side_effect = Exception("SQS unavailable")

        with (
            patch("src.query_api.handler._dynamodb") as mock_dynamo,
            patch("src.query_api.handler._sqs", mock_sqs),
        ):
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("POST", "/repos", body={"github_url": "https://github.com/octocat/Hello-World"}),
                None,
            )

        assert resp["statusCode"] == 500
        mock_table.delete_item.assert_called_once()


class TestGetRepo:
    def test_returns_200_with_status_for_known_repo(self) -> None:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"repo_id": "abc", "status": "ready", "error": None}
        }

        with patch("src.query_api.handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("GET", "/repos/{repo_id}", path_params={"repo_id": "abc"}),
                None,
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["repo_id"] == "abc"
        assert body["status"] == "ready"

    def test_returns_404_for_unknown_repo(self) -> None:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch("src.query_api.handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("GET", "/repos/{repo_id}", path_params={"repo_id": "nope"}),
                None,
            )

        assert resp["statusCode"] == 404

    def test_returns_400_when_repo_id_missing(self) -> None:
        resp = lambda_handler(
            _event("GET", "/repos/{repo_id}", path_params={}),
            None,
        )
        assert resp["statusCode"] == 400


class TestQueryRepo:
    def _ready_table(self) -> MagicMock:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"repo_id": "abc", "status": "ready", "error": None}
        }
        return mock_table

    def test_returns_200_with_answer_and_sources(self) -> None:
        mock_table = self._ready_table()
        mock_s3vectors = MagicMock()
        mock_s3vectors.query_vectors.return_value = {
            "vectors": [{"key": "0", "metadata": {"source": "main.py", "chunk_index": 0}}]
        }
        chunks_json = json.dumps([{"source": "main.py", "chunk_index": 0, "text": "def foo(): pass"}]).encode()
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: chunks_json)}

        with (
            patch("src.query_api.handler._dynamodb") as mock_dynamo,
            patch("src.query_api.handler._s3vectors", mock_s3vectors),
            patch("src.query_api.handler._s3", mock_s3),
            patch("src.query_api.handler.embed_text", return_value=np.zeros(1536, dtype="float32")),
            patch("src.query_api.handler.ask_claude", return_value="It does X."),
        ):
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("POST", "/repos/{repo_id}/query", body={"question": "What does foo do?"}, path_params={"repo_id": "abc"}),
                None,
            )

        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["answer"] == "It does X."
        assert body["sources"][0]["file"] == "main.py"

    def test_returns_404_when_repo_not_found(self) -> None:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch("src.query_api.handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("POST", "/repos/{repo_id}/query", body={"question": "?"}, path_params={"repo_id": "nope"}),
                None,
            )

        assert resp["statusCode"] == 404

    def test_returns_409_when_repo_not_ready(self) -> None:
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"repo_id": "abc", "status": "pending", "error": None}
        }

        with patch("src.query_api.handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("POST", "/repos/{repo_id}/query", body={"question": "?"}, path_params={"repo_id": "abc"}),
                None,
            )

        assert resp["statusCode"] == 409

    def test_returns_400_when_question_empty(self) -> None:
        mock_table = self._ready_table()
        with patch("src.query_api.handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("POST", "/repos/{repo_id}/query", body={"question": "   "}, path_params={"repo_id": "abc"}),
                None,
            )
        assert resp["statusCode"] == 400

    def test_returns_400_when_question_too_long(self) -> None:
        mock_table = self._ready_table()
        with patch("src.query_api.handler._dynamodb") as mock_dynamo:
            mock_dynamo.Table.return_value = mock_table
            resp = lambda_handler(
                _event("POST", "/repos/{repo_id}/query", body={"question": "x" * 2001}, path_params={"repo_id": "abc"}),
                None,
            )
        assert resp["statusCode"] == 400
