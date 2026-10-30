"""Tests for per-sample analysis of .eval logs."""

from types import SimpleNamespace

from runlog import _score


def _sample(value):
    return SimpleNamespace(scores={"score": SimpleNamespace(value=value, answer=None)})


def test_numeric_score_passthrough():
    assert _score(_sample(0.75)) == 0.75
    assert _score(_sample(0)) == 0.0


def test_choice_status_codes():
    # inspect's choice scorer reports C/I/N/P, not a number.
    assert _score(_sample("C")) == 1.0
    assert _score(_sample("I")) == 0.0
    assert _score(_sample("N")) == 0.0
    assert _score(_sample("P")) == 0.5


def test_dict_value_scores():
    # IFEval reports per-constraint booleans; strict prompt adherence is the
    # headline metric.
    assert _score(_sample({"prompt_level_strict": True, "inst_level_strict": 1})) == 1.0
    assert _score(_sample({"prompt_level_strict": False, "inst_level_strict": 0})) == 0.0
    assert _score(_sample({"prompt_level_loose": True})) is None


def test_unscored_sample_returns_none():
    assert _score(SimpleNamespace(scores={})) is None


def test_sample_report_filters_failures_and_paginates(monkeypatch):
    from types import SimpleNamespace

    import runlog

    def sample(sample_id, value=None, error=None):
        scores = {} if value is None else {"score": SimpleNamespace(value=value, answer=None)}
        completion = "ok" if value == 1.0 else "bad"
        return SimpleNamespace(
            id=sample_id,
            epoch=1,
            scores=scores,
            error=error,
            input="input",
            target="target",
            output=SimpleNamespace(completion=completion),
        )

    samples = [
        sample("a", 1.0),
        sample("b", 0.0),
        sample("c", error=SimpleNamespace(message="boom")),
        sample("d", 1.0),
    ]
    monkeypatch.setattr(
        "inspect_ai.log.read_eval_log", lambda path: SimpleNamespace(samples=samples)
    )

    page = runlog.sample_report("x.eval", limit=1, offset=0, failures_only=True)
    assert page["total"] == 4
    assert page["failures"] == 2
    assert page["filtered_total"] == 2
    assert page["failures_only"] is True
    assert [row["id"] for row in page["samples"]] == ["b"]

    next_page = runlog.sample_report("x.eval", limit=1, offset=1, failures_only=True)
    assert [row["id"] for row in next_page["samples"]] == ["c"]

    everything = runlog.sample_report("x.eval", limit=10)
    assert everything["filtered_total"] == 4
    # The errored sample is unscored: (1.0 + 0.0 + 1.0) / 3.
    assert everything["mean_score"] == 2 / 3
