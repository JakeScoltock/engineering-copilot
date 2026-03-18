"""Fetches text files from a public GitHub repository."""

import logging
from urllib.parse import urlparse

import httpx

from src.shared.models import Document

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_RAW_BASE = "https://raw.githubusercontent.com"

# File extensions treated as readable text
_TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".rst",
    ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs",
    ".yaml", ".yml", ".toml", ".json",
    ".html", ".css", ".sh", ".bash",
    ".tf", ".hcl", ".sql", ".r", ".scala", ".kt", ".swift",
}

# Skip files larger than 200 KB — likely generated or binary-ish
_MAX_FILE_BYTES = 200_000


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a github.com URL.

    Args:
        url: A URL of the form https://github.com/owner/repo[/...].

    Returns:
        Tuple of (owner, repo).

    Raises:
        ValueError: If the URL is not a valid public GitHub repo URL.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise ValueError(f"URL must be https://github.com/owner/repo, got: {url}")

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Cannot extract owner/repo from URL: {url}")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return owner, repo


def fetch_repo(url: str, github_token: str | None = None) -> list[Document]:
    """Download all text files from a public GitHub repo.

    Uses the GitHub Trees API to enumerate files then fetches each via
    raw.githubusercontent.com. Binary files and files over 200 KB are skipped.

    Args:
        url: A https://github.com/owner/repo URL.
        github_token: Optional personal access token for higher API rate limits.

    Returns:
        List of Document objects, one per text file, in tree order.

    Raises:
        ValueError: If the URL is invalid.
        httpx.HTTPStatusError: If the GitHub API returns a non-2xx response.
    """
    owner, repo = parse_github_url(url)
    logger.info("fetch_repo started owner=%s repo=%s", owner, repo)

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    with httpx.Client(headers=headers, timeout=30) as client:
        default_branch = _get_default_branch(client, owner, repo)
        logger.info("default branch owner=%s repo=%s branch=%s", owner, repo, default_branch)

        tree = _get_tree(client, owner, repo, default_branch)
        blobs = [i for i in tree if i.get("type") == "blob"]
        logger.info("tree fetched owner=%s repo=%s total_items=%d blobs=%d", owner, repo, len(tree), len(blobs))

        documents = []
        skipped_binary = 0
        skipped_size = 0
        skipped_fetch = 0

        for item in blobs:
            path: str = item["path"]

            if not _is_text_file(path):
                skipped_binary += 1
                continue

            if item.get("size", 0) > _MAX_FILE_BYTES:
                logger.debug("skipping oversized file path=%s size=%d", path, item.get("size", 0))
                skipped_size += 1
                continue

            raw_url = f"{_RAW_BASE}/{owner}/{repo}/{default_branch}/{path}"
            resp = client.get(raw_url)
            if resp.status_code != 200:
                logger.warning("file fetch failed path=%s status=%d", path, resp.status_code)
                skipped_fetch += 1
                continue

            text = resp.text
            if text.strip():
                documents.append(Document(source=path, content=text))

        logger.info(
            "fetch_repo complete owner=%s repo=%s documents=%d "
            "skipped_binary=%d skipped_size=%d skipped_fetch=%d",
            owner, repo, len(documents),
            skipped_binary, skipped_size, skipped_fetch,
        )
        return documents


def _get_default_branch(client: httpx.Client, owner: str, repo: str) -> str:
    resp = client.get(f"{_GITHUB_API}/repos/{owner}/{repo}")
    resp.raise_for_status()
    return resp.json()["default_branch"]


def _get_tree(
    client: httpx.Client, owner: str, repo: str, branch: str
) -> list[dict]:
    resp = client.get(
        f"{_GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}",
        params={"recursive": "1"},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("truncated"):
        logger.warning("git tree truncated owner=%s repo=%s — repo exceeds 100k items, some files will be skipped", owner, repo)
    return data.get("tree", [])


def _is_text_file(path: str) -> bool:
    """Return True if the file path has a recognised text extension."""
    if "." not in path.rsplit("/", 1)[-1]:
        return False
    suffix = "." + path.rsplit(".", 1)[-1].lower()
    return suffix in _TEXT_EXTENSIONS
