"""Skema collection Qdrant dan payload untuk kartu LoR."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from qdrant_client import QdrantClient, models

from src.common import config
from src.vector.text import (
    EMBEDDING_TEMPLATE_VERSION,
    build_embedding_text,
    clean_keyword_refs,
    clean_keywords,
    embedding_text_hash,
)

# Namespace tetap agar UUID untuk cardCode selalu sama antar-run.
POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "runeterra-rag/cards")

DISTANCE = models.Distance.COSINE

# Payload yang perlu index agar filter tidak melakukan full scan.
PAYLOAD_INDEXES: dict[str, models.PayloadSchemaType] = {
    "type": models.PayloadSchemaType.KEYWORD,
    "supertype": models.PayloadSchemaType.KEYWORD,
    "set": models.PayloadSchemaType.KEYWORD,
    "rarity": models.PayloadSchemaType.KEYWORD,
    "text_status": models.PayloadSchemaType.KEYWORD,
    "regions": models.PayloadSchemaType.KEYWORD,
    "keywords": models.PayloadSchemaType.KEYWORD,
    "keyword_refs": models.PayloadSchemaType.KEYWORD,
    "subtypes": models.PayloadSchemaType.KEYWORD,
    "formats": models.PayloadSchemaType.KEYWORD,
    "cost": models.PayloadSchemaType.INTEGER,
    "attack": models.PayloadSchemaType.INTEGER,
    "health": models.PayloadSchemaType.INTEGER,
    "collectible": models.PayloadSchemaType.BOOL,
    "has_native_text": models.PayloadSchemaType.BOOL,
    "has_embedding_text": models.PayloadSchemaType.BOOL,
}


def point_id(card_code: str) -> str:
    """UUID deterministik untuk satu cardCode."""
    return str(uuid.uuid5(POINT_NAMESPACE, card_code))


def build_payload(
    card: Mapping[str, Any],
    embedding_text: str | None = None,
    *,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    """Payload Qdrant minimal yang cukup untuk filter dan context builder."""
    code = str(card.get("cardCode") or card.get("card_code") or "")
    text = embedding_text if embedding_text is not None else build_embedding_text(card)

    payload: dict[str, Any] = {
        "card_code": code,
        "name": card.get("name") or "",
        "type": card.get("type") or "",
        "regions": list(card.get("regions") or []),
        "keywords": clean_keywords(card),
        "keyword_refs": clean_keyword_refs(card),
        "subtypes": list(card.get("subtypes") or []),
        "formats": list(card.get("formats") or []),
        "collectible": bool(card.get("collectible", False)),
        "has_native_text": bool(card.get("hasNativeText", False)),
        "has_embedding_text": bool(text.strip()),
        "text_status": card.get("textStatus") or "unknown",
        "embedding_model": embedding_model or config.EMBEDDING_MODEL,
        "embedding_template_version": EMBEDDING_TEMPLATE_VERSION,
        "text_hash": embedding_text_hash(text),
    }

    optional = {
        "supertype": card.get("supertype"),
        "set": card.get("set"),
        "set_display_name": card.get("setDisplayName"),
        "rarity": card.get("rarity"),
        "cost": card.get("cost"),
        "attack": card.get("attack"),
        "health": card.get("health"),
        "patch": card.get("patch"),
    }
    for key, value in optional.items():
        if value is not None and value != "":
            payload[key] = value

    return payload


def ensure_collection(
    client: QdrantClient,
    *,
    recreate: bool = False,
    collection_name: str | None = None,
    vector_size: int | None = None,
) -> str:
    """Buat collection dan payload index jika belum ada."""
    name = collection_name or config.QDRANT_COLLECTION
    size = vector_size or config.EMBEDDING_DIM

    if recreate and client.collection_exists(name):
        client.delete_collection(name)

    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=size, distance=DISTANCE),
        )

    existing = set(client.get_collection(name).payload_schema or {})
    for field_name, field_schema in PAYLOAD_INDEXES.items():
        if field_name in existing:
            continue
        client.create_payload_index(
            collection_name=name,
            field_name=field_name,
            field_schema=field_schema,
        )

    return name
