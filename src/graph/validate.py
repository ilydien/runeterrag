"""Validasi isi graph Neo4j terhadap artefak ekstraksi.

Jalankan:
    python -m src.graph.validate

Exit code 0 jika semua assertion lolos, 1 jika ada yang gagal.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from src.common import config
from src.graph import schema

logger = logging.getLogger(__name__)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _check(
    name: str,
    actual: Any,
    expected: Any,
    op: str = "==",
) -> dict[str, Any]:
    if op == "==":
        passed = actual == expected
    elif op == ">=":
        passed = actual >= expected
    elif op == "<=":
        passed = actual <= expected
    else:
        raise ValueError(f"Operator tidak didukung: {op}")
    return {
        "name": name,
        "actual": actual,
        "expected": expected,
        "op": op,
        "passed": bool(passed),
    }


def run_validation(driver) -> dict[str, Any]:
    cards = read_jsonl(config.PROCESSED_DIR / "cards.jsonl")
    dimensions = read_jsonl(config.PROCESSED_DIR / "dims.jsonl")
    edges = read_jsonl(config.PROCESSED_DIR / "edges.jsonl")

    expected_edge_counts = Counter(edge["rel"] for edge in edges)
    expected_dim_counts = Counter(dimension["label"] for dimension in dimensions)
    expected_text_status = Counter(card["textStatus"] for card in cards)
    expected_level1_missing = sum(
        1 for card in cards if card.get("level1TextMissing")
    )
    expected_occurrences = {
        rel: sum(
            int(edge.get("props", {}).get("count", 1))
            for edge in edges
            if edge["rel"] == rel
        )
        for rel in (
            "ASSOCIATED_WITH",
            "REFERENCES",
            "MENTIONS_KEYWORD",
            "MENTIONS_TERM",
        )
    }

    actual: dict[str, Any] = {}
    with driver.session(database=config.NEO4J_DATABASE) as session:
        actual["cards"] = session.run(
            "MATCH (c:Card) RETURN count(c) AS n"
        ).single()["n"]

        actual["dimensions"] = {
            label: session.run(
                f"MATCH (n:`{label}`) RETURN count(n) AS n"
            ).single()["n"]
            for label in schema.DIM_LABELS
        }

        actual["edges"] = {
            record["rel"]: record["n"]
            for record in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS n"
            )
        }

        actual["textStatus"] = {
            record["status"]: record["n"]
            for record in session.run(
                "MATCH (c:Card) "
                "RETURN c.textStatus AS status, count(*) AS n"
            )
        }

        actual["level1TextMissing"] = session.run(
            "MATCH (c:Card) WHERE c.level1TextMissing RETURN count(c) AS n"
        ).single()["n"]

        actual["dangling"] = session.run(
            "MATCH (c:Card)-[r:ASSOCIATED_WITH|REFERENCES]->(t) "
            "WHERE NOT t:Card RETURN count(r) AS n"
        ).single()["n"]

        actual["occurrences"] = {
            rel: session.run(
                f"MATCH ()-[r:{rel}]->() "
                "RETURN sum(coalesce(r.count, 1)) AS n"
            ).single()["n"]
            for rel in (
                "ASSOCIATED_WITH",
                "REFERENCES",
                "MENTIONS_KEYWORD",
                "MENTIONS_TERM",
            )
        }

    checks: list[dict[str, Any]] = []
    checks.append(_check("Card count", actual["cards"], 2512))
    checks.append(_check("Textless cards", sum(1 for c in cards if not c["hasNativeText"]), 183))
    checks.append(_check("Placeholder cards", sum(1 for c in cards if c["textPlaceholder"]), 4))
    checks.append(_check("level1TextMissing", actual["level1TextMissing"], 12))
    checks.append(_check("Dangling card references", actual["dangling"], 0))

    for status, count in expected_text_status.items():
        checks.append(
            _check(
                f"textStatus[{status}]",
                actual["textStatus"].get(status, 0),
                count,
            )
        )

    for label in schema.DIM_LABELS:
        checks.append(
            _check(
                f"dimension[{label}]",
                actual["dimensions"].get(label, 0),
                expected_dim_counts.get(label, 0),
            )
        )
    checks.append(
        _check("dimension[Keyword] minimum", actual["dimensions"].get("Keyword", 0), 49, ">=")
    )
    checks.append(
        _check(
            "dimension[VocabTerm] minimum",
            actual["dimensions"].get("VocabTerm", 0),
            40,
            ">=",
        )
    )

    # Semua rel type: actual harus sama dengan yang diekstraksi.
    for rel, expected_count in expected_edge_counts.items():
        checks.append(
            _check(
                f"edge[{rel}]",
                actual["edges"].get(rel, 0),
                expected_count,
            )
        )

    # Benchmark inti yang sudah diverifikasi dari dataset.
    benchmarks = {
        "IN_REGION": 2602,
        "HAS_KEYWORD": 2344,
        "HAS_SUBTYPE": 675,
        "IN_SET": 2512,
        "HAS_RARITY": 2512,
        "AVAILABLE_IN": 4577,
        "HAS_SPELL_SPEED": 902,
    }
    for rel, expected_count in benchmarks.items():
        checks.append(
            _check(
                f"benchmark[{rel}]",
                actual["edges"].get(rel, 0),
                expected_count,
            )
        )

    checks.append(
        _check(
            "occurrences[ASSOCIATED_WITH]",
            actual["occurrences"].get("ASSOCIATED_WITH", 0),
            2089,
        )
    )
    checks.append(
        _check(
            "occurrences[REFERENCES] minimum",
            actual["occurrences"].get("REFERENCES", 0),
            800,
            ">=",
        )
    )
    checks.append(
        _check(
            "occurrences[MENTIONS_KEYWORD] minimum",
            actual["occurrences"].get("MENTIONS_KEYWORD", 0),
            1100,
            ">=",
        )
    )
    checks.append(
        _check(
            "occurrences[MENTIONS_TERM] minimum",
            actual["occurrences"].get("MENTIONS_TERM", 0),
            1100,
            ">=",
        )
    )

    report = {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "actual": actual,
        "expected": {
            "edgeCounts": dict(expected_edge_counts),
            "dimensionCounts": dict(expected_dim_counts),
            "textStatus": dict(expected_text_status),
            "level1TextMissing": expected_level1_missing,
            "occurrences": expected_occurrences,
        },
        "processedDir": str(config.PROCESSED_DIR),
    }

    report_path = config.PROCESSED_DIR / "validation_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Validation report ditulis ke %s", report_path)
    return report


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    driver = GraphDatabase.driver(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )
    try:
        report = run_validation(driver)
    finally:
        driver.close()

    for check in report["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(
            f"[{status}] {check['name']}: "
            f"actual={check['actual']!r} "
            f"{check['op']} expected={check['expected']!r}"
        )

    print()
    if report["passed"]:
        print("SEMUA VALIDASI LOLOS.")
        return 0

    print("ADA VALIDASI YANG GAGAL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
