"""Lambda Function URL streaming handler for POST /repos/{repo_id}/query.

Streams NDJSON events directly to the Lambda Runtime API using HTTP chunked
transfer encoding with the Lambda-Runtime-Function-Response-Mode: streaming
header.  This bypasses awslambdaric's buffered post_invocation_result so that
tokens arrive at the client as the model generates them.

Wire protocol (one JSON object per line):
  {"type": "sources", "sources": [{"file": "...", "chunk_index": 0}, ...]}
  {"type": "delta",   "text": "..."}      (one per token / small batch)
  {"type": "done",    "answer": "..."}    (full assembled answer)
  {"type": "error",   "error": "..."}     (replaces the above on failure)
"""

import base64
import http.client
import json
import logging
import os

import boto3

import awslambdaric.lambda_runtime_client as _rtc

from src.query_api.bedrock import embed_text, generate_answer_streaming
from src.shared.models import IngestionStatus, QueryRequest

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
_TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "")
_BUCKET_NAME = os.environ.get("S3_BUCKET", "")
_VECTOR_BUCKET_NAME = os.environ.get("VECTOR_BUCKET_NAME", "")
_API_KEY = os.environ.get("API_KEY", "")
_TOP_K = 5
_MAX_QUESTION_LEN = 2000

_dynamodb = boto3.resource("dynamodb", region_name=_AWS_REGION)
_s3 = boto3.client("s3", region_name=_AWS_REGION)
_s3vectors = boto3.client("s3vectors", region_name=_AWS_REGION)
_bedrock = boto3.client("bedrock-runtime", region_name=_AWS_REGION)

# ---------------------------------------------------------------------------
# awslambdaric 4.0.0 has no Python streaming API so we write directly to the
# Lambda Runtime HTTP API ourselves.  After the handler returns, awslambdaric
# would POST the return value to the same endpoint and crash the loop — this
# patch turns that second call into a no-op.  A WebSocket API would be the
# cleaner production approach; this is kept simple intentionally.
# ---------------------------------------------------------------------------
_streaming_sent = False
_orig_post_invocation_result = _rtc.BaseLambdaRuntimeClient.post_invocation_result


def _patched_post_invocation_result(self, invoke_id, result_data, content_type="application/json"):
    global _streaming_sent
    if _streaming_sent:
        _streaming_sent = False  # reset for the next warm invocation
        return
    return _orig_post_invocation_result(self, invoke_id, result_data, content_type)


_rtc.BaseLambdaRuntimeClient.post_invocation_result = _patched_post_invocation_result


# ---------------------------------------------------------------------------
# Streaming response writer
# ---------------------------------------------------------------------------

def _stream_events(request_id: str, events):
    """Write NDJSON events to the Lambda Runtime API as a chunked HTTP body."""
    global _streaming_sent
    runtime_api = os.environ["AWS_LAMBDA_RUNTIME_API"]
    conn = http.client.HTTPConnection(runtime_api)
    conn.putrequest("POST", f"/2018-06-01/runtime/invocation/{request_id}/response")
    conn.putheader("Content-Type", "application/x-ndjson")
    conn.putheader("Lambda-Runtime-Function-Response-Mode", "streaming")
    conn.putheader("Transfer-Encoding", "chunked")
    conn.endheaders()

    try:
        for event in events:
            line = json.dumps(event).encode() + b"\n"
            conn.send(f"{len(line):x}\r\n".encode() + line + b"\r\n")
    finally:
        # Set _streaming_sent first so the monkey-patch no-ops awslambdaric's
        # subsequent post_invocation_result even if teardown raises.
        _streaming_sent = True
        conn.send(b"0\r\n\r\n")  # end of chunked body
        conn.getresponse().read()
        conn.close()


# ---------------------------------------------------------------------------
# Event generator — module-level so it can be unit-tested independently
# ---------------------------------------------------------------------------

def _generate_events(event: dict):
    """Yield NDJSON event dicts for the given Lambda Function URL event.

    Factored out of lambda_handler so tests can drive it directly without
    involving the streaming runtime API or http.client.
    """
    # Auth check.
    if _API_KEY:
        headers = event.get("headers") or {}
        if headers.get("x-api-key", "") != _API_KEY:
            yield {"type": "error", "error": "Unauthorized"}
            return

    # Extract repo_id from rawPath: /repos/<uuid>/query
    raw_path = event.get("rawPath", "")
    parts = raw_path.strip("/").split("/")
    if len(parts) < 3 or parts[0] != "repos" or parts[2] != "query":
        yield {"type": "error", "error": "invalid path — expected /repos/{repo_id}/query"}
        return

    repo_id = parts[1]
    if not repo_id:
        yield {"type": "error", "error": "repo_id is required"}
        return

    # Validate repo exists and is ready.
    db_result = _dynamodb.Table(_TABLE_NAME).get_item(Key={"repo_id": repo_id})
    item = db_result.get("Item")
    if not item:
        yield {"type": "error", "error": f"repo {repo_id} not found"}
        return
    if item["status"] != IngestionStatus.READY.value:
        yield {"type": "error", "error": f"repo {repo_id} is not ready (status: {item['status']})"}
        return

    # Parse request body.
    try:
        raw_body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw_body = base64.b64decode(raw_body).decode()
        req = QueryRequest(**json.loads(raw_body))
    except Exception:
        yield {"type": "error", "error": "body must be JSON with a 'question' field"}
        return

    if not req.question.strip():
        yield {"type": "error", "error": "question must not be empty"}
        return
    if len(req.question) > _MAX_QUESTION_LEN:
        yield {"type": "error", "error": f"question must be {_MAX_QUESTION_LEN} characters or fewer"}
        return

    logger.info("streaming_query repo_id=%s question_len=%d history_turns=%d",
                repo_id, len(req.question), len(req.history))

    # Embed question and find relevant chunks.
    query_vec = embed_text(req.question, _bedrock)
    response = _s3vectors.query_vectors(
        vectorBucketName=_VECTOR_BUCKET_NAME,
        indexName=repo_id,
        queryVector={"float32": query_vec.tolist()},
        topK=_TOP_K,
        returnMetadata=True,
    )
    hits = response.get("vectors", [])
    logger.info("streaming_query vectors repo_id=%s hits=%d", repo_id, len(hits))

    if not hits:
        yield {"type": "sources", "sources": []}
        yield {"type": "done", "answer": "No relevant content found."}
        return

    chunks_obj = _s3.get_object(Bucket=_BUCKET_NAME, Key=f"repos/{repo_id}/chunks.json")
    chunks = json.loads(chunks_obj["Body"].read())

    context_parts, sources = [], []
    for hit in hits:
        idx = int(hit["key"])
        chunk = chunks[idx]
        context_parts.append(chunk["text"])
        sources.append({"file": chunk["source"], "chunk_index": chunk["chunk_index"]})

    # Emit sources before streaming text so the frontend can render them immediately.
    yield {"type": "sources", "sources": sources}

    # Stream answer tokens.
    context_text = "\n\n---\n\n".join(context_parts)
    answer_parts = []
    for delta in generate_answer_streaming(req.question, context_text, req.history, _bedrock):
        answer_parts.append(delta)
        yield {"type": "delta", "text": delta}

    yield {"type": "done", "answer": "".join(answer_parts)}


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """Entry point for the streaming query Function URL."""
    _stream_events(context.aws_request_id, _generate_events(event))
    return None
