"""SQLite-backed local card index with full-text search (FTS5).

The index persists parsed cards to ~/.opencaselist-mcp/index.db.
Supports exact phrase, keyword (FTS5 BM25), tag, and cite search.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import CardSearchResult, CardType, DebateCard, MatchType, ParsedDocument, Side

_DEFAULT_DB_PATH = Path.home() / ".opencaselist-mcp" / "index.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id          TEXT PRIMARY KEY,
    tag         TEXT NOT NULL DEFAULT '',
    cite        TEXT NOT NULL DEFAULT '',
    card_text   TEXT NOT NULL DEFAULT '',
    full_text   TEXT NOT NULL DEFAULT '',
    card_type   TEXT NOT NULL DEFAULT 'evidence',
    pocket      TEXT NOT NULL DEFAULT '',
    hat         TEXT NOT NULL DEFAULT '',
    block       TEXT NOT NULL DEFAULT '',
    source_file TEXT NOT NULL DEFAULT '',
    source_file_path TEXT NOT NULL DEFAULT '',
    source_url  TEXT,
    wiki_url    TEXT,
    team        TEXT NOT NULL DEFAULT '',
    school      TEXT NOT NULL DEFAULT '',
    tournament  TEXT NOT NULL DEFAULT '',
    round       TEXT NOT NULL DEFAULT '',
    side        TEXT NOT NULL DEFAULT 'unknown',
    year        TEXT NOT NULL DEFAULT '',
    topic       TEXT NOT NULL DEFAULT '',
    paragraph_index INTEGER NOT NULL DEFAULT 0,
    indexed_at  REAL NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
    id       UNINDEXED,
    tag,
    cite,
    card_text,
    full_text,
    content  = 'cards',
    content_rowid = 'rowid'
);

CREATE TRIGGER IF NOT EXISTS cards_ai AFTER INSERT ON cards BEGIN
    INSERT INTO cards_fts(rowid, id, tag, cite, card_text, full_text)
    VALUES (new.rowid, new.id, new.tag, new.cite, new.card_text, new.full_text);
END;

CREATE TRIGGER IF NOT EXISTS cards_ad AFTER DELETE ON cards BEGIN
    INSERT INTO cards_fts(cards_fts, rowid, id, tag, cite, card_text, full_text)
    VALUES ('delete', old.rowid, old.id, old.tag, old.cite, old.card_text, old.full_text);
END;

CREATE TRIGGER IF NOT EXISTS cards_au AFTER UPDATE ON cards BEGIN
    INSERT INTO cards_fts(cards_fts, rowid, id, tag, cite, card_text, full_text)
    VALUES ('delete', old.rowid, old.id, old.tag, old.cite, old.card_text, old.full_text);
    INSERT INTO cards_fts(rowid, id, tag, cite, card_text, full_text)
    VALUES (new.rowid, new.id, new.tag, new.cite, new.card_text, new.full_text);
END;

CREATE TABLE IF NOT EXISTS indexed_files (
    file_path   TEXT PRIMARY KEY,
    file_name   TEXT NOT NULL,
    card_count  INTEGER NOT NULL DEFAULT 0,
    indexed_at  REAL NOT NULL DEFAULT 0,
    metadata    TEXT NOT NULL DEFAULT '{}'
);
"""


def _row_to_card(row: sqlite3.Row) -> DebateCard:
    return DebateCard(
        id=row["id"],
        tag=row["tag"],
        cite=row["cite"],
        card_text=row["card_text"],
        full_text=row["full_text"],
        card_type=CardType(row["card_type"]),
        pocket=row["pocket"],
        hat=row["hat"],
        block=row["block"],
        source_file=row["source_file"],
        source_file_path=row["source_file_path"],
        source_url=row["source_url"],
        wiki_url=row["wiki_url"],
        team=row["team"],
        school=row["school"],
        tournament=row["tournament"],
        round=row["round"],
        side=Side(row["side"]),
        year=row["year"],
        topic=row["topic"],
        paragraph_index=row["paragraph_index"],
        indexed_at=row["indexed_at"],
    )


