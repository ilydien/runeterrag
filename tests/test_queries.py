from src.graph.queries import build_aggregate_query, build_search_query
from src.retrieval.hybrid import reciprocal_rank_fusion


def test_search_query_with_filters():
    cypher, params = build_search_query(
        {"region": "Ionia", "keyword": "Elusive", "max_cost": 2}
    )
    assert "$region IN c.regions" in cypher
    assert "$keyword IN c.keywords" in cypher
    assert "c.cost <= $max_cost" in cypher
    assert params["region"] == "Ionia"
    assert params["max_cost"] == 2


def test_search_query_without_filters():
    cypher, params = build_search_query({})
    assert "WHERE true" in cypher
    assert params["limit"] == 20


def test_aggregate_query_region():
    cypher, params = build_aggregate_query("region")
    assert "IN_REGION" in cypher
    assert "count(DISTINCT c)" in cypher
    assert params["limit"] == 100


def test_aggregate_query_invalid_group():
    try:
        build_aggregate_query("unknown")
    except ValueError as exc:
        assert "tidak didukung" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Seharusnya raise ValueError")


def test_reciprocal_rank_fusion():
    graph = [{"card_code": "A"}, {"card_code": "B"}]
    vector = [{"card_code": "B"}, {"card_code": "C"}]
    fused = reciprocal_rank_fusion([graph, vector])
    assert fused[0]["card_code"] == "B"
    assert {item["card_code"] for item in fused} == {"A", "B", "C"}
