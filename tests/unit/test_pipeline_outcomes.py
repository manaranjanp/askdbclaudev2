"""One test per SPEC §18 condition. The LLM and the database are stubbed."""

from datetime import date

from askdb.adapters.base import ColumnInfo, DatabaseAdapter, QueryError, QueryResult, QueryTimeout
from askdb.config import DatabaseConfig, Limits
from askdb.llm import LLMError, SqlPlan
from askdb.pipeline import answer_question

TODAY = date(2026, 10, 21)


def demo_db() -> DatabaseConfig:
    return DatabaseConfig.model_validate(
        {
            "name": "demo",
            "display_name": "Demo",
            "path": "/unused.db",
            "calendar": {"fiscal_year_start_month": 1},
            "description": "Demo data, March 2022 to November 2025.",
            "tables": [
                {
                    "name": "t",
                    "description": "A table.",
                    "columns": [{"name": "id", "type": "INTEGER"}],
                }
            ],
        }
    )


class ScriptedLLM:
    """Returns planned results in order. Records what it was asked."""

    def __init__(self, plans=(), explanation="Explained.", explain_error=None, plan_error=None):
        self.plans = list(plans)
        self.explanation = explanation
        self.explain_error = explain_error
        self.plan_error = plan_error
        self.plan_questions: list[str] = []
        self.explain_messages: list[str] = []

    def plan_sql(self, system, question, history=()):
        self.plan_questions.append(question)
        if self.plan_error:
            raise self.plan_error
        return self.plans.pop(0)

    def explain(self, system, message):
        self.explain_messages.append(message)
        if self.explain_error:
            raise self.explain_error
        return self.explanation


class ScriptedAdapter(DatabaseAdapter):
    """Each execute() pops the next item: a QueryResult, or an exception to raise."""

    dialect = "sqlite"

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[str] = []

    def connect(self):
        raise AssertionError("tests must not open a real connection")

    def introspect(self) -> dict[str, list[ColumnInfo]]:
        return {}

    def execute(self, sql, row_cap, timeout_seconds):
        self.calls.append(sql)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def one_row() -> QueryResult:
    return QueryResult(columns=["n"], rows=[(42,)], total=1)


def run(llm, adapter, limits=None):
    return answer_question("a question", demo_db(), adapter, llm, limits or Limits(), TODAY)


def query(sql, assumptions=()):
    return SqlPlan(sql, False, None, list(assumptions))


# --- SPEC §18 rows ---------------------------------------------------------


def test_happy_path_answers_with_explanation_and_assumptions():
    llm = ScriptedLLM([query("SELECT COUNT(*) AS n FROM t", ["All rows"])], explanation="There are 42.")
    adapter = ScriptedAdapter([one_row()])
    outcome = run(llm, adapter)
    assert outcome.status == "answer"
    assert outcome.explanation == "There are 42."
    assert outcome.assumptions == ["All rows"]
    assert outcome.rows == [(42,)]


def test_ambiguous_question_asks_back_and_runs_no_sql():
    llm = ScriptedLLM([SqlPlan("", True, "Which region?", [])])
    adapter = ScriptedAdapter([])
    outcome = run(llm, adapter)
    assert outcome.status == "clarify"
    assert outcome.message == "Which region?"
    assert adapter.calls == []


def test_non_data_request_is_declined_and_runs_no_sql():
    llm = ScriptedLLM([SqlPlan("", False, None, [], kind="non_data", message="Data questions only.")])
    adapter = ScriptedAdapter([])
    outcome = run(llm, adapter)
    assert outcome.status == "declined"
    assert outcome.message == "Data questions only."
    assert adapter.calls == []


def test_data_the_schema_cannot_answer_says_so_and_runs_no_sql():
    llm = ScriptedLLM([SqlPlan("", False, None, [], kind="not_in_schema", message="Not in this database.")])
    adapter = ScriptedAdapter([])
    outcome = run(llm, adapter)
    assert outcome.status == "no_data"
    assert outcome.message == "Not in this database."
    assert adapter.calls == []


