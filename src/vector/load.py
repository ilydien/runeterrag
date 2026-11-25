"""Vector ingestion kartu LoR ke Qdrant.

Alur:
1. Baca ``data/processed/cards.jsonl`` dari pipeline graph.
2. Bangun teks embedding berlabel.
3. Encode dengan model E5 (prefix ``passage:``).
4. Upsert ke collection Qdrant dengan UUID deterministik.
5. Tulis manifest ingestion.

Contoh:
    python -m src.vector.load --recreate
    python -m src.vector.load --limit 100 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from src.common import config
from src.vector import schema
from src.vector.text import (
    EMBEDDING_TEMPLATE_VERSION,
    build_embedding_text,
)

logger = logging.getLogger(__name__)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def ensure_processed() -> Path:
    """Pastikan ``cards.jsonl`` tersedia, tanpa membutuhkan Neo4j."""
    cards_path = config.PROCESSED_DIR / "cards.jsonl"
    if cards_path.exists():
        return cards_path

    logger.info("cards.jsonl belum ada; menjalankan ekstraksi graph...")
    from src.graph.extract import extract_all, write_outputs

    write_outputs(extract_all())
    return cards_path


def load_cards(limit: int | None = None) -> list[dict[str, Any]]:
    path = ensure_processed()
    cards = read_jsonl(path)
    if limit is not None:
        cards = cards[: max(0, limit)]
    if not cards:
        raise ValueError("Tidak ada kartu untuk di-ingest.")
    return cards


def build_records(
    cards: Iterable[Mapping[str, Any]],
    *,
    embedding_model: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for card in cards:
        code = str(card.get("cardCode") or "")
        if not code:
            raise ValueError(f"Kartu tanpa cardCode: {card!r}")
        text = build_embedding_text(card)
        payload = schema.build_payload(
            card,
            text,
            embedding_model=embedding_model,
        )
        records.append(
            {
                "id": schema.point_id(code),
                "card_code": code,
                "text": text,
                "payload": payload,
            }
        )
    return records


def batched(rows: list[Any], size: int) -> Iterable[list[Any]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


@lru_cache(maxsize=4)
def get_client(url: str | None = None) -> QdrantClient:
    return QdrantClient(url=url or config.QDRANT_URL)


@lru_cache(maxsize=4)
def get_model(model_name: str, device: str | None = None):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


def embed_passages(
    model,
    texts: list[str],
    *,
    batch_size: int,
) -> list[list[float]]:
    prefixed = [f"passage: {text}" for text in texts]
    vectors = model.encode(
        prefixed,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [vector.tolist() if hasattr(vector, "tolist") else list(vector) for vector in vectors]


def upsert_records(
    client: QdrantClient,
    collection_name: str,
    records: list[dict[str, Any]],
    vectors: list[list[float]],
    *,
    batch_size: int,
) -> None:
    points = [
        models.PointStruct(
            id=record["id"],
            vector=vector,
            payload=record["payload"],
        )
        for record, vector in zip(records, vectors, strict=True)
    ]
    for batch in batched(points, batch_size):
        client.upsert(
            collection_name=collection_name,
            points=batch,
            wait=True,
        )


def write_manifest(
    *,
    cards: list[dict[str, Any]],
    collection_name: str,
    embedding_model: str,
    vector_size: int,
    total_points: int,
) -> Path:
    patches = sorted(
        {str(card.get("patch")) for card in cards if card.get("patch")}
    )
    manifest = {
        "source": "data/processed/cards.jsonl",
        "source_patch": ", ".join(patches),
        "collection": collection_name,
        "embedding_model": embedding_model,
        "vector_size": vector_size,
        "distance": "Cosine",
        "embedding_template_version": EMBEDDING_TEMPLATE_VERSION,
        "total_points": total_points,
        "created_at": datetime.now(UTC).isoformat(),
    }
    path = config.PROCESSED_DIR / "vector_manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Manifest ditulis ke %s", path)
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Embedding kartu LoR ke Qdrant."
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Hapus dan buat ulang collection sebelum ingest.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Batasi jumlah kartu (untuk smoke test). Tanpa --recreate, "
            "point lama di collection tidak dihapus."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch encoding model (default: 32).",
    )
    parser.add_argument(
        "--upsert-batch-size",
        type=int,
        default=256,
        help="Batch upsert Qdrant (default: 256).",
    )
    parser.add_argument(
        "--model",
        default=config.EMBEDDING_MODEL,
        help="Nama model SentenceTransformers.",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Device model, mis. cpu atau cuda.",
    )
    parser.add_argument(
        "--collection",
        default=config.QDRANT_COLLECTION,
        help="Nama collection Qdrant.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=config.QDRANT_URL,
        help="URL Qdrant (default dari QDRANT_URL).",
    )
    parser.add_argument(
        "--vector-size",
        type=int,
        default=config.EMBEDDING_DIM,
        help="Dimensi vector collection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Bangun teks dan payload tanpa model atau Qdrant.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = parse_args(argv)

    cards = load_cards(args.limit)
    records = build_records(cards, embedding_model=args.model)
    logger.info(
        "Kartu: %d | teks kosong: %d | collection: %s",
        len(records),
        sum(1 for record in records if not record["text"].strip()),
        args.collection,
    )

    if args.dry_run:
        for record in records[:3]:
            logger.info(
                "Contoh %s:\n%s\n---",
                record["card_code"],
                record["text"],
            )
        logger.info("Dry-run selesai; Qdrant tidak disentuh.")
        return

    if args.limit is not None and not args.recreate:
        logger.warning(
            "--limit tanpa --recreate hanya meng-upsert subset; "
            "point lama di collection tidak dihapus."
        )

    started = time.perf_counter()
    model = get_model(args.model, args.device)
    dimension_getter = getattr(model, "get_embedding_dimension", None)
    if dimension_getter is None:
        dimension_getter = getattr(model, "get_sentence_embedding_dimension", None)
    model_dim = dimension_getter() if dimension_getter else None
    if model_dim is not None and int(model_dim) != args.vector_size:
        raise ValueError(
            f"Dimensi model {model_dim} tidak sama dengan "
            f"--vector-size {args.vector_size}."
        )

    client = get_client(args.qdrant_url)
    collection_name = schema.ensure_collection(
        client,
        recreate=args.recreate,
        collection_name=args.collection,
        vector_size=args.vector_size,
    )

    vectors = embed_passages(
        model,
        [record["text"] for record in records],
        batch_size=args.batch_size,
    )
    upsert_records(
        client,
        collection_name,
        records,
        vectors,
        batch_size=args.upsert_batch_size,
    )

    total = client.count(collection_name=collection_name, exact=True).count
    write_manifest(
        cards=cards,
        collection_name=collection_name,
        embedding_model=args.model,
        vector_size=args.vector_size,
        total_points=int(total),
    )
    elapsed = time.perf_counter() - started
    logger.info(
        "Selesai. Points=%d | collection=%s | waktu=%.2fs",
        total,
        collection_name,
        elapsed,
    )


if __name__ == "__main__":
    main()
