SHELL := /bin/bash
.RECIPEPREFIX = >

.PHONY: help up down logs ps extract load-graph load-vector load-vector-recreate vector-verify snapshot-vector restore-vector verify reset-graph test shell

help:
> @echo "RuneTerraRAG - perintah utama"
> @echo "  make up           # jalankan Neo4j + Qdrant"
> @echo "  make extract      # ekstrak dataset latest -> data/processed"
> @echo "  make load-graph   # ekstrak (jika perlu) + load graph ke Neo4j"
> @echo "  make load-vector  # load vektor ke Qdrant (tugas Yuda)"
> @echo "  make load-vector-recreate # rebuild collection Qdrant"
> @echo "  make vector-verify # validasi collection Qdrant"
> @echo "  make snapshot-vector # buat snapshot Qdrant untuk handoff"
> @echo "  make restore-vector SNAPSHOT=... # restore snapshot Qdrant"
> @echo "  make verify       # validasi isi graph"
> @echo "  make reset-graph  # hapus semua node/edge"
> @echo "  make down         # hentikan semua service"
> @echo "  make test         # jalankan pytest lokal"

up:
> docker compose up -d neo4j qdrant

down:
> docker compose down

logs:
> docker compose logs -f --tail=100

ps:
> docker compose ps

extract:
> docker compose --profile ingest run --rm graph-ingest python -m src.graph.extract

load-graph:
> docker compose --profile ingest run --rm graph-ingest

load-vector:
> docker compose --profile ingest run --rm vector-ingest

load-vector-recreate:
> docker compose --profile ingest run --rm vector-ingest python -m src.vector.load --recreate

vector-verify:
> docker compose --profile ingest run --rm vector-ingest python -m src.vector.validate

snapshot-vector:
> ./scripts/create_qdrant_snapshot.sh

restore-vector:
> ./scripts/restore_qdrant_snapshot.sh $(SNAPSHOT)

verify:
> docker compose --profile ingest run --rm graph-ingest python -m src.graph.validate

reset-graph:
> docker compose --profile ingest run --rm graph-ingest python -m src.graph.reset

test:
> pytest -q

shell:
> docker compose --profile ingest run --rm graph-ingest bash
