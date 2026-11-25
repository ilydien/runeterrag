"""Representasi teks untuk embedding kartu LoR.

Graph memakai ``cardCode`` sebagai identitas dan relasi eksplisit. Modul ini
hanya membangun representasi teks yang mudah dipahami model embedding, tanpa
mengubah artifact graph.

Prinsip:
- teks berlabel, bukan pipe-separated;
- atribut yang tidak berlaku tidak dipaksakan menjadi nol;
- ``Missing Translation`` dibersihkan dari keyword sebelum embedding;
- flavor text tetap di graph, tetapi tidak di-embed pada versi v1.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

MISSING_TRANSLATION = "Missing Translation"
EMBEDDING_TEMPLATE_VERSION = "v1"

_WHITESPACE_RE = re.compile(r"\s+")
_MISSING_TRANSLATION_RE = re.compile(
    re.escape(MISSING_TRANSLATION), re.IGNORECASE
)


def clean_text(value: str | None) -> str | None:
    """Bersihkan satu field teks dan buang placeholder lokalisasi.

    Nilai yang kosong atau hanya berisi ``Missing Translation`` dianggap tidak
    tersedia. Jika placeholder muncul di tengah teks, token tersebut dibuang
    tanpa membuang sisa teks yang valid.
    """
    if not value:
        return None
    text = _MISSING_TRANSLATION_RE.sub(" ", str(value))
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text or None


def _clean_string_list(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item == MISSING_TRANSLATION:
            continue
        if item not in result:
            result.append(item)
    return result


def clean_keywords(card: Mapping[str, Any]) -> list[str]:
    """Ambil keyword yang valid dari kartu, tanpa placeholder.

    ``keywords`` adalah nilai lokal yang dipakai untuk teks. ``keywordRefs``
    tidak dipakai untuk embedding karena merupakan identifier, bukan teks
    semantik.
    """
    return _clean_string_list(card.get("keywords"))


def clean_keyword_refs(card: Mapping[str, Any]) -> list[str]:
    """Versi bersih dari ``keywordRefs`` untuk payload audit, bukan embedding."""
    return _clean_string_list(card.get("keywordRefs"))


def _join(values: list[str]) -> str | None:
    cleaned = [value for value in values if value]
    return ", ".join(cleaned) if cleaned else None


def _int_value(card: Mapping[str, Any], key: str) -> int | None:
    value = card.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_embedding_text(card: Mapping[str, Any]) -> str:
    """Bangun teks berlabel untuk satu kartu.

    Contoh unit:
        Card: Yasuo
        Type: Unit
        Supertype: Champion
        Region: Ionia
        Keywords: Quick Attack
        Cost: 4
        Stats: 5 Attack, 4 Health
        Description: ...

    Kartu tanpa teks tetap mendapat representasi dari atribut terstruktur.
    """
    lines: list[str] = []

    name = clean_text(card.get("name"))
    if name:
        lines.append(f"Card: {name}")

    card_type = clean_text(card.get("type"))
    if card_type:
        lines.append(f"Type: {card_type}")

    supertype = clean_text(card.get("supertype"))
    if supertype:
        lines.append(f"Supertype: {supertype}")

    regions = [value for value in (card.get("regions") or []) if value]
    if regions:
        label = "Region" if len(regions) == 1 else "Regions"
        lines.append(f"{label}: {', '.join(regions)}")

    subtypes = [value for value in (card.get("subtypes") or []) if value]
    if subtypes:
        lines.append(f"Subtypes: {', '.join(subtypes)}")

    keywords = clean_keywords(card)
    lines.append(f"Keywords: {', '.join(keywords) if keywords else 'None'}")

    cost = _int_value(card, "cost")
    if cost is not None:
        lines.append(f"Cost: {cost}")

    attack = _int_value(card, "attack")
    health = _int_value(card, "health")
    if card_type == "Unit" and attack is not None and health is not None:
        lines.append(f"Stats: {attack} Attack, {health} Health")
    elif card_type == "Equipment" and attack is not None and health is not None:
        # Pada Data Dragon, attack/health Equipment adalah bonus, bukan stat unit.
        if attack != 0 or health != 0:
            lines.append(f"Bonus Stats: +{attack}/+{health}")

    description = clean_text(card.get("descriptionRaw"))
    if description:
        lines.append(f"Description: {description}")
    else:
        lines.append("Card Description: No native card description available.")

    levelup = clean_text(card.get("levelupDescriptionRaw"))
    if levelup:
        lines.append(f"Level-up Condition: {levelup}")

    return "\n".join(lines).strip()


def embedding_text_hash(text: str) -> str:
    """Hash teks embedding untuk deteksi perubahan dan incremental ingestion."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def has_embedding_text(card: Mapping[str, Any]) -> bool:
    """Apakah kartu menghasilkan teks embedding yang tidak kosong."""
    return bool(build_embedding_text(card).strip())
