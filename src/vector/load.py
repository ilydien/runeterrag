"""Stub Vector Ingestion (tugas Yuda).

File ini sengaja hanya menyediakan kontrak awal:
- membaca ``data/processed/cards.jsonl`` (sumber yang sama dengan graph),
- menyusun ``embedding_text`` sesuai kesepakatan,
- placeholder untuk pembuatan collection + upsert ke Qdrant.

Ganti ``main`` dengan implementasi embedding yang sebenarnya.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.common import config

logger = logging.getLogger(__name__)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} belum ada. Jalankan `python -m src.graph.extract` dulu."
        )
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_embedding_text(card: dict[str, Any]) -> str:
    """Spesifikasi teks embedding yang disepakati tim.

    Untuk 183 kartu tanpa teks native, tetap dihasilkan teks atribut
    (nama, keyword, region) agar tidak ada kartu yang tanpa vektor.
    """
    parts = [
        card.get("name", ""),
        card.get("descriptionRaw", ""),
        card.get("levelupDescriptionRaw", ""),
        card.get("flavorText", ""),
        ", ".join(card.get("keywords", [])),
        ", ".join(card.get("regions", [])),
    ]
    return " | ".join(part.strip() for part in parts if part and part.strip())


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    cards = read_jsonl(config.PROCESSED_DIR / "cards.jsonl")
    logger.info("Cards terbaca: %d", len(cards))
    logger.info("Contoh embedding_text:")
    logger.info("%s", build_embedding_text(cards[0]))
    raise SystemExit(
        "Vector ingestion belum diimplementasikan (tugas Yuda). "
        "Lihat docs/kontrak-integrasi.md untuk payload Qdrant."
    )


if __name__ == "__main__":
    main()
