"""API Gateway Lambda: POST /repos, GET /repos/{repo_id}, POST /repos/{repo_id}/query, GET /health."""

import json
import logging
import os
from datetime import UTC, datetime, timedelta

import boto3

from src.ingestion.github_fetcher import parse_github_url
from src.query_api.bedrock import ask_claude, embed_text
from src.shared.models import IngestionStatus, QueryRequest, QueryResponse, RepoJob, SourceRef

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")

_dynamodb = boto3.resource("dynamodb", region_name=_AWS_REGION)
_sqs = boto3.client("sqs", region_name=_AWS_REGION)
_s3 = boto3.client("s3", region_name=_AWS_REGION)
_s3vectors = boto3.client("s3vectors", region_name=_AWS_REGION)
_bedrock = boto3.client("bedrock-runtime", region_name=_AWS_REGION)

_TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "")
_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
_BUCKET_NAME = os.environ.get("S3_BUCKET", "")
_VECTOR_BUCKET_NAME = os.environ.get("VECTOR_BUCKET_NAME", "")

_TOP_K = 5
_MAX_QUESTION_LEN = 2000
_JOB_TTL_DAYS = 30


def lambda_handler(event, context):
    method = event.get("httpMethod", "")
    resource = event.get("resource", "")
    logger.info("request method=%s resource=%s", method, resource)

    if method == "GET" and resource == "/health":
        return _ok({"status": "ok", "service": "query-api"})

    if method == "POST" and resource == "/repos":
        return _create_repo(event)

    if method == "GET" and resource == "/repos/{repo_id}":
        return _get_repo(event)

    if method == "POST" and resource == "/repos/{repo_id}/query":
        return _query_repo(event)

    logger.warning("unmatched route method=%s resource=%s", method, resource)
    return _error(404, "Not found")


# Handlers

def _create_repo(event: dict) -> dict:
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _error(400, "Request body must be valid JSON")
    github_url = body.get("github_url", "").strip()

    if not github_url:
        logger.warning("create_repo rejected: github_url missing")
        return _error(400, "github_url is required")

    try:
        parse_github_url(github_url)
    except ValueError as exc:
        logger.warning("create_repo rejected invalid url=%s error=%s", github_url, exc)
        return _error(400, str(exc))

    job = RepoJob(github_url=github_url)
    now = datetime.now(UTC)
    expires_at = int((now + timedelta(days=_JOB_TTL_DAYS)).timestamp())

    table = _dynamodb.Table(_TABLE_NAME)
    table.put_item(
        Item={
            "repo_id": job.repo_id,
            "github_url": job.github_url,
            "status": IngestionStatus.PENDING.value,
            "error": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": expires_at,
        }
    )
    logger.info("repo_job created repo_id=%s github_url=%s", job.repo_id, job.github_url)

    try:
        _sqs.send_message(
            QueueUrl=_QUEUE_URL,
            MessageBody=json.dumps(
                {"repo_id": job.repo_id, "github_url": job.github_url}
            ),
        )
    except Exception:
        table.delete_item(Key={"repo_id": job.repo_id})
        logger.exception("sqs enqueue failed, rolled back dynamodb repo_id=%s", job.repo_id)
        return _error(500, "Failed to enqueue ingestion job")

    logger.info("ingestion enqueued repo_id=%s", job.repo_id)

    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"repo_id": job.repo_id, "status": IngestionStatus.PENDING.value}),
    }


def _get_repo(event: dict) -> dict:
    params = event.get("pathParameters") or {}
    repo_id = params.get("repo_id", "").strip()

    if not repo_id:
        logger.warning("get_repo rejected: repo_id missing")
        return _error(400, "repo_id is required")

    result = _dynamodb.Table(_TABLE_NAME).get_item(Key={"repo_id": repo_id})
    item = result.get("Item")

    if not item:
        logger.warning("get_repo not found repo_id=%s", repo_id)
        return _error(404, f"repo {repo_id} not found")

    logger.info("get_repo repo_id=%s status=%s", repo_id, item["status"])
    return _ok(
        {
            "repo_id": item["repo_id"],
            "status": item["status"],
            "error": item.get("error"),
        }
    )


def _query_repo(event: dict) -> dict:
    params = event.get("pathParameters") or {}
    repo_id = params.get("repo_id", "").strip()

    if not repo_id:
        return _error(400, "repo_id is required")

    # Validate repo exists and is ready.
    result = _dynamodb.Table(_TABLE_NAME).get_item(Key={"repo_id": repo_id})
    item = result.get("Item")
    if not item:
        return _error(404, f"repo {repo_id} not found")
    if item["status"] != IngestionStatus.READY.value:
        return _error(409, f"repo {repo_id} is not ready (status: {item['status']})")

    try:
        req = QueryRequest(**json.loads(event.get("body") or "{}"))
    except Exception:
        return _error(400, "body must be JSON with a 'question' field")

    if not req.question.strip():
        return _error(400, "question must not be empty")
    if len(req.question) > _MAX_QUESTION_LEN:
        return _error(400, f"question must be {_MAX_QUESTION_LEN} characters or fewer")

    logger.info("query_repo repo_id=%s question_len=%d", repo_id, len(req.question))

    # Embed the question.
    query_vec = embed_text(req.question, _bedrock)

    # Find the most relevant chunks via S3 Vectors ANN search.
    response = _s3vectors.query_vectors(
        vectorBucketName=_VECTOR_BUCKET_NAME,
        indexName=repo_id,
        queryVector={"float32": query_vec.tolist()},
        topK=_TOP_K,
        returnMetadata=True,
    )
    hits = response.get("vectors", [])
    logger.info("query_vectors repo_id=%s hits=%d", repo_id, len(hits))

    if not hits:
        return _ok(QueryResponse(answer="No relevant content found.", sources=[]).model_dump())

    chunks_obj = _s3.get_object(Bucket=_BUCKET_NAME, Key=f"repos/{repo_id}/chunks.json")
    chunks = json.loads(chunks_obj["Body"].read())

    # Assemble context from the returned hits.
    context_parts = []
    sources = []
    for hit in hits:
        idx = int(hit["key"])
        chunk = chunks[idx]
        context_parts.append(chunk["text"])
        sources.append(SourceRef(file=chunk["source"], chunk_index=chunk["chunk_index"]))

    context = "\n\n---\n\n".join(context_parts)

    # Ask Claude.
    answer = ask_claude(req.question, context, _bedrock)
    logger.info("query_repo complete repo_id=%s answer_len=%d", repo_id, len(answer))

    response_body = QueryResponse(answer=answer, sources=sources)
    return _ok(response_body.model_dump())


# Helpers

def _ok(body: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _error(status: int, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }
