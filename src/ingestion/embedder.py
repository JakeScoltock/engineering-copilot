"""Bedrock Titan Embeddings v2 wrapper."""

import logging

import numpy as np

from src.shared.bedrock import TITAN_MODEL_ID, embed_text

logger = logging.getLogger(__name__)

_LOG_EVERY = 25


def embed_texts(texts: list[str], bedrock_client) -> np.ndarray:
    """Embed a list of texts, returning a float32 array of shape (len(texts), 1536)."""
    total = len(texts)
    logger.info("embedding started total=%d model=%s", total, TITAN_MODEL_ID)

    embeddings = []
    for i, text in enumerate(texts):
        embeddings.append(embed_text(text, bedrock_client).tolist())
        if (i + 1) % _LOG_EVERY == 0 or (i + 1) == total:
            logger.info("embedding progress %d/%d", i + 1, total)

    array = np.array(embeddings, dtype="float32")
    logger.info("embedding complete shape=%s", array.shape)
    return array
