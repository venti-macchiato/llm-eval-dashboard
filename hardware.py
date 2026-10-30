"""Hardware and backend provenance for a model.

Neither inspect's ``.eval`` log nor an OpenAI-compatible endpoint reports the
machine, quantisation, or context size a model runs with, yet those decide
whether two scores are comparable at all. The dashboard therefore records two
independent kinds of evidence:

* **declared** - fields under each model's ``hardware:`` block in
  ``config.yaml``. Authoritative, and the only option when the endpoint is
  remote (a tailnet peer or LAN box).
* **probe** - an optional local ``nvidia-smi`` query (``host_probe`` in
  ``config.yaml``). Only recorded when the endpoint host is this machine, and
  tagged with the probed hostname, so local GPU evidence is never mistaken for
  a remote server's hardware.

Nothing here raises: provenance is enrichment and must not block ingestion.
"""

from __future__ import annotations

import shlex
import socket
import subprocess
from datetime import datetime
from urllib.parse import urlsplit

import config

# nvidia-smi emits "MiB" for memory.total; nounits keeps it parseable.
DEFAULT_COMMAND = (
    "nvidia-smi --query-gpu=name,memory.total,driver_version "
    "--format=csv,noheader,nounits"
)

_NUMERIC = {"vram_gb": float, "ctx_size": int, "timeout": float}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _coerce(key: str, value):
    """Coerce one declared value; return None for anything unusable."""
    if value is None or isinstance(value, bool):
        return value
    if key in _NUMERIC:
        try:
            return _NUMERIC[key](value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        items = [_coerce(key, item) for item in value]
        items = [item for item in items if item not in (None, "")]
        return items or None
    return None


def declared(model_cfg: dict | None) -> dict:
    """Normalise a model's declared ``hardware:`` block into a flat dict."""
    if not isinstance(model_cfg, dict):
        return {}
    raw = model_cfg.get("hardware")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name or name.startswith("_"):
            continue
        coerced = _coerce(name, value)
        if coerced is not None:
            out[name] = coerced
    return out


def endpoint_host(base_url: str | None) -> str | None:
    """Hostname/IP from an endpoint URL, tolerating a missing scheme."""
    if not base_url:
        return None
    url = base_url if "://" in base_url else f"http://{base_url}"
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def local_addresses() -> set[str]:
    """Names and addresses that identify this machine."""
    names = {socket.gethostname().lower(), socket.getfqdn().lower()}
    addrs: set[str] = set()
    for name in list(names):
        try:
            _, _, ips = socket.gethostbyname_ex(name)
        except OSError:
            continue
        addrs.update(ip for ip in ips if ip)
    return {n for n in names if n} | addrs


def is_local_endpoint(base_url: str | None) -> bool:
    """True when the endpoint host is this machine.

    A local probe only describes the server if the server is here; otherwise
    the GPU would be evidence about the wrong box.
    """
    host = endpoint_host(base_url)
    if not host:
        return False
    host = host.lower()
    if host in _LOCAL_HOSTS:
        return True
    return host in local_addresses()


def _parse_gpus(text: str) -> list[dict]:
    """Parse ``nvidia-smi --format=csv,noheader,nounits`` output."""
    gpus: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name,"):
            continue
        parts = [part.strip() for part in line.split(",")]
        # The documented contract is `name, memory, driver`; a line without a
        # memory column is not nvidia-smi output and must not become evidence.
        if len(parts) < 2 or not parts[0]:
            continue
        try:
            memory_gb = round(float(parts[1]) / 1024, 1)
        except ValueError:
            continue
        gpu: dict = {"name": parts[0], "memory_gb": memory_gb}
        if len(parts) > 2 and parts[2]:
            gpu["driver"] = parts[2]
        gpus.append(gpu)
    return gpus


def probe(model_cfg: dict | None = None, probe_cfg: dict | None = None) -> dict | None:
    """Run the configured host probe for one model.

    Returns a snapshot tagged ``source: "probe"`` with the probed hostname, or
    None when the probe is disabled, the endpoint is remote, the command is
    missing, or its output is unusable.
    """
    cfg = config.HOST_PROBE if probe_cfg is None else probe_cfg
    if not isinstance(cfg, dict) or not cfg.get("enabled"):
        return None
    model_cfg = model_cfg or {}
    if not is_local_endpoint(model_cfg.get("base_url")):
        return None
    command = str(cfg.get("command") or DEFAULT_COMMAND)
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if not argv:
        return None
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=float(cfg.get("timeout") or 10),
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    gpus = _parse_gpus(proc.stdout)
    if not gpus:
        return None
    return {
        "source": "probe",
        "host": socket.gethostname(),
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "command": command,
        "gpus": gpus,
    }


def snapshot(model_cfg: dict | None) -> dict | None:
    """Declared + probed hardware evidence for a model, or None if neither."""
    out: dict = {}
    declared_block = declared(model_cfg)
    if declared_block:
        out["declared"] = declared_block
    probed = probe(model_cfg)
    if probed:
        out["probe"] = probed
    return out or None
