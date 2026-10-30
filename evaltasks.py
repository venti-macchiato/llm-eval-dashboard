"""Task-list normalization and validation errors for eval runs."""

from __future__ import annotations

import config


class EvalError(Exception):
    """Raised for unknown model/suite or a missing/invalid inspect CLI."""


def suite_for(suite_name: str) -> list[dict]:
    suites = config.SUITES
    if suite_name not in suites:
        known = ", ".join(sorted(suites)) or "(none configured)"
        raise EvalError(f"unknown suite: {suite_name} (known: {known})")
    return suites[suite_name]


def with_defaults(items: list[dict], epochs: int | None) -> list[dict]:
    """Normalise a task list, applying the run-wide epochs default."""
    out = []
    for item in items:
        name = str(item.get("task", "")).strip()
        if not name:
            continue
        try:
            limit = int(item.get("limit", 20))
        except (TypeError, ValueError):
            limit = 20
        raw_epochs = item.get("epochs", epochs)
        try:
            item_epochs = int(raw_epochs) if raw_epochs is not None else 1
        except (TypeError, ValueError):
            item_epochs = 1
        out.append(
            {
                "task": name,
                "limit": max(1, limit),
                "epochs": max(1, min(item_epochs, 20)),
            }
        )
    return out


def normalise_tasks(
    suite_name: str, tasks: list[dict] | None, epochs: int | None = None
) -> list[dict]:
    """Return a task list, from an explicit override or the named suite."""
    if tasks:
        out = with_defaults(tasks, epochs)
        if out:
            return out
    return with_defaults(suite_for(suite_name), epochs)