def test_zero_rows_is_an_explicit_empty_state_with_no_explanation():
    llm = ScriptedLLM([query("SELECT id FROM t WHERE id < 0")])
    adapter = ScriptedAdapter([QueryResult(columns=["id"], rows=[], total=0)])
    outcome = run(llm, adapter)
    assert outcome.status == "empty"
    assert outcome.message == "No rows matched."
    assert outcome.sql == "SELECT id FROM t WHERE id < 0"
    assert llm.explain_messages == []


def test_blocked_sql_is_refused_without_execution():
    llm = ScriptedLLM([query("DELETE FROM t")])
    adapter = ScriptedAdapter([])
    outcome = run(llm, adapter)
    assert outcome.status == "blocked"
    assert "could not be run safely" in outcome.message
    assert adapter.calls == []


def test_sql_error_gets_one_repair_and_the_repair_succeeds():
    llm = ScriptedLLM([query("SELECT nope FROM t"), query("SELECT COUNT(*) AS n FROM t")])
    adapter = ScriptedAdapter([QueryError("no such column: nope"), one_row()])
    outcome = run(llm, adapter)
    assert outcome.status == "answer"
    assert adapter.calls == ["SELECT nope FROM t", "SELECT COUNT(*) AS n FROM t"]
    repair = llm.plan_questions[1]
    assert "SELECT nope FROM t" in repair
    assert "no such column: nope" in repair


def test_sql_error_after_one_repair_is_reported_and_does_not_loop():
    llm = ScriptedLLM([query("SELECT nope FROM t"), query("SELECT still_nope FROM t")])
    adapter = ScriptedAdapter([QueryError("no such column: nope"), QueryError("no such column: still_nope")])
    outcome = run(llm, adapter)
    assert outcome.status == "error"
    assert "Please rephrase" in outcome.message
    assert len(adapter.calls) == 2
    assert len(llm.plan_questions) == 2


def test_timeout_says_so_and_suggests_narrowing():
    llm = ScriptedLLM([query("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT x FROM c")])
    adapter = ScriptedAdapter([QueryTimeout("the query did not finish within 60 seconds")])
    outcome = run(llm, adapter)
    assert outcome.status == "timeout"
    assert "narrowing" in outcome.message


def test_planning_api_failure_is_a_clear_error_and_no_answer():
    llm = ScriptedLLM(plan_error=LLMError("The AI service did not respond. Please try again."))
    adapter = ScriptedAdapter([])
    outcome = run(llm, adapter)
    assert outcome.status == "error"
    assert outcome.explanation is None
    assert outcome.rows == []
    assert adapter.calls == []


def test_explanation_api_failure_shows_no_answer_and_no_table():
    llm = ScriptedLLM([query("SELECT COUNT(*) AS n FROM t")], explain_error=LLMError("unavailable"))
    adapter = ScriptedAdapter([one_row()])
    outcome = run(llm, adapter)
    assert outcome.status == "error"
    assert outcome.explanation is None
    assert outcome.rows == []


def test_token_budget_exceeded_tells_the_model_it_saw_only_some_rows():
    wide = QueryResult(columns=["text"], rows=[("x" * 200,) for _ in range(300)], total=300)
    llm = ScriptedLLM([query("SELECT text FROM t")])
    adapter = ScriptedAdapter([wide])
    outcome = run(llm, adapter, Limits(explain_token_budget=500))
    assert outcome.status == "answer"
    assert outcome.total == 300
    message = llm.explain_messages[0]
    shown = int(message.split("rows_shown: ")[1].split("\n")[0])
    assert 0 < shown < 300
    assert "total_rows: 300" in message


def test_the_model_is_told_to_cover_only_shown_rows_in_the_prompt():
    from askdb.prompts import explain_system_prompt

    assert "rows_shown is less than total_rows" in explain_system_prompt()
