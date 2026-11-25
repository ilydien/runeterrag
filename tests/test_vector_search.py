from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.vector.search import vector_search


class FakeModel:
    def encode(self, texts, **kwargs):
        assert texts and texts[0].startswith("query: ")
        return [[0.1, 0.2, 0.3]]


@dataclass
class FakePoint:
    score: float
    payload: dict[str, Any]


class FakeResponse:
    def __init__(self, points):
        self.points = points


class FakeClient:
    def __init__(self, points):
        self.points = points
        self.kwargs = None

    def query_points(self, **kwargs):
        self.kwargs = kwargs
        return FakeResponse(self.points)


def point(score: float, card_code: str, name: str) -> FakePoint:
    return FakePoint(
        score=score,
        payload={
            "card_code": card_code,
            "name": name,
            "type": "Unit",
            "regions": ["Ionia"],
            "cost": 4,
        },
    )


def test_vector_search_sorts_and_dedupes() -> None:
    client = FakeClient(
        [
            point(0.5, "A", "Alpha"),
            point(0.9, "B", "Beta"),
            point(0.7, "A", "Alpha duplicate"),
        ]
    )
    results = vector_search(
        "cari kartu Ionia",
        top_k=5,
        client=client,
        model=FakeModel(),
    )
    assert [item["card_code"] for item in results] == ["B", "A"]
    assert results[0]["score"] == 0.9
    assert client.kwargs["limit"] == 5


def test_vector_search_passes_filter() -> None:
    client = FakeClient([point(0.8, "A", "Alpha")])
    vector_search(
        "kartu elusive",
        filters={"region": "Ionia", "keyword": "Elusive"},
        client=client,
        model=FakeModel(),
    )
    assert client.kwargs["query_filter"] is not None
    assert len(client.kwargs["query_filter"].must) == 2


def test_empty_query_returns_empty() -> None:
    client = FakeClient([])
    assert vector_search("   ", client=client, model=FakeModel()) == []
