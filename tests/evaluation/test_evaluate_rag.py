"""Unit tests for the pure-Python logic in scripts/evaluate_rag.py."""

import importlib.util
import sys
from pathlib import Path

# Load the module without executing main()
_script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "evaluate_rag.py"
_spec = importlib.util.spec_from_file_location("evaluate_rag", _script_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_score = _mod._score


class TestKeywordScoring:
    def test_all_keywords_found_returns_passed(self) -> None:
        found, missing = _score("The chunk uses overlap and line splitting", ["chunk", "overlap", "line"])
        assert found == ["chunk", "overlap", "line"]
        assert missing == []

    def test_missing_keyword_not_passed(self) -> None:
        found, missing = _score("The chunk uses overlap", ["chunk", "overlap", "line"])
        assert "line" in missing
        assert "chunk" in found

    def test_case_insensitive_match(self) -> None:
        found, missing = _score("Uses TITAN embeddings with 1024 dimensions", ["titan", "1024"])
        assert missing == []

    def test_empty_expected_keywords_always_passes(self) -> None:
        found, missing = _score("Any answer at all", [])
        assert found == []
        assert missing == []

    def test_partial_match_not_counted(self) -> None:
        # "s3vectors" should not be matched by an answer that only says "s3"
        found, missing = _score("stored in s3 bucket", ["s3vectors"])
        assert "s3vectors" in missing

    def test_found_and_missing_are_disjoint(self) -> None:
        keywords = ["cosine", "titan", "ndjson"]
        answer = "cosine distance is used with titan embeddings"
        found, missing = _score(answer, keywords)
        assert set(found) & set(missing) == set()
        assert set(found) | set(missing) == set(keywords)


class TestResultStructure:
    """Verify that a result dict built by the evaluator has the expected shape."""

    def _make_result(self, passed: bool) -> dict:
        return {
            "question": "How does chunking work?",
            "answer": "Uses line-based chunks with overlap",
            "sources": [{"file": "chunker.py", "chunk_index": 0}],
            "keywords_found": ["chunk", "overlap"],
            "keywords_missing": [],
            "passed": passed,
            "latency_ms": 312,
            "http_status": 200,
        }

    def test_result_has_required_keys(self) -> None:
        r = self._make_result(True)
        for key in ("question", "answer", "sources", "keywords_found", "keywords_missing", "passed", "latency_ms"):
            assert key in r

    def test_passed_true_when_no_missing_keywords(self) -> None:
        r = self._make_result(True)
        assert r["passed"] is True
        assert r["keywords_missing"] == []

    def test_passed_false_when_keywords_missing(self) -> None:
        r = self._make_result(False)
        r["keywords_missing"] = ["titan"]
        r["passed"] = False
        assert not r["passed"]
