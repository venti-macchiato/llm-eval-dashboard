"""Custom prompt tests: user-defined prompts with pass/fail criteria.

Definitions live in ``prompts.yaml`` (user-editable, like ``benchmarks.yaml``).
Each entry is a prompt plus a check that turns the model's reply into a
pass/fail. Malformed files or entries degrade to "no tests" rather than
crashing the app.

Supported checks (``check.type``):
  contains / not_contains  substring, case-insensitive by default
  regex                    re.search with an optional ignore_case
  equals                   normalised (whitespace + case) equality
  json                     parse JSON (fenced or embedded), require keys/types
  tool_call                a tool call with the given name/arguments
  refusal                  the reply declines (default: common refusal phrases)
  recall                   a generated needle must reappear in the reply
  max_words                reply length in words
"""

from __future__ import annotations

import json
import re

import yaml

import config

DEFAULT_REFUSALS = [
    "cannot",
    "can't",
    "can not",
    "unable to",
    "won't",
    "will not",
    "not able to",
    "i'm sorry",
    "i am sorry",
]


def _clean(value, limit: int = 2000) -> str:
    text = str(value).strip() if value is not None else ""
    return text[:limit]


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _check_spec(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("type") or "").strip().lower()
    if not kind:
        return None
    spec = dict(raw)
    spec["type"] = kind
    return spec


def load(path: str | None = None) -> list[dict]:
    """Load and validate prompt tests. Returns [] on any file problem."""
    target = path or config.PROMPTS_PATH
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    items = data.get("prompts")
    if not isinstance(items, list):
        return []

    tests: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        test_id = _clean(item.get("id"), 80)
        prompt = _clean(item.get("prompt"), 20000)
        spec = _check_spec(item.get("check"))
        if not test_id or not prompt or spec is None or test_id in seen:
            continue
        seen.add(test_id)
        test = {
            "id": test_id,
            "title": _clean(item.get("title"), 120) or test_id,
            "category": _clean(item.get("category"), 40) or "custom",
            "description": _clean(item.get("description"), 400),
            "prompt": prompt,
            "check": spec,
            "max_tokens": _int(item.get("max_tokens") or 512, 512),
            "temperature": _float(item.get("temperature") or 0, 0.0),
            "context_tokens": _int(item.get("context_tokens") or 2000, 2000),
        }
        if item.get("system"):
            test["system"] = _clean(item.get("system"), 2000)
        if isinstance(item.get("tools"), list) and item["tools"]:
            test["tools"] = item["tools"]
        tests.append(test)
    return tests


# --- checkers ---------------------------------------------------------------


def _normalise(text: str) -> str:
    return " ".join(text.split()).lower()


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _extract_json(text: str):
    stripped = _strip_fences(text)
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(stripped[start : end + 1])
        except ValueError:
            return None
    return None


def _type_ok(value, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True


def check(
    spec: dict,
    output: str,
    tool_calls: list[dict] | None = None,
    needle: str | None = None,
):
    """Return ``(passed, detail)`` for one reply."""
    kind = spec.get("type")
    text = output or ""
    insensitive = not spec.get("case_sensitive", False)

    if kind in ("contains", "not_contains"):
        value = _clean(spec.get("value"))
        if not value:
            return False, "check is missing 'value'"
        haystack = text.lower() if insensitive else text
        found = (value.lower() if insensitive else value) in haystack
        if kind == "contains":
            return (True, f"found {value!r}") if found else (False, f"missing {value!r}")
        return (False, f"must not contain {value!r}") if found else (True, f"{value!r} absent")

    if kind == "regex":
        pattern = _clean(spec.get("pattern"))
        if not pattern:
            return False, "check is missing 'pattern'"
        try:
            match = re.search(pattern, text, re.IGNORECASE if insensitive else 0)
        except re.error as exc:
            return False, f"invalid pattern: {exc}"
        return (True, "pattern matched") if match else (False, "pattern not found")

    if kind == "equals":
        expected = _clean(spec.get("value"))
        if not expected:
            return False, "check is missing 'value'"
        got = _normalise(text)
        want = _normalise(expected)
        return (True, "exact match") if got == want else (False, f"expected {expected[:80]!r}")

    if kind == "max_words":
        try:
            limit = int(spec.get("value"))
        except (TypeError, ValueError):
            return False, "check is missing a numeric 'value'"
        count = len(text.split())
        return (True, f"{count} words") if count <= limit else (False, f"{count} words > {limit}")

    if kind == "json":
        parsed = _extract_json(text)
        if parsed is None:
            return False, "reply is not parseable JSON"
        if not isinstance(parsed, dict):
            return False, "JSON root is not an object"
        required = spec.get("required") or []
        missing = [key for key in required if key not in parsed]
        if missing:
            return False, f"missing key(s): {', '.join(map(str, missing))}"
        properties = spec.get("properties") or {}
        if isinstance(properties, dict):
            for key, expected in properties.items():
                if key in parsed and not _type_ok(parsed[key], str(expected)):
                    return False, f"{key} is not {expected}"
        return True, "valid JSON with required keys"

    if kind == "tool_call":
        name = _clean(spec.get("name"))
        if not name:
            return False, "check is missing 'name'"
        calls = tool_calls or []
        for call in calls:
            function = call.get("function") or {}
            if function.get("name") != name:
                continue
            arguments = function.get("arguments")
            try:
                parsed_args = json.loads(arguments) if isinstance(arguments, str) else arguments
            except ValueError:
                parsed_args = None
            required = spec.get("required_args") or []
            if required and not isinstance(parsed_args, dict):
                return False, f"{name} arguments are not a JSON object"
            missing = [arg for arg in required if not isinstance(parsed_args, dict) or arg not in parsed_args]
            if missing:
                return False, f"{name} missing argument(s): {', '.join(missing)}"
            return True, f"called {name}"
        return False, f"no tool call to {name}"

    if kind == "refusal":
        raw = spec.get("any_of")
        if isinstance(raw, str):
            phrases = [raw]
        elif isinstance(raw, list):
            phrases = [str(phrase) for phrase in raw if str(phrase).strip()]
        else:
            phrases = DEFAULT_REFUSALS
        if not phrases:
            phrases = DEFAULT_REFUSALS
        lowered = text.lower()
        hit = next((phrase for phrase in phrases if str(phrase).lower() in lowered), None)
        return (True, f"refused ({hit})") if hit else (False, "did not refuse")

    if kind == "recall":
        if not needle:
            return False, "no needle generated for this run"
        return (True, "needle recalled") if needle.lower() in text.lower() else (False, f"missing {needle}")

    return False, f"unknown check type: {kind}"
