# OpenCaselist MCP

A [Model Context Protocol](https://modelcontextprotocol.io) server that turns Claude into a debate evidence librarian for [OpenCaselist](https://opencaselist.com).

Ask questions like:
- *"Find me cards about nuclear deterrence causing escalation"*
- *"What files has Harvard KP disclosed this year?"*
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

**Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).**

```bash
git clone https://github.com/YOUR_USERNAME/opencaselist-mcp
cd opencaselist-mcp
uv sync
```

### 2. Configure

Copy `.env.example` to `.env` and fill in your credentials (only needed for file downloads):

```bash
cp .env.example .env
# edit .env
```

### 3. Add to Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "opencaselist": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/opencaselist-mcp/server.py"],
      "env": {
        "OPENCASELIST_BASE_URL": "https://opencaselist.com",
        "OPENCASELIST_USERNAME": "your_username",
        "OPENCASELIST_PASSWORD": "your_password"
      }
    }
  }
}
```

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

## Skills (Claude Code only)

| Skill | Invoke | Description |
|-------|--------|-------------|
| Search evidence | `/search-evidence` | Search indexed cards with filters |
| Parse file | `/parse-file` | Index a local `.docx` file |
| Find team | `/find-team` | Browse a team's OpenCaselist page |
| Build packet | `/build-packet` | Compile cards into a `.docx` packet |

---

## Local storage

All data is stored in `~/.opencaselist-mcp/`:
- `index.db` — SQLite FTS5 card database (persists across sessions)
- `downloads/` — files you've downloaded
- `packets/` — generated evidence packets

---

## Ethics & constraints

- **No mass crawling.** Only fetches pages and files the user explicitly asks for.
- **Respects robots.txt** and OpenCaselist community norms.
- **Login required** for file downloads — credentials never leave your machine.
- If a file can't be downloaded automatically, the server returns the wiki URL for manual access.

---

## Development

```bash
uv sync
uv run server.py          # test the server directly
uv run python -c "from docx_parser import parse_debate_docx; ..."
```

---

## License

MIT
