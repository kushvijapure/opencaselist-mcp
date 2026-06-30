# Authentication

## How it works today

Authentication to OpenCaselist is **session-cookie based**, using the standard MediaWiki API login flow. Credentials are never resent on every request — they are exchanged once for a session cookie that is then reused.

### Login flow (two-step MediaWiki API)

1. `GET /api.php?action=query&meta=tokens&type=login` → receive a `logintoken`
2. `POST /api.php` with `lgname`, `lgpassword`, `lgtoken` → receive session cookies on success
3. Cookies are saved to `~/.opencaselist-mcp/wiki_session.json` and reloaded on next server start

### Session reuse

On startup, the client loads any existing session cookies from disk. If the file exists and the cookies are still valid, no login is needed. Cookies are sent with every subsequent request via httpx's cookie jar.

### Re-authentication on 401

If any API call or file download receives an HTTP 401 response, the client automatically calls `login()` once and retries the original request. If re-login fails, the error is returned to the caller without further retries.

### Session expiry

MediaWiki sessions typically expire after a period of inactivity (site-dependent; commonly 30 days). There is no proactive expiry detection — re-auth is triggered reactively on 401 responses.

---

## HTTPS enforcement

`OPENCASELIST_BASE_URL` **must** start with `https://`. The client raises `ValueError` at startup if an `http://` URL is configured. Credentials are never sent over plain HTTP.

---

## Credential scope and storage

- Credentials are **only required** for `download_docx` (Phase 3 tool). Wiki search and browsing work without login.
- If `OPENCASELIST_USERNAME` / `OPENCASELIST_PASSWORD` are not set when a download is attempted, the server returns a clear error immediately — no partial request is made.
- Credentials are sent **only** to `OPENCASELIST_BASE_URL` (default: `https://opencaselist.com`) over HTTPS, during the login step only. They are never forwarded to third parties and never logged.
- `~/.opencaselist-mcp/wiki_session.json` stores session **cookies** (tokens issued by the server after login), not the raw password.
- Your `.env` file stores the raw credentials locally on your machine. It is listed in `.gitignore` and never read by the server at any path other than the local filesystem.

---

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENCASELIST_BASE_URL` | No | `https://opencaselist.com` | Wiki base URL. Must be HTTPS. |
| `OPENCASELIST_USERNAME` | Phase 3 only | — | OpenCaselist account username |
| `OPENCASELIST_PASSWORD` | Phase 3 only | — | OpenCaselist account password |

---

## Known gaps

- No proactive session health check — an expired session is only detected on first 401 response.
- No token refresh for long-lived server processes; if the cookie expires mid-session, the next API call will get a 401 and trigger re-auth.
