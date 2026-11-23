"""Judge factories, tested without an LLM by replacing openevals' factory with a recorder."""

from typing import Any

import pytest
from openevals.prompts import CORRECTNESS_PROMPT, RAG_GROUNDEDNESS_PROMPT

from expat.evals import judges
from expat.evals.judges import BRIEF_REASONING, REFUSAL_PROMPT, JudgeCache, JudgeSet


class Recorder:
    """Stands in for create_llm_as_judge: records the factory kwargs and every evaluator call."""

    def __init__(self) -> None:
        self.factory_kwargs: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any):
        self.factory_kwargs.append(kwargs)

        def evaluator(**call_kwargs: Any) -> dict[str, Any]:
            self.calls.append(call_kwargs)
            return {"key": kwargs["feedback_key"], "score": True, "comment": "Supported by S1. Thus, true."}

        return evaluator


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(judges, "create_llm_as_judge", rec.create)
    return rec


def test_judge_set_uses_binary_reasoning_first_prompts(recorder: Recorder) -> None:
    fake_model = object()
    JudgeSet.from_model(fake_model)  # type: ignore[arg-type]
    prompts = [k["prompt"] for k in recorder.factory_kwargs]
    # openevals' rubrics, plus the short-reasoning instruction (the judges' long output was the cost driver)
    assert prompts == [RAG_GROUNDEDNESS_PROMPT + BRIEF_REASONING, CORRECTNESS_PROMPT + BRIEF_REASONING, REFUSAL_PROMPT]
    assert "at most 60 words" in BRIEF_REASONING and "at most 40 words" in REFUSAL_PROMPT
    for kwargs in recorder.factory_kwargs:
        assert kwargs["judge"] is fake_model  # injected, never created inside
        assert kwargs.get("continuous", False) is False  # binary
        assert kwargs.get("use_reasoning", True) is True  # reasoning before score


def test_judges_pass_the_right_template_variables(recorder: Recorder) -> None:
    js = JudgeSet.from_model(object())  # type: ignore[arg-type]
    g = js.groundedness(answer="6 months [S1]", context="[S1] § 573c ...")
    c = js.correctness(question="q", answer="a", reference="r")
    r = js.refusal(question="q", answer="a", should_refuse=True)
    assert recorder.calls[0] == {"outputs": "6 months [S1]", "context": "[S1] § 573c ..."}
    assert recorder.calls[1] == {"inputs": "q", "outputs": "a", "reference_outputs": "r"}
    assert recorder.calls[2] == {"inputs": "q", "outputs": "a", "should_refuse": "true"}
    assert (g.key, g.score, c.key, r.key) == ("groundedness", True, "correctness", "refusal_correct")
    assert "Supported by S1" in g.reasoning


def test_refusal_prompt_formats() -> None:
    text = REFUSAL_PROMPT.format(should_refuse="true", inputs="asylum?", outputs="I can't advise.")
    assert "<should_refuse>\ntrue" in text and "asylum?" in text


def test_cache_pays_each_identical_judge_call_once(recorder: Recorder, tmp_path) -> None:
    cache = JudgeCache(tmp_path / "cache.jsonl")
    js = JudgeSet.from_model(object(), cache=cache, model_name="judge-a")  # type: ignore[arg-type]
    first = js.groundedness(answer="6 months [S1]", context="[S1] ...")
    again = js.groundedness(answer="6 months [S1]", context="[S1] ...")
    js.groundedness(answer="7 months [S1]", context="[S1] ...")  # a changed answer is a new call
    assert len(recorder.calls) == 2
    assert again == first
    assert (cache.hits, cache.misses) == (1, 2)


def test_cache_survives_a_restart_and_is_keyed_by_model(recorder: Recorder, tmp_path) -> None:
    path = tmp_path / "cache.jsonl"
    JudgeSet.from_model(object(), cache=JudgeCache(path), model_name="judge-a").correctness(  # type: ignore[arg-type]
        question="q", answer="a", reference="r"
    )
    reloaded = JudgeSet.from_model(object(), cache=JudgeCache(path), model_name="judge-a")  # type: ignore[arg-type]
    reloaded.correctness(question="q", answer="a", reference="r")
    other_model = JudgeSet.from_model(object(), cache=JudgeCache(path), model_name="judge-b")  # type: ignore[arg-type]
    other_model.correctness(question="q", answer="a", reference="r")
    assert len(recorder.calls) == 2  # judge-a once (then from disk), judge-b once


def test_failing_judge_calls_are_not_cached(tmp_path) -> None:
    calls = []

    def flaky(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("Key limit exceeded")

    cache = JudgeCache(tmp_path / "cache.jsonl")
    wrapped = cache.wrap("judge-a", "correctness", flaky)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            wrapped(question="q", answer="a", reference="r")
    assert len(calls) == 2 and not (tmp_path / "cache.jsonl").exists()
