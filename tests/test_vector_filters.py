from __future__ import annotations

from src.vector.search import build_qdrant_filter


def test_empty_filters_return_none() -> None:
    assert build_qdrant_filter(None) is None
    assert build_qdrant_filter({}) is None
    assert build_qdrant_filter({"text": "Yasuo"}) is None


def test_graph_filters_map_to_qdrant() -> None:
    result = build_qdrant_filter(
        {
            "region": "Ionia",
            "keyword": "Elusive",
            "max_cost": 2,
            "has_text": True,
        }
    )
    assert result is not None
    assert len(result.must) == 4
    rendered = " ".join(str(condition) for condition in result.must)
    assert "regions" in rendered
    assert "keywords" in rendered
    assert "cost" in rendered
    assert "has_native_text" in rendered


def test_range_filters_are_combined_on_cost() -> None:
    result = build_qdrant_filter({"min_cost": 1, "max_cost": 3})
    assert result is not None
    assert len(result.must) == 1
    rendered = str(result.must[0])
    assert "cost" in rendered
    assert "gte" in rendered
    assert "lte" in rendered


def test_bool_filter_uses_native_text_not_embedding_text() -> None:
    result = build_qdrant_filter({"has_text": False})
    assert result is not None
    rendered = str(result.must[0])
    assert "has_native_text" in rendered
    assert "False" in rendered or "false" in rendered
