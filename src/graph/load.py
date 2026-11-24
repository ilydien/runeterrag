"""Load hasil ekstraksi JSONL ke Neo4j.

Jalankan:
    python -m src.graph.load

Jika ``data/processed/cards.jsonl`` belum ada, loader otomatis menjalankan
ekstraksi terlebih dahulu (praktis untuk ``make load-graph``).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from neo4j import GraphDatabase

from src.common import config
from src.graph import schema

logger = logging.getLogger(__name__)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def batched(rows: list[Any], size: int) -> Iterable[list[Any]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def ensure_processed() -> None:
    """Pastikan artefak ekstraksi tersedia."""
    required = [
        config.PROCESSED_DIR / "cards.jsonl",
        config.PROCESSED_DIR / "dims.jsonl",
        config.PROCESSED_DIR / "edges.jsonl",
    ]
    if all(path.exists() for path in required):
        return

    logger.info("Artefak ekstraksi belum lengkap; menjalankan extract...")
    from src.graph.extract import extract_all, write_outputs

    write_outputs(extract_all())


def create_schema(session) -> None:
    for statement in schema.SCHEMA_STATEMENTS:
        session.run(statement).consume()


def load_dimensions(session, rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["label"]].append(row)

    for label, items in grouped.items():
        if label not in schema.DIM_LABELS:
            raise ValueError(f"Label dimensi tidak dikenal: {label}")
        query = (
            f"UNWIND $rows AS row "
            f"MERGE (n:`{label}` {{name: row.name}}) "
            f"SET n += row.props"
        )
        for batch in batched(items, config.BATCH_SIZE):
            session.run(
                query,
                rows=[
                    {"name": item["name"], "props": item.get("props", {})}
                    for item in batch
                ],
            ).consume()
    logger.info("Dimensi dimuat: %d node", len(rows))


def load_cards(session, rows: list[dict[str, Any]]) -> None:
    query = (
        "UNWIND $rows AS row "
        "MERGE (c:Card {cardCode: row.cardCode}) "
        "SET c += row.props"
    )
    for batch in batched(rows, config.BATCH_SIZE):
        session.run(
            query,
            rows=[
                {
                    "cardCode": row["cardCode"],
                    "props": _card_props(row),
                }
                for row in batch
            ],
        ).consume()
    logger.info("Card dimuat: %d node", len(rows))


def _card_props(row: dict[str, Any]) -> dict[str, Any]:
    """Buang cardCode dan rename ``set`` -> ``setRef`` (hindari kata kunci Cypher)."""
    props = {key: value for key, value in row.items() if key != "cardCode"}
    if "set" in props:
        props["setRef"] = props.pop("set")
    return props


def load_edges(session, rows: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        src_label = row["srcLabel"]
        dst_label = row["dstLabel"]
        rel = row["rel"]
        if src_label not in schema.ALL_LABELS:
            raise ValueError(f"Label sumber tidak dikenal: {src_label}")
        if dst_label not in schema.ALL_LABELS:
            raise ValueError(f"Label tujuan tidak dikenal: {dst_label}")
        if rel not in schema.REL_TYPES:
            raise ValueError(f"Rel type tidak dikenal: {rel}")
        grouped[(src_label, rel, dst_label)].append(row)

    for (src_label, rel, dst_label), items in grouped.items():
        src_key = schema.key_property(src_label)
        dst_key = schema.key_property(dst_label)
        query = (
            "UNWIND $rows AS row "
            f"MATCH (s:`{src_label}` {{{src_key}: row.srcKey}}) "
            f"MATCH (t:`{dst_label}` {{{dst_key}: row.dstKey}}) "
            f"MERGE (s)-[r:`{rel}`]->(t) "
            "SET r += row.props"
        )
        for batch in batched(items, config.BATCH_SIZE):
            session.run(
                query,
                rows=[
                    {
                        "srcKey": item["srcKey"],
                        "dstKey": item["dstKey"],
                        "props": item.get("props", {}),
                    }
                    for item in batch
                ],
            ).consume()
        logger.info("Edge %-18s dimuat: %d", rel, len(items))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    ensure_processed()

    cards = read_jsonl(config.PROCESSED_DIR / "cards.jsonl")
    dimensions = read_jsonl(config.PROCESSED_DIR / "dims.jsonl")
    edges = read_jsonl(config.PROCESSED_DIR / "edges.jsonl")

    driver = GraphDatabase.driver(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )
    try:
        driver.verify_connectivity()
        logger.info("Terhubung ke Neo4j: %s", config.NEO4J_URI)
        with driver.session(database=config.NEO4J_DATABASE) as session:
            create_schema(session)
            load_dimensions(session, dimensions)
            load_cards(session, cards)
            load_edges(session, edges)
            total = session.run(
                "MATCH (c:Card) RETURN count(c) AS n"
            ).single()["n"]
            logger.info("Selesai. Total Card di graph: %d", total)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
