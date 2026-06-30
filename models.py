"""Data models for the OpenCaselist MCP server."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


__all__ = [
    "CardType",
    "MatchType",
    "Side",
    "DebateCard",
    "ParsedDocument",
    "CardSearchResult",
]


class Side(str, Enum):
    AFF = "aff"
    NEG = "neg"
    UNKNOWN = "unknown"


class CardType(str, Enum):
    EVIDENCE = "evidence"
    ANALYTIC = "analytic"
    UNKNOWN = "unknown"


class MatchType(str, Enum):
    EXACT = "exact"
    TAG = "tag"
    CITE = "cite"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"


class DebateCard(BaseModel):
    id: str
    tag: str
    cite: str = ""
    card_text: str = ""
    full_text: str = ""  # tag + cite + card_text combined
    card_type: CardType = CardType.EVIDENCE

    # Document hierarchy (pocket > hat > block > card)
    pocket: str = ""
    hat: str = ""
    block: str = ""

    # Source
    source_file: str = ""
    source_file_path: str = ""
    source_url: Optional[str] = None
    wiki_url: Optional[str] = None

    # Debate metadata (filled in when known)
    team: str = ""
    school: str = ""
    tournament: str = ""
    round: str = ""
    side: Side = Side.UNKNOWN
    year: str = ""
    topic: str = ""

    paragraph_index: int = 0
    indexed_at: float = Field(default_factory=time.time)


class ParsedDocument(BaseModel):
    file_path: str
    file_name: str
    total_cards: int = 0
    total_analytics: int = 0
    headings: List[str] = []
    cards: List[DebateCard] = []
    analytics: List[Dict[str, Any]] = []
    is_verbatim_format: bool = False
    metadata: Dict[str, Any] = {}
    parse_errors: List[str] = []


class CardSearchResult(BaseModel):
    card_id: str
    card: DebateCard
    score: float
    match_type: MatchType
    snippet: str
    can_download: bool = False
    wiki_url: Optional[str] = None
    file_url: Optional[str] = None


class WikiSearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    page_type: str  # "team", "round", "tournament", "school", "file"
    team: str = ""
    school: str = ""
    tournament: str = ""
    year: str = ""
    side: Side = Side.UNKNOWN
    topic: str = ""
    file_urls: List[str] = []
    relevance_score: float = 0.0


class RoundMetadata(BaseModel):
    url: str
    title: str = ""
    tournament: str = ""
    year: str = ""
    round_number: str = ""
    aff_team: str = ""
    neg_team: str = ""
    judge: str = ""
    topic: str = ""
    result: str = ""
    disclosed_files: List[Dict[str, str]] = []


class TeamFilesResult(BaseModel):
    team_name: str
    school: str = ""
    wiki_url: str = ""
    topic: str = ""
    year: str = ""
    files: List[Dict[str, str]] = []
    rounds: List[Dict[str, str]] = []
