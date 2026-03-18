"""Splits documents into overlapping line-based chunks with source attribution metadata."""

import logging

from src.shared.models import Document, DocumentChunk

logger = logging.getLogger(__name__)

# Default chunk size and overlap match the values that worked well in local RAG testing.
# 120 lines keeps chunks focused on a single function/class while staying under
# Bedrock Titan's 8192-token input limit even for dense code.
DEFAULT_CHUNK_SIZE = 120
DEFAULT_OVERLAP = 20

_LANGUAGE_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".tf": "terraform",
    ".hcl": "hcl",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".rst": "rst",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
}


def _detect_language(source: str) -> str:
    ext = "." + source.rsplit(".", 1)[-1].lower() if "." in source.rsplit("/", 1)[-1] else ""
    return _LANGUAGE_MAP.get(ext, "")


def chunk_document(
    document: Document,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[DocumentChunk]:
    """Split a document into overlapping line-based chunks.

    Each chunk is prefixed with a ``# File: <source>`` header so the LLM knows
    the source file when reading retrieved context — without needing to look at
    metadata separately.

    Small files (≤ chunk_size lines) are returned as a single chunk.

    Args:
        document: The document to chunk.
        chunk_size: Maximum number of source lines per chunk (default 120).
        overlap: Number of lines repeated at the start of the next chunk (default 20).

    Returns:
        List of DocumentChunk objects with full source attribution metadata.

    Raises:
        ValueError: If overlap >= chunk_size.
    """
    if overlap >= chunk_size:
        raise ValueError(
            f"chunk_size ({chunk_size}) must be greater than overlap ({overlap})"
        )

    lines = document.content.splitlines(keepends=True)

    if not lines:
        return []

    raw_chunks = _split_lines(lines, chunk_size, overlap)

    language = _detect_language(document.source)
    result = []
    for chunk_index, (start_line, chunk_lines) in enumerate(raw_chunks):
        header = f"# File: {document.source}\n"
        text = header + "".join(chunk_lines)
        result.append(
            DocumentChunk(
                source=document.source,
                chunk_index=chunk_index,
                text=text,
                line_count=len(chunk_lines),
                start_line=start_line,
                end_line=start_line + len(chunk_lines),
                language=language,
            )
        )

    logger.debug("chunked source=%s chunks=%d", document.source, len(result))
    return result


def chunk_documents(
    documents: list[Document],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[DocumentChunk]:
    """Chunk a list of documents.

    Args:
        documents: Documents to chunk.
        chunk_size: Maximum number of source lines per chunk.
        overlap: Number of lines repeated between consecutive chunks.

    Returns:
        Flat list of DocumentChunk objects across all documents.
    """
    all_chunks: list[DocumentChunk] = []
    for document in documents:
        all_chunks.extend(chunk_document(document, chunk_size=chunk_size, overlap=overlap))
    logger.info("chunk_documents complete documents=%d total_chunks=%d", len(documents), len(all_chunks))
    return all_chunks


def _split_lines(
    lines: list[str], chunk_size: int, overlap: int
) -> list[tuple[int, list[str]]]:
    """Split lines into overlapping windows.

    Returns a list of (start_line_index, lines_in_chunk) tuples.
    """
    if len(lines) <= chunk_size:
        return [(0, lines)]

    chunks = []
    start = 0
    while start < len(lines):
        end = min(start + chunk_size, len(lines))
        chunks.append((start, lines[start:end]))
        if end == len(lines):
            break
        start += chunk_size - overlap

    return chunks
