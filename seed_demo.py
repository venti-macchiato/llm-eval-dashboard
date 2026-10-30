"""Insert clearly-marked demo rows so every view has data.

Usage:
    python seed_demo.py            # insert demo runs, speed and prompt results
    python seed_demo.py --clear    # remove only the demo rows

Demo runs use ``demo-`` eval ids / batch ids and ``meta.demo = true``; real
runs are never touched. Safe to re-run: it clears then inserts.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone

import config
import db
import promptstore
import prompts
import speed

# name, quant, score bump over the q3 baseline
DEMO_MODELS = [
    ("polystrata-q3", "Q3_K_XL", 0.0),
    ("polystrata-q5", "Q5_K_M", 0.02),
    ("polystrata-q8", "Q8_0", 0.035),
]
TASKS = {"gsm8k": 0.88, "arc_challenge": 0.84, "ifeval": 0.80, "math": 0.44}
REPEATS = 3
SAMPLES = 100
FAMILY = "polystrata"

RUN_COLUMNS = (
    "eval_id",
    "task",
    "model",
    "created",
    "score",
    "stderr",
    "samples",
    "input_tokens",
    "output_tokens",
    "duration_s",
    "log_path",
    "meta",
    "error_samples",
)


def _clear(conn) -> None:
    conn.execute("DELETE FROM runs WHERE eval_id LIKE 'demo-%'")
    conn.execute("DELETE FROM speed WHERE batch_id LIKE 'demo-%'")
    conn.execute("DELETE FROM prompt_results WHERE run_id LIKE 'demo-%'")
    conn.execute("DELETE FROM prompt_runs WHERE run_id LIKE 'demo-%'")


def _meta(model: str, quant: str, dataset: str) -> str:
    return json.dumps(
        {
            "base_url": "http://100.112.119.2:8080/v1",
            "model_id": f"tiel-coder-35b-a3b-ud-{quant.lower()}",
            "inspect_model": f"openai/tiel-coder-35b-a3b-ud-{quant.lower()}",
            "base_model": FAMILY,
            "dataset": dataset,
            "epochs": 1,
            "packages": {"inspect_ai": "demo", "inspect_evals": "demo"},
            "hardware": {
                "declared": {
                    "backend": "llama.cpp",
                    "quant": quant,
                    "gpu": "RTX 4090",
                    "vram_gb": 24,
                    "ctx_size": 32768,
                }
            },
            "demo": True,
        },
        default=str,
    )


def _seed_runs(conn) -> int:
    now = datetime.now()
    rows = []
    for model_index, (model, quant, bump) in enumerate(DEMO_MODELS):
        for task, base in TASKS.items():
            for repeat in range(REPEATS):
                score = round(min(0.99, base + bump + (repeat - 1) * 0.004), 4)
                stderr = round(math.sqrt(score * (1 - score) / SAMPLES), 4)
                # Newest rows so the demo configuration is the current one for
                # each model. UTC + offset matches ingest's stored format, so
                # the dashboard's text comparisons sort chronologically.
                created = (
                    now + timedelta(minutes=20 - (model_index * 3 + repeat))
                ).astimezone(timezone.utc).isoformat(sep=" ", timespec="seconds")
                rows.append(
                    (
                        f"demo-{model}-{task}-{repeat + 1}",
                        task,
                        model,
                        created,
                        score,
                        stderr,
                        SAMPLES,
                        int(SAMPLES * 120),
                        int(SAMPLES * 40),
                        round(SAMPLES * 0.85 + repeat * 6, 1),
                        None,
                        _meta(model, quant, f"openai/{task}"),
                        0,
                    )
                )
    placeholders = ", ".join("?" * len(RUN_COLUMNS))
    conn.executemany(
        f"INSERT OR REPLACE INTO runs ({', '.join(RUN_COLUMNS)}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def _seed_speed(conn) -> int:
    now = datetime.now()
    rows = []
    for model, _quant, _bump in DEMO_MODELS:
        for ctx in (2000, 16000):
            for level in (1, 4):
                batch = f"demo-speed-{model}-{ctx}-c{level}"
                for iteration in range(3):
                    drift = 1 - 0.05 * iteration
                    ttft = round((0.14 if level == 1 else 0.42) * (1 + 0.04 * iteration), 3)
                    values = {
                        "model": model,
                        "ts": (
                            now - timedelta(minutes=90 - iteration)
                        ).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                        "ctx_tokens": ctx,
                        "concurrency": level,
                        "batch_id": batch,
                        "ttft_s": ttft,
                        "ttft_p50": ttft,
                        "ttft_p95": round(ttft * 1.7, 3),
                        "prefill_tps": round(1500 / ttft, 1),
                        "gen_tps": round((44 if level == 1 else 30) * drift, 1),
                        "agg_gen_tps": round((42 if level == 1 else 110) * drift, 1),
                        "out_tokens": 200,
                        "requests": level,
                        "errors": 0,
                        "wall_s": round(4.8 + ctx / 20000 + iteration * 0.2, 2),
                    }
                    rows.append(tuple(values.get(column) for column in speed.COLUMNS))
    placeholders = ", ".join("?" * len(speed.COLUMNS))
    conn.executemany(
        f"INSERT INTO speed ({', '.join(speed.COLUMNS)}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def _seed_prompts() -> int:
    tests = prompts.load()
    if not tests:
        return 0
    now = datetime.now()
    total = 0
    for run_index, (age_hours, failures) in enumerate(
        [(26, {1, 2}), (1, set())], start=1
    ):
        results = []
        for index, test in enumerate(tests):
            passed = index not in failures
            results.append(
                {
                    "model": "polystrata-q3",
                    "test_id": test["id"],
                    "title": test["title"],
                    "category": test["category"],
                    "repeat": 1,
                    "passed": passed,
                    "output": (
                        "demo output: check satisfied"
                        if passed
                        else "demo output: the reply did not satisfy the check"
                    ),
                    "detail": (
                        "passes demo check"
                        if passed
                        else f"demo failure for {test['check'].get('type', 'check')}"
                    ),
                    "latency_s": round(0.6 + index * 0.07, 2),
                    "input_tokens": 120 + index * 15,
                    "output_tokens": 18 + index,
                    "error": None,
                }
            )
        ts = (now - timedelta(hours=age_hours)).isoformat(timespec="seconds")
        promptstore.save_run(
            config.DB_PATH, f"demo-prompt-{run_index}", "polystrata-q3", ts, 1, results
        )
        total += len(results)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="remove demo rows only")
    args = parser.parse_args()

    conn = db.connect(config.DB_PATH)
    try:
        db.init_schema(conn)
        _clear(conn)
        if not args.clear:
            runs = _seed_runs(conn)
            samples = _seed_speed(conn)
        conn.commit()
    finally:
        db.close(conn)

    if args.clear:
        print("Removed demo runs, speed samples, and prompt results.")
        return

    prompt_rows = _seed_prompts()
    print(
        f"Inserted {runs} demo runs, {samples} speed samples, "
        f"{prompt_rows} prompt results."
    )
    print("Remove them with: python seed_demo.py --clear")


if __name__ == "__main__":
    main()
