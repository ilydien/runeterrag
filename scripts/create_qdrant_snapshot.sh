#!/usr/bin/env bash
# Buat dan unduh snapshot collection Qdrant untuk handoff.
#
# Contoh:
#   ./scripts/create_qdrant_snapshot.sh
#   ./scripts/create_qdrant_snapshot.sh --url http://localhost:6333
#
# Environment:
#   QDRANT_URL          default http://localhost:6333
#   QDRANT_COLLECTION   default cards
#   SNAPSHOT_DIR        default qdrant-snapshots
set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-cards}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-qdrant-snapshots}"

usage() {
  cat <<'EOF'
Usage: create_qdrant_snapshot.sh [options]

Options:
  --url URL           Qdrant URL (default: $QDRANT_URL)
  --collection NAME   Nama collection (default: $QDRANT_COLLECTION)
  --out DIR           Folder output (default: qdrant-snapshots)
  -h, --help          Tampilkan bantuan
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      QDRANT_URL="$2"
      shift 2
      ;;
    --collection)
      QDRANT_COLLECTION="$2"
      shift 2
      ;;
    --out)
      SNAPSHOT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! curl -fsS "$QDRANT_URL/collections/$QDRANT_COLLECTION" >/dev/null; then
  echo "Collection '$QDRANT_COLLECTION' tidak ditemukan di $QDRANT_URL" >&2
  exit 3
fi

mkdir -p "$SNAPSHOT_DIR"

echo "Membuat snapshot $QDRANT_COLLECTION..."
response="$(curl -fsS -X POST \
  "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots?wait=true")"
snapshot_name="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')"

if [[ -z "$snapshot_name" ]]; then
  echo "Gagal membaca nama snapshot dari respons Qdrant." >&2
  echo "$response" >&2
  exit 4
fi

target="$SNAPSHOT_DIR/$snapshot_name"
echo "Mengunduh snapshot ke $target..."
curl -fsS -o "$target" \
  "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$snapshot_name"

sha256sum "$target" > "$target.sha256"

cat <<EOF
Snapshot siap.

File : $target
Hash : $target.sha256
Size : $(du -h "$target" | cut -f1)

Untuk release asset, unggah file snapshot, .sha256, dan
data/processed/vector_manifest.json.
EOF
