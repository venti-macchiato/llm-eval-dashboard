"""Tests for the eval suite runner (evalrun.py / evaljobs.py).

These tests NEVER run the real ``inspect`` CLI and NEVER contact a server.
INSPECT_CMD is pointed at a small fake script (a Python file run via
sys.executable) that prints progress lines and a ``Log:`` line, can be told to
fail, and can sleep. The runner spawns it via subprocess exactly as it would
the real CLI.
"""

import os
import sys
import textwrap
import time
from pathlib import Path

import config
import pytest


import evaljobs
import evalrun


# The fake CLI. Behaviour is controlled by env vars the runner sets:
#   FAKE_OK_EXIT=1 -> exit non-zero after printing progress
#   FAKE_SLEEP=2   -> sleep instead of printing progress (for cancel test)
FAKE_SCRIPT = textwrap.dedent(
    """\
    import os, sys, time

    def _write_eval_log(task, logpath):
        from inspect_ai.log import (
            EvalConfig,
            EvalDataset,
            EvalLog,
            EvalMetric,
            EvalResults,
            EvalScore,
            EvalSpec,
            EvalStats,
            write_eval_log,
        )
        from datetime import datetime, timedelta
        model = "openai/tiel-coder-35b-a3b-ud-q3_k_xl"
        score = 0.8
        created = datetime.now() - timedelta(days=1)
        samples = 100
        se = round((score * (1 - score) / samples) ** 0.5, 4)
        metrics = {
            "accuracy": EvalMetric(name="accuracy", value=score),
            "stderr": EvalMetric(name="stderr", value=se),
        }
        result_score = EvalScore(
            name="score", scorer="accuracy", reducer="mean", metrics=metrics
        )
        results = EvalResults(
            total_samples=samples, completed_samples=samples, scores=[result_score]
        )
        stats = EvalStats(
            started_at=created.isoformat(), completed_at=created.isoformat()
        )
        spec = EvalSpec(
            eval_id=f"run_{task.replace('/', '_')}_{int(created.timestamp())}",
            run_id=f"{model}-{task}",
            created=created.isoformat(),
            task=task,
            task_id=task,
            task_version=1,
            task_display_name=task,
            model=model,
            dataset=EvalDataset(name=f"{task}-bench", samples=samples),
            config=EvalConfig(token_limit=128000),
        )
        log = EvalLog(
            version=1,
            status="success",
            eval=spec,
            results=results,
            stats=stats,
            metadata={"model": model},
        )
        log.location = logpath
        write_eval_log(log, format="eval")

    if "--version" in sys.argv:
        print("inspect fake 0.0.0")
        sys.exit(0)
    marker = os.environ.get("FAKE_MARKER", "")
    if marker:
        open(marker, "w").close()
    sleep = float(os.environ.get("FAKE_SLEEP", "0"))
    for i in range(1, 6):
        print(f"Samples: {i:>2}/ 5")
        if sleep:
            time.sleep(sleep)
        else:
            time.sleep(0.01)
    if os.environ.get("FAKE_OK_EXIT") == "1":
        print("Something went wrong")
        sys.exit(1)
    logdir = os.environ.get("FAKE_LOGDIR", "/tmp")
    os.makedirs(logdir, exist_ok=True)
    task = sys.argv[2] if len(sys.argv) > 2 else "inspect_evals/gsm8k"
    logpath = os.path.join(logdir, f"fake_run_{task.replace('/', '_')}.eval")
    _write_eval_log(task, logpath)
    print(f"Log: {logpath}")
    print("Score: 0.8")
    """
)


