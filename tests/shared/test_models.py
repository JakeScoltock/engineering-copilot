"""Unit tests for shared Pydantic models."""

from src.shared.models import (
    IngestionStatus,
    QueryRequest,
    QueryResponse,
    RepoJob,
    SourceRef,
)


class TestRepoJob:
    def test_default_status_is_pending(self) -> None:
        job = RepoJob(github_url="https://github.com/octocat/Hello-World")
        assert job.status == IngestionStatus.PENDING

    def test_repo_id_is_auto_generated(self) -> None:
        job = RepoJob(github_url="https://github.com/octocat/Hello-World")
        assert job.repo_id is not None
        assert len(job.repo_id) == 36  # UUID4 string length

    def test_each_job_gets_unique_repo_id(self) -> None:
        job1 = RepoJob(github_url="https://github.com/a/b")
        job2 = RepoJob(github_url="https://github.com/a/b")
        assert job1.repo_id != job2.repo_id

    def test_error_is_none_by_default(self) -> None:
        job = RepoJob(github_url="https://github.com/octocat/Hello-World")
        assert job.error is None

    def test_can_set_failed_status_with_error(self) -> None:
        job = RepoJob(
            github_url="https://github.com/octocat/Hello-World",
            status=IngestionStatus.FAILED,
            error="Rate limit exceeded",
        )
        assert job.status == IngestionStatus.FAILED
        assert job.error == "Rate limit exceeded"

    def test_status_values(self) -> None:
        assert IngestionStatus.PENDING == "pending"
        assert IngestionStatus.READY == "ready"
        assert IngestionStatus.FAILED == "failed"


class TestQueryRequestAndResponse:
    def test_query_request_stores_question(self) -> None:
        req = QueryRequest(question="What does this repo do?")
        assert req.question == "What does this repo do?"

    def test_query_response_stores_answer_and_sources(self) -> None:
        resp = QueryResponse(
            answer="It is a web server.",
            sources=[SourceRef(file="README.md", chunk_index=0)],
        )
        assert resp.answer == "It is a web server."
        assert len(resp.sources) == 1
        assert resp.sources[0].file == "README.md"
        assert resp.sources[0].chunk_index == 0

    def test_query_response_can_have_multiple_sources(self) -> None:
        resp = QueryResponse(
            answer="See multiple files.",
            sources=[
                SourceRef(file="README.md", chunk_index=0),
                SourceRef(file="src/main.py", chunk_index=2),
            ],
        )
        assert len(resp.sources) == 2

    def test_query_response_can_have_empty_sources(self) -> None:
        resp = QueryResponse(answer="I don't know.", sources=[])
        assert resp.sources == []
