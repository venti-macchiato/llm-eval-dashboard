"""Tests for hardware provenance: declared config fields and the host probe.

No test may run a real ``nvidia-smi``: the probe command is always supplied
explicitly, with a fake python one-liner standing in for the GPU tool.
"""

import shlex
import sys

import config
import hardware


def _probe_cfg(script: str, enabled: bool = True) -> dict:
    exe = shlex.quote(sys.executable)
    return {"enabled": enabled, "command": f"{exe} -c {shlex.quote(script)}", "timeout": 20}


def test_declared_normalises_numbers_and_drops_empty():
    cfg = {
        "hardware": {
            "backend": "llama.cpp",
            "quant": " Q3_K_XL ",
            "vram_gb": "24",
            "ctx_size": "32768",
            "gpu": "",
            "offload": None,
        }
    }
    assert hardware.declared(cfg) == {
        "backend": "llama.cpp",
        "quant": "Q3_K_XL",
        "vram_gb": 24.0,
        "ctx_size": 32768,
    }


def test_declared_handles_missing_or_malformed():
    assert hardware.declared({"name": "x"}) == {}
    assert hardware.declared({"hardware": "not-a-dict"}) == {}
    assert hardware.declared({"hardware": {"ctx_size": "lots"}}) == {}
    assert hardware.declared(None) == {}


def test_declared_keeps_gpu_list():
    cfg = {"hardware": {"gpu": ["RTX 4090", "RTX 4090"], "vram_gb": 24}}
    assert hardware.declared(cfg) == {"gpu": ["RTX 4090", "RTX 4090"], "vram_gb": 24.0}


def test_endpoint_host_parses_with_and_without_scheme():
    assert hardware.endpoint_host("http://127.0.0.1:8080/v1") == "127.0.0.1"
    assert hardware.endpoint_host("100.112.119.2:8080/v1") == "100.112.119.2"
    assert hardware.endpoint_host("") is None
    assert hardware.endpoint_host(None) is None


def test_is_local_endpoint():
    assert hardware.is_local_endpoint("http://127.0.0.1:8080/v1")
    assert hardware.is_local_endpoint("http://localhost:8080/v1")
    assert hardware.is_local_endpoint("http://[::1]:8080/v1")
    assert not hardware.is_local_endpoint("http://100.112.119.2:8080/v1")


def test_probe_parses_gpu_csv():
    probe_cfg = _probe_cfg("print('NVIDIA GeForce RTX 4090, 24564, 550.54')")
    result = hardware.probe({"base_url": "http://127.0.0.1:8080/v1"}, probe_cfg)
    assert result is not None
    assert result["source"] == "probe"
    assert result["host"]
    assert result["gpus"] == [
        {"name": "NVIDIA GeForce RTX 4090", "memory_gb": 24.0, "driver": "550.54"}
    ]


def test_probe_disabled_returns_none():
    probe_cfg = _probe_cfg("print('GPU, 1024, 1.0')", enabled=False)
    assert hardware.probe({"base_url": "http://127.0.0.1:8080/v1"}, probe_cfg) is None


def test_probe_skips_remote_endpoint():
    """A local GPU must never be attributed to a remote server."""
    probe_cfg = _probe_cfg("print('GPU, 1024, 1.0')")
    assert hardware.probe({"base_url": "http://100.112.119.2:8080/v1"}, probe_cfg) is None


def test_probe_survives_missing_command_and_bad_output():
    local = {"base_url": "http://127.0.0.1:8080/v1"}
    missing = {"enabled": True, "command": "definitely-not-a-real-binary-xyz", "timeout": 5}
    assert hardware.probe(local, missing) is None

    failing = _probe_cfg("raise SystemExit(3)")
    assert hardware.probe(local, failing) is None

    garbage = _probe_cfg("print('no csv here')")
    assert hardware.probe(local, garbage) is None


def test_snapshot_combines_declared_and_probe(monkeypatch):
    monkeypatch.setattr(
        config,
        "HOST_PROBE",
        _probe_cfg("print('NVIDIA GeForce RTX 4090, 24564, 550.54')"),
    )
    model = {
        "base_url": "http://127.0.0.1:8080/v1",
        "hardware": {"backend": "llama.cpp", "quant": "Q3_K_XL"},
    }
    snap = hardware.snapshot(model)
    assert snap["declared"] == {"backend": "llama.cpp", "quant": "Q3_K_XL"}
    assert snap["probe"]["gpus"][0]["memory_gb"] == 24.0


def test_snapshot_none_without_evidence(monkeypatch):
    monkeypatch.setattr(config, "HOST_PROBE", {})
    assert hardware.snapshot({"base_url": "http://127.0.0.1:8080/v1"}) is None
