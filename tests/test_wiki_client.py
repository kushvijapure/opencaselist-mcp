import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
import respx
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from wiki_client import OpenCaselistClient, _RateLimiter

BASE = "https://opencaselist.com"


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Unauthenticated client — no credentials set."""
    monkeypatch.setenv("OPENCASELIST_BASE_URL", BASE)
    monkeypatch.setenv("OPENCASELIST_USERNAME", "")
    monkeypatch.setenv("OPENCASELIST_PASSWORD", "")
    monkeypatch.setattr("wiki_client._SESSION_FILE", tmp_path / "session.json")
    return OpenCaselistClient()


@pytest.fixture
def credentialed_client(monkeypatch, tmp_path):
    """Client with credentials configured — needed for download tests."""
    monkeypatch.setenv("OPENCASELIST_BASE_URL", BASE)
    monkeypatch.setenv("OPENCASELIST_USERNAME", "testuser")
    monkeypatch.setenv("OPENCASELIST_PASSWORD", "testpass")
    monkeypatch.setattr("wiki_client._SESSION_FILE", tmp_path / "session.json")
    return OpenCaselistClient()


class TestSearch:
    async def test_search_success(self, client):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "query": {"search": [{
                    "title": "24-25NationalCircuit/Harvard/KP",
                    "snippet": "Harvard KP neg file",
                    "titlesnippet": "",
                    "sectiontitle": "",
                }]}
            }))
            results = await client.search("Harvard")
        assert len(results) == 1
        assert results[0].title == "24-25NationalCircuit/Harvard/KP"

    async def test_search_populates_url(self, client):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "query": {"search": [{
                    "title": "24-25NDTCEDA/Michigan/DM",
                    "snippet": "", "titlesnippet": "", "sectiontitle": "",
                }]}
            }))
            results = await client.search("Michigan")
        assert BASE in results[0].url

    async def test_search_empty_results(self, client):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "query": {"search": []}
            }))
            results = await client.search("nonexistent xyz")
        assert results == []

    async def test_search_malformed_response_no_crash(self, client):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={}))
            results = await client.search("anything")
        assert isinstance(results, list)
        assert results == []

    async def test_search_network_error_returns_error_result(self, client):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(side_effect=Exception("Connection refused"))
            results = await client.search("anything")
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].page_type == "error"

    async def test_search_http_500_returns_error_result(self, client):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(500))
            results = await client.search("anything")
        assert results[0].page_type == "error"

    async def test_search_year_filter(self, client):
        # The filter does a literal string match: filters["year"] in title
        # OpenCaselist titles that embed the year literally (e.g. "NDT2024/...") match;
        # season-notation titles ("24-25/...") do not — that's a known gap flagged in Phase 0.
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "query": {"search": [
                    {"title": "NDT2024/TeamA/AB", "snippet": "", "titlesnippet": "", "sectiontitle": ""},
                    {"title": "NDT2023/TeamB/CD", "snippet": "", "titlesnippet": "", "sectiontitle": ""},
                ]}
            }))
            results = await client.search("team", filters={"year": "2024"})
        titles = [r.title for r in results]
        assert len(titles) == 1
        assert "2024" in titles[0]

    async def test_search_enriches_team_from_title(self, client):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "query": {"search": [{
                    "title": "24-25NDTCEDA/Harvard/KP",
                    "snippet": "", "titlesnippet": "", "sectiontitle": "",
                }]}
            }))
            results = await client.search("Harvard")
        assert results[0].team == "KP"
        assert results[0].school == "Harvard"


class TestDownload:
    async def test_download_success(self, credentialed_client, tmp_path):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n"))
            mock.get(f"{BASE}/files/test.docx").mock(
                return_value=httpx.Response(200, content=b"PK\x03\x04fake_docx_content")
            )
            dest = tmp_path / "test.docx"
            result = await credentialed_client.download_file(f"{BASE}/files/test.docx", dest)
        assert result["success"] is True
        assert dest.exists()
        assert result["size_bytes"] > 0

    async def test_download_creates_parent_dirs(self, credentialed_client, tmp_path):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n"))
            mock.get(f"{BASE}/files/test.docx").mock(
                return_value=httpx.Response(200, content=b"content")
            )
            dest = tmp_path / "subdir" / "test.docx"
            await credentialed_client.download_file(f"{BASE}/files/test.docx", dest)
        assert dest.exists()

    async def test_download_no_credentials_returns_error(self, client, tmp_path):
        # No network call is made — fails fast before touching the wire
        result = await client.download_file(f"{BASE}/files/test.docx", tmp_path / "test.docx")
        assert result["success"] is False
        assert "credentials" in result["error"].lower() or "password" in result["error"].lower()

    async def test_download_server_401_triggers_reauth(self, credentialed_client, tmp_path, monkeypatch):
        call_count = {"n": 0}

        def download_side_effect(request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(401)
            return httpx.Response(200, content=b"docx content here")

        login_called = {"n": 0}

        async def mock_login():
            login_called["n"] += 1
            return {"success": True}

        monkeypatch.setattr(credentialed_client, "login", mock_login)

        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n"))
            mock.get(f"{BASE}/files/test.docx").mock(side_effect=download_side_effect)
            dest = tmp_path / "test.docx"
            result = await credentialed_client.download_file(f"{BASE}/files/test.docx", dest)

        assert result["success"] is True
        assert login_called["n"] == 1   # re-auth was triggered once
        assert call_count["n"] == 2     # initial 401 + successful retry

    async def test_download_network_error(self, credentialed_client, tmp_path):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n"))
            mock.get(f"{BASE}/files/test.docx").mock(side_effect=Exception("Network error"))
            result = await credentialed_client.download_file(
                f"{BASE}/files/test.docx", tmp_path / "test.docx"
            )
        assert result["success"] is False
        assert "error" in result


class TestLogin:
    async def test_no_credentials_returns_error(self, client):
        result = await client.login()
        assert result["success"] is False
        assert "credentials" in result["error"].lower()

    async def test_no_credentials_makes_no_network_call(self, client):
        with respx.mock(assert_all_called=False):
            result = await client.login()
        assert result["success"] is False

    async def test_login_success_returns_true(self, monkeypatch, tmp_path):
        monkeypatch.setattr("wiki_client._SESSION_FILE", tmp_path / "session.json")
        monkeypatch.setenv("OPENCASELIST_USERNAME", "user")
        monkeypatch.setenv("OPENCASELIST_PASSWORD", "pass")
        c = OpenCaselistClient()
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "query": {"tokens": {"logintoken": "tok123"}}
            }))
            mock.post(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "login": {"result": "Success", "lgusername": "user"}
            }))
            result = await c.login()
        assert result["success"] is True

    async def test_login_success_saves_session_file(self, monkeypatch, tmp_path):
        session_path = tmp_path / "session.json"
        monkeypatch.setattr("wiki_client._SESSION_FILE", session_path)
        monkeypatch.setenv("OPENCASELIST_USERNAME", "user")
        monkeypatch.setenv("OPENCASELIST_PASSWORD", "pass")
        c = OpenCaselistClient()
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "query": {"tokens": {"logintoken": "tok123"}}
            }))
            mock.post(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "login": {"result": "Success", "lgusername": "user"}
            }))
            await c.login()
        assert session_path.exists()

    async def test_login_wrong_password_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setattr("wiki_client._SESSION_FILE", tmp_path / "session.json")
        monkeypatch.setenv("OPENCASELIST_USERNAME", "user")
        monkeypatch.setenv("OPENCASELIST_PASSWORD", "wrong")
        c = OpenCaselistClient()
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "query": {"tokens": {"logintoken": "tok123"}}
            }))
            mock.post(f"{BASE}/api.php").mock(return_value=httpx.Response(200, json={
                "login": {"result": "Failed", "reason": "Incorrect password"}
            }))
            result = await c.login()
        assert result["success"] is False
        assert "Incorrect password" in result["error"]

    async def test_login_token_fetch_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr("wiki_client._SESSION_FILE", tmp_path / "session.json")
        monkeypatch.setenv("OPENCASELIST_USERNAME", "user")
        monkeypatch.setenv("OPENCASELIST_PASSWORD", "pass")
        c = OpenCaselistClient()
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(side_effect=Exception("timeout"))
            result = await c.login()
        assert result["success"] is False
        assert "token" in result["error"].lower()


class TestHTTPSEnforcement:
    def test_http_base_url_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr("wiki_client._SESSION_FILE", tmp_path / "session.json")
        monkeypatch.setenv("OPENCASELIST_BASE_URL", "http://opencaselist.com")
        monkeypatch.setenv("OPENCASELIST_USERNAME", "")
        monkeypatch.setenv("OPENCASELIST_PASSWORD", "")
        with pytest.raises(ValueError, match="HTTPS"):
            OpenCaselistClient()

    def test_https_base_url_ok(self, monkeypatch, tmp_path):
        monkeypatch.setattr("wiki_client._SESSION_FILE", tmp_path / "session.json")
        monkeypatch.setenv("OPENCASELIST_BASE_URL", "https://opencaselist.com")
        monkeypatch.setenv("OPENCASELIST_USERNAME", "")
        monkeypatch.setenv("OPENCASELIST_PASSWORD", "")
        c = OpenCaselistClient()   # must not raise
        assert c._base_url == "https://opencaselist.com"


class TestRetry:
    async def test_500_is_retried(self, client):
        call_count = {"n": 0}

        def flaky(request):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return httpx.Response(500)
            return httpx.Response(200, json={"query": {"search": []}})

        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(side_effect=flaky)
            results = await client.search("anything")
        assert call_count["n"] == 3
        assert results == []

    async def test_retries_exhausted_raises(self, client):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(500))
            results = await client.search("anything")
        assert results[0].page_type == "error"

    async def test_connect_error_is_retried(self, client):
        call_count = {"n": 0}

        def flaky(request):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise httpx.ConnectError("connection refused")
            return httpx.Response(200, json={"query": {"search": []}})

        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(side_effect=flaky)
            results = await client.search("anything")
        assert call_count["n"] == 2
        assert results == []

    async def test_429_triggers_backoff(self, client):
        call_count = {"n": 0}

        def rate_limited(request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(429)
            return httpx.Response(200, json={"query": {"search": []}})

        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(side_effect=rate_limited)
            results = await client.search("anything")
        assert call_count["n"] == 2
        assert results == []


class TestRateLimiter:
    async def test_enforces_min_interval(self):
        limiter = _RateLimiter(min_interval=0.1)
        await limiter.acquire()
        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed >= 0.08  # allow small timer jitter

    async def test_no_delay_after_interval_passes(self):
        limiter = _RateLimiter(min_interval=0.05)
        await limiter.acquire()
        await asyncio.sleep(0.1)  # wait longer than min_interval
        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.05  # should not have slept


class TestRobotsTxt:
    async def test_disallowed_path_blocks_download(self, credentialed_client, tmp_path):
        robots = "User-agent: *\nDisallow: /files/\n"
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
            result = await credentialed_client.download_file(
                f"{BASE}/files/secret.docx", tmp_path / "out.docx"
            )
        assert result["success"] is False
        assert "robots" in result["error"].lower()

    async def test_allowed_path_proceeds(self, credentialed_client, tmp_path):
        robots = "User-agent: *\nAllow: /\n"
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
            mock.get(f"{BASE}/files/ok.docx").mock(
                return_value=httpx.Response(200, content=b"content")
            )
            result = await credentialed_client.download_file(
                f"{BASE}/files/ok.docx", tmp_path / "ok.docx"
            )
        assert result["success"] is True

    async def test_robots_fetch_failure_allows_all(self, credentialed_client, tmp_path):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(side_effect=Exception("timeout"))
            mock.get(f"{BASE}/files/ok.docx").mock(
                return_value=httpx.Response(200, content=b"content")
            )
            result = await credentialed_client.download_file(
                f"{BASE}/files/ok.docx", tmp_path / "ok.docx"
            )
        assert result["success"] is True

    async def test_disallowed_subpath(self, credentialed_client, tmp_path):
        robots = "User-agent: OpenCaselistMCP\nDisallow: /private/\n"
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
            result = await credentialed_client.download_file(
                f"{BASE}/private/file.docx", tmp_path / "out.docx"
            )
        assert result["success"] is False

    async def test_unlisted_path_is_allowed(self, credentialed_client, tmp_path):
        robots = "User-agent: *\nDisallow: /blocked/\n"
        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))
            mock.get(f"{BASE}/files/allowed.docx").mock(
                return_value=httpx.Response(200, content=b"content")
            )
            result = await credentialed_client.download_file(
                f"{BASE}/files/allowed.docx", tmp_path / "allowed.docx"
            )
        assert result["success"] is True


class TestApiGetReauth:
    async def test_401_triggers_login_exactly_once(self, credentialed_client, monkeypatch, tmp_path):
        call_count = {"n": 0}
        login_calls = {"n": 0}

        def api_side_effect(request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(401)
            return httpx.Response(200, json={"query": {"search": []}})

        async def mock_login():
            login_calls["n"] += 1
            (tmp_path / "session.json").write_text("{}")
            return {"success": True}

        monkeypatch.setattr(credentialed_client, "login", mock_login)

        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(side_effect=api_side_effect)
            results = await credentialed_client.search("anything")

        assert login_calls["n"] == 1  # login triggered exactly once
        assert call_count["n"] == 2   # initial 401 + successful retry
        assert results == []           # search succeeded with empty results

    async def test_401_retry_uses_refreshed_cookie(self, credentialed_client, monkeypatch, tmp_path):
        """Fix 1: after reauth, client.cookies.update(_load_session()) must send the new token."""
        call_count = {"n": 0}
        second_request_cookie = {"value": ""}

        def api_side_effect(request):
            call_count["n"] += 1
            if call_count["n"] == 2:
                second_request_cookie["value"] = request.headers.get("cookie", "")
            if call_count["n"] == 1:
                return httpx.Response(401)
            return httpx.Response(200, json={"query": {"search": []}})

        async def mock_login():
            # Simulate real login: write a new session cookie to the session file.
            # mock_login does NOT make any httpx requests, so Set-Cookie headers are
            # never processed — only the explicit client.cookies.update(_load_session())
            # call in Fix 1 can get this token into the in-flight jar.
            (tmp_path / "session.json").write_text('{"opencaselist_session": "fresh_token_xyz"}')
            return {"success": True}

        monkeypatch.setattr(credentialed_client, "login", mock_login)

        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(side_effect=api_side_effect)
            await credentialed_client.search("anything")

        assert "fresh_token_xyz" in second_request_cookie["value"]

    async def test_double_401_returns_error_result(self, credentialed_client, monkeypatch, tmp_path):
        """Both the initial request and the post-reauth retry return 401 — must not raise."""
        async def mock_login():
            (tmp_path / "session.json").write_text("{}")
            return {"success": True}

        monkeypatch.setattr(credentialed_client, "login", mock_login)

        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE}/api.php").mock(return_value=httpx.Response(401))
            results = await credentialed_client.search("anything")

        assert results[0].page_type == "error"
