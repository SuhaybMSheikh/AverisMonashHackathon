"""Measure representative local API list/detail latency for the 520-email demo."""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings_from_env
from backend.app.main import create_app


def measure(client, path: str, repeats: int = 5) -> dict:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        response = client.get(path)
        samples.append((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            raise RuntimeError(f"{path}: HTTP {response.status_code}")
    return {"path": path, "median_ms": round(statistics.median(samples), 2), "max_ms": round(max(samples), 2)}


def main() -> None:
    settings = settings_from_env()
    app = create_app({"DATA_DIR": settings.data_dir, "DATABASE_PATH": settings.database_path, "DERIVED_DIR": settings.derived_dir})
    client = app.test_client()
    results = [measure(client, "/api/emails?page=1&page_size=50"), measure(client, "/api/emails/email_004"), measure(client, "/api/emails/email_004/comparison")]
    for result in results:
        print(f"{result['path']}: median {result['median_ms']} ms, max {result['max_ms']} ms")


if __name__ == "__main__":
    main()
