"""SQS-triggered Lambda: fetch GitHub repo → chunk → embed → store in S3 Vectors."""

import json
import logging
import os
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError

from src.ingestion.chunker import chunk_documents
from src.ingestion.embedder import embed_texts
from src.ingestion.github_fetcher import fetch_repo
from src.shared.bedrock import EMBEDDING_DIM
from src.shared.models import IngestionStatus
from src.shared.observability import Timer, log_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")

_dynamodb = boto3.resource("dynamodb", region_name=_AWS_REGION)
_s3 = boto3.client("s3", region_name=_AWS_REGION)
_s3vectors = boto3.client("s3vectors", region_name=_AWS_REGION)
_bedrock = boto3.client("bedrock-runtime", region_name=_AWS_REGION)

_TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "")
_BUCKET_NAME = os.environ.get("S3_BUCKET", "")
_VECTOR_BUCKET_NAME = os.environ.get("VECTOR_BUCKET_NAME", "")
_GITHUB_TOKEN_SECRET_ARN = os.environ.get("GITHUB_TOKEN_SECRET_ARN", "")

_secrets = boto3.client("secretsmanager", region_name=_AWS_REGION)
_github_token_cache: str | None = None


def _get_github_token() -> str | None:
    """Fetch the GitHub token from Secrets Manager, caching within the container lifetime."""
    global _github_token_cache
    if not _GITHUB_TOKEN_SECRET_ARN:
        return None
    if _github_token_cache is not None:
        return _github_token_cache
    response = _secrets.get_secret_value(SecretId=_GITHUB_TOKEN_SECRET_ARN)
    _github_token_cache = response.get("SecretString") or None
    return _github_token_cache

_PUT_VECTORS_BATCH_SIZE = 500
_MAX_CHUNKS = 10_000


def lambda_handler(event, context):
    records = event.get("Records", [])
    logger.info("ingestion_handler invoked records=%d", len(records))
    for record in records:
        body = json.loads(record["body"])
        _ingest(repo_id=body["repo_id"], github_url=body["github_url"])


def _ingest(repo_id: str, github_url: str) -> None:
    table = _dynamodb.Table(_TABLE_NAME)
    with Timer() as total_timer:
        log_event(logger, "info", "ingestion_started", repo_id=repo_id, github_url=github_url)
        try:
            with Timer() as t:
                docs = fetch_repo(github_url, github_token=_get_github_token())
            log_event(logger, "info", "fetch_complete", repo_id=repo_id, docs=len(docs), latency_ms=round(t.elapsed_ms))

            with Timer() as t:
                chunks = chunk_documents(docs)
            if len(chunks) > _MAX_CHUNKS:
                logger.warning("chunk cap reached repo_id=%s chunks=%d cap=%d — truncating", repo_id, len(chunks), _MAX_CHUNKS)
                chunks = chunks[:_MAX_CHUNKS]
            log_event(logger, "info", "chunking_complete", repo_id=repo_id, chunks=len(chunks), latency_ms=round(t.elapsed_ms))

            log_event(logger, "info", "embedding_started", repo_id=repo_id, chunks=len(chunks))
            with Timer() as t:
                embeddings = embed_texts([c.text for c in chunks], _bedrock)
            log_event(logger, "info", "embedding_complete", repo_id=repo_id, shape=str(embeddings.shape), latency_ms=round(t.elapsed_ms))

            # Store chunk metadata in S3 so the query Lambda can retrieve text.
            with Timer() as t:
                _s3.put_object(
                    Bucket=_BUCKET_NAME,
                    Key=f"repos/{repo_id}/chunks.json",
                    Body=json.dumps([c.model_dump(mode="json") for c in chunks]),
                    ContentType="application/json",
                )
            log_event(logger, "info", "chunks_written", repo_id=repo_id, bucket=_BUCKET_NAME, latency_ms=round(t.elapsed_ms))

            # Store vectors in S3 Vectors for ANN similarity search.
            with Timer() as t:
                _ensure_vector_bucket()
                _reset_index(repo_id)
                _put_vectors(repo_id, chunks, embeddings)
            log_event(logger, "info", "vectors_written", repo_id=repo_id, total=len(chunks), latency_ms=round(t.elapsed_ms))

            _update_status(table, repo_id, IngestionStatus.READY)
            log_event(logger, "info", "ingestion_complete",
                      repo_id=repo_id, chunks=len(chunks), docs=len(docs),
                      total_latency_ms=round(total_timer.elapsed_ms))

        except Exception as exc:
            log_event(logger, "error", "ingestion_failed",
                      repo_id=repo_id, error=type(exc).__name__,
                      total_latency_ms=round(total_timer.elapsed_ms))
            logger.exception("ingestion failed repo_id=%s error=%s", repo_id, exc)
            _update_status(table, repo_id, IngestionStatus.FAILED, error=str(exc))
            raise


def _ensure_vector_bucket() -> None:
    """Create the vector bucket if it does not already exist."""
    try:
        _s3vectors.create_vector_bucket(vectorBucketName=_VECTOR_BUCKET_NAME)
        logger.info("vector bucket created name=%s", _VECTOR_BUCKET_NAME)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("ConflictException", "BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
            logger.debug("vector bucket already exists name=%s", _VECTOR_BUCKET_NAME)
        else:
            raise


def _reset_index(repo_id: str) -> None:
    """Delete the existing index for this repo (if any) and create a fresh one.

    Deleting before re-creating ensures a re-ingested repo never has stale
    vectors from the previous run.
    """
    try:
        _s3vectors.delete_index(vectorBucketName=_VECTOR_BUCKET_NAME, indexName=repo_id)
        logger.info("existing vector index deleted repo_id=%s", repo_id)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NotFoundException":
            raise

    _s3vectors.create_index(
        vectorBucketName=_VECTOR_BUCKET_NAME,
        indexName=repo_id,
        dataType="float32",
        dimension=EMBEDDING_DIM,
        distanceMetric="cosine",
    )
    logger.info("vector index created repo_id=%s", repo_id)


def _put_vectors(repo_id: str, chunks, embeddings) -> None:
    """Write all chunk vectors to S3 Vectors in batches of 500."""
    vectors = [
        {
            "key": str(i),
            "data": {"float32": embeddings[i].tolist()},
            "metadata": {
                "source": chunk.source,
                "chunk_index": chunk.chunk_index,
            },
        }
        for i, chunk in enumerate(chunks)
    ]

    for batch_start in range(0, len(vectors), _PUT_VECTORS_BATCH_SIZE):
        batch = vectors[batch_start: batch_start + _PUT_VECTORS_BATCH_SIZE]
        _s3vectors.put_vectors(
            vectorBucketName=_VECTOR_BUCKET_NAME,
            indexName=repo_id,
            vectors=batch,
        )
        logger.debug(
            "put_vectors batch repo_id=%s offset=%d count=%d",
            repo_id,
            batch_start,
            len(batch),
        )


def _update_status(
    table, repo_id: str, status: IngestionStatus, error: str | None = None
) -> None:
    table.update_item(
        Key={"repo_id": repo_id},
        UpdateExpression="SET #s = :s, #e = :e, updated_at = :u",
        ExpressionAttributeNames={"#s": "status", "#e": "error"},
        ExpressionAttributeValues={
            ":s": status.value,
            ":e": error,
            ":u": datetime.now(UTC).isoformat(),
        },
    )
    logger.info("status updated repo_id=%s status=%s", repo_id, status.value)
