import pathlib
from datetime import datetime, timedelta

from inspect_ai.log import EvalLog, EvalSpec, EvalConfig, EvalResults, EvalStats
from inspect_ai.log._log import EvalScore, EvalMetric, EvalDataset


def stderr_of_mean(n, score):
    return round((score * (1 - score) / n) ** 0.5, 4)


def build(root, eval_id, task, model, score, created, samples=100):
    spec = EvalSpec(
        eval_id=eval_id,
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
    se = stderr_of_mean(samples, score)
    metrics = {
        "accuracy": EvalMetric(name="accuracy", value=score),
        "stderr": EvalMetric(name="stderr", value=se),
    }
    result_score = EvalScore(name="score", scorer="accuracy",
                             reducer="mean", metrics=metrics)
    results = EvalResults(total_samples=samples, completed_samples=samples,
                          scores=[result_score])
    stats = EvalStats(started_at=created.isoformat(),
                      completed_at=created.isoformat())
    log = EvalLog(version=1, status="success", eval=spec, results=results,
                  stats=stats, metadata={"model": model})
    log.location = str(root / f"{eval_id}.eval")
    from inspect_ai.log import write_eval_log
    write_eval_log(log, format="eval")


root = pathlib.Path("sample_logs")
root.mkdir(exist_ok=True)
now = datetime.now()

specs = [
    ("run_a_math_polystrata", "math", "polystrata-q3", 0.72, now - timedelta(days=10), 100),
    ("run_b_math_polystrata", "math", "polystrata-q3", 0.75, now - timedelta(days=3), 120),
    ("run_c_math_polystrata", "math", "polystrata-q3", 0.80, now - timedelta(days=1), 150),
    ("run_a_hist_polystrata", "history", "polystrata-q3", 0.65, now - timedelta(days=9), 90),
    ("run_b_hist_polystrata", "history", "polystrata-q3", 0.70, now - timedelta(days=2), 110),
    ("run_a_math_gpt4o", "math", "gpt-4o", 0.68, now - timedelta(days=11), 100),
    ("run_b_math_gpt4o", "math", "gpt-4o", 0.71, now - timedelta(days=4), 120),
]
for sid, task, model, score, created, s in specs:
    build(root, sid, task, model, score, created, s)
    print("wrote", sid)
print("DONE")