def _snippet_around(text: str, query: str, window: int = 200) -> str:
    """Return a snippet of `text` centered on the first occurrence of `query`."""
    q = query.lower()
    t = text.lower()
    pos = t.find(q)
    if pos == -1:
        return text[:window].strip()
    start = max(0, pos - window // 2)
    end = min(len(text), pos + len(query) + window // 2)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


class LocalCardIndex:
    """
    Persistent card index backed by SQLite.

    Usage:
        idx = LocalCardIndex()
        idx.index_document(parsed_doc)
        results = idx.search("nuclear deterrence", limit=20)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_document(self, doc: ParsedDocument, metadata_override: Dict[str, Any] = {}) -> int:
        """
        Index all cards from a ParsedDocument.

        metadata_override can supply team, school, tournament, round, side,
        year, topic, source_url, wiki_url for all cards in this document.
        """
        with self._conn:
            # Remove old cards for this file
            self._conn.execute(
                "DELETE FROM cards WHERE source_file_path = ?", (doc.file_path,)
            )

            count = 0
            for card in doc.cards:
                # Apply any metadata overrides
                card_data = card.model_dump()
                for key in ("team", "school", "tournament", "round", "side", "year",
                            "topic", "source_url", "wiki_url"):
                    if key in metadata_override and metadata_override[key]:
                        card_data[key] = metadata_override[key]

                self._conn.execute(
                    """INSERT OR REPLACE INTO cards
                       (id, tag, cite, card_text, full_text, card_type, pocket, hat, block,
                        source_file, source_file_path, source_url, wiki_url,
                        team, school, tournament, round, side, year, topic,
                        paragraph_index, indexed_at)
                       VALUES
                       (:id, :tag, :cite, :card_text, :full_text, :card_type, :pocket, :hat, :block,
                        :source_file, :source_file_path, :source_url, :wiki_url,
                        :team, :school, :tournament, :round, :side, :year, :topic,
                        :paragraph_index, :indexed_at)""",
                    card_data,
                )
                count += 1

            # Record the indexed file
            import time
            self._conn.execute(
                """INSERT OR REPLACE INTO indexed_files (file_path, file_name, card_count, indexed_at, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc.file_path, doc.file_name, count, time.time(), json.dumps(metadata_override)),
            )

        return count

    def remove_document(self, file_path: str) -> int:
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM cards WHERE source_file_path = ?", (file_path,)
            )
            self._conn.execute(
                "DELETE FROM indexed_files WHERE file_path = ?", (file_path,)
            )
        return cur.rowcount

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_card(self, card_id: str) -> Optional[DebateCard]:
        row = self._conn.execute(
            "SELECT * FROM cards WHERE id = ?", (card_id,)
        ).fetchone()
        return _row_to_card(row) if row else None

    def list_indexed_files(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT file_path, file_name, card_count, indexed_at, metadata FROM indexed_files ORDER BY indexed_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def total_card_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM cards").fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 20,
        search_fields: str = "all",  # "tag", "cite", "card_text", "all"
        filters: Dict[str, Any] = {},
        exact: bool = False,
    ) -> List[CardSearchResult]:
        """
        Search indexed cards.

        If `exact=True`, performs case-insensitive substring match.
        Otherwise, uses SQLite FTS5 with BM25 ranking.
        """
        if exact:
            return self._exact_search(query, limit, search_fields, filters)
        return self._fts_search(query, limit, search_fields, filters)

    def _fts_search(
        self,
        query: str,
        limit: int,
        search_fields: str,
        filters: Dict[str, Any],
    ) -> List[CardSearchResult]:
        # Build FTS5 column filter
        if search_fields == "tag":
            fts_query = f"tag:{self._fts_escape(query)}"
        elif search_fields == "cite":
            fts_query = f"cite:{self._fts_escape(query)}"
        elif search_fields == "card_text":
            fts_query = f"card_text:{self._fts_escape(query)}"
        else:
            fts_query = self._fts_escape(query)

        where_clauses, params = self._build_filter_clauses(filters)
        filter_sql = f"AND {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
            SELECT c.*, bm25(cards_fts) AS score
            FROM cards c
            JOIN cards_fts ON cards_fts.id = c.id
            WHERE cards_fts MATCH ?
            {filter_sql}
            ORDER BY score
            LIMIT ?
        """
        try:
            rows = self._conn.execute(sql, [fts_query] + params + [limit]).fetchall()
        except sqlite3.OperationalError:
            # FTS query syntax error — fall back to exact search
            return self._exact_search(query, limit, search_fields, filters)

        results = []
        for row in rows:
            card = _row_to_card(row)
            match_type = MatchType.TAG if search_fields == "tag" else (
                MatchType.CITE if search_fields == "cite" else MatchType.KEYWORD
            )
            snippet = _snippet_around(card.full_text, query)
            results.append(CardSearchResult(
                card_id=card.id,
                card=card,
                score=abs(float(row["score"])),
                match_type=match_type,
                snippet=snippet,
                wiki_url=card.wiki_url,
                file_url=card.source_url,
                can_download=bool(card.source_url),
            ))
        return results

    def _exact_search(
        self,
        query: str,
        limit: int,
        search_fields: str,
        filters: Dict[str, Any],
    ) -> List[CardSearchResult]:
        q_lower = query.lower()
        where_clauses = []
        params = []

        if search_fields == "tag":
            where_clauses.append("LOWER(tag) LIKE ?")
            params.append(f"%{q_lower}%")
        elif search_fields == "cite":
            where_clauses.append("LOWER(cite) LIKE ?")
            params.append(f"%{q_lower}%")
        elif search_fields == "card_text":
            where_clauses.append("LOWER(card_text) LIKE ?")
            params.append(f"%{q_lower}%")
        else:
            where_clauses.append(
                "(LOWER(tag) LIKE ? OR LOWER(cite) LIKE ? OR LOWER(card_text) LIKE ?)"
            )
            params.extend([f"%{q_lower}%", f"%{q_lower}%", f"%{q_lower}%"])

        extra_clauses, extra_params = self._build_filter_clauses(filters)
        where_clauses.extend(extra_clauses)
        params.extend(extra_params)

        sql = f"""
            SELECT * FROM cards
            WHERE {' AND '.join(where_clauses)}
            LIMIT ?
        """
        rows = self._conn.execute(sql, params + [limit]).fetchall()
        results = []
        for row in rows:
            card = _row_to_card(row)
            snippet = _snippet_around(card.full_text, query)
            results.append(CardSearchResult(
                card_id=card.id,
                card=card,
                score=1.0,
                match_type=MatchType.EXACT,
                snippet=snippet,
                wiki_url=card.wiki_url,
                file_url=card.source_url,
                can_download=bool(card.source_url),
            ))
        return results

    def _build_filter_clauses(self, filters: Dict[str, Any]) -> tuple[list, list]:
        clauses = []
        params = []
        for col in ("team", "school", "tournament", "side", "year", "topic",
                    "source_file", "card_type"):
            if col in filters and filters[col]:
                clauses.append(f"LOWER({col}) LIKE ?")
                params.append(f"%{str(filters[col]).lower()}%")
        return clauses, params

    @staticmethod
    def _fts_escape(query: str) -> str:
        """Escape a user query for FTS5 MATCH."""
        # Strip FTS5 operators to avoid syntax errors from raw user input
        safe = re.sub(r'["\(\)\*\:\^]', " ", query).strip()
        # Wrap in quotes for phrase search if multi-word
        if " " in safe:
            return f'"{safe}"'
        return safe

    def close(self):
        self._conn.close()
