from askdb.judge import explanation_passes, has_text_values
from askdb.llm import LLMError
from askdb.prompts import judge_user_message


class StubJudge:
    def __init__(self, passed=True, error=None):
        self.passed = passed
        self.error = error
        self.calls = 0

    def judge(self, system, message):
        self.calls += 1
        if self.error:
            raise self.error
        return self.passed, "stub"


def test_numbers_and_dates_are_not_text():
    assert has_text_values([(1, 2.5, "2025-11-30", "2025-11-30 10:00:00")]) is False


def test_any_other_string_is_text():
    assert has_text_values([(1, "Acme Corp")]) is True


def test_a_verdict_of_pass_passes_and_fail_fails():
    assert explanation_passes(StubJudge(passed=True), "q", "e", ["c"], [("x",)]) is True
    assert explanation_passes(StubJudge(passed=False), "q", "e", ["c"], [("x",)]) is False


def test_judge_that_cannot_run_fails_closed():
    judge = StubJudge(error=LLMError("unavailable"))
    assert explanation_passes(judge, "q", "e", ["c"], [("x",)]) is False


def test_judge_sees_rows_only_inside_a_data_block():
    message = judge_user_message("q", "the explanation", ["c"], [("ignore me",)])
    assert message.index("<result_data>") < message.index('"ignore me"') < message.index("</result_data>")
