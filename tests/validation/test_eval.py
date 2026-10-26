"""On-demand evaluation harness (SPEC §17.4). Run with: uv run pytest tests/validation

Runs every case in tests/cloudmetrics/cloudmetrics_eval.yaml through the full
pipeline against a copy of the fixture database, with the real Claude API.
Skipped without ANTHROPIC_API_KEY. Writes a report to docs/eval-runs/.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from askdb.adapters.sqlite import SqliteAdapter
from askdb.config import LLMSettings, Limits, load_database_config
from askdb.llm import LLM
from askdb.pipeline import answer_question
from askdb.prompts import HistoryTurn
from tests.validation.grading import outcome_matches, results_match

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "cloudmetrics"
PASS_BAR = 0.9
EXPECTED_ROW_LIMIT = 1_000_000  # the expected SQL is compared in full

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY is not set; evaluation harness skipped",
)


@dataclass
class CaseResult:
    case_id: str
    category: str
    passed: bool
    status: str
    detail: str


class CountingAdapter(SqliteAdapter):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.runs = 0

    def execute(self, sql, row_cap, timeout_seconds):
        self.runs += 1
        return super().execute(sql, row_cap, timeout_seconds)


def _grade(case: dict, adapter: SqliteAdapter, db_path: Path, limits: Limits, llm: LLM) -> CaseResult:
    history = [
        HistoryTurn(question=turn["question"], sql=turn["sql"], summary="Result shown to the user.")
        for turn in case.get("conversation", [])
    ]
    counting = CountingAdapter(db_path)
    config = load_database_config(FIXTURE_DIR / "cloudmetrics.yaml")
    today = date.fromisoformat(str(case["today"])) if case.get("today") else date.today()
    outcome = answer_question(case["question"], config, counting, llm, limits, today, history)

    if "expected_outcome" in case:
        passed = outcome_matches(case["expected_outcome"], outcome.status, counting.runs)
        detail = f"expected {case['expected_outcome']}, got {outcome.status} after {counting.runs} SQL run(s)"
        return CaseResult(case["id"], case["category"], passed, outcome.status, detail)

    expected = adapter.execute(case["expected_sql"], EXPECTED_ROW_LIMIT, timeout_seconds=60)
    if outcome.status != "answer":
        return CaseResult(case["id"], case["category"], False, outcome.status, outcome.message or "")
    if outcome.total != expected.total:
        detail = f"row count {outcome.total}, expected {expected.total}"
        return CaseResult(case["id"], case["category"], False, outcome.status, detail)
    if expected.total > limits.display_rows:
        # The shown rows are capped; only the row count can be compared in full.
        return CaseResult(case["id"], case["category"], True, outcome.status, "row count matches (over display cap)")
    passed = results_match(expected.columns, expected.rows, outcome.columns, outcome.rows)
    detail = "result set matches" if passed else "result set differs from expected_sql"
    return CaseResult(case["id"], case["category"], passed, outcome.status, detail)


@pytest.fixture(scope="module")
def cases():
    data = yaml.safe_load((FIXTURE_DIR / "cloudmetrics_eval.yaml").read_text(encoding="utf-8"))
    return data["cases"]


@pytest.fixture(scope="module")
def results(cases, tmp_path_factory):
    db = tmp_path_factory.mktemp("eval") / "cloudmetrics.db"
    shutil.copy(FIXTURE_DIR / "cloudmetrics.db", db)
    adapter = SqliteAdapter(db)
    limits = Limits()
    llm = LLM(LLMSettings())
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CLOUDMETRICS_DB_PATH", str(db))
        run = [_grade(case, adapter, db, limits, llm) for case in cases]
    _write_report(run)
    return run


def _write_report(run: list[CaseResult]) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    passed = sum(r.passed for r in run)
    lines = [
        f"# Evaluation run {stamp}",
        "",
        f"Passed {passed} of {len(run)} ({passed / len(run):.0%}). Pass bar {PASS_BAR:.0%}.",
        "",
        "| Case | Category | Result | Status | Detail |",
        "|---|---|---|---|---|",
    ]
    for r in run:
        mark = "pass" if r.passed else "FAIL"
        lines.append(f"| {r.case_id} | {r.category} | {mark} | {r.status} | {r.detail} |")
    out = ROOT / "docs" / "eval-runs" / f"{stamp}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_each_case(cases, results):
    by_id = {r.case_id: r for r in results}
    for case in cases:
        result = by_id[case["id"]]
        assert result.passed, f"{case['id']}: {result.detail}"


def test_pass_bar_and_no_silent_wrong_answers(results):
    failures = [r for r in results if not r.passed]
    silent_wrong = [r for r in failures if r.status == "answer"]
    assert not silent_wrong, f"silent wrong answers: {[r.case_id for r in silent_wrong]}"
    passed = len(results) - len(failures)
    assert passed / len(results) >= PASS_BAR, f"{passed} of {len(results)} passed"
