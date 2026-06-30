import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from docx import Document
from docx_parser import parse_debate_docx
from models import ParsedDocument


class TestVerbatimParser:
    def test_is_verbatim_format(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert result.is_verbatim_format is True

    def test_card_count(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert result.total_cards == 2

    def test_first_card_tag(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert "Deterrence prevents great power conflict" in result.cards[0].tag

    def test_first_card_cite(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert "Smith" in result.cards[0].cite
        assert "2023" in result.cards[0].cite

    def test_first_card_text(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert "deterrence" in result.cards[0].card_text.lower()

    def test_pocket_propagated(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert result.cards[0].pocket == "Deterrence Advantage"

    def test_hat_propagated(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert result.cards[0].hat == "Nuclear War"

    def test_block_propagated(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert result.cards[0].block == "Deterrence Works"

    def test_second_card_tag(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert "Credibility" in result.cards[1].tag

    def test_no_parse_errors(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert result.parse_errors == []

    def test_card_ids_are_unique(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        ids = [c.id for c in result.cards]
        assert len(ids) == len(set(ids))

    def test_full_text_contains_tag(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        c = result.cards[0]
        assert c.tag in c.full_text

    def test_source_file_path_set(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert all(c.source_file_path == str(verbatim_docx) for c in result.cards)

    def test_returns_parseddocument(self, verbatim_docx):
        result = parse_debate_docx(str(verbatim_docx))
        assert isinstance(result, ParsedDocument)


class TestGenericParser:
    def test_is_not_verbatim_format(self, generic_docx):
        result = parse_debate_docx(str(generic_docx))
        assert result.is_verbatim_format is False

    def test_card_count(self, generic_docx):
        result = parse_debate_docx(str(generic_docx))
        assert result.total_cards == 2

    def test_first_card_tag_detected(self, generic_docx):
        result = parse_debate_docx(str(generic_docx))
        assert "Warming" in result.cards[0].tag

    def test_first_card_cite_detected(self, generic_docx):
        result = parse_debate_docx(str(generic_docx))
        assert "Hansen" in result.cards[0].cite

    def test_first_card_text(self, generic_docx):
        result = parse_debate_docx(str(generic_docx))
        assert "climate" in result.cards[0].card_text.lower()

    def test_second_card_tag(self, generic_docx):
        result = parse_debate_docx(str(generic_docx))
        assert "Feedback" in result.cards[1].tag

    def test_second_card_cite(self, generic_docx):
        result = parse_debate_docx(str(generic_docx))
        assert "Mann" in result.cards[1].cite


class TestMalformedParser:
    def test_no_crash(self, malformed_docx):
        result = parse_debate_docx(str(malformed_docx))
        assert result is not None

    def test_returns_parseddocument(self, malformed_docx):
        result = parse_debate_docx(str(malformed_docx))
        assert isinstance(result, ParsedDocument)

    def test_tag_without_cite_survives(self, malformed_docx):
        result = parse_debate_docx(str(malformed_docx))
        tags = [c.tag for c in result.cards]
        assert any("Tag without cite" in t for t in tags)

    def test_tag_without_cite_has_empty_cite(self, malformed_docx):
        result = parse_debate_docx(str(malformed_docx))
        card = next(c for c in result.cards if "Tag without cite" in c.tag)
        assert card.cite == ""

    def test_all_cards_have_tag_or_text(self, malformed_docx):
        result = parse_debate_docx(str(malformed_docx))
        for card in result.cards:
            assert card.tag or card.card_text, f"Card {card.id} has neither tag nor body"


class TestEdgeCases:
    def test_file_not_found(self, tmp_path):
        result = parse_debate_docx(str(tmp_path / "nonexistent.docx"))
        assert result.parse_errors
        assert "not found" in result.parse_errors[0].lower()
        assert result.cards == []

    def test_non_docx_file(self, tmp_path):
        bad = tmp_path / "fake.docx"
        bad.write_bytes(b"this is not a docx file at all")
        result = parse_debate_docx(str(bad))
        assert result.parse_errors
        assert result.cards == []

    def test_empty_docx(self, tmp_path):
        empty = tmp_path / "empty.docx"
        Document().save(str(empty))
        result = parse_debate_docx(str(empty))
        assert result.cards == []
        assert result.parse_errors == []
