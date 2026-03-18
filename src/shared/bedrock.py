"""Shared Bedrock helpers used by both ingestion and query pipelines."""

import json
import logging

import numpy as np

logger = logging.getLogger(__name__)

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIM = 1536


def embed_text(text: str, bedrock_client) -> np.ndarray:
    """Embed a single string using Bedrock Titan, returning a normalised float32 vector."""
    response = bedrock_client.invoke_model(
        modelId=TITAN_MODEL_ID,
        body=json.dumps({"inputText": text, "dimensions": EMBEDDING_DIM, "normalize": True}),
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    return np.array(result["embedding"], dtype="float32")
