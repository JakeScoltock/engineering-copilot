#!/usr/bin/env python3
"""End-to-end RAG evaluation script.

Reads eval/questions.json, fires each question at the live API, checks for
expected keywords in the answer, and writes a structured results file.

Required env vars:
    QUERY_API_URL   Base URL of the deployed API, e.g.
                    https://<id>.execute-api.eu-west-1.amazonaws.com/prod
    REPO_ID         UUID of an already-ingested repo to query against

Optional env vars:
    API_KEY         Value for the x-api-key header (omit if not configured)

Exit code:
    0  all questions passed
    1  one or more questions failed
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

_ROOT = Path(__file__).resolve().parent.parent
_QUESTIONS_FILE = _ROOT / "eval" / "questions.json"
_RESULTS_DIR = _ROOT / "eval" / "results"
_RESULTS_FILE = _RESULTS_DIR / "latest.json"


def _score(answer: str, expected_keywords: list[str]) -> tuple[list[str], list[str]]:
    """Return (found, missing) keyword lists (case-insensitive)."""
    lower = answer.lower()
    found = [kw for kw in expected_keywords if kw.lower() in lower]
    missing = [kw for kw in expected_keywords if kw.lower() not in lower]
    return found, missing


def _run_eval(base_url: str, repo_id: str, api_key: str | None) -> list[dict]:
    questions = json.loads(_QUESTIONS_FILE.read_text())
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    results = []
    with httpx.Client(timeout=60) as client:
        for item in questions:
            question = item["question"]
            expected = item.get("expected_keywords", [])

            t0 = time.perf_counter()
            response = client.post(
                f"{base_url}/repos/{repo_id}/query",
                headers=headers,
                json={"question": question},
            )
            latency_ms = round((time.perf_counter() - t0) * 1000)

            if response.status_code != 200:
                results.append({
                    "question": question,
                    "answer": None,
                    "sources": [],
                    "keywords_found": [],
                    "keywords_missing": expected,
                    "passed": False,
                    "latency_ms": latency_ms,
                    "http_status": response.status_code,
                    "error": response.text,
                })
                continue

            data = response.json()
            answer = data.get("answer", "")
            sources = data.get("sources", [])
            found, missing = _score(answer, expected)
            passed = len(missing) == 0

            results.append({
                "question": question,
                "answer": answer,
                "sources": sources,
                "keywords_found": found,
                "keywords_missing": missing,
                "passed": passed,
                "latency_ms": latency_ms,
                "http_status": response.status_code,
            })

    return results


def _print_table(results: list[dict]) -> None:
    col = 52
    print()
    print(f"{'Question':<{col}}  {'Pass':>4}  {'Latency':>8}  Missing keywords")
    print("-" * (col + 40))
    for r in results:
        q = r["question"][:col - 1].ljust(col)
        passed = "PASS" if r["passed"] else "FAIL"
        latency = f"{r['latency_ms']} ms"
        missing = ", ".join(r["keywords_missing"]) if r["keywords_missing"] else "-"
        print(f"{q}  {passed:>4}  {latency:>8}  {missing}")
    print()
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    print(f"Results: {passed_count}/{total} passed")
    print()


def main() -> None:
    base_url = os.environ.get("QUERY_API_URL", "").rstrip("/")
    repo_id = os.environ.get("REPO_ID", "")
    api_key = os.environ.get("API_KEY") or None

    if not base_url:
        print("ERROR: QUERY_API_URL environment variable is required", file=sys.stderr)
        sys.exit(1)
    if not repo_id:
        print("ERROR: REPO_ID environment variable is required", file=sys.stderr)
        sys.exit(1)

    print(f"Evaluating against: {base_url}")
    print(f"Repo ID: {repo_id}")

    results = _run_eval(base_url, repo_id, api_key)

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _RESULTS_FILE.write_text(json.dumps(results, indent=2))
    print(f"Full results written to: {_RESULTS_FILE}")

    _print_table(results)

    all_passed = all(r["passed"] for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
