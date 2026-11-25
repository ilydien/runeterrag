"""Vector search Qdrant untuk hybrid retrieval."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Mapping
from typing import Any

from qdrant_client import QdrantClient, models

from src.common import config
from src.vector.load import get_client, get_model

logger = logging.getLogger(__name__)

_SCALAR_FIELDS = {
    "type": "type",
    "supertype": "supertype",
    "set": "set",
    "rarity": "rarity",
    "text_status": "text_status",
}

_LIST_FIELDS = {
    "region": "regions",
    "keyword": "keywords",
    "subtype": "subtypes",
    "format": "formats",
}

_BOOL_FIELDS = {
    "collectible": "collectible",
    "has_text": "has_native_text",
    "has_native_text": "has_native_text",
    "has_embedding_text": "has_embedding_text",
}

_RANGE_FIELDS = {
    "min_cost": ("cost", "gte"),
    "max_cost": ("cost", "lte"),
    "min_attack": ("attack", "gte"),
    "max_attack": ("attack", "lte"),
    "min_health": ("health", "gte"),
    "max_health": ("health", "lte"),
}


def build_qdrant_filter(
    filters: Mapping[str, Any] | None,
) -> models.Filter | None:
    """Terjemahkan filter graph ke Qdrant.

    Semantik MVP mengikuti graph:
    - ``region`` dan ``keyword`` singular berarti match salah satu nilai;
    - filter berbeda digabung dengan AND;
    - ``text`` sengaja diabaikan karena itu tanggung jawab graph.
    """
    if not filters:
        return None

    must: list[models.Condition] = []
    seen_fields: set[str] = set()

    for key, field in _SCALAR_FIELDS.items():
        value = filters.get(key)
        if value is not None and value != "" and field not in seen_fields:
            must.append(
                models.FieldCondition(
                    key=field,
                    match=models.MatchValue(value=value),
                )
            )
            seen_fields.add(field)

    for key, field in _LIST_FIELDS.items():
        value = filters.get(key)
        if value and field not in seen_fields:
            must.append(
                models.FieldCondition(
                    key=field,
                    match=models.MatchAny(any=[value]),
                )
            )
            seen_fields.add(field)

    for key, field in _BOOL_FIELDS.items():
        value = filters.get(key)
        if value is not None and field not in seen_fields:
            must.append(
                models.FieldCondition(
                    key=field,
                    match=models.MatchValue(value=bool(value)),
                )
            )
            seen_fields.add(field)

    range_values: dict[str, float | int] = {}
    for key, (field, operator) in _RANGE_FIELDS.items():
        value = filters.get(key)
        if value is not None:
            range_values.setdefault(field, {})[operator] = value
    for field, bounds in range_values.items():
        must.append(
            models.FieldCondition(
                key=field,
                range=models.Range(**bounds),
            )
        )

    ignored = {
        key
        for key in filters
        if key not in _SCALAR_FIELDS
        and key not in _LIST_FIELDS
        and key not in _BOOL_FIELDS
        and key not in _RANGE_FIELDS
        and key != "text"
    }
    if ignored:
        logger.debug("Filter tidak dikenal di vector search: %s", sorted(ignored))

    return models.Filter(must=must) if must else None


def _encode_query(model, query: str) -> list[float]:
    vector = model.encode(
        [f"query: {query}"],
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]
    return vector.tolist() if hasattr(vector, "tolist") else list(vector)


def _query_points(
    client: QdrantClient,
    *,
    collection_name: str,
    vector: list[float],
    query_filter: models.Filter | None,
    top_k: int,
):
    if hasattr(client, "query_points"):
        return client.query_points(
            collection_name=collection_name,
            query=vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        ).points
    return client.search(
        collection_name=collection_name,
        query_vector=vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )


def vector_search(
    query: str,
    filters: Mapping[str, Any] | None = None,
    top_k: int = 10,
    *,
    client: QdrantClient | None = None,
    model: Any | None = None,
) -> list[dict[str, Any]]:
    """Cari kartu secara semantik.

    Hasil sudah diurutkan berdasarkan cosine similarity dan dideduplikasi
    berdasarkan ``card_code``. ``score`` adalah skor cosine asli, bukan skor RRF.
    """
    if not query.strip():
        return []

    active_model = model or get_model(config.EMBEDDING_MODEL)
    active_client = client or get_client()
    vector = _encode_query(active_model, query)
    points = _query_points(
        active_client,
        collection_name=config.QDRANT_COLLECTION,
        vector=vector,
        query_filter=build_qdrant_filter(filters),
        top_k=max(1, int(top_k)),
    )

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for point in points:
        payload = dict(point.payload or {})
        card_code = payload.get("card_code")
        if not card_code or card_code in seen:
            continue
        seen.add(card_code)
        results.append(
            {
                "card_code": card_code,
                "score": float(point.score),
                **payload,
            }
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test vector search.")
    parser.add_argument("query", help="Pertanyaan atau frasa pencarian.")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--qdrant-url", default=config.QDRANT_URL)
    parser.add_argument("--json", action="store_true", help="Cetak JSON penuh.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    args = parse_args(argv)
    results = vector_search(
        args.query,
        top_k=args.top_k,
        client=get_client(args.qdrant_url),
    )
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    for rank, result in enumerate(results, start=1):
        print(
            f"{rank:>2}. {result.get('card_code')} "
            f"{result.get('name')} "
            f"({result.get('type')}, {result.get('regions')}) "
            f"score={result.get('score'):.4f}"
        )


if __name__ == "__main__":
    main()
