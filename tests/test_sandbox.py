"""Tests for sandbox preflight (sandbox.py). Never runs a real docker."""

import sys

import pytest

import sandbox


def _cmd(script: str) -> list[str]:
    return [sys.executable, "-c", script]


@pytest.fixture(autouse=True)
def _clear_cache():
    sandbox.clear_cache()
    yield
    sandbox.clear_cache()


def test_required_maps_known_tasks():
    assert sandbox.required("inspect_evals/humaneval") == ["docker"]
    assert sandbox.required("MBPP") == ["docker"]
    assert sandbox.required("inspect_evals/ifeval") == []
    assert sandbox.required("gsm8k") == []


def test_docker_available(monkeypatch):
    monkeypatch.setattr(sandbox, "DOCKER_CMD", _cmd("print('24.0.7')"))
    assert sandbox.docker_status() == {"available": True, "detail": "24.0.7"}
    assert sandbox.capabilities()["docker"]["available"] is True


def test_docker_cli_missing(monkeypatch):
    monkeypatch.setattr(sandbox, "DOCKER_CMD", ["definitely-not-a-real-binary-xyz"])
    status = sandbox.docker_status()
    assert status["available"] is False
    assert "not found" in status["detail"]


def test_docker_daemon_down(monkeypatch):
    monkeypatch.setattr(
        sandbox,
        "DOCKER_CMD",
        _cmd("import sys; print('cannot connect to the Docker daemon'); sys.exit(1)"),
    )
    status = sandbox.docker_status()
    assert status["available"] is False
    assert "cannot connect" in status["detail"]


def test_missing_and_ensure(monkeypatch):
    monkeypatch.setattr(sandbox, "DOCKER_CMD", _cmd("import sys; sys.exit(1)"))
    assert sandbox.missing(["inspect_evals/ifeval"]) == {}
    assert sandbox.missing(["inspect_evals/humaneval", "inspect_evals/ifeval"]) == {
        "inspect_evals/humaneval": ["docker"]
    }
    with pytest.raises(sandbox.SandboxError) as excinfo:
        sandbox.ensure(["inspect_evals/humaneval"])
    message = str(excinfo.value)
    assert "humaneval needs Docker" in message
    assert "Start Docker Desktop" in message


def test_ensure_passes_when_available(monkeypatch):
    monkeypatch.setattr(sandbox, "DOCKER_CMD", _cmd("print('24.0.7')"))
    sandbox.ensure(["inspect_evals/humaneval", "inspect_evals/ifeval"])


def test_no_probe_when_no_task_needs_a_capability(monkeypatch, tmp_path):
    marker = tmp_path / "docker_called"
    monkeypatch.setattr(
        sandbox,
        "DOCKER_CMD",
        [
            sys.executable,
            "-c",
            f"open({str(marker)!r}, 'a').write('x'); import sys; sys.exit(1)",
        ],
    )
    assert sandbox.missing(["inspect_evals/ifeval", "inspect_evals/gsm8k"]) == {}
    assert not marker.exists()
