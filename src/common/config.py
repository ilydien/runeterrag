"""Konfigurasi terpusat untuk RuneTerraRAG.

Semua path dan kredensial dibaca dari environment variable agar aman
dipakai baik saat run lokal maupun di dalam Docker Compose.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# .env hanya ada saat run lokal; di Docker env sudah di-inject oleh Compose.
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default.resolve()
    return Path(value).expanduser().resolve()


DATA_DIR = _path_from_env("DATA_DIR", PROJECT_ROOT / "data")
LATEST_DIR = DATA_DIR / "latest"
GLOBALS_FILE = DATA_DIR / "globals-en_us.json"
PROCESSED_DIR = _path_from_env("PROCESSED_DIR", DATA_DIR / "processed")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "runeterra123")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "500"))
DEFAULT_PATCH = os.getenv("DATA_PATCH", "7_11_0")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "cards")
