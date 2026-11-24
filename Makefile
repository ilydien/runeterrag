SHELL := /bin/bash
.RECIPEPREFIX = >

.PHONY: help up down logs ps extract load-graph load-vector verify reset-graph test shell

help:
> @echo "RuneTerraRAG - perintah utama"
> @echo "  make up           # jalankan Neo4j + Qdrant"
> @echo "  make extract      # ekstrak dataset latest -> data/processed"
> @echo "  make load-graph   # ekstrak (jika perlu) + load graph ke Neo4j"
> @echo "  make load-vector  # load vektor ke Qdrant (tugas Yuda)"
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

verify:
> docker compose --profile ingest run --rm graph-ingest python -m src.graph.validate

reset-graph:
> docker compose --profile ingest run --rm graph-ingest python -m src.graph.reset

test:
> pytest -q

shell:
> docker compose --profile ingest run --rm graph-ingest bash
