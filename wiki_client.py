"""OpenCaselist MediaWiki API client.

OpenCaselist runs on MediaWiki. This client uses the standard MediaWiki
Action API (api.php) for search, page fetching, and file listing.

Authentication uses the MediaWiki cookie-based login flow:
  1. GET  /api.php?action=query&meta=tokens&type=login  → logintoken
  2. POST /api.php  action=login + credentials + token  → session cookie
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.robotparser
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse, quote

import httpx
from bs4 import BeautifulSoup

from models import RoundMetadata, Side, TeamFilesResult, WikiSearchResult

_SESSION_FILE = Path.home() / ".opencaselist-mcp" / "wiki_session.json"

_PAGE_TYPE_PATTERNS = {
    "team": re.compile(r"/wiki/[\w\-]+/[\w\-]+/[\w\-]+$"),
    "school": re.compile(r"/wiki/[\w\-]+/[\w\-]+$"),
    "tournament": re.compile(r"/wiki/Tournaments?"),
    "round": re.compile(r"/wiki/[\w\-]+/[\w\-]+/[\w\-]+/rounds", re.IGNORECASE),
}

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3


def _infer_page_type(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    depth = len(parts)
    if depth >= 4:
        return "round"
    if depth == 3:
        return "team"
    if depth == 2:
        return "school"
    if depth == 1:
        return "topic"
    return "unknown"


def _extract_year(text: str) -> str:
    m = re.search(r"\b(20\d{2})\b", text)
    return m.group(1) if m else ""


def _extract_side(text: str) -> Side:
    tl = text.lower()
    if "aff" in tl:
        return Side.AFF
    if "neg" in tl:
        return Side.NEG
    return Side.UNKNOWN


class _RateLimiter:
    def __init__(self, min_interval: float = 0.5):
        self._min_interval = min_interval
        self._last = 0.0

    async def acquire(self) -> None:
        loop = asyncio.get_event_loop()
        now = loop.time()
        gap = now - self._last
        if gap < self._min_interval:
            await asyncio.sleep(self._min_interval - gap)
        self._last = asyncio.get_event_loop().time()


class OpenCaselistClient:
    """
    Async HTTP client for the OpenCaselist MediaWiki API.

    Configure via environment variables:
        OPENCASELIST_BASE_URL  (default: https://opencaselist.com)
        OPENCASELIST_USERNAME
        OPENCASELIST_PASSWORD
    """

    def __init__(self):
        self._base_url = os.environ.get(
            "OPENCASELIST_BASE_URL", "https://opencaselist.com"
        ).rstrip("/")
        if not self._base_url.startswith("https://"):
            raise ValueError(
                f"OPENCASELIST_BASE_URL must use HTTPS (got {self._base_url!r}). "
                "Credentials are never sent over plain HTTP."
            )
        self._api_url = f"{self._base_url}/api.php"
        self._username = os.environ.get("OPENCASELIST_USERNAME", "")
        self._password = os.environ.get("OPENCASELIST_PASSWORD", "")
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = _RateLimiter()
        self._robots_parser: Optional[urllib.robotparser.RobotFileParser] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            cookies = self._load_session()
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                cookies=cookies,
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": (
                        "OpenCaselistMCP/1.0 (debate evidence assistant; "
                        "contact via GitHub)"
                    ),
                },
            )
        return self._client

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def _load_session(self) -> dict:
        if _SESSION_FILE.exists():
            try:
                return json.loads(_SESSION_FILE.read_text())
            except Exception:
                return {}
        return {}

    def _save_session(self, cookies: dict) -> None:
        _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_FILE.write_text(json.dumps(cookies))

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self) -> dict:
        """Log in to OpenCaselist using MediaWiki cookie auth."""
        if not self._username or not self._password:
            return {"success": False, "error": "No credentials configured. Set OPENCASELIST_USERNAME and OPENCASELIST_PASSWORD."}

        client = await self._get_client()

        # Step 1: get login token
        try:
            r = await client.get(
                self._api_url,
                params={"action": "query", "meta": "tokens", "type": "login", "format": "json"},
            )
            r.raise_for_status()
            login_token = r.json()["query"]["tokens"]["logintoken"]
        except Exception as e:
            return {"success": False, "error": f"Failed to get login token: {e}"}

        # Step 2: authenticate
        try:
            r = await client.post(
                self._api_url,
                data={
                    "action": "login",
                    "lgname": self._username,
                    "lgpassword": self._password,
                    "lgtoken": login_token,
                    "format": "json",
                },
            )
            r.raise_for_status()
            result = r.json()
            if result.get("login", {}).get("result") == "Success":
                self._save_session(dict(client.cookies))
                return {"success": True, "user": self._username}
            else:
                return {"success": False, "error": result.get("login", {}).get("reason", "Unknown error")}
        except Exception as e:
            return {"success": False, "error": f"Login failed: {e}"}

    async def _api_get(self, params: dict) -> Any:
        client = await self._get_client()
        params.setdefault("format", "json")
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            await self._rate_limiter.acquire()
            try:
                r = await client.get(self._api_url, params=params)
                if r.status_code == 401:
                    await self.login()
                    r = await client.get(self._api_url, params=params)
                if r.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return r.json()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
        raise last_exc or RuntimeError("Max retries exceeded")

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------

    async def _is_allowed(self, url: str) -> bool:
        """Check robots.txt. Returns True if the URL is allowed (or robots.txt is unreachable)."""
        if self._robots_parser is None:
            robots_url = f"{self._base_url}/robots.txt"
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            try:
                client = await self._get_client()
                r = await client.get(robots_url)
                if r.status_code == 200:
                    parser.parse(r.text.splitlines())
                else:
                    # Unreachable robots.txt → allow all
                    return True
            except Exception:
                return True
            self._robots_parser = parser
        ua = "OpenCaselistMCP"
        return self._robots_parser.can_fetch(ua, url)

    # ------------------------------------------------------------------
    # Wiki search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 20,
        filters: Dict[str, Any] = {},
    ) -> List[WikiSearchResult]:
        """
        Full-text search of OpenCaselist wiki pages.

        Returns pages (teams, rounds, tournaments, schools) matching the query.
        """
        try:
            data = await self._api_get({
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(limit, 50),
                "srnamespace": "0",
                "srprop": "snippet|titlesnippet|sectiontitle",
            })
        except Exception as e:
            return [WikiSearchResult(
                title="Error",
                url="",
                snippet=f"Search failed: {e}",
                page_type="error",
            )]

        results = []
        for item in data.get("query", {}).get("search", []):
            title = item["title"]
            snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))  # strip HTML
            page_url = f"{self._base_url}/wiki/{quote(title.replace(' ', '_'))}"

            result = WikiSearchResult(
                title=title,
                url=page_url,
                snippet=snippet,
                page_type=_infer_page_type(page_url),
                year=_extract_year(title),
            )

            # Apply query-time filter matching
            if filters:
                if filters.get("year") and filters["year"] not in title:
                    continue
                if filters.get("side"):
                    side_filter = filters["side"].lower()
                    if side_filter in ("aff", "neg") and side_filter not in title.lower():
                        continue

            # Enrich from title structure (e.g., "23-24NDTCEDA/Harvard/KP")
            parts = title.split("/")
            if len(parts) >= 3:
                result.team = parts[2]
                result.school = parts[1]
                result.topic = parts[0]
            elif len(parts) == 2:
                result.school = parts[1]
                result.topic = parts[0]

            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Page content
    # ------------------------------------------------------------------

    async def get_page_html(self, title_or_url: str) -> str:
        """Fetch rendered HTML for a wiki page."""
        title = self._title_from_url_or_title(title_or_url)
        try:
            data = await self._api_get({
                "action": "parse",
                "page": title,
                "prop": "text",
            })
            return data.get("parse", {}).get("text", {}).get("*", "")
        except Exception as e:
            return f"Error fetching page: {e}"

    async def get_page_wikitext(self, title_or_url: str) -> str:
        """Fetch raw wikitext for a wiki page."""
        title = self._title_from_url_or_title(title_or_url)
        try:
            data = await self._api_get({
                "action": "query",
                "titles": title,
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
            })
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                revs = page.get("revisions", [{}])
                if revs:
                    return revs[0].get("slots", {}).get("main", {}).get("*", "")
        except Exception as e:
            return f"Error: {e}"
        return ""

    # ------------------------------------------------------------------
    # Round metadata
    # ------------------------------------------------------------------

    async def get_round_metadata(self, url_or_title: str) -> RoundMetadata:
        """Parse a round/team page and extract round metadata + disclosed files."""
        html = await self.get_page_html(url_or_title)
        title = self._title_from_url_or_title(url_or_title)
        page_url = f"{self._base_url}/wiki/{quote(title.replace(' ', '_'))}"

        meta = RoundMetadata(url=page_url, title=title)
        parts = title.split("/")
        if parts:
            meta.topic = parts[0]
        if len(parts) >= 2:
            meta.school = parts[1]
        if len(parts) >= 3:
            meta.team = parts[2]

        if not html or html.startswith("Error"):
            meta.judge = html  # surface error
            return meta

        soup = BeautifulSoup(html, "html.parser")

        # Extract round table rows
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            header = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])] if rows else []
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if not cells:
                    continue
                round_info: Dict[str, str] = {}
                for i, h in enumerate(header):
                    if i < len(cells):
                        round_info[h] = cells[i]
                if round_info:
                    meta.disclosed_files.append(round_info)

        # Extract file links (.docx attachments)
        file_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".docx" in href.lower() or "File:" in href or "/Special:FilePath" in href:
                abs_url = urljoin(self._base_url, href)
                file_links.append({
                    "name": a.get_text(strip=True) or href.split("/")[-1],
                    "url": abs_url,
                })
        meta.disclosed_files = file_links

        # Extract year
        meta.year = _extract_year(title) or _extract_year(html[:500])

        return meta

    # ------------------------------------------------------------------
    # Team files
    # ------------------------------------------------------------------

    async def get_team_files(
        self,
        url_or_title: str,
        filters: Dict[str, Any] = {},
    ) -> TeamFilesResult:
        """List all disclosed files for a team page."""
        html = await self.get_page_html(url_or_title)
        title = self._title_from_url_or_title(url_or_title)
        page_url = f"{self._base_url}/wiki/{quote(title.replace(' ', '_'))}"

        parts = title.split("/")
        result = TeamFilesResult(
            team_name=parts[2] if len(parts) >= 3 else title,
            school=parts[1] if len(parts) >= 2 else "",
            wiki_url=page_url,
            topic=parts[0] if parts else "",
            year=_extract_year(title),
        )

        if not html or html.startswith("Error"):
            return result

        soup = BeautifulSoup(html, "html.parser")

        # File attachments
        for a in soup.find_all("a", href=True):
            href = a["href"]
            name = a.get_text(strip=True)
            if ".docx" in href.lower():
                abs_url = urljoin(self._base_url, href)
                file_info = {
                    "name": name or href.split("/")[-1],
                    "url": abs_url,
                    "type": "docx",
                }
                # Apply filters
                if filters.get("side"):
                    if filters["side"].lower() not in name.lower():
                        continue
                if filters.get("keyword"):
                    if filters["keyword"].lower() not in name.lower():
                        continue
                result.files.append(file_info)

        # Round links (subpages)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            name = a.get_text(strip=True)
            if f"/wiki/{parts[0]}" in href and href.count("/") > page_url.count("/"):
                abs_url = urljoin(self._base_url, href)
                result.rounds.append({"name": name, "url": abs_url})

        return result

    # ------------------------------------------------------------------
    # File download
    # ------------------------------------------------------------------

    async def get_file_download_url(self, file_title: str) -> Optional[str]:
        """Return the direct download URL for a wiki file attachment."""
        title = file_title if file_title.startswith("File:") else f"File:{file_title}"
        try:
            data = await self._api_get({
                "action": "query",
                "prop": "imageinfo",
                "titles": title,
                "iiprop": "url|size|mime",
            })
            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                info = page.get("imageinfo", [{}])
                if info:
                    return info[0].get("url")
        except Exception:
            pass
        return None

    async def download_file(self, url: str, dest_path: Path) -> Dict[str, Any]:
        """
        Download a single file from `url` to `dest_path`.

        Only call this when the user has explicitly requested the file.
        Requires OPENCASELIST_USERNAME and OPENCASELIST_PASSWORD to be set.
        Checks robots.txt before downloading. Re-authenticates once automatically
        if the server returns 401.
        """
        if not self._username or not self._password:
            return {
                "success": False,
                "error": (
                    "Credentials required for file downloads. "
                    "Set OPENCASELIST_USERNAME and OPENCASELIST_PASSWORD in .env."
                ),
                "url": url,
            }

        if not await self._is_allowed(url):
            return {
                "success": False,
                "error": f"robots.txt disallows fetching {url}",
                "url": url,
            }

        await self._rate_limiter.acquire()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        client = await self._get_client()
        try:
            result = await self._stream_download(client, url, dest_path)
            if result.get("_reauth"):
                login_result = await self.login()
                if not login_result.get("success"):
                    return {
                        "success": False,
                        "error": f"Session expired and re-login failed: {login_result.get('error', 'unknown')}",
                        "url": url,
                    }
                result = await self._stream_download(client, url, dest_path)
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "url": url}

    async def _stream_download(
        self, client: httpx.AsyncClient, url: str, dest_path: Path
    ) -> Dict[str, Any]:
        async with client.stream("GET", url) as r:
            if r.status_code == 401:
                return {"_reauth": True}
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            with open(dest_path, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
        size = dest_path.stat().st_size
        return {
            "success": True,
            "path": str(dest_path),
            "size_bytes": size,
            "content_type": content_type,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _title_from_url_or_title(self, s: str) -> str:
        """Extract wiki page title from a full URL or return as-is."""
        if s.startswith("http"):
            path = urlparse(s).path
            # /wiki/Title -> Title
            match = re.match(r"/wiki/(.+)", path)
            if match:
                from urllib.parse import unquote
                return unquote(match.group(1)).replace("_", " ")
        return s

    def page_url(self, title: str) -> str:
        return f"{self._base_url}/wiki/{quote(title.replace(' ', '_'))}"

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
