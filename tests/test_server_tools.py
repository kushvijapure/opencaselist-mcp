"""Tests for server-layer input validation (Phase 3 audit).

These tests exercise the _tool_* functions directly, verifying that bad
inputs are rejected with clear error messages before any network call
or index access is attempted.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import server


class TestDownloadDocxValidation:
    async def test_http_url_rejected(self):
        result = await server._tool_download_docx(
            {"file_url": "http://opencaselist.com/files/test.docx"}
        )
        assert result["success"] is False
        assert "https" in result["error"].lower() or "HTTPS" in result["error"]

    async def test_https_url_accepted_shape(self):
        # Passes HTTPS check; fails later at credential check in wiki_client — not a crash
        result = await server._tool_download_docx(
            {"file_url": "https://opencaselist.com/files/test.docx"}
        )
        # success may be False due to missing credentials, but must not raise
        assert "success" in result or "error" in result

    async def test_http_url_returns_url_field(self):
        result = await server._tool_download_docx(
            {"file_url": "http://evil.com/file.docx"}
        )
        assert result.get("url") == "http://evil.com/file.docx"


class TestRoundMetadataValidation:
    async def test_empty_string_rejected(self):
        result = await server._tool_round_metadata({"url_or_title": ""})
        assert "error" in result

    async def test_whitespace_only_rejected(self):
        result = await server._tool_round_metadata({"url_or_title": "   "})
        assert "error" in result


class TestTeamFilesValidation:
    async def test_empty_string_rejected(self):
        result = await server._tool_team_files({"url_or_title": ""})
        assert "error" in result

    async def test_whitespace_only_rejected(self):
        result = await server._tool_team_files({"url_or_title": "\t"})
        assert "error" in result
