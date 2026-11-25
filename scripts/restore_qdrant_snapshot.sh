#!/usr/bin/env bash
# Restore a Qdrant collection snapshot.
#
# Contoh:
#   ./scripts/restore_qdrant_snapshot.sh cards-7_11_0.snapshot
#   ./scripts/restore_qdrant_snapshot.sh --force cards-7_11_0.snapshot
#
# Environment:
#   QDRANT_URL          default http://localhost:6333
#   QDRANT_COLLECTION   default cards
#   EXPECTED_POINTS     default 2512
set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-cards}"
EXPECTED_POINTS="${EXPECTED_POINTS:-2512}"

usage() {
  cat <<'EOF'
Usage: restore_qdrant_snapshot.sh [options] <snapshot-file>

Options:
  --force                 Hapus collection yang sudah ada sebelum restore
  --url URL               Qdrant URL (default: $QDRANT_URL)
  --collection NAME       Nama collection (default: $QDRANT_COLLECTION)
  --expected-points N     Jumlah point yang diharapkan (default: 2512)
  -h, --help              Tampilkan bantuan
EOF
}

FORCE=0
SNAPSHOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force|-f)
      FORCE=1
      shift
      ;;
    --url)
      QDRANT_URL="$2"
      shift 2
      ;;
    --collection)
      QDRANT_COLLECTION="$2"
      shift 2
      ;;
    --expected-points)
      EXPECTED_POINTS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      SNAPSHOT="$1"
      shift
      ;;
  esac
done

if [[ -z "$SNAPSHOT" || ! -f "$SNAPSHOT" ]]; then
  echo "Snapshot file tidak ditemukan: ${SNAPSHOT:-<empty>}" >&2
  usage >&2
  exit 2
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl tidak tersedia." >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 tidak tersedia untuk membaca respons JSON." >&2
  exit 2
fi

echo "Qdrant: $QDRANT_URL"
echo "Collection: $QDRANT_COLLECTION"
echo "Snapshot: $SNAPSHOT"

if ! curl -fsS "$QDRANT_URL/collections" >/dev/null; then
  echo "Qdrant tidak bisa diakses di $QDRANT_URL" >&2
  echo "Jalankan: docker compose up -d qdrant" >&2
  exit 3
fi

collection_exists() {
  curl -fsS "$QDRANT_URL/collections/$QDRANT_COLLECTION" >/dev/null 2>&1
}

points_count() {
  curl -fsS "$QDRANT_URL/collections/$QDRANT_COLLECTION" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["points_count"])'
}

if collection_exists; then
  current="$(points_count)"
  if [[ "$FORCE" -eq 1 ]]; then
    echo "Menghapus collection '$QDRANT_COLLECTION' ($current points) karena --force..."
    curl -fsS -X DELETE "$QDRANT_URL/collections/$QDRANT_COLLECTION" >/dev/null
  else
    cat >&2 <<EOF
Collection '$QDRANT_COLLECTION' sudah ada ($current points).
Gunakan --force kalau memang ingin menimpanya.
EOF
    exit 4
  fi
fi

echo "Mengunggah snapshot..."
curl -fsS -X POST \
  "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/upload?wait=true" \
  -F "snapshot=@$SNAPSHOT" >/dev/null

actual="$(points_count)"
echo "Points setelah restore: $actual"

if [[ "$actual" -ne "$EXPECTED_POINTS" ]]; then
  echo "Jumlah point tidak sesuai. Diharapkan $EXPECTED_POINTS, dapat $actual." >&2
  exit 5
fi

cat <<EOF
Restore selesai.

Langkah berikutnya:
  make vector-verify
  python -m src.vector.search "kartu yang membekukan musuh"

Catatan: query embedding tetap membutuhkan model intfloat/multilingual-e5-large.
EOF
