# Kontrak Integrasi RuneTerraRAG

Dokumen ini adalah kesepakatan antara tiga bagian:

| Bagian | Penanggung jawab | Output |
|---|---|---|
| Graph Ingestion | Lolo | Neo4j + `data/processed/*` |
| Vector Ingestion | Yuda | Qdrant collection `cards` |
| Integrasi | Kesan | Hybrid retrieval + API/LLM |

## 1. Sumber data

**Keputusan: latest-only.**

- `data/latest/set*-en_us.json` → 2.512 kartu, 11 set, patch `7_11_0`.
- `data/globals-en_us.json` → dimensi.
- `data/versioned/` **tidak di-ingest**; hanya arsip/backfill.

## 2. Artefak bersama (`data/processed/`)

Dihasilkan oleh `python -m src.graph.extract`:

| File | Isi |
|---|---|
| `cards.jsonl` | 2.512 kartu, satu JSON per baris |
| `dims.jsonl` | node dimensi |
| `edges.jsonl` | edge graph |
| `aliases.json` | alias nama → `cardCode` / keyword / region |
| `extract_report.json` | statistik ekstraksi |
| `unresolved_mentions.json` | sebutan markup yang ambigu/tidak ter-resolve |
| `validation_report.json` | hasil validasi Neo4j |

**Kunci identitas: `cardCode`.** Jangan memakai nama sebagai kunci; ada 193 nama duplikat.

### Field penting di `cards.jsonl`

| Field | Catatan |
|---|---|
| `cardCode` | unik, contoh `01IO015` |
| `name`, `type`, `supertype` | `type`: Unit/Spell/Ability/Landmark/Equipment/Trap |
| `cost`, `attack`, `health` | Equipment: `attack/health` = buff |
| `regions[]`, `keywords[]`, `subtypes[]`, `formats[]` | list |
| `set`, `setDisplayName` | `Set9` → `Dreamlit Paths` (di Neo4j menjadi `setRef`) |
| `rarity`, `collectible` | 865 non-collectible (token/skill) |
| `descriptionRaw` | teks bersih (bisa kosong) |
| `descriptionMarkup` | teks dengan `<link=...>` |
| `levelupDescriptionRaw` | teks level-up |
| `hasNativeText` | false untuk 183 kartu |
| `textStatus` | `native` / `placeholder` / `attributes_only` |
| `textPlaceholder` | true untuk 4 kartu |
| `level1TextMissing` | true untuk 12 champion level 1 |
| `cardFamily` | kode tanpa suffix T |
| `patch` | `7_11_0` |

## 3. Skema graph Neo4j

### Node

| Label | Jumlah (perkiraan) | Kunci |
|---|---:|---|
| `Card` | 2.512 | `cardCode` |
| `Region` | 11 | `name` |
| `Keyword` | ≥49 | `name` |
| `VocabTerm` | ≥40 | `name` |
| `Subtype` | 27 | `name` |
| `CardSet` | 11 | `name` (mis. `Set1`) |
| `Format` | 5 | `name` |
| `Rarity` | 5 | `name` |
| `SpellSpeed` | 3 | `name` |

### Edge

| Edge | Jumlah | Keterangan |
|---|---:|---|
| `IN_REGION` | 2.602 | 90 kartu multi-region |
| `HAS_KEYWORD` | 2.343 | dari `keywords[]` (duplikat `Spirit` pada `09DE033` sudah di-dedupe) |
| `HAS_SUBTYPE` | 675 | |
| `IN_SET` | 2.512 | |
| `HAS_RARITY` | 2.512 | |
| `AVAILABLE_IN` | 4.577 | |
| `HAS_SPELL_SPEED` | 902 | |
| `ASSOCIATED_WITH` | ±2.076 unik (2.089 sebutan) | properti `role` |
| `REFERENCES` | ±700–800 unik (890 sebutan) | properti `count`, `spans`, `linkKeys`, `confidence` |
| `MENTIONS_KEYWORD` | 1.201 | properti `count` |
| `MENTIONS_TERM` | 1.182 | properti `count` |

