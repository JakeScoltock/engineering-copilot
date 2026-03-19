"""Bedrock helpers for the query API."""

import json
import logging

from src.shared.bedrock import embed_text  # noqa: F401 — re-exported for handler imports

logger = logging.getLogger(__name__)

_CLAUDE_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def ask_claude(question: str, context: str, bedrock_client) -> str:
    """Ask Claude Haiku a question, grounded in the provided context."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": (
            "You are a helpful assistant that answers questions about a software repository. "
            "Answer using only the context provided by the user. "
            "When referencing code, mention the file path. "
            "If the context does not contain enough information, say so."
        ),
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
