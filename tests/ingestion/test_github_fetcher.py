"""Unit tests for the GitHub repository fetcher."""

from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.github_fetcher import _is_text_file, fetch_repo, parse_github_url


class TestParseGithubUrl:
    def test_valid_url(self) -> None:
        owner, repo = parse_github_url("https://github.com/octocat/Hello-World")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_strips_git_suffix(self) -> None:
        owner, repo = parse_github_url("https://github.com/octocat/Hello-World.git")
        assert repo == "Hello-World"

    def test_extra_path_segments_ignored(self) -> None:
        owner, repo = parse_github_url("https://github.com/octocat/Hello-World/tree/main")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="https://github.com"):
            parse_github_url("http://github.com/octocat/Hello-World")

    def test_rejects_non_github(self) -> None:
        with pytest.raises(ValueError, match="https://github.com"):
            parse_github_url("https://gitlab.com/octocat/Hello-World")

    def test_rejects_missing_repo(self) -> None:
        with pytest.raises(ValueError, match="Cannot extract"):
            parse_github_url("https://github.com/octocat")

    def test_rejects_bare_domain(self) -> None:
        with pytest.raises(ValueError, match="Cannot extract"):
            parse_github_url("https://github.com/")


class TestIsTextFile:
    def test_python_file(self) -> None:
        assert _is_text_file("src/main.py") is True

    def test_markdown_file(self) -> None:
        assert _is_text_file("README.md") is True

    def test_typescript_file(self) -> None:
        assert _is_text_file("app/index.ts") is True

    def test_terraform_file(self) -> None:
        assert _is_text_file("infra/main.tf") is True

    def test_png_excluded(self) -> None:
        assert _is_text_file("assets/logo.png") is False

    def test_binary_excluded(self) -> None:
        assert _is_text_file("dist/app.exe") is False

    def test_no_extension_excluded(self) -> None:
        assert _is_text_file("Makefile") is False

    def test_extension_case_insensitive(self) -> None:
        assert _is_text_file("README.MD") is True


class TestFetchRepo:
    def _make_mock_client(
        self,
        default_branch: str = "main",
        tree: list[dict] | None = None,
        file_contents: dict[str, str] | None = None,
    ) -> MagicMock:
        """Build a mock httpx.Client that returns controlled responses."""
        if tree is None:
            tree = []
        if file_contents is None:
            file_contents = {}

        def mock_get(url: str, **kwargs) -> MagicMock:
            resp = MagicMock()
            resp.status_code = 200

            if "/repos/" in url and "/git/trees/" not in url and "raw.githubusercontent" not in url:
                # Repo metadata endpoint
                resp.json.return_value = {"default_branch": default_branch}
            elif "/git/trees/" in url:
                # Tree endpoint
                resp.json.return_value = {"tree": tree}
            elif "raw.githubusercontent" in url:
                # Raw file content
                path = url.split(f"/{default_branch}/", 1)[-1]
                content = file_contents.get(path, "")
                resp.text = content
                if content == "__404__":
                    resp.status_code = 404
            else:
                resp.json.return_value = {}

            resp.raise_for_status = MagicMock()
            return resp

        client = MagicMock()
        client.get.side_effect = mock_get
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        return client

    def test_returns_documents_for_text_files(self) -> None:
        tree = [
            {"type": "blob", "path": "README.md", "size": 100},
            {"type": "blob", "path": "src/main.py", "size": 200},
        ]
        file_contents = {
            "README.md": "# Hello World",
            "src/main.py": "print('hello')",
        }
        client = self._make_mock_client(tree=tree, file_contents=file_contents)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client):
            docs = fetch_repo("https://github.com/octocat/Hello-World")

        assert len(docs) == 2
        sources = {d.source for d in docs}
        assert sources == {"README.md", "src/main.py"}

    def test_excludes_binary_files(self) -> None:
        tree = [
            {"type": "blob", "path": "README.md", "size": 100},
            {"type": "blob", "path": "image.png", "size": 5000},
        ]
        file_contents = {"README.md": "# Hello"}
        client = self._make_mock_client(tree=tree, file_contents=file_contents)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client):
            docs = fetch_repo("https://github.com/octocat/Hello-World")

        assert len(docs) == 1
        assert docs[0].source == "README.md"

    def test_excludes_files_over_size_limit(self) -> None:
        tree = [
            {"type": "blob", "path": "small.py", "size": 100},
            {"type": "blob", "path": "huge.py", "size": 300_000},
        ]
        file_contents = {"small.py": "x = 1"}
        client = self._make_mock_client(tree=tree, file_contents=file_contents)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client):
            docs = fetch_repo("https://github.com/octocat/Hello-World")

        assert len(docs) == 1
        assert docs[0].source == "small.py"

    def test_excludes_tree_entries_that_are_not_blobs(self) -> None:
        tree = [
            {"type": "tree", "path": "src", "size": 0},
            {"type": "blob", "path": "README.md", "size": 50},
        ]
        file_contents = {"README.md": "hello"}
        client = self._make_mock_client(tree=tree, file_contents=file_contents)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client):
            docs = fetch_repo("https://github.com/octocat/Hello-World")

        assert len(docs) == 1

    def test_skips_file_when_raw_fetch_returns_404(self) -> None:
        tree = [
            {"type": "blob", "path": "README.md", "size": 50},
            {"type": "blob", "path": "missing.py", "size": 50},
        ]
        file_contents = {"README.md": "hello", "missing.py": "__404__"}
        client = self._make_mock_client(tree=tree, file_contents=file_contents)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client):
            docs = fetch_repo("https://github.com/octocat/Hello-World")

        assert len(docs) == 1
        assert docs[0].source == "README.md"

    def test_skips_empty_files(self) -> None:
        tree = [
            {"type": "blob", "path": "empty.py", "size": 0},
            {"type": "blob", "path": "real.py", "size": 50},
        ]
        file_contents = {"empty.py": "   ", "real.py": "x = 1"}
        client = self._make_mock_client(tree=tree, file_contents=file_contents)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client):
            docs = fetch_repo("https://github.com/octocat/Hello-World")

        assert len(docs) == 1
        assert docs[0].source == "real.py"

    def test_document_content_matches_raw_response(self) -> None:
        tree = [{"type": "blob", "path": "app.py", "size": 30}]
        file_contents = {"app.py": "def hello():\n    return 'hi'\n"}
        client = self._make_mock_client(tree=tree, file_contents=file_contents)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client):
            docs = fetch_repo("https://github.com/octocat/Hello-World")

        assert docs[0].content == "def hello():\n    return 'hi'\n"

    def test_invalid_url_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            fetch_repo("https://gitlab.com/owner/repo")

    def test_passes_auth_header_when_token_provided(self) -> None:
        tree = [{"type": "blob", "path": "README.md", "size": 10}]
        file_contents = {"README.md": "hello"}
        client = self._make_mock_client(tree=tree, file_contents=file_contents)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client) as mock_cls:
            fetch_repo("https://github.com/octocat/Hello-World", github_token="tok_abc")
            _, kwargs = mock_cls.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer tok_abc"

    def test_no_auth_header_without_token(self) -> None:
        tree: list = []
        client = self._make_mock_client(tree=tree)

        with patch("src.ingestion.github_fetcher.httpx.Client", return_value=client) as mock_cls:
            fetch_repo("https://github.com/octocat/Hello-World")
            _, kwargs = mock_cls.call_args
            assert "Authorization" not in kwargs["headers"]
