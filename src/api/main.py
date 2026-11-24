"""API skeleton RuneTerraRAG.

Endpoint graph sederhana sudah aktif agar tim bisa integrasi lebih awal:
- GET /health
- GET /cards/{card_code}
- GET /search
- GET /related/{card_code}
- GET /aggregate
- POST /query  -> 501 (hybrid, tugas Kesan)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from neo4j import GraphDatabase
from pydantic import BaseModel, Field

from src.common import config
from src.graph import queries


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.driver = GraphDatabase.driver(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )
    yield
    app.state.driver.close()


app = FastAPI(title="RuneTerraRAG API", version="0.1.0", lifespan=lifespan)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    filters: dict[str, Any] | None = None


@app.get("/health")
def health(request: Request):
    driver = request.app.state.driver
    try:
        driver.verify_connectivity()
        return {"status": "ok", "neo4j": "up"}
    except Exception as exc:  # noqa: BLE001 - ingin tampilkan pesan asli
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "neo4j": str(exc)},
        )


@app.get("/cards/{card_code}")
def get_card(card_code: str, request: Request):
    try:
        result = queries.detail(request.app.state.driver, card_code)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Neo4j error: {exc}") from exc
    if not result.get("card"):
        raise HTTPException(status_code=404, detail="Card not found")
    return result


@app.get("/search")
def search_cards(
    request: Request,
    type: str | None = None,
    region: str | None = None,
    keyword: str | None = None,
    set: str | None = None,
    rarity: str | None = None,
    max_cost: int | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    filters = {
        key: value
        for key, value in {
            "type": type,
            "region": region,
            "keyword": keyword,
            "set": set,
            "rarity": rarity,
            "max_cost": max_cost,
        }.items()
        if value is not None
    }
    try:
        return {
            "filters": filters,
            "results": queries.search(
                request.app.state.driver, filters, limit=limit
            ),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Neo4j error: {exc}") from exc


@app.get("/related/{card_code}")
def related_cards(
    card_code: str,
    request: Request,
    rel_types: str | None = None,
    depth: int = Query(default=1, ge=1, le=3),
    limit: int = Query(default=20, ge=1, le=100),
):
    rels = [item.strip() for item in rel_types.split(",")] if rel_types else None
    try:
        return {
            "card_code": card_code,
            "results": queries.related(
                request.app.state.driver,
                card_code,
                rel_types=rels,
                depth=depth,
                limit=limit,
            ),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Neo4j error: {exc}") from exc


@app.get("/aggregate")
def aggregate_cards(
    request: Request,
    group_by: str = Query(..., description="type/set/rarity/cost/region/keyword/subtype/format"),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return {
            "group_by": group_by,
            "results": queries.aggregate(
                request.app.state.driver, group_by, limit=limit
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Neo4j error: {exc}") from exc


@app.post("/query")
def hybrid_query(payload: QueryRequest, request: Request):
    raise HTTPException(
        status_code=501,
        detail=(
            "Hybrid retrieval (graph + vector + LLM) belum diimplementasikan. "
            "Ini bagian Kesan; lihat docs/kontrak-integrasi.md."
        ),
    )
