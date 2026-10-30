"""Subprocess driver for a single inspect eval task.

Kept separate from :mod:`evalrun` so the orchestration logic stays readable.
"""

from __future__ import annotations

import subprocess

import evaljobs

MAX_TAIL = 40
TAIL_LIMIT = 300


def iter_output(stream):
    """Yield logical lines, splitting on CR as well as LF.

    inspect's plain display redraws a progress line with ``\\r`` and never
    emits a newline until it moves on, so iterating ``\\n`` lines would show
    progress only once at the end.
    """
    buf = ""
    while True:
        char = stream.read(1)
        if not char:
            break
        if char in "\r\n":
            if buf:
                yield buf
                buf = ""
        else:
            buf += char
    if buf:
        yield buf


def tail_append(line: str) -> None:
    evaljobs.append_tail(evaljobs.redact(line.rstrip("\n"))[:TAIL_LIMIT], MAX_TAIL)


def run_task(
    cmd: list[str],
    env: dict,
    progress_base: int = 0,
    progress_total: int | None = None,
) -> tuple[bool, str | None]:
    """Run one inspect eval task. Returns (ok, error_or_log_path).

    ``progress_base``/``progress_total`` let a caller show progress across
    repeated runs of the same task (repeat 2 of 3) instead of resetting the bar.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    evaljobs.set_process(proc)
    assert proc.stdout is not None
    error_lines: list[str] = []
    log_path: str | None = None
    for line in iter_output(proc.stdout):
        low = line.lower()
        parsed = evaljobs.parse_samples(line)
        if parsed:
            total = progress_total if progress_total is not None else parsed[1]
            evaljobs.set_state(
                samples_done=progress_base + parsed[0], samples_total=total
            )
        # Progress redraws are noisy: keep them out of the captured tail.
        if not ("Steps:" in line and "Samples:" in line):
            tail_append(line)
        if "assertionerror" in low or "modulenotfounderror" in low or "traceback" in low:
            error_lines.append(line)
        stripped = line.strip()
        if stripped.startswith("Log:") and not log_path:
            log_path = stripped[len("Log:"):].strip() or None
    proc.wait(timeout=3600)
    if proc.returncode != 0:
        if not error_lines:
            job = evaljobs.get_job() or {}
            error_lines = [l for l in job.get("log_tail", [])[-10:] if l.strip()]
        return False, "\n".join(error_lines) or f"exit code {proc.returncode}"
    return True, log_path
