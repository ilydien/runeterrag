# RuneTerraRAG

Hybrid Graph RAG untuk dataset **Legends of Runeterra (LoR) Data Dragon**.
Proyek ini menggabungkan **Neo4j** (graph), **Qdrant** (vector), dan **FastAPI**
sebagai kerangka integrasi.

> Status: scaffold awal. Bagian graph ingestion sudah diimplementasikan;
> vector ingestion dan hybrid retrieval masih stub untuk dikerjakan Yuda & Kesan.

## Cakupan data

- **latest-only**: `data/latest/*.json` + `data/globals-en_us.json`
- 2.512 kartu, 11 set, patch final `7_11_0`
- `data/versioned/` **tidak di-ingest** (hanya arsip/backfill)

## Quick start (Docker)

```bash
cp .env.example .env
make up              # Neo4j + Qdrant
make load-graph      # ekstrak + load graph
make verify          # validasi graph
```

Neo4j Browser: http://localhost:7474 (user `neo4j`, password dari `.env`).
API: http://localhost:8000/docs (setelah `docker compose up api`).

## Perintah Make

| Perintah | Fungsi |
|---|---|
| `make up` | jalankan Neo4j + Qdrant |
| `make extract` | ekstrak `latest` → `data/processed/` |
| `make load-graph` | ekstrak (jika perlu) + load ke Neo4j |
| `make load-vector` | load vektor (Yuda) |
| `make verify` | validasi isi graph |
| `make reset-graph` | hapus semua node/edge |
| `make down` | hentikan semua service |
| `make test` | jalankan pytest lokal |

## Run lokal (tanpa Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export NEO4J_URI=bolt://localhost:7687
export DATA_DIR=./data
export PROCESSED_DIR=./data/processed

python -m src.graph.extract
python -m src.graph.load
python -m src.graph.validate
```

## Struktur repo

```
.
├─ docker-compose.yml
├─ Dockerfile
├─ Dockerfile.vector
├─ Makefile
├─ requirements.txt
├─ requirements-vector.txt
├─ data/
│  ├─ latest/                 # dataset sumber
│  ├─ globals-en_us.json
│  └─ processed/              # artefak hasil ekstraksi
├─ src/
│  ├─ common/                 # config, model, text helper
│  ├─ graph/                  # extract, load, queries, validate, reset
│  ├─ vector/                 # stub Yuda
│  ├─ retrieval/              # RRF + stub hybrid (Kesan)
│  └─ api/                    # FastAPI skeleton
├─ tests/
└─ docs/
   ├─ kontrak-integrasi.md
   └─ arsitektur.md
```

## Skema graph singkat

```
(Card)-[:IN_REGION]->(Region)
(Card)-[:HAS_KEYWORD]->(Keyword)
(Card)-[:HAS_SUBTYPE]->(Subtype)
(Card)-[:IN_SET]->(CardSet)
(Card)-[:HAS_RARITY]->(Rarity)
(Card)-[:AVAILABLE_IN]->(Format)
(Card)-[:HAS_SPELL_SPEED]->(SpellSpeed)
(Card)-[:ASSOCIATED_WITH {role}]->(Card)
(Card)-[:REFERENCES {count, spans}]->(Card)
(Card)-[:MENTIONS_KEYWORD {count}]->(Keyword)
(Card)-[:MENTIONS_TERM {count}]->(VocabTerm)
```

## Catatan data penting

- 183 kartu tanpa `descriptionRaw` (179 vanilla + 4 placeholder).
- 12 champion level 1 tanpa teks (Darius, Lucian, Lux, Fiora, Jinx,
  Tryndamere, Kalista, Thresh, Nautilus, Sivir, LeBlanc, Pantheon).
- 4 placeholder: `02BW041`, `02BW030T4`, `06SH008`, `06SH010`.
- `06DE048` Blocking Badgerbear kehilangan teks di `7_11_0`.
- 3 Equipment mencurigakan: `06DE032`, `06FR024`, `06NX026`.
- Tidak ada data deck/match/meta.

Detail lengkap: `docs/kontrak-integrasi.md`.

## Kolaborasi

| Bagian | PIC | Mulai dari |
|---|---|---|
| Graph ingestion | Lolo | `src/graph/` |
| Vector ingestion | Yuda | `src/vector/load.py` |
| Hybrid + API | Kesan | `src/retrieval/hybrid.py`, `src/api/main.py` |
