from __future__ import annotations

from src.graph.extract import extract_all
from src.vector.load import build_records


def test_vector_records_match_graph_artifact() -> None:
    result = extract_all()
    cards = [card.to_props() for card in result.cards]
    records = build_records(
        cards,
        embedding_model="intfloat/multilingual-e5-large",
    )

    assert len(records) == 2512
    assert len({record["id"] for record in records}) == 2512
    assert all(record["text"].strip() for record in records)
    assert all(record["payload"]["has_embedding_text"] for record in records)
    assert all(
        "Missing Translation" not in record["payload"]["keywords"]
        for record in records
    )
    assert all(
        "Missing Translation" not in record["payload"]["keyword_refs"]
        for record in records
    )
    assert all(record["payload"]["card_code"] for record in records)
