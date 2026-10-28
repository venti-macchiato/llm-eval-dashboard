"""Load config.yaml into importable constants.

Kept separate from the fixed contract file so modules can import
LOGS_DIR, DB_PATH, MODELS, and INSPECT_VIEW_URL without touching yaml.
"""

from __future__ import annotations

import pathlib

import yaml

BASE_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"


def _load(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


_CONFIG = _load(CONFIG_PATH)

LOGS_DIR: str = _CONFIG.get("logs_dir", "sample_logs")
DB_PATH: str = _CONFIG.get("db_path", "bench.db")
INSPECT_VIEW_URL: str = _CONFIG.get("inspect_view_url", "")
MODELS: list[dict] = _CONFIG.get("models", [])
