"""Kerangka hybrid retrieval (graph + vector + lexical).

Bagian ini milik Kesan. Di sini hanya disediakan helper RRF yang umum
dipakai untuk menggabungkan hasil graph dan vector.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def reciprocal_rank_fusion(
    result_lists: Iterable[list[dict[str, Any]]],
    key: str = "card_code",
    k: int = 60,
) -> list[dict[str, Any]]:
    """Gabungkan beberapa daftar hasil dengan Reciprocal Rank Fusion.

    Parameters
    ----------
    result_lists:
        Daftar hasil retriever; setiap item minimal punya field ``key``.
    key:
        Field identitas kartu (default ``card_code``).
    k:
        Konstanta RRF (umumnya 60).
    """
    scores: dict[str, float] = defaultdict(float)
    payload: dict[str, dict[str, Any]] = {}

    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            identifier = item.get(key)
            if not identifier:
                continue
            scores[identifier] += 1.0 / (k + rank)
            payload.setdefault(identifier, item)

    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    return [
        {**payload[identifier], "fusion_score": score}
        for identifier, score in ranked
    ]


def hybrid_search(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """TODO (Kesan): panggil graph_search + vector_search lalu lakukan RRF."""
    raise NotImplementedError(
        "Hybrid search belum diimplementasikan. "
        "Gunakan reciprocal_rank_fusion() setelah graph & vector siap."
    )
