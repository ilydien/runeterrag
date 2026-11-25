# Handoff Vector Retrieval

Dokumen ini untuk anggota tim yang ingin memakai collection Qdrant hasil
embedding tanpa menjalankan embedding 2.512 kartu lagi.

## Artefak

Release GitHub:

```text
tag: vectors-7_11_0-e5large-v1
```

Asset:

```text
runeterra-cards-7_11_0-e5large-v1.snapshot
runeterra-cards-7_11_0-e5large-v1.sha256
vector_manifest.json
```

Snapshot berisi:

- 2.512 vector, 1024 dimensi, cosine;
- payload kartu;
- payload indexes;
- konfigurasi collection `cards`.

Snapshot tidak berisi model embedding dan tidak berisi graph Neo4j.

## Prasyarat

- Docker dan Docker Compose.
- Qdrant versi `v1.20.2` (lihat `docker-compose.yml`).
- Python 3.11 untuk menjalankan script validasi/search.
- Model `intfloat/multilingual-e5-large` untuk meng-embed pertanyaan user.

Model tetap dibutuhkan untuk query. Yang tidak perlu diulang adalah embedding
corpus 2.512 kartu.

## 1. Siapkan repo dan Qdrant

```bash
git clone https://github.com/ilydien/runeterrag.git
cd runeterrag
cp .env.example .env
docker compose up -d qdrant
```

Cek Qdrant:

```bash
curl -s http://localhost:6333/collections
```

## 2. Unduh snapshot

Dengan GitHub CLI:

```bash
gh release download vectors-7_11_0-e5large-v1 \
  --pattern 'runeterra-cards-7_11_0-e5large-v1.snapshot'
gh release download vectors-7_11_0-e5large-v1 \
  --pattern 'runeterra-cards-7_11_0-e5large-v1.sha256'
```

Tanpa GitHub CLI, unduh manual dari halaman release GitHub.

Verifikasi checksum:

```bash
sha256sum -c runeterra-cards-7_11_0-e5large-v1.sha256
```

## 3. Restore snapshot

```bash
chmod +x scripts/restore_qdrant_snapshot.sh
./scripts/restore_qdrant_snapshot.sh \
  runeterra-cards-7_11_0-e5large-v1.snapshot
```

Jika collection `cards` sudah ada dan ingin ditimpa:

```bash
./scripts/restore_qdrant_snapshot.sh --force \
  runeterra-cards-7_11_0-e5large-v1.snapshot
```

## 4. Verifikasi

```bash
make vector-verify
```

Harus menghasilkan:

```text
source_cards: 2512
points: 2512
missing: 0
extra: 0
passed: True
```

Alternatif tanpa `make`:

```bash
python3.11 -m venv .venv
source .venv/bin/activate.fish
pip install -r requirements.txt -r requirements-vector.txt
python -m src.vector.validate
```

## 5. Query

Query membutuhkan model embedding:

```bash
python -m src.vector.search "kartu yang membekukan musuh"
```

Atau lewat Docker:

```bash
docker compose --profile ingest run --rm vector-ingest \
  python -m src.vector.search "kartu yang membekukan musuh"
```

## Troubleshooting

**Collection sudah ada**

Gunakan `--force`, atau hapus manual:

```bash
curl -X DELETE http://localhost:6333/collections/cards
```

**Jumlah point tidak 2512**

Pastikan snapshot yang dipakai adalah asset release yang benar. Cek:

```bash
curl -s http://localhost:6333/collections/cards
```

**Qdrant version mismatch**

Gunakan `qdrant/qdrant:v1.20.2`. Snapshot lintas versi major tidak dijamin
kompatibel.

**Model dimension mismatch**

Collection memakai 1024 dimensi. Jangan mengganti model query ke model dengan
dimensi lain. Jika mengganti model, buat collection baru dan embed ulang.

## Kalau ingin embedding ulang

Jalankan:

```bash
make load-vector-recreate
```

Ini akan meng-embed ulang 2.512 kartu dan menimpa collection. Hanya lakukan
kalau memang ingin membangun ulang vector, bukan untuk sekadar memakai hasil
handoff.
