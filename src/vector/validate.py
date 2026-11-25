"""Validasi collection Qdrant terhadap artifact cards.jsonl.

Jalankan:
    python -m src.vector.validate

Exit code 0 jika jumlah, identitas, dan payload konsisten.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from qdrant_client import QdrantClient

from src.common import config
from src.vector.load import get_client, load_cards

logger = logging.getLogger(__name__)


def scroll_payloads(
    client: QdrantClient,
    collection_name: str,
    *,
    batch_size: int = 256,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        payloads.extend(dict(point.payload or {}) for point in points)
        if offset is None:
            break
    return payloads


def validate(
    client: QdrantClient,
    *,
    collection_name: str,
    source_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    payloads = scroll_payloads(client, collection_name)
    stored_codes = [
        str(payload.get("card_code"))
        for payload in payloads
        if payload.get("card_code")
    ]
    source_codes = {
        str(card.get("cardCode")) for card in source_cards if card.get("cardCode")
    }

    problems: list[str] = []

    if len(stored_codes) != len(source_codes):
        problems.append(
            f"Jumlah point {len(stored_codes)} != jumlah kartu {len(source_codes)}"
        )
    if len(stored_codes) != len(set(stored_codes)):
        problems.append("Ada card_code duplikat di collection")
    missing = source_codes - set(stored_codes)
    extra = set(stored_codes) - source_codes
    if missing:
        problems.append(f"Kartu hilang dari Qdrant: {len(missing)}")
    if extra:
        problems.append(f"Point tidak ada di sumber: {len(extra)}")
    if any(not payload.get("has_embedding_text") for payload in payloads):
        problems.append("Ada point tanpa has_embedding_text=true")
    if any(
        "Missing Translation" in (payload.get("keywords") or [])
        or "Missing Translation" in (payload.get("keyword_refs") or [])
        for payload in payloads
    ):
        problems.append("Masih ada Missing Translation di payload keyword")

    report = {
        "collection": collection_name,
        "source_cards": len(source_cards),
        "points": len(stored_codes),
        "missing": len(missing),
        "extra": len(extra),
        "problems": problems,
        "passed": not problems,
    }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validasi collection Qdrant.")
    parser.add_argument("--collection", default=config.QDRANT_COLLECTION)
    parser.add_argument("--qdrant-url", default=config.QDRANT_URL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = parse_args(argv)
    cards = load_cards()
    report = validate(
        get_client(args.qdrant_url),
        collection_name=args.collection,
        source_cards=cards,
    )
    for key, value in report.items():
        logger.info("%s: %s", key, value)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
