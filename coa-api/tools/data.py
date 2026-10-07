"""Cached loaders for the CSV files under dataset/. Stdlib csv: no pandas at runtime."""

import csv
from functools import lru_cache
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


@lru_cache
def load(name: str) -> tuple[dict[str, str], ...]:
    """Rows of dataset/<name>.csv as dicts. Cached; the files are read-only."""
    with (DATASET_DIR / f"{name}.csv").open(newline="", encoding="utf-8") as f:
        return tuple(csv.DictReader(f))
