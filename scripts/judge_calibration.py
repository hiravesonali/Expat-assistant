"""Calibrate the LLM judge against a human: how often does the "correctness" judge agree with you?

    uv run python scripts/judge_calibration.py export   # writes evals/calibration/labels_v1.md (fill it in)
    uv run python scripts/judge_calibration.py score    # compares your labels with the judge -> RESULT.md
    uv run python scripts/judge_calibration.py rejudge  # same answers, current MODEL_JUDGE -> RESULT_<model>.md

The sheet deliberately does NOT show the judge's verdict, so the human label is not anchored on it.
The judge verdicts are kept in key_v1.json next to the sheet. Sampling: every answer the judge failed
(those are the interesting ones) plus random passes, up to N, from the latest R5 dev + holdout runs.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from expat.evals.dataset import load_golden  # noqa: E402

RESULTS = REPO / "evals" / "results"
OUT = REPO / "evals" / "calibration"
SHEET, KEY, RESULT = OUT / "labels_v1.md", OUT / "key_v1.json", OUT / "RESULT.md"
N, SEED = 15, 7
_LABEL_RE = re.compile(r"^### (\d+)\..*?^\*\*Your label \(yes / no\):\*\*[ \t]*(\S*)", re.MULTILINE | re.DOTALL)


def _latest(split: str) -> dict:
    path = sorted(RESULTS.glob(f"answers-R5-{split}-*.json"))[-1]
    return json.loads(path.read_text(encoding="utf-8"))


def export() -> None:
    golden = {g.id: g for g in load_golden()}
    items = []
    for split in ("dev", "holdout"):
        run = _latest(split)
        for ex in run["per_example"]:
            verdict = ex["metrics"].get("correctness")
            if verdict is not None:  # answerable questions that the judge scored
                items.append(
                    {"id": ex["id"], "split": split, "judge": bool(verdict), "answer": ex["details"]["answer"]}
                )
    rng = random.Random(SEED)
    fails = [i for i in items if not i["judge"]]
    passes = [i for i in items if i["judge"]]
    sample = fails + rng.sample(passes, max(0, N - len(fails)))
    rng.shuffle(sample)

    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Judge calibration sheet (v1)",
        "",
        "For each answer, compare it with the **reference answer** and write **yes** if it is correct and",
        "complete enough to be useful (same key facts, no wrong facts), otherwise **no**. Extra correct detail",
        "is fine. A note is optional. Then run `uv run python scripts/judge_calibration.py score`.",
        "",
    ]
    for n, item in enumerate(sample, 1):
        g = golden[item["id"]]
        lines += [
            f"### {n}. `{item['id']}`",
            "",
            f"**Question:** {g.question}",
            "",
            f"**Reference answer:** {g.reference_answer}",
            "",
            "**Assistant's answer:**",
            "",
            *[f"> {line}" if line else ">" for line in item["answer"].splitlines()],
            "",
            "**Your label (yes / no):** ",
            "",
            "**Note (optional):** ",
            "",
            "---",
            "",
        ]
    SHEET.write_text("\n".join(lines), encoding="utf-8")
    KEY.write_text(json.dumps([{k: i[k] for k in ("id", "split", "judge")} for i in sample], indent=2), "utf-8")
    print(f"wrote {SHEET.relative_to(REPO)} ({len(sample)} answers: {len(fails)} judge fails + random passes)")


def _labels(key: list[dict]) -> dict[int, str]:
    labels = {int(n): v.strip().lower() for n, v in _LABEL_RE.findall(SHEET.read_text(encoding="utf-8"))}
    missing = [n for n in range(1, len(key) + 1) if labels.get(n) not in ("yes", "no")]
    if missing:
        sys.exit(f"Please label every answer with yes or no; missing/invalid: {missing}")
    return labels


def _sheet_answers() -> dict[int, str]:
    """The assistant's answer per item, read back from the sheet's quoted block."""
    answers: dict[int, str] = {}
    for block in re.split(r"^### ", SHEET.read_text(encoding="utf-8"), flags=re.MULTILINE)[1:]:
        number = int(block.split(".", 1)[0])
        body = block.split("**Assistant's answer:**", 1)[1].split("**Your label", 1)[0]
        quoted = [
            line[2:] if line.startswith("> ") else "" for line in body.strip().splitlines() if line.startswith(">")
        ]
        answers[number] = "\n".join(quoted).strip()
    return answers


def rejudge(labeller: str = "human") -> None:
    """Judge the SAME labelled answers again with the current MODEL_JUDGE and score its agreement.

    Use it before switching judge models: the new judge must agree with the reference labels at least as well as
    the old one (RESULT.md) before its numbers replace the old ones. Costs 15 judge calls.
    """
    from expat.config import get_settings
    from expat.evals.judges import default_judge_model, make_correctness_judge

    model_name = get_settings().model_judge
    judge = make_correctness_judge(default_judge_model())
    golden = {g.id: g for g in load_golden()}
    key = json.loads(KEY.read_text(encoding="utf-8"))
    answers = _sheet_answers()
    items = []
    for n, item in enumerate(key, 1):
        g = golden[item["id"]]
        verdict = judge(question=g.question, answer=answers[n], reference=g.reference_answer)
        items.append({**item, "judge": verdict.score})
        print(f"{n:2}. {item['id']:8} old judge {item['judge']!s:5} -> {model_name}: {verdict.score}")
    slug = model_name.split("/")[-1]
    score(labeller, key=items, judge_name=model_name, result=OUT / f"RESULT_{slug}.md")


def score(
    labeller: str = "human", key: list[dict] | None = None, judge_name: str = "claude-haiku-4.5", result: Path = RESULT
) -> None:
    key = key if key is not None else json.loads(KEY.read_text(encoding="utf-8"))
    labels = _labels(key)
    pairs = [(labels[n] == "yes", item["judge"], item["id"]) for n, item in enumerate(key, 1)]
    agree = sum(h == j for h, j, _ in pairs)
    total = len(pairs)
    # Cohen's kappa: agreement corrected for chance (1 = perfect, 0 = no better than chance).
    p_o = agree / total
    h_yes = sum(h for h, _, _ in pairs) / total
    j_yes = sum(j for _, j, _ in pairs) / total
    p_e = h_yes * j_yes + (1 - h_yes) * (1 - j_yes)
    kappa = (p_o - p_e) / (1 - p_e) if p_e < 1 else 1.0
    too_strict = [i for h, j, i in pairs if h and not j]
    too_lenient = [i for h, j, i in pairs if j and not h]
    text = "\n".join(
        [
            f"# Judge calibration result (correctness judge, {judge_name})",
            "",
            f"Reference labels by: **{labeller}**",
            "",
            f"- Agreement with the reference label: **{agree}/{total}** ({p_o:.0%}), Cohen's kappa **{kappa:.2f}**",
            f"- Reference 'correct' rate {h_yes:.0%}, judge 'correct' rate {j_yes:.0%}",
            f"- Judge too strict (reference yes, judge no): {', '.join(too_strict) or 'none'}",
            f"- Judge too lenient (reference no, judge yes): {', '.join(too_lenient) or 'none'}",
            "",
            "Sample: all judge fails + random judge passes (seed 7), so the sample is enriched for failures and",
            "the agreement here is a conservative estimate for the full run.",
        ]
    )
    result.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("export", "score", "rejudge"))
    parser.add_argument("--labeller", default="human", help='who filled the sheet, e.g. "Claude (not a human)"')
    args = parser.parse_args()
    {"export": lambda: export(), "score": lambda: score(args.labeller), "rejudge": lambda: rejudge(args.labeller)}[
        args.command
    ]()
