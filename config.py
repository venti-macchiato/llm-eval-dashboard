"""Load config.yaml into importable constants.

Kept separate from the fixed contract file so modules can import
LOGS_DIR, DB_PATH, INSPECT_CMD, SUITES, and MODELS without touching yaml.
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
INSPECT_CMD: str = _CONFIG.get("inspect_cmd", "")
SUITES: dict[str, list[dict]] = _CONFIG.get("suites", {})
MODELS: list[dict] = _CONFIG.get("models", [])
PROMPTS_PATH = BASE_DIR / _CONFIG.get("prompts_path", "prompts.yaml")

# Optional local host probe (nvidia-smi). Off unless enabled in config.yaml:
# it only describes the server when the endpoint is this machine.
_HOST_PROBE = _CONFIG.get("host_probe")
HOST_PROBE: dict = _HOST_PROBE if isinstance(_HOST_PROBE, dict) else {}
