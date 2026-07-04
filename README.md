# OpenCaselist MCP

<p align="left">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-compatible-purple" alt="MCP"></a>
</p>


A [Model Context Protocol](https://modelcontextprotocol.io) server that turns Claude into a librarian for [OpenCaselist](https://opencaselist.com).

Ask questions like:
- *"Find me cards about deterrence causing escalation"*
- *"What files has [Team] XY disclosed this year?"*
- *"Find rounds where teams read a cap K link against AI affs"*
- *"Search my neg files for warming good cards"*
- *"Build me a packet of the best deterrence cards from my index"*

---

## Features

| Phase | What it does |
|-------|-------------|
| **1 — Local index** | Parse your own `.docx` files; full-text search over tags, cites, and card text |
| **2 — Wiki search** | Search OpenCaselist for teams, rounds, schools, and tournaments; browse disclosed file lists |
| **3 — Download** | Download specific files on request (requires login) |
| **4 — Packet builder** | Export selected cards to a Verbatim-compatible `.docx` |

Handles both **Verbatim-styled** documents (Pocket/Hat/Block/Tag/Cite styles) and **generic** debate docs (bold/underlined tags, italic cites).

---

## Quickstart

### 1. Install

**Requires Python 3.12+.** Use [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended) or plain pip.

```bash
git clone https://github.com/kushvijapure/opencaselist-mcp
cd opencaselist-mcp

# with uv (recommended)
uv sync

# or with pip — activate first, then install
python3.12 -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate.bat
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and fill in your credentials (only needed for file downloads):

```bash
cp .env.example .env
# edit .env
```

### 3. Add to Claude Desktop

Edit the Claude Desktop config file for your platform:

| Platform | Config file path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "opencaselist": {
      "command": "/absolute/path/to/opencaselist-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/opencaselist-mcp/server.py"],
      "env": {
        "OPENCASELIST_BASE_URL": "https://opencaselist.com",
        "OPENCASELIST_USERNAME": "your_username",
        "OPENCASELIST_PASSWORD": "your_password"
      }
    }
  }
}
```

> **uv users:** replace `command` with `"uv"` and set `"args"` to `["run", "/absolute/path/to/opencaselist-mcp/server.py"]`.

Restart Claude Desktop. The `opencaselist` tools will be available immediately.

### 4. Add to Claude Code

If you clone this repo and open it in Claude Code, the `.mcp.json` at the root is picked up automatically — just approve it when prompted and add your credentials.

---

## Tools

| Tool | Description |
|------|-------------|
| `parse_debate_docx` | Parse & index a local `.docx` into the card database |
| `search_cards` | Full-text search over indexed cards (BM25 + exact) |
| `search_opencaselist` | Search the OpenCaselist wiki for teams, rounds, schools |
| `get_round_metadata` | Get tournament/teams/judge/files for a round page |
| `get_team_files` | List all disclosed files for a team |
| `download_docx` | Download a specific file (explicit user request only) |
| `build_card_packet` | Export selected cards as a `.docx` packet |
| `open_result_location` | Get the wiki URL and source metadata for a card |

## Local storage

All data is stored in `~/.opencaselist-mcp/`:
- `index.db` — SQLite FTS5 card database (persists across sessions)
- `downloads/` — files you've downloaded
- `packets/` — generated evidence packets

---

## Ethics & constraints

- **No mass crawling.** Only fetches pages and files the user explicitly asks for.
- **Respects robots.txt.** File downloads are checked against `robots.txt` before proceeding; disallowed URLs are rejected with a clear error.
- **Rate limited.** A minimum 0.5-second delay is enforced between outgoing requests.
- **Login required** for file downloads — credentials are sent only to `opencaselist.com` over HTTPS. The server makes no third-party network calls and never logs credentials. See [`docs/AUTH.md`](docs/AUTH.md) for the full auth flow.
- If a file can't be downloaded automatically, the server returns the wiki URL for manual access.

---

## Development

```bash
# Install dev dependencies (uv)
uv sync --dev

# Install dev dependencies (pip — activate venv first)
pip install -r requirements-dev.txt

# Run server directly (uv)
uv run server.py

# Run server directly (venv)
.venv/bin/python server.py          # macOS/Linux
# .venv\Scripts\python server.py   # Windows

# Run tests (uv)
uv run pytest --tb=short -q

# Run tests (venv)
.venv/bin/pytest --tb=short -q --cov=. --cov-report=term-missing
```

CI runs on Python 3.12 and 3.13 via GitHub Actions (`.github/workflows/test.yml`).

---

## License

MIT