@pytest.fixture
def fake_cmd(tmp_path, monkeypatch):
    """Point INSPECT_CMD at the fake inspect script; reset job state."""
    script = tmp_path / "fake_inspect.py"
    script.write_text(FAKE_SCRIPT)
    monkeypatch.setattr("config.INSPECT_CMD", sys.executable + " " + str(script))
    monkeypatch.setattr("config.LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("config.DB_PATH", str(tmp_path / "bench.db"))
    monkeypatch.setattr(
        "config.MODELS",
        [
            {
                "name": "polystrata-q3",
                "inspect_model": "openai/tiel-coder-35b-a3b-ud-q3_k_xl",
                "base_url": "",
                "model_id": "tiel-coder-35b-a3b-ud-q3_k_xl",
                "api_key_file": "",
            }
        ],
    )
    monkeypatch.setattr(
        "config.SUITES",
        {
            "smoke": [
                {"task": "inspect_evals/ifeval", "limit": 5},
                {"task": "inspect_evals/gsm8k", "limit": 5},
            ]
        },
    )
    # Never run the real docker CLI from the test suite.
    import sandbox

    sandbox.clear_cache()
    monkeypatch.setattr(
        sandbox, "DOCKER_CMD", [sys.executable, "-c", "import sys; sys.exit(1)"]
    )
    evaljobs.start_job("polystrata-q3", "smoke", 0)
    yield script
    sandbox.clear_cache()
    evaljobs.start_job("polystrata-q3", "smoke", 0)


def _wait_done(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = evaljobs.get_job()
        if job and job["state"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    return evaljobs.get_job()


def test_success_suite_ends_done_and_ingests(fake_cmd, tmp_path, monkeypatch):
    import config
    monkeypatch.setenv("FAKE_LOGDIR", config.LOGS_DIR)
    result = evalrun.start_suite("polystrata-q3", "smoke")
    assert result == {"started": True}
    job = _wait_done()
    assert job["state"] == "done"
    assert job["task_index"] == job["task_total"]
    assert len(job["results"]) == job["task_total"]
    assert all(r["ok"] for r in job["results"])
    assert job["ingest"] is not None
    assert "new" in job["ingest"]


def test_failing_task_recorded_and_others_run(fake_cmd, tmp_path, monkeypatch):
    # Make task 1 fail (FAKE_OK_EXIT=1) but task 2 succeed. The runner runs
    # each task in sequence; we control per-task via a marker file.
    marker = tmp_path / "mode"
    marker.write_text("inspect_evals/ifeval")
    script = tmp_path / "fake_inspect.py"
    script.write_text(
        textwrap.dedent(
            """\
            import os, sys, time
            if "--version" in sys.argv:
                print("inspect fake 0.0.0")
                sys.exit(0)
            mode = open(os.environ.get("FAKE_MODE", "")).read().strip()
            task = sys.argv[2] if len(sys.argv) > 2 else ""
            for i in range(1, 6):
                print(f"Samples: {i:>2}/ 5")
                time.sleep(0.01)
            if mode and task == mode:
                print("AssertionError: missing optional dependency")
                print("Run: pip install inspect-evals")
                sys.exit(1)
            print("Log: /tmp/fake_run.eval")
            print("Score: 0.8")
            """
        )
    )
    monkeypatch.setenv("FAKE_MODE", str(marker))
    monkeypatch.setattr("config.INSPECT_CMD", sys.executable + " " + str(script))
    monkeypatch.setattr("config.LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("config.DB_PATH", str(tmp_path / "bench.db"))

    result = evalrun.start_suite("polystrata-q3", "smoke")
    assert result == {"started": True}
    job = _wait_done()
    assert job["state"] == "failed"
    assert job["results"][0]["ok"] is False
    assert "AssertionError" in job["error"]
    assert job["results"][1]["ok"] is True
    assert job["results"][1]["log_path"] == "/tmp/fake_run.eval"


def test_second_start_while_running_is_busy(fake_cmd):
    evaljobs.start_job("polystrata-q3", "smoke", 1)
    evaljobs.set_state(state="running")
    result = evalrun.start_suite("polystrata-q3", "smoke")
    assert result == {"started": False, "reason": "another job is running"}
    evaljobs.set_state(state="idle")

def test_cancel_works(fake_cmd, tmp_path, monkeypatch):
    # Use the shared script but make it sleep so we can cancel mid-run.
    script = fake_cmd
    monkeypatch.setenv("FAKE_SLEEP", "30")
    marker = tmp_path / "started"
    monkeypatch.setenv("FAKE_MARKER", str(marker))
    monkeypatch.setattr("config.INSPECT_CMD", sys.executable + " " + str(script))
    monkeypatch.setattr("config.LOGS_DIR", str(fake_cmd.parent / "logs"))
    monkeypatch.setattr("config.DB_PATH", str(fake_cmd.parent / "bench.db"))
    # Launch the suite; the fake sleeps so we can cancel mid-run.
    result = evalrun.start_suite("polystrata-q3", "smoke")
    assert result == {"started": True}
    # Wait for the child to actually be up (and tracked) before cancelling.
    deadline = time.time() + 5
    while time.time() < deadline and not marker.exists() and not evaljobs.has_process():
        time.sleep(0.02)
    cancelled = evalrun.cancel()
    assert cancelled is True
    job = _wait_done()
    assert job["state"] == "failed"
    assert "cancelled" in job["error"]


def test_unknown_model_rejected(fake_cmd):
    with pytest.raises(evalrun.EvalError, match="unknown model"):
        evalrun.start_suite("nope", "smoke")


def test_unknown_suite_rejected(fake_cmd):
    with pytest.raises(evalrun.EvalError, match="unknown suite"):
        evalrun.start_suite("polystrata-q3", "nope")


def test_env_has_keys_but_key_not_in_tail(fake_cmd, tmp_path, monkeypatch):
    keyfile = tmp_path / "key"
    keyfile.write_text("sk-testsecretkey1234567890abcdef")
    monkeypatch.setattr(
        config,
        "MODELS",
        [
            {
                "name": "polystrata-q3",
                "inspect_model": "openai/x",
                "base_url": "http://localhost:9/v1",
                "api_key_file": str(keyfile),
            }
        ],
    )
    env = evalrun._build_env(config.MODELS[0])
    assert env["OPENAI_BASE_URL"] == "http://localhost:9/v1"
    assert env["OPENAI_API_KEY"] == "sk-testsecretkey1234567890abcdef"
    # Redaction masks the key.
    assert "sk-testsecretkey" not in evaljobs.redact(env["OPENAI_API_KEY"])


def test_progress_parsing():
    assert evaljobs.parse_samples("Samples:   6/ 10") == (6, 10)
    assert evaljobs.parse_samples("Samples: 10/ 10") == (10, 10)
    assert evaljobs.parse_samples("no match") is None


def test_cancel_after_completion_is_a_noop(fake_cmd, monkeypatch):
    monkeypatch.setenv("FAKE_LOGDIR", config.LOGS_DIR)
    assert evalrun.start_suite("polystrata-q3", "smoke") == {"started": True}
    job = _wait_done()
    assert job["state"] == "done"

    assert evaljobs.cancel() is False
    after = evaljobs.get_job()
    assert after["state"] == "done"
    assert after["error"] is None


def test_try_start_is_atomic(fake_cmd):
    evaljobs.start_job("polystrata-q3", "smoke", 0)  # idle
    first = evaljobs.try_start("polystrata-q3", "smoke", 1)
    second = evaljobs.try_start("polystrata-q3", "smoke", 1)
    assert first is not None
    assert second is None


def _recording_cli(tmp_path, monkeypatch):
    """Fake CLI that records its argv so repeat/epoch flags can be asserted."""
    calls = tmp_path / "calls.txt"
    script = tmp_path / "record_inspect.py"
    script.write_text(
        textwrap.dedent(
            f"""\
            import sys, time
            if "--version" in sys.argv:
                print("inspect fake 0.0.0")
                sys.exit(0)
            with open({str(calls)!r}, "a") as fh:
                fh.write(" ".join(sys.argv[1:]) + "\\n")
            epochs = 1
            for arg in sys.argv:
                if arg.startswith("--epochs="):
                    epochs = int(arg.split("=", 1)[1])
            total = 3 * epochs
            for i in range(1, total + 1):
                print(f"Samples: {{i}}/{{total}}")
                time.sleep(0.003)
            print("Log: /nonexistent/record.eval")
            """
        )
    )
    monkeypatch.setattr("config.INSPECT_CMD", sys.executable + " " + str(script))
    monkeypatch.setattr("config.LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("config.DB_PATH", str(tmp_path / "bench.db"))
    monkeypatch.setattr(
        "config.SUITES",
        {"one": [{"task": "inspect_evals/gsm8k", "limit": 3}]},
    )
    return calls


def test_repeats_run_cli_once_per_repeat(fake_cmd, tmp_path, monkeypatch):
    calls = _recording_cli(tmp_path, monkeypatch)
    assert evalrun.start_suite("polystrata-q3", "one", repeats=2, epochs=3) == {
        "started": True
    }
    job = _wait_done()
    assert job["state"] == "done"
    assert len(job["results"]) == 2
    assert [r["repeat"] for r in job["results"]] == [1, 2]
    assert job["repeat_total"] == 2
    # Progress spans both repeats and epoch-scaled samples (3 limit x 3 epochs).
    assert job["samples_total"] == 18
    assert job["samples_done"] == 18

    lines = calls.read_text().strip().splitlines()
    assert len(lines) == 2
    assert all("--epochs=3" in line for line in lines)
    assert all("--limit=3" in line for line in lines)


def test_epochs_flag_only_when_requested(fake_cmd, tmp_path, monkeypatch):
    calls = _recording_cli(tmp_path, monkeypatch)
    assert evalrun.start_suite("polystrata-q3", "one") == {"started": True}
    assert _wait_done()["state"] == "done"
    lines = calls.read_text().strip().splitlines()
    assert len(lines) == 1
    assert "--epochs" not in lines[0]


def test_task_epochs_override_the_run_default(fake_cmd, tmp_path, monkeypatch):
    calls = _recording_cli(tmp_path, monkeypatch)
    tasks = [{"task": "inspect_evals/gsm8k", "limit": 2, "epochs": 2}]
    assert evalrun.start_suite(
        "polystrata-q3", "one", tasks=tasks, epochs=5
    ) == {"started": True}
    assert _wait_done()["state"] == "done"
    assert "--epochs=2" in calls.read_text()


def test_missing_sandbox_blocks_start(fake_cmd, monkeypatch):
    import sandbox

    sandbox.clear_cache()
    monkeypatch.setattr(
        sandbox, "DOCKER_CMD", [sys.executable, "-c", "import sys; sys.exit(1)"]
    )
    monkeypatch.setattr(
        "config.SUITES",
        {"code": [{"task": "inspect_evals/humaneval", "limit": 1}]},
    )
    with pytest.raises(evalrun.EvalError, match="needs Docker"):
        evalrun.start_suite("polystrata-q3", "code")
    # Nothing was claimed: the job slot is still idle.
    assert evaljobs.get_job()["state"] == "idle"
    sandbox.clear_cache()


def test_docker_probe_not_run_for_plain_tasks(fake_cmd, tmp_path, monkeypatch):
    """A suite without sandbox tasks must not shell out to docker at all."""
    import sandbox

    marker = tmp_path / "docker_called"
    script = (
        f"open({str(marker)!r}, 'a').write('x'); "
        "import sys; sys.exit(1)"
    )
    monkeypatch.setattr(sandbox, "DOCKER_CMD", [sys.executable, "-c", script])
    sandbox.clear_cache()
    monkeypatch.setenv("FAKE_LOGDIR", config.LOGS_DIR)
    assert evalrun.start_suite("polystrata-q3", "smoke") == {"started": True}
    assert _wait_done()["state"] == "done"
    assert not marker.exists()


def test_prompt_run_blocks_eval_start(fake_cmd, monkeypatch):
    import promptharness

    monkeypatch.setattr(promptharness, "is_running", lambda: True)
    with pytest.raises(evalrun.EvalError, match="prompt run"):
        evalrun.start_suite("polystrata-q3", "smoke")
    assert evaljobs.get_job()["state"] == "idle"
