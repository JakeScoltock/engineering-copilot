"""Unit tests for the line-based document chunking logic."""

import pytest

from src.ingestion.chunker import chunk_document, chunk_documents
from src.shared.models import Document


def make_document(content: str, source: str = "test.py") -> Document:
    return Document(source=source, content=content)


def make_lines(n: int) -> str:
    """Return a string with n numbered lines."""
    return "".join(f"line {i}\n" for i in range(n))


class TestChunkDocument:
    def test_single_chunk_for_short_document(self) -> None:
        doc = make_document(make_lines(10))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        assert len(chunks) == 1

    def test_multiple_chunks_for_long_document(self) -> None:
        doc = make_document(make_lines(300))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        assert len(chunks) > 1

    def test_chunk_size_respected(self) -> None:
        doc = make_document(make_lines(300))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        for chunk in chunks:
            assert chunk.line_count <= 120

    def test_overlap_repeats_lines_between_chunks(self) -> None:
        doc = make_document(make_lines(200))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        assert len(chunks) > 1
        # The last 20 lines of chunk 0 should be the first 20 lines of chunk 1
        # (ignoring the file header prepended to each chunk)
        lines_0 = chunks[0].text.splitlines()[1:]  # skip header
        lines_1 = chunks[1].text.splitlines()[1:]  # skip header
        assert lines_0[-20:] == lines_1[:20]

    def test_chunk_index_is_sequential(self) -> None:
        doc = make_document(make_lines(300))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_source_attribution_preserved(self) -> None:
        doc = make_document(make_lines(10), source="src/main.py")
        chunks = chunk_document(doc)
        for chunk in chunks:
            assert chunk.source == "src/main.py"

    def test_file_header_prepended_to_each_chunk(self) -> None:
        doc = make_document(make_lines(10), source="src/utils.py")
        chunks = chunk_document(doc)
        for chunk in chunks:
            assert chunk.text.startswith("# File: src/utils.py\n")

    def test_start_line_of_first_chunk_is_zero(self) -> None:
        doc = make_document(make_lines(200))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        assert chunks[0].start_line == 0

    def test_start_line_advances_by_chunk_size_minus_overlap(self) -> None:
        doc = make_document(make_lines(300))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        assert chunks[1].start_line == 100  # 120 - 20

    def test_end_line_equals_start_plus_line_count(self) -> None:
        doc = make_document(make_lines(300))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        for chunk in chunks:
            assert chunk.end_line == chunk.start_line + chunk.line_count

    def test_no_empty_chunks(self) -> None:
        doc = make_document(make_lines(300))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        for chunk in chunks:
            assert chunk.line_count > 0

    def test_empty_document_produces_no_chunks(self) -> None:
        doc = make_document("")
        assert chunk_document(doc) == []

    def test_raises_when_overlap_exceeds_chunk_size(self) -> None:
        doc = make_document(make_lines(10))
        with pytest.raises(ValueError, match="chunk_size"):
            chunk_document(doc, chunk_size=10, overlap=20)

    def test_exact_chunk_size_document_is_single_chunk(self) -> None:
        doc = make_document(make_lines(120))
        chunks = chunk_document(doc, chunk_size=120, overlap=20)
        assert len(chunks) == 1
        assert chunks[0].line_count == 120


class TestChunkDocuments:
    def test_chunks_multiple_documents(self) -> None:
        docs = [
            make_document(make_lines(200), source="a.py"),
            make_document(make_lines(200), source="b.py"),
        ]
        chunks = chunk_documents(docs, chunk_size=120, overlap=20)
        sources = {c.source for c in chunks}
        assert "a.py" in sources
        assert "b.py" in sources

    def test_chunk_indices_are_per_document(self) -> None:
        docs = [
            make_document(make_lines(200), source="a.py"),
            make_document(make_lines(200), source="b.py"),
        ]
        chunks = chunk_documents(docs, chunk_size=120, overlap=20)
        for source in ("a.py", "b.py"):
            source_chunks = [c for c in chunks if c.source == source]
            assert [c.chunk_index for c in source_chunks] == list(range(len(source_chunks)))

    def test_empty_list_returns_empty(self) -> None:
        assert chunk_documents([]) == []
