"""Unit tests for the Bedrock embedder."""

import io
import json
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.ingestion.embedder import embed_texts
from src.shared.bedrock import EMBEDDING_DIM


def _mock_bedrock(embedding: list[float] | None = None) -> MagicMock:
    """Return a mock bedrock-runtime client that yields a fixed embedding."""
    if embedding is None:
        embedding = [0.1] * EMBEDDING_DIM

    client = MagicMock()
    client.invoke_model.side_effect = lambda **_: {
        "body": io.BytesIO(json.dumps({"embedding": embedding}).encode())
    }
    return client


class TestEmbedTexts:
    def test_returns_numpy_array(self) -> None:
        client = _mock_bedrock()
        result = embed_texts(["hello"], client)
        assert isinstance(result, np.ndarray)

    def test_shape_matches_input_length(self) -> None:
        client = _mock_bedrock()
        result = embed_texts(["hello", "world", "foo"], client)
        assert result.shape == (3, EMBEDDING_DIM)

    def test_dtype_is_float32(self) -> None:
        client = _mock_bedrock()
        result = embed_texts(["hello"], client)
        assert result.dtype == np.float32

    def test_calls_bedrock_once_per_text(self) -> None:
        client = _mock_bedrock()
        embed_texts(["a", "b", "c"], client)
        assert client.invoke_model.call_count == 3

    def test_uses_correct_model_id(self) -> None:
        client = _mock_bedrock()
        embed_texts(["hello"], client)
        _, kwargs = client.invoke_model.call_args
        assert kwargs["modelId"] == "amazon.titan-embed-text-v2:0"

    def test_embedding_values_match_mock(self) -> None:
        expected = [float(i) / EMBEDDING_DIM for i in range(EMBEDDING_DIM)]
        client = _mock_bedrock(embedding=expected)
        result = embed_texts(["hello"], client)
        np.testing.assert_allclose(result[0], expected, rtol=1e-5)

    def test_single_text_has_correct_shape(self) -> None:
        client = _mock_bedrock()
        result = embed_texts(["only one"], client)
        assert result.shape == (1, EMBEDDING_DIM)
