"""In-memory state for a running eval job.

A single job lives at module scope: the dashboard runs one suite at a time
(the model server handles one request at a time), so there is one current job
and the API just reads its state. State is a plain dict so it can be returned
verbatim by the endpoints.
"""

from __future__ import annotations

import re
import threading

# One job at a time; the model server serializes requests.
_job: dict | None = None
_proc = None
_lock = threading.Lock()

# Progress lines: "Samples:   6/ 10" or a bare "6/10" on a line mentioning
# samples (inspect's plain display varies between versions).
_SAMPLES_RE = re.compile(r"Samples:\s*(\d+)\s*/\s*(\d+)")
_SAMPLES_LOOSE = re.compile(r"(\d+)\s*/\s*(\d+)")

# API keys look like long base64/hex strings; redact if they ever appear in
# the captured log tail.
_KEY_RE = re.compile(r"(sk-[A-Za-z0-9]{20,}|[A-Za-z0-9]{32,})")


def redact(text: str) -> str:
    """Mask likely API keys so they never land in log tail / status."""
    return _KEY_RE.sub("<redacted>", text)


def parse_samples(line: str) -> tuple[int, int] | None:
    """Parse 'Samples:   6/ 10' -> (6, 10). Returns None if not found."""
    m = _SAMPLES_RE.search(line)
    if not m and "sample" in line.lower():
        m = _SAMPLES_LOOSE.search(line)
    if not m:
        return None
    done, total = int(m.group(1)), int(m.group(2))
    if total <= 0:
        return None
    return done, total


def append_tail(line: str, max_tail: int = 40) -> None:
    """Append a redacted line to the current job's log tail under the lock."""
    with _lock:
        if _job is None:
            return
        tail = _job["log_tail"]
        tail.append(line)
        if len(tail) > max_tail:
            _job["log_tail"] = tail[-max_tail:]


def start_job(model: str, suite_name: str, task_total: int) -> dict:
    """Create a fresh idle job record for the given model/suite."""
    global _job, _proc
    from datetime import datetime

    with _lock:
        _job = {
            "state": "idle",
            "model": model,
            "suite": suite_name,
            "task_index": 0,
            "task_total": task_total,
            "current_task": None,
            "samples_done": 0,
            "samples_total": 0,
            "log_tail": [],
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "error": None,
            "results": [],
            "ingest": None,
            "cancel_requested": False,
            "repeat_index": 0,
            "repeat_total": 0,
        }
        _proc = None
    return _job


def try_start(model: str, suite_name: str, task_total: int) -> dict | None:
    """Atomically claim the single job slot.

    Returns the new job record with ``state="running"``, or None if another
    job is still active. Checking and replacing happen under one lock so two
    concurrent starts cannot both succeed.
    """
    global _job, _proc
    from datetime import datetime

    with _lock:
        if _job is not None and _job.get("state") not in ("done", "failed", "idle"):
            return None
        _job = {
            "state": "running",
            "model": model,
            "suite": suite_name,
            "task_index": 0,
            "task_total": task_total,
            "current_task": None,
            "samples_done": 0,
            "samples_total": 0,
            "log_tail": [],
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "error": None,
            "results": [],
            "ingest": None,
            "cancel_requested": False,
            "repeat_index": 0,
            "repeat_total": 0,
        }
        _proc = None
        return dict(_job)


def finish(state: str, error: str | None = None) -> None:
    """Publish the terminal state and clear runtime fields under one lock.

    Doing this in a single critical section means the job slot is only free
    once every final write (state, error, finished_at, current_task, process)
    has happened.
    """
    global _proc
    from datetime import datetime

    with _lock:
        if _job is None:
            return
        _job["state"] = state
        if error is not None:
            _job["error"] = error
        _job["finished_at"] = datetime.now().isoformat()
        _job["current_task"] = None
        _job["phase"] = None
        _proc = None


def cancel() -> bool:
    """Request cancellation of the running job.

    Terminates the child if alive and flags the job; the worker thread marks
    the job failed in its ``finally`` block, so the single job slot is not
    released until the worker has actually stopped. Finished jobs are never
    mutated. Returns True only if a running job was asked to cancel.
    """
    with _lock:
        if _job is None or _job.get("state") != "running":
            return False
        if _job.get("cancel_requested") or _job.get("phase") == "finalizing":
            return False
        _job["cancel_requested"] = True
        proc = _proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        return True



def append_result(
    task: str,
    ok: bool,
    log_path: str | None,
    repeat: int | None = None,
    repeats: int | None = None,
) -> None:
    """Append a task result to the current job under the lock."""
    with _lock:
        if _job is not None:
            _job["results"].append(
                {
                    "task": task,
                    "ok": ok,
                    "log_path": log_path,
                    "repeat": repeat,
                    "repeats": repeats,
                }
            )



def has_process() -> bool:
    """Return True if a child process is currently tracked."""
    with _lock:
        return _proc is not None

def set_process(proc) -> None:
    with _lock:
        global _proc
        _proc = proc


def get_job() -> dict | None:
    """Return a copy of the current job state, or None if idle."""
    with _lock:
        if _job is None:
            return None
        return dict(_job)


def set_state(**fields) -> None:
    """Update fields on the current job under the lock."""
    with _lock:
        if _job is None:
            return
        _job.update(fields)


def is_running() -> bool:
    with _lock:
        return _job is not None and _job.get("state") == "running"
