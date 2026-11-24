# Arsitektur RuneTerraRAG

## Tujuan

Menjawab pertanyaan tentang kartu Legends of Runeterra dengan **Hybrid Graph RAG**:

- **Graph DB (Neo4j)** → fakta, filter, relasi, agregasi.
- **Vector DB (Qdrant)** → kemiripan makna/deskripsi.
- **BM25/full-text** → nama kartu eksak.
- **LLM** → routing intent dan penyusunan jawaban dengan sitasi `cardCode`.

## Alur

```
Pertanyaan (ID/EN)
   │
   ├─ Entity linking (aliases.json + fuzzy)
   ├─ Intent router
   │
   ├─ Graph search (Cypher template) ─┐
   ├─ Vector search (Qdrant) ──────────┤
   ├─ Lexical/BM25 ────────────────────┤
   │                                   ▼
   └────────────────────────── RRF / merge by card_code
                                       │
                              Graph expansion 1 hop
                                       │
                              Context builder
                                       │
                              LLM answer + citation
```

## Pembagian tanggung jawab

| Komponen | PIC | Lokasi |
|---|---|---|
| Graph ingestion | Lolo | `src/graph/` |
| Vector ingestion | Yuda | `src/vector/` |
| Hybrid + API | Kesan | `src/retrieval/`, `src/api/` |
| Docker | Lolo (inisiator) | `docker-compose.yml` |

## Prinsip desain

1. **Satu sumber kebenaran:** `latest` patch `7_11_0`.
2. **Satu kunci identitas:** `cardCode`.
3. **Graph deterministik:** relasi dibangun dari `associatedCardRefs` dan markup, bukan LLM extraction.
4. **Vector untuk semantik, graph untuk presisi.**
5. **Tidak mengarang jawaban:** jika bukti tidak ada, RAG harus menolak.

## Skala

- 2.512 kartu
- ±2.663 node graph
- ±21.477 edge
- ±141k token korpus embedding
- Latensi target: < 2 detik untuk retrieval graph/vector (tanpa LLM).
