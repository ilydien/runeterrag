import pytest

from src.graph.extract import extract_all


@pytest.fixture(scope="module")
def result():
    return extract_all()


def test_card_counts(result):
    assert len(result.cards) == 2512
    assert sum(1 for card in result.cards if not card.hasNativeText) == 183
    assert sum(1 for card in result.cards if card.textPlaceholder) == 4
    assert sum(1 for card in result.cards if card.level1TextMissing) == 12


def test_dimension_counts(result):
    dimensions = result.stats["dimensions"]
    assert dimensions["Region"] == 11
    assert dimensions["Subtype"] == 27
    assert dimensions["CardSet"] == 11
    assert dimensions["Format"] == 5
    assert dimensions["Rarity"] == 5
    assert dimensions["SpellSpeed"] == 3
    assert dimensions["Keyword"] >= 49
    assert dimensions["VocabTerm"] >= 40


def test_core_edge_counts(result):
    assert result.edge_count("IN_REGION") == 2602
    assert result.edge_count("HAS_KEYWORD") == 2344
    assert result.edge_count("HAS_SUBTYPE") == 675
    assert result.edge_count("IN_SET") == 2512
    assert result.edge_count("HAS_RARITY") == 2512
    assert result.edge_count("AVAILABLE_IN") == 4577
    assert result.edge_count("HAS_SPELL_SPEED") == 902


def test_mention_counts(result):
    assert result.mention_count("ASSOCIATED_WITH") == 2089
    assert result.mention_count("REFERENCES") >= 800
    assert result.mention_count("MENTIONS_KEYWORD") >= 1100
    assert result.mention_count("MENTIONS_TERM") >= 1100


def test_no_dangling_card_edges(result):
    card_codes = {card.cardCode for card in result.cards}
    for edge in result.edges:
        if edge.rel in {"ASSOCIATED_WITH", "REFERENCES"}:
            assert edge.srcKey in card_codes
            assert edge.dstKey in card_codes


def test_alias_map_contains_champion(result):
    yasuo_codes = result.aliases["cards"].get("yasuo", [])
    assert "01IO015" in yasuo_codes


def test_unresolved_mentions_are_small(result):
    # Dari 890 sebutan kartu, hanya sebagian kecil yang ambigu/tidak ter-resolve.
    assert len(result.unresolved["cards"]) <= 20
