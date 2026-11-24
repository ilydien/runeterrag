"""Hapus seluruh node/edge dari Neo4j (untuk reload bersih).

Jalankan:
    python -m src.graph.reset
"""

from __future__ import annotations

import logging

from neo4j import GraphDatabase

from src.common import config

logger = logging.getLogger(__name__)


def reset_graph(driver, batch_size: int = 10000) -> int:
    total = 0
    with driver.session(database=config.NEO4J_DATABASE) as session:
        while True:
            record = session.run(
                "MATCH (n) WITH n LIMIT $batch "
                "DETACH DELETE n RETURN count(*) AS deleted",
                batch=batch_size,
            ).single()
            deleted = int(record["deleted"]) if record else 0
            total += deleted
            if deleted == 0:
                break
    return total


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    driver = GraphDatabase.driver(
        config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )
    try:
        total = reset_graph(driver)
        logger.info("Selesai. %d node dihapus dari graph.", total)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