Role `ASSOCIATED_WITH`: `LEVELS_INTO`, `CHAMPION_SPELL`, `BACKREF_BASE`, `SAME_FAMILY`, `SKILL`, `TOKEN_OR_UNIT`, `SPELL`, `LANDMARK`, `TRAP`, `EQUIPMENT`, `OTHER`.

## 4. Kontrak fungsi

### Graph (Lolo)

```python
graph_search(filters: dict, limit: int = 20) -> list[dict]
# filters: type, supertype, region, keyword, subtype, format,
#          set, rarity, spell_speed, min_cost, max_cost,
#          min_attack, max_attack, min_health, max_health,
#          collectible, has_text, text

card_detail(card_code: str) -> dict
related(card_code: str, rel_types: list[str] | None, depth: int = 1, limit: int = 50) -> list[dict]
aggregate(group_by: str, filters: dict | None = None, limit: int = 100) -> list[dict]
compare(card_codes: list[str]) -> list[dict]
```

Semua hasil **wajib** mengandung `cardCode` (atau `card_code` setelah dinormalisasi oleh Kesan).

### Vector (Yuda)

Qdrant collection: `cards`

Payload minimal:

```json
{
  "card_code": "01IO015",
  "name": "Yasuo",
  "type": "Unit",
  "regions": ["Ionia"],
  "cost": 4,
  "collectible": true,
  "has_native_text": true,
  "text_status": "native"
}
```

Spesifikasi teks embedding:

```
name | descriptionRaw | levelupDescriptionRaw | flavorText | keywords | regions
```

Untuk 183 kartu tanpa teks native, teks atribut tetap dibuat agar semua kartu punya vektor.

### Hybrid (Kesan)

```python
vector_search(query: str, filters: dict, top_k: int) -> list[dict]
hybrid_search(query: str, top_k: int = 10) -> list[dict]
```

Merge memakai **Reciprocal Rank Fusion** (`src/retrieval/hybrid.py`), dedupe by `card_code`.

## 5. Endpoint API awal

| Method | Path | Status |
|---|---|---|
| GET | `/health` | aktif |
| GET | `/cards/{card_code}` | aktif |
| GET | `/search` | aktif |
| GET | `/related/{card_code}` | aktif |
| GET | `/aggregate` | aktif |
| POST | `/query` | 501 (Kesan) |

## 6. Keterbatasan data yang wajib diketahui

- 183 kartu tanpa `descriptionRaw` (179 vanilla + 4 placeholder).
- 4 placeholder: `02BW041`, `02BW030T4`, `06SH008`, `06SH010`.
- 12 champion level 1 tanpa teks: Darius, Lucian, Lux, Fiora, Jinx, Tryndamere, Kalista, Thresh, Nautilus, Sivir, LeBlanc, Pantheon.- `06DE048` Blocking Badgerbear kehilangan teks di axis `7_11_0`; backfill dari `versioned/set6cde` patch `4_2_0` jika perlu.
- 3 Equipment mencurigakan (0/0, tanpa teks): `06DE032`, `06FR024`, `06NX026`.
- 15 token Husk berkode `06RU` tetapi region non-Runeterra → gunakan `regions`, bukan `cardCode`.
- Tidak ada data deck/match/win-rate/meta.
- `versioned` tidak di-ingest.

## 7. Checklist handoff

- [ ] `data/processed/cards.jsonl` tersedia untuk Yuda.
- [ ] `data/processed/aliases.json` tersedia untuk entity linking.
- [ ] `make verify` lolos.
- [ ] `docs/kontrak-integrasi.md` dibagikan ke Yuda & Kesan.
- [ ] Endpoint `/cards/{code}` bisa diakses Kesan.
