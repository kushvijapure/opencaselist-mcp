# OpenCaselist MCP

Debate evidence and card search assistant for [OpenCaselist](https://opencaselist.com).

## What this does

This MCP server lets you search, browse, parse, and compile debate evidence from OpenCaselist. It exposes 8 tools covering four phases:

| Phase | Tools | Status |
|-------|-------|--------|
| 1 — Local | `parse_debate_docx`, `search_cards` | No login needed |
| 2 — Wiki | `search_opencaselist`, `get_round_metadata`, `get_team_files`, `open_result_location` | Public wiki pages |
| 3 — Download | `download_docx` | Requires login |
| 4 — Output | `build_card_packet` | Uses local index |

## Tool reference

### `parse_debate_docx(file_path, metadata?)`
Parse a local `.docx` file — Verbatim-styled or generic — into structured cards (tag + cite + card text). Automatically indexes them for `search_cards`. Pass `metadata` to attach team/tournament/side info to every card in the file.

### `search_cards(query, search_field?, exact?, limit?, filters?)`
Full-text BM25 search over all locally indexed cards. `search_field` can be `"all"`, `"tag"`, `"cite"`, or `"card_text"`. Set `exact: true` for substring match. Filter by `team`, `school`, `tournament`, `side`, `year`, `topic`.

### `search_opencaselist(query, filters?, limit?)`
Search the OpenCaselist wiki for teams, rounds, schools, and tournaments. Returns wiki page URLs and metadata — **does not download files**. Follow up with `get_team_files` to list a team's disclosed documents.

### `get_round_metadata(url_or_title)`
Fetch tournament, teams, sides, judge, year, and disclosed file links for a round or team page.

### `get_team_files(url_or_title, filters?)`
List all disclosed `.docx` files for a team. Filter by `side` (`"aff"` / `"neg"`) or `keyword` (filename match).

### `download_docx(file_url, file_name?, metadata?)`
Download a single `.docx` from OpenCaselist to `~/.opencaselist-mcp/downloads/`. Always follow with `parse_debate_docx` to index the cards. Requires `OPENCASELIST_USERNAME` / `OPENCASELIST_PASSWORD` in env.

### `build_card_packet(card_ids, title?, group_by?, output_path?, include_source_metadata?)`
Export selected cards (by ID from `search_cards`) to a new `.docx` with Verbatim-compatible formatting. `group_by` can be `"pocket"`, `"block"`, `"source_file"`, or `"none"`.

### `open_result_location(card_id)`
Return the wiki URL, download URL, team/tournament metadata, and file location for a card.

## Typical workflows

**Index a file you already have:**
```
parse_debate_docx("/path/to/my/neg.docx", {"team": "Harvard KP", "side": "neg", "year": "2024"})
search_cards("nuclear deterrence escalation")
```

**Find a team's files on OpenCaselist:**
```
search_opencaselist("Harvard", {"year": "2024"})
get_team_files("24-25NationalCircuit/Harvard/KP")
download_docx("<url from above>", metadata={"team": "Harvard KP", "side": "neg"})
parse_debate_docx("~/.opencaselist-mcp/downloads/HarvardKP.neg.docx")
```

**Build a card packet from search results:**
```
search_cards("warming good")
build_card_packet(["card_abc123", "card_def456"], title="Warming Good 2NR", group_by="pocket")
```

## Important constraints

- Do **not** bulk-download or crawl the wiki. Download only files the user explicitly requests.
- Respect robots.txt and OpenCaselist community norms.
- If a file requires login and no credentials are configured, return the wiki URL and tell the user to download manually.

## Environment variables

Copy `.env.example` → `.env` and fill in your credentials.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENCASELIST_BASE_URL` | `https://opencaselist.com` | Wiki base URL |
| `OPENCASELIST_USERNAME` | — | Login (Phase 3 only) |
| `OPENCASELIST_PASSWORD` | — | Login (Phase 3 only) |

## Local storage

All user data is kept in `~/.opencaselist-mcp/`:
- `index.db` — SQLite FTS5 card index
- `downloads/` — downloaded `.docx` files
- `packets/` — generated card packets
- `wiki_session.json` — login session cookie (auto-managed)
