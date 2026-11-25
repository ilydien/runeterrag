"""Ekstraksi dataset LoR ``latest`` menjadi node/edge siap Neo4j.

Pipeline:
1. Baca ``data/latest/set*-en_us.json`` + ``globals-en_us.json``.
2. Normalisasi teks dan tandai status teks.
3. Bangun node Card + node dimensi.
4. Bangun edge eksplisit + relasi hasil parsing markup.
5. Tulis JSONL ke ``PROCESSED_DIR`` untuk dipakai loader dan tim lain.

Jalankan:
    python -m src.graph.extract
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common import config
from src.common.models import CardRecord, DimensionNode, EdgeRecord
from src.common.text import (
    LINK_KEYWORD_RE,
    LINK_VOCAB_RE,
    extract_card_links,
    extract_link_targets,
    normalize_name,
    singularize,
    strip_markup,
    text_status,
)

logger = logging.getLogger(__name__)

CARD_CODE_RE = re.compile(r"^(\d{2})([A-Z]{2})(\d{3})(T\d+)?$")
ASSET_PATCH_RE = re.compile(r"pvp\.net/([^/]+)/")


@dataclass
class ExtractionResult:
    cards: list[CardRecord]
    dimensions: list[DimensionNode]
    edges: list[EdgeRecord]
    aliases: dict[str, Any]
    stats: dict[str, Any]
    unresolved: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def edges_by_rel(self, rel: str) -> list[EdgeRecord]:
        return [edge for edge in self.edges if edge.rel == rel]

    def edge_count(self, rel: str) -> int:
        return len(self.edges_by_rel(rel))

    def mention_count(self, rel: str) -> int:
        return sum(int(edge.props.get("count", 1)) for edge in self.edges_by_rel(rel))


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_latest_cards() -> list[dict[str, Any]]:
    files = sorted(config.LATEST_DIR.glob("set*-en_us.json"))
    if not files:
        raise FileNotFoundError(f"Tidak ada file set di {config.LATEST_DIR}")

    cards: list[dict[str, Any]] = []
    for path in files:
        payload = read_json(path)
        if not isinstance(payload, list):
            raise ValueError(f"Format file tidak valid (harus list): {path}")
        cards.extend(payload)
    return cards


def load_globals() -> dict[str, Any]:
    if not config.GLOBALS_FILE.exists():
        raise FileNotFoundError(f"File globals tidak ditemukan: {config.GLOBALS_FILE}")
    return read_json(config.GLOBALS_FILE)


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------
def code_family(card_code: str) -> str:
    """Kode keluarga tanpa suffix T (mis. 01IO015T1 -> 01IO015)."""
    return re.sub(r"T\d+$", "", card_code)


def is_t_form(card_code: str) -> bool:
    match = CARD_CODE_RE.match(card_code)
    return bool(match and match.group(4))


def is_base_champion(card: dict[str, Any]) -> bool:
    return (
        card.get("supertype") == "Champion"
        and card.get("type") == "Unit"
        and not is_t_form(card["cardCode"])
    )


def infer_role(source: dict[str, Any], target: dict[str, Any]) -> str:
    """Inferensi role edge ASSOCIATED_WITH dari tipe dan keluarga kode."""
    src_code = source["cardCode"]
    dst_code = target["cardCode"]
    same_family = code_family(src_code) == code_family(dst_code)
    both_champion = (
        source.get("supertype") == "Champion"
        and target.get("supertype") == "Champion"
    )

    if same_family and both_champion:
        if not is_t_form(src_code) and target.get("type") == "Unit":
            return "LEVELS_INTO"
        if not is_t_form(src_code) and target.get("type") == "Spell":
            return "CHAMPION_SPELL"
        if is_t_form(src_code) and not is_t_form(dst_code):
            return "BACKREF_BASE"
        return "SAME_FAMILY"

    return {
        "Ability": "SKILL",
        "Unit": "TOKEN_OR_UNIT",
        "Landmark": "LANDMARK",
        "Trap": "TRAP",
        "Equipment": "EQUIPMENT",
        "Spell": "SPELL",
    }.get(target.get("type", ""), "OTHER")


# ---------------------------------------------------------------------------
# Lookup & mentions
# ---------------------------------------------------------------------------
def _lookup_keys(value: str | None) -> set[str]:
    normalized = normalize_name(value)
    if not normalized:
        return set()
    return {normalized, normalized.replace(" ", "")}


def _unique(values: list[str]) -> list[str]:
    """Dedupe sambil mempertahankan urutan (mis. Spirit x2 di 09DE033)."""
    return list(dict.fromkeys(values))


def build_keyword_lookup(globals_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entry in globals_data.get("keywords", []):
        for raw in (entry.get("name"), entry.get("nameRef")):
            for key in _lookup_keys(raw):
                lookup[key] = entry
    return lookup


def build_vocab_lookup(globals_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for entry in globals_data.get("vocabTerms", []):
        for raw in (entry.get("name"), entry.get("nameRef")):
            for key in _lookup_keys(raw):
                lookup[key] = entry
    return lookup


def resolve_keyword(target: str, lookup: dict[str, dict[str, Any]]) -> str | None:
    for key in _lookup_keys(target):
        entry = lookup.get(key)
        if entry:
            return entry.get("name") or target
    return None


def resolve_vocab(target: str, lookup: dict[str, dict[str, Any]]) -> str | None:
    for key in _lookup_keys(target):
        entry = lookup.get(key)
        if entry:
            return entry.get("name") or target
    return None


def _choose_assoc_candidate(
    candidates: list[str],
    link_key: str,
    source_code: str,
    card_by_code: dict[str, dict[str, Any]],
) -> str:
    if len(candidates) == 1:
        return candidates[0]

    key = (link_key or "").lower()
    base = code_family(source_code)

    if key in {"level1", "me", "selfref"}:
        if base in candidates:
            return base
        if source_code in candidates:
            return source_code

    if key in {"summon", "create", "transform", "shuffle", "cast"}:
        non_champion = [
            code
            for code in candidates
            if card_by_code[code].get("supertype") != "Champion"
        ]
        if non_champion:
            return non_champion[0]

    if base in candidates:
        return base
    return candidates[0]


def _resolve_card_target(
    source_code: str,
    link_key: str,
    display_name: str,
    by_name: dict[str, set[str]],
    assoc_by_name: dict[str, dict[str, set[str]]],
    card_by_code: dict[str, dict[str, Any]],
) -> tuple[str | None, str | None]:
    key = normalize_name(display_name)
    singular = singularize(display_name)
    link_lower = (link_key or "").lower()

    # card.me / card.selfRef selalu menunjuk kartu sumber.
    if link_lower in {"me", "selfref"} and source_code in card_by_code:
        return source_code, "self_reference"

    assoc = assoc_by_name.get(source_code, {})
    candidates = sorted(assoc.get(key, set()) | assoc.get(singular, set()))
    if candidates:
        return (
            _choose_assoc_candidate(candidates, link_key, source_code, card_by_code),
            "associated_ref",
        )

    global_candidates = sorted(by_name.get(key, set()) | by_name.get(singular, set()))
    if len(global_candidates) == 1:
        return global_candidates[0], "global_unique"

    # Ambiguitas nama global (mis. 10 kartu "Lucky Find") sengaja tidak
    # dipaksa resolve agar tidak membuat edge yang salah.
    return None, None


def collect_mentions(
    cards: list[dict[str, Any]],
    card_by_code: dict[str, dict[str, Any]],
    keyword_lookup: dict[str, dict[str, Any]],
    vocab_lookup: dict[str, dict[str, Any]],
) -> tuple[
    list[tuple[str, str, str, str, str]],
    list[tuple[str, str]],
    list[tuple[str, str]],
    dict[str, list[dict[str, Any]]],
]:
    by_name: dict[str, set[str]] = defaultdict(set)
    for card in cards:
        code = card["cardCode"]
        for key in _lookup_keys(card.get("name")) | {singularize(card.get("name"))}:
            if key:
                by_name[key].add(code)

    assoc_by_name: dict[str, dict[str, set[str]]] = {}
    for card in cards:
        mapping: dict[str, set[str]] = defaultdict(set)
        for ref in card.get("associatedCardRefs", []):
            target = card_by_code.get(ref)
            if not target:
                continue
            for key in _lookup_keys(target.get("name")) | {
                singularize(target.get("name"))
            }:
                if key:
                    mapping[key].add(ref)
        assoc_by_name[card["cardCode"]] = mapping

    card_mentions: list[tuple[str, str, str, str, str]] = []
    keyword_mentions: list[tuple[str, str]] = []
    vocab_mentions: list[tuple[str, str]] = []
    unresolved: dict[str, list[dict[str, Any]]] = {
        "cards": [],
        "keywords": [],
        "vocab": [],
    }

    for card in cards:
        code = card["cardCode"]
        text = " ".join(
            filter(
                None,
                [
                    card.get("description", "") or "",
                    card.get("levelupDescription", "") or "",
                ],
            )
        )

        for link_key, display_name in extract_card_links(text):
            target, confidence = _resolve_card_target(
                code, link_key, display_name, by_name, assoc_by_name, card_by_code
            )
            if target:
                card_mentions.append(
                    (code, target, link_key, display_name, confidence or "resolved")
                )
            else:
                unresolved["cards"].append(
                    {"src": code, "linkKey": link_key, "name": display_name}
                )

        for target in extract_link_targets(text, LINK_KEYWORD_RE):
            canonical = resolve_keyword(target, keyword_lookup)
            if canonical:
                keyword_mentions.append((code, canonical))
            else:
                unresolved["keywords"].append({"src": code, "target": target})

        for target in extract_link_targets(text, LINK_VOCAB_RE):
            canonical = resolve_vocab(target, vocab_lookup)
            if canonical:
                vocab_mentions.append((code, canonical))
            else:
                unresolved["vocab"].append({"src": code, "target": target})

    return card_mentions, keyword_mentions, vocab_mentions, unresolved


# ---------------------------------------------------------------------------
# Build records
# ---------------------------------------------------------------------------
def build_card_records(
    cards: list[dict[str, Any]], globals_data: dict[str, Any]
) -> list[CardRecord]:
    set_names = {
        entry.get("nameRef"): entry.get("name")
        for entry in globals_data.get("sets", [])
    }

    records: list[CardRecord] = []
    for card in cards:
        code = card["cardCode"]
        description = card.get("description", "") or ""
        raw_source = card.get("descriptionRaw", "") or ""
        raw = strip_markup(raw_source)
        status = text_status(description, raw_source)

        asset = (card.get("assets") or [{}])[0] or {}
        asset_game = asset.get("gameAbsolutePath", "") or ""
        patch_match = ASSET_PATCH_RE.search(asset_game)
        set_ref = card.get("set", "") or ""

        records.append(
            CardRecord(
                cardCode=code,
                name=card.get("name", "") or "",
                type=card.get("type", "") or "",
                supertype=card.get("supertype", "") or "",
                cost=int(card.get("cost", 0) or 0),
                attack=int(card.get("attack", 0) or 0),
                health=int(card.get("health", 0) or 0),
                rarity=card.get("rarity", "") or "",
                rarityRef=card.get("rarityRef", "") or "",
                setRef=set_ref,
                setDisplayName=set_names.get(set_ref, set_ref),
                collectible=bool(card.get("collectible", False)),
                regions=list(card.get("regions", []) or []),
                regionRefs=list(card.get("regionRefs", []) or []),
                keywords=_unique(list(card.get("keywords", []) or [])),
                keywordRefs=_unique(list(card.get("keywordRefs", []) or [])),
                subtypes=list(card.get("subtypes", []) or []),
                spellSpeed=card.get("spellSpeed", "") or "",
                spellSpeedRef=card.get("spellSpeedRef", "") or "",
                descriptionRaw=raw,
                descriptionMarkup=description,
                levelupDescriptionRaw=strip_markup(
                    card.get("levelupDescriptionRaw", "") or ""
                ),
                levelupDescriptionMarkup=card.get("levelupDescription", "") or "",
                flavorText=strip_markup(card.get("flavorText", "") or ""),
                artistName=card.get("artistName", "") or "",
                formats=list(card.get("formats", []) or []),
                formatRefs=list(card.get("formatRefs", []) or []),
                hasNativeText=bool(raw),
                textStatus=status,
                textPlaceholder=(status == "placeholder"),
                level1TextMissing=is_base_champion(card) and not raw,
                patch=patch_match.group(1) if patch_match else config.DEFAULT_PATCH,
                assetGame=asset_game,
                assetFull=asset.get("fullAbsolutePath", "") or "",
                cardFamily=code_family(code),
                isChampion=(card.get("supertype") == "Champion"),
                isBaseChampion=is_base_champion(card),
            )
        )
    return records


def build_dimensions(
    cards: list[dict[str, Any]],
    globals_data: dict[str, Any],
    keyword_mentions: list[tuple[str, str]],
    vocab_mentions: list[tuple[str, str]],
) -> list[DimensionNode]:
    dimensions: list[DimensionNode] = []

    # Region
    region_entries = {
        entry.get("name"): entry for entry in globals_data.get("regions", [])
    }
    used_regions = sorted(
        {region for card in cards for region in card.get("regions", [])}
    )
    for name in used_regions:
        entry = region_entries.get(name, {})
        dimensions.append(
            DimensionNode(
                "Region",
                name,
                {
                    "nameRef": entry.get("nameRef", name),
                    "abbreviation": entry.get("abbreviation", ""),
                    "icon": entry.get("iconAbsolutePath") or "",
                },
            )
        )

    # Keyword
    keyword_entries: dict[str, dict[str, Any]] = {}
    for entry in globals_data.get("keywords", []):
        for raw in (entry.get("name"), entry.get("nameRef")):
            for key in _lookup_keys(raw):
                keyword_entries[key] = entry

    used_keywords = {kw for card in cards for kw in card.get("keywords", [])}
    used_keywords.update(keyword for _, keyword in keyword_mentions)
    for name in sorted(used_keywords):
        entry = keyword_entries.get(normalize_name(name)) or keyword_entries.get(
            normalize_name(name).replace(" ", ""), {}
        )
        dimensions.append(
            DimensionNode(
                "Keyword",
                name,
                {
                    "nameRef": entry.get("nameRef", name),
                    "description": entry.get("description", ""),
                },
            )
        )

    # VocabTerm
    vocab_entries: dict[str, dict[str, Any]] = {}
    for entry in globals_data.get("vocabTerms", []):
        for raw in (entry.get("name"), entry.get("nameRef")):
            for key in _lookup_keys(raw):
                vocab_entries[key] = entry

    used_vocab = {term for _, term in vocab_mentions}
    for name in sorted(used_vocab):
        entry = vocab_entries.get(normalize_name(name)) or vocab_entries.get(
            normalize_name(name).replace(" ", ""), {}
        )
        dimensions.append(
            DimensionNode(
                "VocabTerm",
                name,
                {
                    "nameRef": entry.get("nameRef", name),
                    "description": entry.get("description", ""),
                },
            )
        )

    # Subtype
    for name in sorted(
        {subtype for card in cards for subtype in card.get("subtypes", [])}
    ):
        dimensions.append(DimensionNode("Subtype", name))

    # CardSet
    set_entries = {
        entry.get("nameRef"): entry for entry in globals_data.get("sets", [])
    }
    for set_ref in sorted({card.get("set", "") for card in cards}):
        entry = set_entries.get(set_ref, {})
        dimensions.append(
            DimensionNode(
                "CardSet",
                set_ref,
                {
                    "displayName": entry.get("name", set_ref),
                    "icon": entry.get("iconAbsolutePath") or "",
                },
            )
        )

    # Format
    format_entries = {
        entry.get("name"): entry for entry in globals_data.get("formats", [])
    }
    used_formats = sorted(
        {fmt for card in cards for fmt in card.get("formats", [])}
    )
    for name in used_formats:
        entry = format_entries.get(name, {})
        dimensions.append(
            DimensionNode(
                "Format",
                name,
                {
                    "nameRef": entry.get("nameRef", name),
                    "icon": entry.get("iconAbsolutePath") or "",
                },
            )
        )

    # Rarity
    rarity_entries = {
        entry.get("name"): entry for entry in globals_data.get("rarities", [])
    }
    for name in sorted({card.get("rarity", "") for card in cards}):
        entry = rarity_entries.get(name, {})
        dimensions.append(
            DimensionNode("Rarity", name, {"nameRef": entry.get("nameRef", name)})
        )

    # SpellSpeed
    speed_entries = {
        entry.get("name"): entry for entry in globals_data.get("spellSpeeds", [])
    }
    for name in sorted(
        {card.get("spellSpeed", "") for card in cards if card.get("spellSpeed")}
    ):
        entry = speed_entries.get(name, {})
        dimensions.append(
            DimensionNode(
                "SpellSpeed", name, {"nameRef": entry.get("nameRef", name)}
            )
        )

    return dimensions


def build_edges(
    cards: list[dict[str, Any]],
    card_by_code: dict[str, dict[str, Any]],
    card_mentions: list[tuple[str, str, str, str, str]],
    keyword_mentions: list[tuple[str, str]],
    vocab_mentions: list[tuple[str, str]],
) -> list[EdgeRecord]:
    edges: list[EdgeRecord] = []

    for card in cards:
        code = card["cardCode"]
        for region in card.get("regions", []):
            edges.append(EdgeRecord("Card", code, "IN_REGION", "Region", region))
        for keyword in _unique(list(card.get("keywords", []) or [])):
            edges.append(
                EdgeRecord("Card", code, "HAS_KEYWORD", "Keyword", keyword)
            )
        for subtype in card.get("subtypes", []):
            edges.append(
                EdgeRecord("Card", code, "HAS_SUBTYPE", "Subtype", subtype)
            )
        edges.append(
            EdgeRecord("Card", code, "IN_SET", "CardSet", card.get("set", ""))
        )
        edges.append(
            EdgeRecord("Card", code, "HAS_RARITY", "Rarity", card.get("rarity", ""))
        )
        for fmt in card.get("formats", []):
            edges.append(EdgeRecord("Card", code, "AVAILABLE_IN", "Format", fmt))
        if card.get("spellSpeed"):
            edges.append(
                EdgeRecord(
                    "Card",
                    code,
                    "HAS_SPELL_SPEED",
                    "SpellSpeed",
                    card["spellSpeed"],
                )
            )

    # ASSOCIATED_WITH: agregasi per (src, dst, role)
    associated: Counter[tuple[str, str, str]] = Counter()
    for card in cards:
        source = card["cardCode"]
        for ref in card.get("associatedCardRefs", []):
            target = card_by_code.get(ref)
            if not target:
                continue
            role = infer_role(card, target)
            associated[(source, ref, role)] += 1

    for (source, target, role), count in sorted(associated.items()):
        props: dict[str, Any] = {"role": role}
        if count > 1:
            props["count"] = count
        edges.append(
            EdgeRecord("Card", source, "ASSOCIATED_WITH", "Card", target, props)
        )

    # REFERENCES: agregasi per (src, dst)
    references: dict[tuple[str, str], dict[str, Any]] = {}
    for source, target, link_key, display_name, confidence in card_mentions:
        bucket = references.setdefault(
            (source, target),
            {"count": 0, "spans": set(), "linkKeys": set(), "confidence": set()},
        )
        bucket["count"] += 1
        bucket["spans"].add(display_name)
        bucket["linkKeys"].add(link_key)
        bucket["confidence"].add(confidence)

    for (source, target), bucket in sorted(references.items()):
        edges.append(
            EdgeRecord(
                "Card",
                source,
                "REFERENCES",
                "Card",
                target,
                {
                    "count": bucket["count"],
                    "spans": sorted(bucket["spans"]),
                    "linkKeys": sorted(bucket["linkKeys"]),
                    "confidence": sorted(bucket["confidence"]),
                },
            )
        )

    # MENTIONS_KEYWORD
    for (source, keyword), count in sorted(Counter(keyword_mentions).items()):
        edges.append(
            EdgeRecord(
                "Card",
                source,
                "MENTIONS_KEYWORD",
                "Keyword",
                keyword,
                {"count": count},
            )
        )

    # MENTIONS_TERM
    for (source, term), count in sorted(Counter(vocab_mentions).items()):
        edges.append(
            EdgeRecord(
                "Card",
                source,
                "MENTIONS_TERM",
                "VocabTerm",
                term,
                {"count": count},
            )
        )

    return edges


def build_aliases(
    cards: list[dict[str, Any]],
    globals_data: dict[str, Any],
    card_mentions: list[tuple[str, str, str, str, str]],
) -> dict[str, Any]:
    card_aliases: dict[str, set[str]] = defaultdict(set)
    for card in cards:
        code = card["cardCode"]
        for key in _lookup_keys(card.get("name")) | {
            singularize(card.get("name"))
        }:
            if key:
                card_aliases[key].add(code)

    for _, target, _, display_name, _ in card_mentions:
        for key in _lookup_keys(display_name) | {singularize(display_name)}:
            if key:
                card_aliases[key].add(target)

    keyword_aliases: dict[str, str] = {}
    for entry in globals_data.get("keywords", []):
        for raw in (entry.get("name"), entry.get("nameRef")):
            for key in _lookup_keys(raw):
                keyword_aliases[key] = entry.get("name", raw)

    vocab_aliases: dict[str, str] = {}
    for entry in globals_data.get("vocabTerms", []):
        for raw in (entry.get("name"), entry.get("nameRef")):
            for key in _lookup_keys(raw):
                vocab_aliases[key] = entry.get("name", raw)

    region_aliases: dict[str, str] = {}
    for entry in globals_data.get("regions", []):
        for raw in (
            entry.get("name"),
            entry.get("nameRef"),
            entry.get("abbreviation"),
        ):
            for key in _lookup_keys(raw):
                region_aliases[key] = entry.get("name", raw)

    return {
        "cards": {
            key: sorted(values) for key, values in sorted(card_aliases.items()) if values
        },
        "keywords": dict(sorted(keyword_aliases.items())),
        "vocab": dict(sorted(vocab_aliases.items())),
        "regions": dict(sorted(region_aliases.items())),
    }


def build_stats(
    cards: list[CardRecord],
    dimensions: list[DimensionNode],
    edges: list[EdgeRecord],
    unresolved: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "cards": len(cards),
        "collectible": sum(1 for card in cards if card.collectible),
        "textless": sum(1 for card in cards if not card.hasNativeText),
        "placeholder": sum(1 for card in cards if card.textPlaceholder),
        "level1TextMissing": sum(1 for card in cards if card.level1TextMissing),
        "dimensions": dict(Counter(dimension.label for dimension in dimensions)),
        "edges": dict(Counter(edge.rel for edge in edges)),
        "mentions": {
            rel: sum(
                int(edge.props.get("count", 1))
                for edge in edges
                if edge.rel == rel
            )
            for rel in (
                "ASSOCIATED_WITH",
                "REFERENCES",
                "MENTIONS_KEYWORD",
                "MENTIONS_TERM",
            )
        },
        "unresolved": {key: len(value) for key, value in unresolved.items()},
    }


def extract_all() -> ExtractionResult:
    cards = load_latest_cards()
    globals_data = load_globals()
    card_by_code = {card["cardCode"]: card for card in cards}

    keyword_lookup = build_keyword_lookup(globals_data)
    vocab_lookup = build_vocab_lookup(globals_data)

    card_mentions, keyword_mentions, vocab_mentions, unresolved = collect_mentions(
        cards, card_by_code, keyword_lookup, vocab_lookup
    )

    card_records = build_card_records(cards, globals_data)
    dimensions = build_dimensions(
        cards, globals_data, keyword_mentions, vocab_mentions
    )
    edges = build_edges(
        cards,
        card_by_code,
        card_mentions,
        keyword_mentions,
        vocab_mentions,
    )
    aliases = build_aliases(cards, globals_data, card_mentions)
    stats = build_stats(card_records, dimensions, edges, unresolved)

    return ExtractionResult(
        cards=card_records,
        dimensions=dimensions,
        edges=edges,
        aliases=aliases,
        stats=stats,
        unresolved=unresolved,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_outputs(result: ExtractionResult) -> None:
    output_dir = config.PROCESSED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_jsonl(output_dir / "cards.jsonl", [card.to_props() for card in result.cards])
    _write_jsonl(
        output_dir / "dims.jsonl",
        [dimension.to_dict() for dimension in result.dimensions],
    )
    _write_jsonl(
        output_dir / "edges.jsonl", [edge.to_dict() for edge in result.edges]
    )

    (output_dir / "aliases.json").write_text(
        json.dumps(result.aliases, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "extract_report.json").write_text(
        json.dumps(result.stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "unresolved_mentions.json").write_text(
        json.dumps(result.unresolved, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    result = extract_all()
    write_outputs(result)
    logger.info("Output ditulis ke %s", config.PROCESSED_DIR)
    logger.info(
        "Cards=%d | dimensi=%d | edges=%d",
        len(result.cards),
        len(result.dimensions),
        len(result.edges),
    )
    logger.info("Statistik: %s", json.dumps(result.stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
