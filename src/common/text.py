"""Helper untuk membersihkan markup LoR dan mendeteksi status teks.

Dataset Data Dragon menyimpan dua versi teks:
- ``description`` / ``levelupDescription``: mengandung markup <link=...>.
- ``descriptionRaw`` / ``levelupDescriptionRaw``: teks bersih.

Modul ini dipakai untuk ekstraksi relasi (dari markup) dan untuk
menandai kartu yang teksnya tidak tersedia.
"""

from __future__ import annotations

import html
import re
import unicodedata

TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r"<style=Variable>\s*</style>", re.IGNORECASE)

LINK_KEYWORD_RE = re.compile(r"<link=keyword\.([^>]+)>", re.IGNORECASE)
LINK_VOCAB_RE = re.compile(r"<link=vocab\.([^>]+)>", re.IGNORECASE)
LINK_CARD_RE = re.compile(
    r"<link=card\.([^>]*)><style=AssociatedCard>(.*?)</style></link>",
    re.IGNORECASE | re.DOTALL,
)


def strip_markup(value: str | None) -> str:
    """Ubah teks bermarkup menjadi teks bersih satu baris."""
    if not value:
        return ""

    text = value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = BR_RE.sub(" ", text)
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def is_placeholder(description: str | None, raw: str | None) -> bool:
    """True jika kartu punya placeholder ``<style=Variable></style>``.

    Placeholder berarti teks mekanik tidak tersedia di dataset (bukan
    vanilla), misalnya The Beast Below dan Void Blaster.
    """
    if (raw or "").strip():
        return False
    return bool(PLACEHOLDER_RE.search(description or ""))


def text_status(description: str | None, raw: str | None) -> str:
    """Klasifikasi status teks kartu.

    Nilai:
    - ``native``: ada teks mekanik asli.
    - ``placeholder``: hanya placeholder <style=Variable>.
    - ``attributes_only``: benar-benar kosong (vanilla/token).
    """
    if (raw or "").strip():
        return "native"
    if is_placeholder(description, raw):
        return "placeholder"
    return "attributes_only"


def normalize_name(value: str | None) -> str:
    """Normalisasi nama untuk entity linking/alias.

    - lowercase
    - buang possessive ('s)
    - ganti tanda baca dengan spasi
    """
    if not value:
        return ""
    text = strip_markup(value).lower()
    text = re.sub(r"['\u2019]s\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def singularize(value: str | None) -> str:
    """Normalisasi bentuk plural sederhana untuk nama kartu di markup.

    Contoh: "Living Shadows" -> "living shadow",
            "Mistwraiths" -> "mistwraith".
    """
    text = normalize_name(value)
    if text.endswith("ies") and len(text) > 3:
        return text[:-3] + "y"
    if text.endswith("es") and len(text) > 2:
        return text[:-2]
    if text.endswith("s") and len(text) > 1:
        return text[:-1]
    return text


def extract_card_links(text: str | None) -> list[tuple[str, str]]:
    """Ambil pasangan (link_key, display_name) dari markup kartu.

    Contoh hasil: ``("level1", "Yasuo")`` atau ``("summon", "Living Shadow")``.
    """
    if not text:
        return []
    return [
        (match.group(1).strip(), strip_markup(match.group(2)))
        for match in LINK_CARD_RE.finditer(text)
    ]


def extract_link_targets(text: str | None, pattern: re.Pattern[str]) -> list[str]:
    """Ambil target dari pola ``<link=...>`` (keyword/vocab)."""
    if not text:
        return []
    return [match.group(1).strip() for match in pattern.finditer(text)]
