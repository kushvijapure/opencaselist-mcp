import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import CardType, DebateCard, ParsedDocument, Side
from local_index import LocalCardIndex


def _card(id, tag, cite="", card_text="", pocket="", side=Side.NEG, **kw):
    return DebateCard(
        id=id,
        tag=tag,
        cite=cite,
        card_text=card_text,
        full_text=f"{tag} {cite} {card_text}".strip(),
        pocket=pocket,
        side=side,
        **kw,
    )


def _doc(file_path, cards):
    for card in cards:
        card.source_file_path = file_path
    return ParsedDocument(
        file_path=file_path,
        file_name=Path(file_path).name,
        total_cards=len(cards),
        cards=cards,
    )


@pytest.fixture
def index(tmp_path):
    idx = LocalCardIndex(db_path=tmp_path / "test.db")
    yield idx
    idx.close()


class TestIndexDocument:
    def test_returns_count(self, index):
        doc = _doc("/tmp/a.docx", [_card("c1", "Nuclear deterrence works")])
        assert index.index_document(doc) == 1

    def test_get_card_roundtrip(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "Nuclear deterrence works")]))
        card = index.get_card("c1")
        assert card is not None
        assert card.tag == "Nuclear deterrence works"

    def test_total_card_count(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "Tag one"), _card("c2", "Tag two")]))
        assert index.total_card_count() == 2

    def test_reindex_replaces_old_cards(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "Original")]))
        index.index_document(_doc("/tmp/a.docx", [_card("c2", "Replacement")]))
        assert index.total_card_count() == 1
        assert index.get_card("c1") is None
        assert index.get_card("c2") is not None

    def test_two_files_accumulate(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "Tag A")]))
        index.index_document(_doc("/tmp/b.docx", [_card("c2", "Tag B")]))
        assert index.total_card_count() == 2

    def test_remove_document(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "Tag")]))
        index.remove_document("/tmp/a.docx")
        assert index.total_card_count() == 0

    def test_metadata_override_team(self, index):
        index.index_document(
            _doc("/tmp/a.docx", [_card("c1", "Tag")]),
            metadata_override={"team": "Harvard KP"},
        )
        assert index.get_card("c1").team == "Harvard KP"

    def test_metadata_override_side(self, index):
        index.index_document(
            _doc("/tmp/a.docx", [_card("c1", "Tag", side=Side.NEG)]),
            metadata_override={"side": "aff"},
        )
        assert index.get_card("c1").side == Side.AFF

    def test_list_indexed_files(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "Tag")]))
        files = index.list_indexed_files()
        assert len(files) == 1
        assert files[0]["file_name"] == "a.docx"

    def test_get_missing_card_returns_none(self, index):
        assert index.get_card("does_not_exist") is None


