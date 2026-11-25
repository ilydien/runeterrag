"""Demo/uji kemampuan graph RuneTerraRAG.

Jalankan di container:
    python -m src.graph.demo

Menguji:
- statistik graph
- filter terstruktur
- agregasi
- detail kartu & level-up
- relasi multi-hop
- full-text search
- path melalui hub dimensi
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import GraphDatabase

from src.common import config
from src.graph import queries


def header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_rows(rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    if not rows:
        print("  (tidak ada hasil)")
        return
    columns = columns or list(rows[0].keys())
    for row in rows:
        print("  " + " | ".join(f"{col}={row.get(col)}" for col in columns))


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    driver = GraphDatabase.driver(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )
    checks: list[tuple[str, bool, Any, Any]] = []

    def check(name: str, actual: Any, expected: Any, op: str = "==") -> None:
        ok = actual == expected if op == "==" else actual >= expected
        checks.append((name, ok, actual, expected))

    try:
        driver.verify_connectivity()
        with driver.session(database=config.NEO4J_DATABASE) as session:
            header("1. STATISTIK GRAPH")
            stats = dict(
                session.run(
                    """
                    MATCH (c:Card)
                    RETURN count(c) AS cards,
                           sum(CASE WHEN c.collectible THEN 1 ELSE 0 END) AS collectible,
                           sum(CASE WHEN NOT c.hasNativeText THEN 1 ELSE 0 END) AS textless,
                           sum(CASE WHEN c.textPlaceholder THEN 1 ELSE 0 END) AS placeholder,
                           sum(CASE WHEN c.level1TextMissing THEN 1 ELSE 0 END) AS level1Missing
                    """
                ).single()
            )
            print_rows([stats])
            check("Card", stats["cards"], 2512)
            check("Collectible", stats["collectible"], 1647)
            check("Textless", stats["textless"], 183)
            check("Placeholder", stats["placeholder"], 4)
            check("level1TextMissing", stats["level1Missing"], 12)

            dims = [
                dict(r)
                for r in session.run(
                    "MATCH (n) WHERE NOT n:Card "
                    "RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label"
                )
            ]
            print("\nNode dimensi:")
            print_rows(dims, ["label", "n"])

            edges = [
                dict(r)
                for r in session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS n ORDER BY rel"
                )
            ]
            print("\nEdge:")
            print_rows(edges, ["rel", "n"])

            header("2. FILTER TERSTRUKTUR")
            ionia = queries.search(
                driver,
                {"region": "Ionia", "keyword": "Elusive", "max_cost": 2},
                limit=100,
            )
            print(f"Ionia + Elusive + cost<=2: {len(ionia)} kartu")
            print_rows(
                [
                    {
                        "code": c["cardCode"],
                        "name": c["name"],
                        "cost": c["cost"],
                        "stats": f"{c['attack']}/{c['health']}",
                    }
                    for c in ionia
                ],
                ["code", "name", "cost", "stats"],
            )
            check("Ionia Elusive <=2", len(ionia), 13)

            si_fast = queries.search(
                driver,
                {
                    "region": "Shadow Isles",
                    "type": "Spell",
                    "spell_speed": "Fast",
                    "max_cost": 3,
                },
                limit=100,
            )
            print(f"\nShadow Isles + Fast spell + cost<=3: {len(si_fast)} kartu")
            check("SI Fast spell <=3", len(si_fast), 16)

            header("3. AGREGASI")
            region_counts = queries.aggregate(driver, "region")
            print("Kartu per region:")
            print_rows(region_counts, ["key", "count"])
            check("Region count", len(region_counts), 11)

            champion_counts = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (c:Card)
                    WHERE c.isBaseChampion
                    RETURN c.regions[0] AS region, count(*) AS champions
                    ORDER BY champions DESC, region
                    """
                )
            ]
            print("\nChampion base per region:")
            print_rows(champion_counts, ["region", "champions"])

            mana_curve = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (c:Card) WHERE c.type='Unit'
                    RETURN c.cost AS cost, count(*) AS units
                    ORDER BY cost
                    """
                )
            ]
            print("\nMana curve unit:")
            print_rows(mana_curve, ["cost", "units"])

            top_keywords = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (:Card)-[:HAS_KEYWORD]->(k:Keyword)
                    RETURN k.name AS keyword, count(*) AS cards
                    ORDER BY cards DESC, keyword LIMIT 10
                    """
                )
            ]
            print("\nTop keyword:")
            print_rows(top_keywords, ["keyword", "cards"])

            header("4. DETAIL KARTU & LEVEL-UP")
            yasuo = queries.detail(driver, "01IO015")
            card = yasuo["card"]
            print(
                f"Yasuo: cost={card['cost']} {card['attack']}/{card['health']} "
                f"region={card['regions']} keyword={card['keywords']}"
            )
            print(f"  teks: {card['descriptionRaw']}")
            print("  associated:")
            print_rows(yasuo["associated"], ["cardCode", "name", "type", "role"])

            level2 = queries.level_up(driver, "01IO015")
            print("\nYasuo level 2:")
            print_rows(
                [
                    {
                        "code": c["cardCode"],
                        "name": c["name"],
                        "stats": f"{c['attack']}/{c['health']}",
                        "text": c["descriptionRaw"],
                    }
                    for c in level2
                ],
                ["code", "name", "stats", "text"],
            )
            check("Yasuo LEVELS_INTO", len(level2), 1, ">=")

            header("5. RELASI MULTI-HOP")
            living_shadow = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (src:Card)-[r:REFERENCES]->(t:Card {name:'Living Shadow'})
                    RETURN DISTINCT src.cardCode AS code, src.name AS name,
                                    r.spans AS spans
                    ORDER BY code
                    """
                )
            ]
            print("Kartu yang menyebut/membuat Living Shadow:")
            print_rows(living_shadow, ["code", "name", "spans"])
            check("Living Shadow refs", len(living_shadow), 1, ">=")

            zed_related = queries.related(driver, "01IO009", depth=1, limit=20)
            print("\nKartu terkait Zed:")
            print_rows(
                [
                    {
                        "code": item["card"].get("cardCode"),
                        "name": item["card"].get("name"),
                        "type": item["card"].get("type"),
                        "rel": item["relTypes"],
                    }
                    for item in zed_related
                ],
                ["code", "name", "type", "rel"],
            )

            yasuo_refs = queries.mentions_of(driver, "01IO015")
            print("\nKartu yang menyebut Yasuo:")
            print_rows(
                [
                    {
                        "code": item["card"]["cardCode"],
                        "name": item["card"]["name"],
                        "spans": item["reference"].get("spans"),
                    }
                    for item in yasuo_refs
                ],
                ["code", "name", "spans"],
            )

            deep = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (c:Card)-[:HAS_KEYWORD]->(:Keyword {name:'Deep'})
                    RETURN c.cardCode AS code, c.name AS name, c.cost AS cost,
                           c.attack AS attack, c.health AS health
                    ORDER BY c.cost, c.name
                    """
                )
            ]
            print("\nKartu dengan keyword Deep:")
            print_rows(deep, ["code", "name", "cost", "attack", "health"])
            check("Deep cards", len(deep), 9)

            equipment = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (c:Card)-[:HAS_KEYWORD]->(:Keyword {name:'Overwhelm'})
                    WHERE c.type='Equipment'
                    RETURN c.cardCode AS code, c.name AS name, c.cost AS cost
                    ORDER BY c.cost, c.name
                    """
                )
            ]
            print("\nEquipment dengan Overwhelm:")
            print_rows(equipment, ["code", "name", "cost"])
            check("Equipment Overwhelm", len(equipment), 2)

            header("6. FULL-TEXT SEARCH")
            fulltext = [
                dict(r)
                for r in session.run(
                    """
                    CALL db.index.fulltext.queryNodes('card_text', $q)
                    YIELD node, score
                    RETURN node.cardCode AS code, node.name AS name,
                           round(score, 3) AS score
                    ORDER BY score DESC LIMIT 5
                    """,
                    q="enemy Nexus",
                )
            ]
            print("Full-text 'enemy Nexus':")
            print_rows(fulltext, ["code", "name", "score"])
            check("Full-text results", len(fulltext), 1, ">=")

            header("7. PATH MELALUI HUB DIMENSI")
            path = session.run(
                """
                MATCH p=shortestPath(
                    (a:Card {cardCode:'01IO015'})
                    -[:IN_REGION|HAS_KEYWORD*1..4]-
                    (b:Card {cardCode:'01IO012'})
                )
                RETURN [n IN nodes(p) | coalesce(n.name, n.cardCode)] AS path,
                       length(p) AS hops
                """
            ).single()
            if path:
                print(f"Yasuo -> Twin Disciplines: hops={path['hops']}")
                print(f"  path={path['path']}")
                check("Path hops", path["hops"], 2)

            header("8. KARTU TANPA TEKS (sample)")
            textless = [
                dict(r)
                for r in session.run(
                    """
                    MATCH (c:Card) WHERE NOT c.hasNativeText
                    RETURN c.cardCode AS code, c.name AS name,
                           c.type AS type, c.textStatus AS status
                    ORDER BY c.cardCode LIMIT 10
                    """
                )
            ]
            print_rows(textless, ["code", "name", "type", "status"])

    finally:
        driver.close()

    header("RINGKASAN TEST")
    for name, ok, actual, expected in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: actual={actual} expected={expected}")
    passed = sum(1 for _, ok, _, _ in checks if ok)
    print(f"\n{passed}/{len(checks)} test lolos.")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
