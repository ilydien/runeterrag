from __future__ import annotations

from src.vector.schema import build_payload, point_id
from src.vector.text import (
    build_embedding_text,
    clean_keywords,
    clean_text,
    embedding_text_hash,
)


def native_card() -> dict:
    return {
        "cardCode": "01IO015",
        "name": "Yasuo",
        "type": "Unit",
        "supertype": "Champion",
        "regions": ["Ionia"],
        "subtypes": [],
        "keywords": ["Quick Attack"],
        "keywordRefs": ["Quick Attack"],
        "cost": 4,
        "attack": 5,
        "health": 4,
        "descriptionRaw": "When I strike, deal 1 to the enemy Nexus.",
        "levelupDescriptionRaw": "You've stunned or recalled 2 enemies.",
        "flavorText": "Death is like the wind.",
        "hasNativeText": True,
        "textStatus": "native",
        "set": "Set1",
        "setDisplayName": "Foundations",
        "rarity": "Champion",
        "formats": ["Standard", "Eternal"],
        "collectible": True,
        "patch": "7_11_0",
    }


def textless_card() -> dict:
    return {
        "cardCode": "01IO005",
        "name": "Nimble Poro",
        "type": "Unit",
        "supertype": "",
        "regions": ["Ionia"],
        "subtypes": ["Poro"],
        "keywords": [],
        "keywordRefs": [],
        "cost": 1,
        "attack": 1,
        "health": 1,
        "descriptionRaw": "",
        "levelupDescriptionRaw": "",
        "flavorText": "",
        "hasNativeText": False,
        "textStatus": "attributes_only",
        "set": "Set1",
        "setDisplayName": "Foundations",
        "rarity": "Common",
        "formats": ["Eternal"],
        "collectible": True,
        "patch": "7_11_0",
    }


def test_native_card_is_labeled_and_excludes_flavor() -> None:
    text = build_embedding_text(native_card())
    assert "Card: Yasuo" in text
    assert "Type: Unit" in text
    assert "Supertype: Champion" in text
    assert "Region: Ionia" in text
    assert "Keywords: Quick Attack" in text
    assert "Stats: 5 Attack, 4 Health" in text
    assert "Description: When I strike" in text
    assert "Level-up Condition: You've stunned" in text
    assert "Death is like the wind" not in text


def test_textless_card_uses_structured_attributes() -> None:
    text = build_embedding_text(textless_card())
    assert "Card: Nimble Poro" in text
    assert "Subtypes: Poro" in text
    assert "Stats: 1 Attack, 1 Health" in text
    assert "Keywords: None" in text
    assert "Card Description: No native card description available." in text


def test_clean_text_drops_empty_placeholder() -> None:
    assert clean_text("  Missing Translation  ") is None
    assert clean_text("Deal 1 damage. Missing Translation") == "Deal 1 damage."


def test_missing_translation_is_removed_from_keywords() -> None:
    card = native_card()
    card["keywords"] = ["Missing Translation", "Quick Attack"]
    assert clean_keywords(card) == ["Quick Attack"]
    text = build_embedding_text(card)
    assert "Missing Translation" not in text
    assert "Keywords: Quick Attack" in text


def test_only_placeholder_keyword_becomes_none() -> None:
    card = native_card()
    card["keywords"] = ["Missing Translation"]
    assert clean_keywords(card) == []
    assert "Keywords: None" in build_embedding_text(card)


def test_equipment_uses_bonus_stats() -> None:
    card = native_card()
    card["type"] = "Equipment"
    card["attack"] = 2
    card["health"] = 1
    text = build_embedding_text(card)
    assert "Bonus Stats: +2/+1" in text
    assert "Stats:" not in text.replace("Bonus Stats:", "")


def test_spell_has_no_stats_line() -> None:
    card = native_card()
    card["type"] = "Spell"
    card["supertype"] = ""
    card["attack"] = 0
    card["health"] = 0
    text = build_embedding_text(card)
    assert "Stats:" not in text
    assert "Bonus Stats:" not in text


def test_payload_contains_identity_and_quality_flags() -> None:
    card = native_card()
    text = build_embedding_text(card)
    payload = build_payload(card, text)
    assert payload["card_code"] == "01IO015"
    assert payload["has_native_text"] is True
    assert payload["has_embedding_text"] is True
    assert payload["text_status"] == "native"
    assert payload["keywords"] == ["Quick Attack"]
    assert len(payload["text_hash"]) == 64
    assert payload["embedding_template_version"] == "v1"


def test_point_id_is_deterministic() -> None:
    assert point_id("01IO015") == point_id("01IO015")
    assert point_id("01IO015") != point_id("01IO016")


def test_text_hash_is_deterministic() -> None:
    text = build_embedding_text(native_card())
    assert embedding_text_hash(text) == embedding_text_hash(text)
    assert len(embedding_text_hash(text)) == 64