class TestFTSSearch:
    def test_finds_card_by_tag(self, index):
        index.index_document(_doc("/tmp/a.docx", [
            _card("c1", "Nuclear deterrence prevents war"),
        ]))
        results = index.search("deterrence")
        assert len(results) == 1
        assert results[0].card_id == "c1"

    def test_no_results(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "Nuclear deterrence")]))
        assert index.search("climate change") == []

    def test_tag_field_excludes_body_match(self, index):
        index.index_document(_doc("/tmp/a.docx", [
            _card("c_tag", "deterrence tag", card_text="unrelated body"),
            _card("c_body", "unrelated tag", card_text="deterrence in body"),
        ]))
        results = index.search("deterrence", search_fields="tag")
        ids = {r.card_id for r in results}
        assert "c_tag" in ids
        assert "c_body" not in ids

    def test_cite_field_search(self, index):
        index.index_document(_doc("/tmp/a.docx", [
            _card("c1", "tag", cite="Smith 2023 Harvard professor"),
            _card("c2", "tag", cite="Jones 2022 MIT"),
        ]))
        results = index.search("Smith", search_fields="cite")
        ids = {r.card_id for r in results}
        assert "c1" in ids
        assert "c2" not in ids

    def test_card_text_field_search(self, index):
        index.index_document(_doc("/tmp/a.docx", [
            _card("c1", "unrelated tag", card_text="deterrence in body text here"),
            _card("c2", "deterrence in tag", card_text="unrelated body"),
        ]))
        results = index.search("deterrence", search_fields="card_text")
        ids = {r.card_id for r in results}
        assert "c1" in ids
        assert "c2" not in ids

    def test_bm25_tag_match_ranks_above_body(self, index):
        # Card with term repeated in short tag should beat card with term buried in long body
        index.index_document(_doc("/tmp/a.docx", [
            _card("c_body", "Unrelated claim about something else entirely",
                  card_text="deterrence once mentioned in a long paragraph of unrelated content"),
            _card("c_tag", "Deterrence deterrence nuclear deterrence stability deterrence",
                  card_text="other unrelated content"),
        ]))
        results = index.search("deterrence")
        assert len(results) == 2
        assert results[0].card_id == "c_tag"

    def test_scores_are_positive(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "deterrence tag")]))
        results = index.search("deterrence")
        assert all(r.score >= 0 for r in results)

    def test_fts_syntax_error_falls_back_gracefully(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "deterrence tag")]))
        results = index.search('"unclosed deterrence')
        assert isinstance(results, list)

    def test_limit_respected(self, index):
        cards = [_card(f"c{i}", f"deterrence tag {i}") for i in range(10)]
        index.index_document(_doc("/tmp/a.docx", cards))
        results = index.search("deterrence", limit=3)
        assert len(results) <= 3

    def test_snippet_contains_query_term(self, index):
        index.index_document(_doc("/tmp/a.docx", [
            _card("c1", "tag", card_text="nuclear deterrence prevents escalation"),
        ]))
        results = index.search("deterrence")
        assert "deterrence" in results[0].snippet.lower()


class TestExactSearch:
    def test_finds_substring(self, index):
        index.index_document(_doc("/tmp/a.docx", [
            _card("c1", "Nuclear deterrence prevents war"),
        ]))
        results = index.search("deterrence prevents", exact=True)
        assert len(results) == 1

    def test_match_type_is_exact(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "deterrence tag")]))
        results = index.search("deterrence", exact=True)
        assert results[0].match_type.value == "exact"

    def test_case_insensitive(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "DETERRENCE WORKS")]))
        results = index.search("deterrence", exact=True)
        assert len(results) == 1

    def test_no_match(self, index):
        index.index_document(_doc("/tmp/a.docx", [_card("c1", "deterrence tag")]))
        assert index.search("climate", exact=True) == []


class TestFilters:
    def test_filter_by_side_aff(self, index):
        index.index_document(_doc("/tmp/a.docx", [
            _card("c_aff", "warming aff card", side=Side.AFF),
            _card("c_neg", "warming neg card", side=Side.NEG),
        ]))
        results = index.search("warming", filters={"side": "aff"})
        ids = {r.card_id for r in results}
        assert "c_aff" in ids
        assert "c_neg" not in ids

    def test_filter_by_team(self, index):
        index.index_document(
            _doc("/tmp/a.docx", [_card("c1", "deterrence tag")]),
            metadata_override={"team": "Harvard KP"},
        )
        index.index_document(
            _doc("/tmp/b.docx", [_card("c2", "deterrence tag")]),
            metadata_override={"team": "Michigan DA"},
        )
        results = index.search("deterrence", filters={"team": "harvard"})
        ids = {r.card_id for r in results}
        assert "c1" in ids
        assert "c2" not in ids

    def test_filter_by_tournament(self, index):
        index.index_document(
            _doc("/tmp/a.docx", [_card("c1", "deterrence tag")]),
            metadata_override={"tournament": "NDT 2024"},
        )
        index.index_document(
            _doc("/tmp/b.docx", [_card("c2", "deterrence tag")]),
            metadata_override={"tournament": "CEDA 2024"},
        )
        results = index.search("deterrence", filters={"tournament": "ndt"})
        ids = {r.card_id for r in results}
        assert "c1" in ids
        assert "c2" not in ids
