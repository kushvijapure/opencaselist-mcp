"""OpenCaselist MCP Server

Exposes 8 tools for locating, parsing, and searching debate evidence on OpenCaselist.

Phase 1  (local):    parse_debate_docx, search_cards
Phase 2  (wiki):     search_opencaselist, get_round_metadata, get_team_files, open_result_location
Phase 3  (download): download_docx
Phase 4  (output):   build_card_packet

Run:
    .venv/bin/python server.py
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from docx_parser import parse_debate_docx
from local_index import LocalCardIndex
from models import DebateCard
from packet_builder import build_card_packet
from wiki_client import OpenCaselistClient

load_dotenv()

_DOWNLOADS_DIR = Path.home() / ".opencaselist-mcp" / "downloads"

app = Server("opencaselist")
_wiki = OpenCaselistClient()
_index = LocalCardIndex()


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="parse_debate_docx",
            description=(
                "Parse a local Verbatim-style or generic debate .docx file into structured "
                "objects: cards (tag + cite + card text), analytics, pockets, hats, blocks, "
                "and headings. Automatically indexes the cards for search_cards. "
                "Use this first on any file the user has downloaded or exported."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the .docx file.",
                    },
                    "metadata": {
                        "type": "object",
                        "description": (
                            "Optional metadata to attach to all cards from this file: "
                            "team, school, tournament, round, side (aff/neg), year, topic, "
                            "source_url (file download URL), wiki_url (wiki page URL)."
                        ),
                    },
                },
                "required": ["file_path"],
            },
        ),
        types.Tool(
            name="search_cards",
            description=(
                "Search all locally indexed debate cards (from files you have parsed). "
                "Supports keyword search, exact phrase search, tag-only search, and cite-only search. "
                "Returns matching cards with tag, cite, snippet, source file, team, tournament, "
                "side, year, wiki URL, and relevance score."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query: phrase, keyword, author name, argument claim, etc.",
                    },
                    "search_field": {
                        "type": "string",
                        "enum": ["all", "tag", "cite", "card_text"],
                        "description": "Which field to search. Default: all.",
                        "default": "all",
                    },
                    "exact": {
                        "type": "boolean",
                        "description": "If true, requires exact substring match instead of keyword ranking.",
                        "default": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 20, max 50).",
                        "default": 20,
                    },
                    "filters": {
                        "type": "object",
                        "description": (
                            "Optional metadata filters: team, school, tournament, side, "
                            "year, topic, source_file, card_type."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="search_opencaselist",
            description=(
                "Search OpenCaselist wiki for teams, rounds, tournaments, schools, topics, "
                "arguments, or disclosed files. Returns wiki page links and metadata. "
                "Does NOT download files — use get_team_files then download_docx for that. "
                "Phase 2: requires the wiki to be reachable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "What to search for: team name, school, argument type, "
                            "evidence phrase, tournament name, etc."
                        ),
                    },
                    "filters": {
                        "type": "object",
                        "description": (
                            "Optional: year (e.g. '2024'), side ('aff'/'neg'), "
                            "topic (topic slug), school, team."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20).",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_round_metadata",
            description=(
                "Fetch metadata for a specific round or team page on OpenCaselist: "
                "tournament, year, teams, sides, judge, disclosed files and their download links. "
                "Pass the full wiki page URL or page title."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url_or_title": {
                        "type": "string",
                        "description": "Full wiki URL or page title (e.g. '24-25NationalCircuit/Harvard/AB').",
                    },
                },
                "required": ["url_or_title"],
            },
        ),
        types.Tool(
            name="get_team_files",
            description=(
                "List all disclosed files (and round links) for a team page on OpenCaselist. "
                "Returns file names, download URLs, and round information. "
                "Pass the team wiki page URL or title."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url_or_title": {
                        "type": "string",
                        "description": "Team wiki page URL or title.",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional: side ('aff'/'neg'), keyword (filename substring).",
                    },
                },
                "required": ["url_or_title"],
            },
        ),
        types.Tool(
            name="download_docx",
            description=(
                "Download a specific .docx file from OpenCaselist to local storage. "
                "Only call this when the user has explicitly requested the file. "
                "After downloading, call parse_debate_docx on the returned file_path to index it. "
                "Requires the user to be logged in (set OPENCASELIST_USERNAME and OPENCASELIST_PASSWORD). "
                "Phase 3."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_url": {
                        "type": "string",
                        "description": "Direct download URL for the .docx file (from get_team_files or get_round_metadata).",
                    },
                    "file_name": {
                        "type": "string",
                        "description": "Optional filename to save as. Defaults to the URL filename.",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata: team, school, tournament, round, side, year, topic, wiki_url.",
                    },
                },
                "required": ["file_url"],
            },
        ),
        types.Tool(
            name="build_card_packet",
            description=(
                "Create a new .docx file containing selected cards from the local index. "
                "Groups cards by pocket/block/source and preserves Verbatim-compatible formatting. "
                "Returns the path to the generated .docx. Phase 4."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "card_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of card IDs to include (from search_cards results).",
                    },
                    "title": {
                        "type": "string",
                        "description": "Packet title for the cover page.",
                        "default": "Evidence Packet",
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["pocket", "block", "source_file", "none"],
                        "description": "How to group cards in the output. Default: pocket.",
                        "default": "pocket",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional absolute path for the output .docx. Auto-generated if omitted.",
                    },
                    "include_source_metadata": {
                        "type": "boolean",
                        "description": "Add a source line after each card. Default: true.",
                        "default": True,
                    },
                },
                "required": ["card_ids"],
            },
        ),
        types.Tool(
            name="open_result_location",
            description=(
                "Return the wiki URL, file download URL, team page, and location metadata "
                "for a card or search result. Use this to point the user to the exact source "
                "on OpenCaselist for manual access."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "card_id": {
                        "type": "string",
                        "description": "Card ID from search_cards results.",
                    },
                },
                "required": ["card_id"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "parse_debate_docx":
            result = await _tool_parse_docx(arguments)
        elif name == "search_cards":
            result = await _tool_search_cards(arguments)
        elif name == "search_opencaselist":
            result = await _tool_search_wiki(arguments)
        elif name == "get_round_metadata":
            result = await _tool_round_metadata(arguments)
        elif name == "get_team_files":
            result = await _tool_team_files(arguments)
        elif name == "download_docx":
            result = await _tool_download_docx(arguments)
        elif name == "build_card_packet":
            result = await _tool_build_packet(arguments)
        elif name == "open_result_location":
            result = await _tool_open_location(arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def _tool_parse_docx(args: dict) -> Any:
    file_path = args["file_path"]
    metadata = args.get("metadata", {})

    parsed = parse_debate_docx(file_path)

    if parsed.parse_errors and not parsed.cards:
        return {
            "success": False,
            "errors": parsed.parse_errors,
            "file": file_path,
        }

    count = _index.index_document(parsed, metadata_override=metadata)

    return {
        "success": True,
        "file": parsed.file_name,
        "is_verbatim_format": parsed.is_verbatim_format,
        "cards_indexed": count,
        "total_analytics": parsed.total_analytics,
        "headings": parsed.headings[:20],
        "parse_errors": parsed.parse_errors[:5],
        "sample_cards": [
            {
                "id": c.id,
                "tag": c.tag[:100],
                "cite": c.cite[:120],
                "pocket": c.pocket,
                "block": c.block,
            }
            for c in parsed.cards[:5]
        ],
        "note": (
            f"Indexed {count} cards from '{parsed.file_name}'. "
            "Use search_cards to find specific arguments."
        ),
    }


async def _tool_search_cards(args: dict) -> Any:
    query = args["query"]
    search_field = args.get("search_field", "all")
    exact = args.get("exact", False)
    limit = min(int(args.get("limit", 20)), 50)
    filters = args.get("filters", {})

    results = _index.search(
        query=query,
        limit=limit,
        search_fields=search_field,
        filters=filters,
        exact=exact,
    )

    total = _index.total_card_count()

    return {
        "query": query,
        "total_indexed_cards": total,
        "results_found": len(results),
        "results": [
            {
                "card_id": r.card_id,
                "tag": r.card.tag[:150],
                "cite": r.card.cite[:150],
                "snippet": r.snippet[:300],
                "match_type": r.match_type,
                "score": round(r.score, 4),
                "pocket": r.card.pocket,
                "block": r.card.block,
                "team": r.card.team,
                "school": r.card.school,
                "tournament": r.card.tournament,
                "round": r.card.round,
                "side": r.card.side,
                "year": r.card.year,
                "topic": r.card.topic,
                "source_file": r.card.source_file,
                "wiki_url": r.card.wiki_url,
                "file_url": r.card.source_url,
                "can_download": r.can_download,
            }
            for r in results
        ],
        "indexed_files": _index.list_indexed_files(),
    }


async def _tool_search_wiki(args: dict) -> Any:
    query = args["query"]
    filters = args.get("filters", {})
    limit = int(args.get("limit", 20))

    results = await _wiki.search(query=query, limit=limit, filters=filters)

    return {
        "query": query,
        "results_found": len(results),
        "results": [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet[:300],
                "page_type": r.page_type,
                "team": r.team,
                "school": r.school,
                "tournament": r.tournament,
                "year": r.year,
                "topic": r.topic,
                "file_urls": r.file_urls,
            }
            for r in results
        ],
        "note": (
            "Use get_team_files(url) to see disclosed files for a team page, "
            "or get_round_metadata(url) for a specific round."
        ),
    }


async def _tool_round_metadata(args: dict) -> Any:
    url_or_title = args.get("url_or_title", "").strip()
    if not url_or_title:
        return {"error": "url_or_title is required and must not be empty."}
    meta = await _wiki.get_round_metadata(url_or_title)
    return {
        "title": meta.title,
        "url": meta.url,
        "tournament": meta.tournament,
        "year": meta.year,
        "round": meta.round_number,
        "aff_team": meta.aff_team,
        "neg_team": meta.neg_team,
        "judge": meta.judge,
        "topic": meta.topic,
        "result": meta.result,
        "disclosed_files": meta.disclosed_files,
        "note": "Use download_docx(file_url) to download a specific file from this round.",
    }


async def _tool_team_files(args: dict) -> Any:
    url_or_title = args.get("url_or_title", "").strip()
    if not url_or_title:
        return {"error": "url_or_title is required and must not be empty."}
    filters = args.get("filters", {})
    result = await _wiki.get_team_files(url_or_title, filters=filters)
    return {
        "team": result.team_name,
        "school": result.school,
        "wiki_url": result.wiki_url,
        "topic": result.topic,
        "year": result.year,
        "files": result.files,
        "rounds": result.rounds[:20],
        "file_count": len(result.files),
        "note": (
            "Use download_docx(file_url) to download a file, then parse_debate_docx to index it."
        ),
    }


async def _tool_download_docx(args: dict) -> Any:
    file_url = args["file_url"]
    if not file_url.startswith("https://"):
        return {
            "success": False,
            "error": (
                f"file_url must use HTTPS (got {file_url!r}). "
                "Credentials are never sent over plain HTTP."
            ),
            "url": file_url,
        }
    file_name = args.get("file_name") or file_url.split("/")[-1].split("?")[0]
    metadata = args.get("metadata", {})

    if not file_name.lower().endswith(".docx"):
        file_name += ".docx"

    _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _DOWNLOADS_DIR / file_name

    result = await _wiki.download_file(file_url, dest)

    if result.get("success"):
        result["next_step"] = (
            f"Call parse_debate_docx(file_path='{dest}', metadata={json.dumps(metadata)}) "
            "to index the cards from this file."
        )
        result["metadata_to_pass"] = metadata

    return result


async def _tool_build_packet(args: dict) -> Any:
    card_ids = args["card_ids"]
    title = args.get("title", "Evidence Packet")
    group_by = args.get("group_by", "pocket")
    include_source = args.get("include_source_metadata", True)
    output_path_str = args.get("output_path")

    if not card_ids:
        return {"success": False, "error": "No card_ids provided."}

    # Fetch cards from the index
    cards = []
    missing = []
    for cid in card_ids:
        card = _index.get_card(cid)
        if card:
            cards.append(card)
        else:
            missing.append(cid)

    if not cards:
        return {
            "success": False,
            "error": "None of the provided card IDs were found in the local index.",
            "missing_ids": missing,
        }

    output_path = Path(output_path_str) if output_path_str else None
    result = build_card_packet(
        cards=cards,
        output_path=output_path,
        group_by=group_by,
        include_source_metadata=include_source,
        title=title,
    )

    if missing:
        result["missing_card_ids"] = missing

    return result


async def _tool_open_location(args: dict) -> Any:
    card_id = args["card_id"]
    card = _index.get_card(card_id)

    if not card:
        return {
            "found": False,
            "card_id": card_id,
            "error": "Card not found in local index. Has it been indexed with parse_debate_docx?",
        }

    return {
        "found": True,
        "card_id": card_id,
        "tag": card.tag[:150],
        "cite": card.cite[:150],
        "source_file": card.source_file,
        "source_file_path": card.source_file_path,
        "file_download_url": card.source_url,
        "wiki_url": card.wiki_url,
        "team": card.team,
        "school": card.school,
        "tournament": card.tournament,
        "round": card.round,
        "side": card.side,
        "year": card.year,
        "topic": card.topic,
        "pocket": card.pocket,
        "hat": card.hat,
        "block": card.block,
        "paragraph_index": card.paragraph_index,
        "can_download": bool(card.source_url),
        "instructions": (
            f"This card is from '{card.source_file}'. "
            + (f"View on wiki: {card.wiki_url}" if card.wiki_url else "")
            + (f" | Download: {card.source_url}" if card.source_url else "")
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream, write_stream, app.create_initialization_options()
        )


def main_sync():
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
