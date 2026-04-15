"""Bedrock helpers for the query API."""

import json
import logging
from collections.abc import Generator

from src.shared.bedrock import embed_text  # noqa: F401 — re-exported for handler imports
from src.shared.models import ChatMessage

logger = logging.getLogger(__name__)

_CLAUDE_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"

_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions about a software repository. "
    "Answer using only the context provided by the user. "
    "When referencing code, mention the file path. "
    "If the context does not contain enough information, say so."
)


def generate_answer(question: str, context: str, bedrock_client) -> str:
    """Generate an answer to a question, grounded in the provided context."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": _SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"<context>\n{context}\n</context>\n\n"
                    f"Question: {question}"
                ),
            }
        ],
    }
    response = bedrock_client.invoke_model(
        modelId=_CLAUDE_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    content = result.get("content", [])
    if not content:
        logger.warning("claude returned empty content stop_reason=%s", result.get("stop_reason"))
        return "I was unable to generate an answer. Please try again."
    return content[0]["text"]


def generate_answer_streaming(
    question: str,
    context: str,
    history: list[ChatMessage],
    bedrock_client,
) -> Generator[str, None, None]:
    """Yield text delta strings from the model via the Bedrock streaming API."""
    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append(
        {
            "role": "user",
            "content": f"<context>\n{context}\n</context>\n\nQuestion: {question}",
        }
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": _SYSTEM_PROMPT,
        "messages": messages,
    }
    response = bedrock_client.invoke_model_with_response_stream(
        modelId=_CLAUDE_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    for event in response["body"]:
        chunk = event.get("chunk")
        if not chunk:
            continue
        data = json.loads(chunk["bytes"])
        if data.get("type") == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                yield delta.get("text", "")
