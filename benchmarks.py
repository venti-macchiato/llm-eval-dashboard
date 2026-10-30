"""Load benchmark metadata from ``benchmarks.yaml``.

Task ids match inspect_evals names. ``measures`` and ``read`` are curated
explanations; the file is plain YAML so it can be edited without touching
Python.
"""

from __future__ import annotations

import pathlib
import threading

import yaml

_PATH = pathlib.Path(__file__).resolve().parent / "benchmarks.yaml"
_cache: dict | None = None
_lock = threading.Lock()
_EMPTY = {"categories": [], "benchmarks": {}, "suites": {}}


def _load() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return dict(_EMPTY)
    if not isinstance(data, dict):
        return dict(_EMPTY)
    out: dict = {}
    for key, default in _EMPTY.items():
        value = data.get(key)
        out[key] = value if isinstance(value, type(default)) else default
    return out


def payload() -> dict:
    """Categories, benchmark descriptions, and suite blurbs (cached)."""
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load()
        return _cache
