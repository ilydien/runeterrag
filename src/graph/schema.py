"""Skema graph Neo4j untuk RuneTerraRAG.

Prinsip:
- ``Card`` adalah satu-satunya label untuk kartu, skill, ability, token.
- Node dimensi dipakai sebagai hub/filter (region, keyword, subtype, set, dll).
- Semua kunci memakai ``cardCode`` (Card) atau ``name`` (dimensi).
"""

from __future__ import annotations

CARD_LABEL = "Card"

DIM_LABELS: tuple[str, ...] = (
    "Region",
    "Keyword",
    "VocabTerm",
    "Subtype",
    "CardSet",
    "Format",
    "Rarity",
    "SpellSpeed",
)

ALL_LABELS: tuple[str, ...] = (CARD_LABEL, *DIM_LABELS)

REL_TYPES: tuple[str, ...] = (
    "IN_REGION",
    "HAS_KEYWORD",
    "HAS_SUBTYPE",
    "IN_SET",
    "HAS_RARITY",
    "AVAILABLE_IN",
    "HAS_SPELL_SPEED",
    "ASSOCIATED_WITH",
    "REFERENCES",
    "MENTIONS_KEYWORD",
    "MENTIONS_TERM",
)


def key_property(label: str) -> str:
    """Property kunci untuk sebuah label."""
    return "cardCode" if label == CARD_LABEL else "name"


def vector_index_cypher(dimensions: int = 1024) -> str:
    """Cypher untuk vector index (dipakai setelah embedding tersedia)."""
    return (
        "CREATE VECTOR INDEX card_embedding IF NOT EXISTS "
        "FOR (c:Card) ON (c.embedding) "
        "OPTIONS {indexConfig: {`vector.dimensions`: "
        f"{int(dimensions)}, `vector.similarity_function`: 'cosine'}}"
    )


def _constraint(label: str) -> str:
    name = f"{label.lower()}_name_unique"
    prop = key_property(label)
    return (
        f"CREATE CONSTRAINT {name} IF NOT EXISTS "
        f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
    )


SCHEMA_STATEMENTS: tuple[str, ...] = (
    # Card
    _constraint(CARD_LABEL),
    "CREATE INDEX card_type_cost IF NOT EXISTS FOR (c:Card) ON (c.type, c.cost)",
    "CREATE INDEX card_set IF NOT EXISTS FOR (c:Card) ON (c.setRef)",
    "CREATE INDEX card_rarity IF NOT EXISTS FOR (c:Card) ON (c.rarity)",
    "CREATE INDEX card_collectible IF NOT EXISTS FOR (c:Card) ON (c.collectible)",
    "CREATE INDEX card_text_status IF NOT EXISTS FOR (c:Card) ON (c.textStatus)",
    (
        "CREATE FULLTEXT INDEX card_text IF NOT EXISTS "
        "FOR (c:Card) ON EACH [c.name, c.descriptionRaw, c.flavorText]"
    ),
    # Dimensi
    *(_constraint(label) for label in DIM_LABELS),
)
