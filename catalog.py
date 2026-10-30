"""inspect_evals task catalog.

Reads the task names exported by ``inspect_evals._registry`` *without*
importing it (importing executes ~250 task modules and can be slow or fail on
optional dependencies). The registry re-exports both tasks and scorers, so the
imported names are filtered against ``@task``-decorated functions found by
parsing the referenced packages. If the package is missing, the catalog is
empty rather than an error.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import threading

_cache: list[str] | None = None
_lock = threading.Lock()


def _has_task_decorator(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "task":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "task":
            return True
    return False


def _decorated_names(directory: pathlib.Path) -> set[str]:
    """Names of ``@task`` functions defined anywhere under ``directory``."""
    names: set[str] = set()
    for path in directory.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _has_task_decorator(node):
                names.add(node.name)
    return names


def _package_dir(module: str) -> pathlib.Path | None:
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    return pathlib.Path(spec.origin).parent


def _scan(origin: str) -> tuple[set[str], set[str]]:
    """Return (imported names, names backed by a @task function)."""
    tree = ast.parse(pathlib.Path(origin).read_text(encoding="utf-8"))
    imported: set[str] = set()
    tasks: set[str] = set()
    seen_dirs: set[pathlib.Path] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("inspect_evals"):
            continue
        names = {alias.asname or alias.name for alias in node.names}
        imported.update(name for name in names if name and not name.startswith("_"))
        directory = _package_dir(node.module)
        if directory is None or directory in seen_dirs:
            continue
        seen_dirs.add(directory)
        tasks.update(_decorated_names(directory))

    return imported, tasks


def load_catalog() -> list[str]:
    """Return sorted inspect_evals task names, cached after the first call."""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        names: set[str] = set()
        try:
            spec = importlib.util.find_spec("inspect_evals._registry")
            origin = spec.origin if spec else None
            if origin:
                imported, tasks = _scan(origin)
                # A package that could not be parsed leaves the decorator set
                # incomplete; fail open rather than hide real tasks.
                names = imported & tasks if tasks else imported
        except (ImportError, OSError, SyntaxError, ValueError):
            names = set()
        _cache = sorted(names)
        return _cache
