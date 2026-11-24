"""Model data yang dipakai oleh pipeline graph.

Representasi ini sengaja datar (flat) agar mudah ditulis ke JSONL dan
di-``UNWIND`` ke Neo4j.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CardRecord:
    cardCode: str
    name: str
    type: str
    supertype: str
    cost: int
    attack: int
    health: int
    rarity: str
    rarityRef: str
    setRef: str
    setDisplayName: str
    collectible: bool
    regions: list[str]
    regionRefs: list[str]
    keywords: list[str]
    keywordRefs: list[str]
    subtypes: list[str]
    spellSpeed: str
    spellSpeedRef: str
    descriptionRaw: str
    descriptionMarkup: str
    levelupDescriptionRaw: str
    levelupDescriptionMarkup: str
    flavorText: str
    artistName: str
    formats: list[str]
    formatRefs: list[str]
    hasNativeText: bool
    textStatus: str
    textPlaceholder: bool
    level1TextMissing: bool
    patch: str
    assetGame: str
    assetFull: str
    cardFamily: str
    isChampion: bool
    isBaseChampion: bool

    def to_props(self) -> dict[str, Any]:
        """Dict siap tulis JSONL / set property Neo4j (termasuk cardCode)."""
        return {
            "cardCode": self.cardCode,
            "name": self.name,
            "type": self.type,
            "supertype": self.supertype,
            "cost": self.cost,
            "attack": self.attack,
            "health": self.health,
            "rarity": self.rarity,
            "rarityRef": self.rarityRef,
            "set": self.setRef,
            "setDisplayName": self.setDisplayName,
            "collectible": self.collectible,
            "regions": self.regions,
            "regionRefs": self.regionRefs,
            "keywords": self.keywords,
            "keywordRefs": self.keywordRefs,
            "subtypes": self.subtypes,
            "spellSpeed": self.spellSpeed,
            "spellSpeedRef": self.spellSpeedRef,
            "descriptionRaw": self.descriptionRaw,
            "descriptionMarkup": self.descriptionMarkup,
            "levelupDescriptionRaw": self.levelupDescriptionRaw,
            "levelupDescriptionMarkup": self.levelupDescriptionMarkup,
            "flavorText": self.flavorText,
            "artistName": self.artistName,
            "formats": self.formats,
            "formatRefs": self.formatRefs,
            "hasNativeText": self.hasNativeText,
            "textStatus": self.textStatus,
            "textPlaceholder": self.textPlaceholder,
            "level1TextMissing": self.level1TextMissing,
            "patch": self.patch,
            "assetGame": self.assetGame,
            "assetFull": self.assetFull,
            "cardFamily": self.cardFamily,
            "isChampion": self.isChampion,
            "isBaseChampion": self.isBaseChampion,
            "textLength": len(self.descriptionRaw),
        }


@dataclass
class DimensionNode:
    label: str
    name: str
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "name": self.name, "props": self.props}


@dataclass
class EdgeRecord:
    srcLabel: str
    srcKey: str
    rel: str
    dstLabel: str
    dstKey: str
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "srcLabel": self.srcLabel,
            "srcKey": self.srcKey,
            "rel": self.rel,
            "dstLabel": self.dstLabel,
            "dstKey": self.dstKey,
            "props": self.props,
        }
