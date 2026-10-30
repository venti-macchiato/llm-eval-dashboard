"""Font face CSS for locally licensed Proxima Nova files.

Proxima Nova is a commercial typeface, so it is not bundled with the dashboard.
Drop licensed ``.woff2`` files into ``static/fonts/`` (for example
``ProximaNova-Regular.woff2``, ``ProximaNova-Medium.woff2``,
``ProximaNova-Semibold.woff2``, ``ProximaNova-Bold.woff2``,
``ProximaNova-Extrabold.woff2``) and this module emits matching ``@font-face``
rules. With no files (and no system-installed font) it emits nothing, so the
CSS stack falls back without 404s or console noise.
"""

from __future__ import annotations

import pathlib

FAMILY = "Proxima Nova"

# Checked in order; the first token found wins.
_WEIGHTS = (
    ("extrabold", 800),
    ("extra-bold", 800),
    ("semibold", 600),
    ("semi-bold", 600),
    ("demibold", 600),
    ("medium", 500),
    ("black", 900),
    ("heavy", 900),
    ("bold", 700),
    ("light", 300),
    ("thin", 200),
)


def _weight(name: str) -> int:
    lowered = name.lower()
    for token, weight in _WEIGHTS:
        if token in lowered:
            return weight
    return 400


def _style(name: str) -> str:
    lowered = name.lower()
    return "italic" if "italic" in lowered or "oblique" in lowered else "normal"


def font_css(directory: str | pathlib.Path) -> str:
    """``@font-face`` rules for every .woff2 file in ``directory``."""
    root = pathlib.Path(directory)
    if not root.is_dir():
        return ""
    rules = []
    for path in sorted(root.glob("*.woff2")):
        rules.append(
            "@font-face{"
            f'font-family:"{FAMILY}";'
            f'src:url("/static/fonts/{path.name}") format("woff2");'
            f"font-weight:{_weight(path.stem)};"
            f"font-style:{_style(path.name)};"
            "font-display:swap;"
            "}"
        )
    return "\n".join(rules)
