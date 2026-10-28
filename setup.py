"""One-time project setup.

Copies config.yaml.example -> config.yaml so a fresh clone is ready to run.
Only creates config.yaml if it does not already exist, so any values you have
already filled in are never overwritten.

Run with:  python setup.py
"""

from __future__ import annotations

import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent
EXAMPLE = BASE_DIR / "config.yaml.example"
TARGET = BASE_DIR / "config.yaml"


def main() -> None:
    if not EXAMPLE.exists():
        raise SystemExit(f"missing {EXAMPLE.name}; cannot initialize config")

    if TARGET.exists():
        print(f"{TARGET.name} already exists; leaving it untouched.")
        return

    TARGET.write_bytes(EXAMPLE.read_bytes())
    print(f"Copied {EXAMPLE.name} -> {TARGET.name}. Edit it with your values.")


if __name__ == "__main__":
    main()
