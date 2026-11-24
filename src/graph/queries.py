"""Template Cypher untuk retrieval berbasis graph.

Semua query memakai parameter (tidak ada string interpolation dari input
user), agar aman dan tidak rentan Cypher injection.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from neo4j import GraphDatabase

from src.common import config

logger = logging.getLogger(__name__)


def _filter_clauses(
    filters: dict[str, Any] | None, alias: str = "c"
) -> tuple[list[str], dict[str, Any]]:
    filters = filters or {}
    clauses: list[str] = []
    params: dict[str, Any] = {}

    scalar = {
        "type": f"{alias}.type = $type",
        "supertype": f"{alias}.supertype = $supertype",
        "set": f"{alias}.setRef = $set",
        "rarity": f"{alias}.rarity = $rarity",
        "spell_speed": f"{alias}.spellSpeed = $spell_speed",
        "min_cost": f"{alias}.cost >= $min_cost",
        "max_cost": f"{alias}.cost <= $max_cost",
        "min_attack": f"{alias}.attack >= $min_attack",
        "max_attack": f"{alias}.attack <= $max_attack",
        "min_health": f"{alias}.health >= $min_health",
        "max_health": f"{alias}.health <= $max_health",
        "collectible": f"{alias}.collectible = $collectible",
        "has_text": f"{alias}.hasNativeText = $has_text",
    }
    for key, clause in scalar.items():
        value = filters.get(key)
        if value is not None:
            clauses.append(clause)
            params[key] = value

    list_filters = {
        "region": f"$region IN {alias}.regions",
        "keyword": f"$keyword IN {alias}.keywords",
        "subtype": f"$subtype IN {alias}.subtypes",
        "format": f"$format IN {alias}.formats",
    }
    for key, clause in list_filters.items():
        value = filters.get(key)
        if value:
            clauses.append(clause)
            params[key] = value

    text = filters.get("text")
    if text:
        clauses.append(
            f"(toLower({alias}.name) CONTAINS toLower($text) "
            f"OR toLower(coalesce({alias}.descriptionRaw, '')) CONTAINS toLower($text) "
            f"OR toLower(coalesce({alias}.flavorText, '')) CONTAINS toLower($text))"
        )
        params["text"] = text

    return clauses, params


def build_search_query(
    filters: dict[str, Any] | None = None, limit: int = 20
) -> tuple[str, dict[str, Any]]:
    """Bangun Cypher pencarian kartu dengan filter opsional."""
    clauses, params = _filter_clauses(filters)
    where = " AND ".join(clauses) if clauses else "true"
    cypher = (
        "MATCH (c:Card) "
        f"WHERE {where} "
        "RETURN c "
        "ORDER BY c.cost, c.name "
        "LIMIT $limit"
    )
    params["limit"] = limit
    return cypher, params


def build_aggregate_query(
    group_by: str,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Any]]:
    """Bangun Cypher agregasi (type/set/rarity/cost/region/keyword/...)."""
    allowed = {
        "type",
        "set",
        "rarity",
        "cost",
        "region",
        "keyword",
        "subtype",
        "format",
    }
    if group_by not in allowed:
        raise ValueError(f"group_by tidak didukung: {group_by}")

    edge_groups = {
        "region": ("IN_REGION", "Region"),
        "keyword": ("HAS_KEYWORD", "Keyword"),
        "subtype": ("HAS_SUBTYPE", "Subtype"),
        "format": ("AVAILABLE_IN", "Format"),
    }

    clauses, params = _filter_clauses(filters)
    where = " AND ".join(clauses) if clauses else "true"

    if group_by in edge_groups:
        rel, label = edge_groups[group_by]
        match = f"MATCH (c:Card)-[:{rel}]->(n:{label})"
        key_expr = "n.name"
    else:
        match = "MATCH (c:Card)"
        key_expr = "c.setRef" if group_by == "set" else f"c.{group_by}"

    cypher = (
        f"{match} "
        f"WHERE {where} "
        f"RETURN {key_expr} AS key, count(DISTINCT c) AS count "
        "ORDER BY count DESC, key ASC "
        "LIMIT $limit"
    )
    params["limit"] = limit
    return cypher, params


def search(
    driver,
    filters: dict[str, Any] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    cypher, params = build_search_query(filters, limit)
    with driver.session(database=config.NEO4J_DATABASE) as session:
        return [dict(record["c"]) for record in session.run(cypher, **params)]


def detail(driver, card_code: str) -> dict[str, Any]:
    cypher = """
    MATCH (c:Card {cardCode: $card_code})
    OPTIONAL MATCH (c)-[r:ASSOCIATED_WITH]->(a:Card)
    WITH c, collect({
        cardCode: a.cardCode,
        name: a.name,
        type: a.type,
        role: r.role
    }) AS associated
    RETURN c, [item IN associated WHERE item.cardCode IS NOT NULL] AS associated
    """
    with driver.session(database=config.NEO4J_DATABASE) as session:
        record = session.run(cypher, card_code=card_code).single()
        if not record:
            return {"card": None, "associated": []}
        return {
            "card": dict(record["c"]),
            "associated": record["associated"],
        }


def related(
    driver,
    card_code: str,
    rel_types: list[str] | None = None,
    depth: int = 1,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rel_types = rel_types or ["ASSOCIATED_WITH", "REFERENCES"]
    depth = max(1, min(int(depth), 3))
    cypher = (
        f"MATCH path=(c:Card {{cardCode: $card_code}})-[rels*1..{depth}]->(n) "
        "WHERE all(r IN rels WHERE type(r) IN $rel_types) "
        "RETURN n, [r IN rels | type(r)] AS relTypes, length(path) AS depth "
        "LIMIT $limit"
    )
    with driver.session(database=config.NEO4J_DATABASE) as session:
        result = session.run(
            cypher,
            card_code=card_code,
            rel_types=rel_types,
            limit=limit,
        )
        return [
            {
                "card": dict(record["n"]),
                "relTypes": record["relTypes"],
                "depth": record["depth"],
            }
            for record in result
        ]


def aggregate(
    driver,
    group_by: str,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    cypher, params = build_aggregate_query(group_by, filters, limit)
    with driver.session(database=config.NEO4J_DATABASE) as session:
        return [
            {"key": record["key"], "count": record["count"]}
            for record in session.run(cypher, **params)
        ]


def compare(driver, card_codes: list[str]) -> list[dict[str, Any]]:
    cypher = (
        "MATCH (c:Card) "
        "WHERE c.cardCode IN $card_codes "
        "RETURN c ORDER BY c.cost, c.name"
    )
    with driver.session(database=config.NEO4J_DATABASE) as session:
        return [
            dict(record["c"])
            for record in session.run(cypher, card_codes=card_codes)
        ]


def level_up(driver, card_code: str) -> list[dict[str, Any]]:
    cypher = (
        "MATCH (c:Card {cardCode: $card_code})"
        "-[:ASSOCIATED_WITH {role: 'LEVELS_INTO'}]->(l2:Card) "
        "RETURN l2"
    )
    with driver.session(database=config.NEO4J_DATABASE) as session:
        return [dict(record["l2"]) for record in session.run(cypher, card_code=card_code)]


def mentions_of(driver, card_code: str) -> list[dict[str, Any]]:
    cypher = (
        "MATCH (src:Card)-[r:REFERENCES]->(t:Card {cardCode: $card_code}) "
        "RETURN src, r"
    )
    with driver.session(database=config.NEO4J_DATABASE) as session:
        return [
            {"card": dict(record["src"]), "reference": dict(record["r"])}
            for record in session.run(cypher, card_code=card_code)
        ]


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    driver = GraphDatabase.driver(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )
    try:
        result = search(
            driver,
            {"region": "Ionia", "keyword": "Elusive", "max_cost": 2},
            limit=5,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
