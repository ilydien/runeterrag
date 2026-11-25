from __future__ import annotations

from qdrant_client import QdrantClient

from src.vector.load import build_records, upsert_records
from src.vector.schema import ensure_collection
from src.vector.validate import validate


def card(code: str, name: str) -> dict:
    return {
        "cardCode": code,
        "name": name,
        "type": "Unit",
        "supertype": "",
        "regions": ["Ionia"],
        "subtypes": [],
        "keywords": [],
        "keywordRefs": [],
        "cost": 1,
        "attack": 1,
        "health": 1,
        "descriptionRaw": "",
        "levelupDescriptionRaw": "",
        "hasNativeText": False,
        "textStatus": "attributes_only",
        "set": "Set1",
        "setDisplayName": "Foundations",
        "rarity": "Common",
        "formats": ["Eternal"],
        "collectible": True,
        "patch": "7_11_0",
    }


def test_validate_reports_complete_collection() -> None:
    source = [card("A", "Alpha"), card("B", "Beta")]
    records = build_records(source, embedding_model="test-model")
    client = QdrantClient(":memory:")
    collection = ensure_collection(
        client,
        collection_name="cards",
        vector_size=3,
    )
    upsert_records(
        client,
        collection,
        records,
        [[0.1, 0.2, 0.3] for _ in records],
        batch_size=2,
    )

    report = validate(
        client,
        collection_name=collection,
        source_cards=source,
    )

    assert report["passed"] is True
    assert report["points"] == 2
    assert report["missing"] == 0
    assert report["extra"] == 0


def test_validate_detects_missing_card() -> None:
    source = [card("A", "Alpha")]
    records = build_records(source, embedding_model="test-model")
    client = QdrantClient(":memory:")
    collection = ensure_collection(
        client,
        collection_name="cards",
        vector_size=3,
    )
    upsert_records(
        client,
        collection,
        records,
        [[0.1, 0.2, 0.3] for _ in records],
        batch_size=1,
    )

    report = validate(
        client,
        collection_name=collection,
        source_cards=[*source, card("C", "Gamma")],
    )

    assert report["passed"] is False
    assert report["missing"] == 1
