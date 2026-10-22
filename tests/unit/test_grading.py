from tests.validation.grading import outcome_matches, results_match


def test_reordered_columns_and_aliases_are_ignored():
    expected_cols = ["plan_name", "monthly_price"]
    expected_rows = [("Starter", 29.0), ("Pro", 79.0)]
    actual_cols = ["price", "name"]
    actual_rows = [(79.0, "Pro"), (29.0, "Starter")]
    assert results_match(expected_cols, expected_rows, actual_cols, actual_rows)


def test_row_order_is_ignored():
    assert results_match(["x"], [(1,), (2,)], ["y"], [(2,), (1,)])


def test_a_wrong_row_is_rejected():
    assert not results_match(["x"], [(1,), (2,)], ["x"], [(1,), (3,)])


def test_a_row_count_difference_is_rejected():
    assert not results_match(["x"], [(1,), (2,)], ["x"], [(1,)])


def test_small_numeric_drift_is_accepted():
    assert results_match(["v"], [(1000.0,)], ["v"], [(1000.00001,)])


def test_larger_numeric_difference_is_rejected():
    assert not results_match(["v"], [(1000.0,)], ["v"], [(1010.0,)])


def test_nulls_match_only_nulls():
    assert results_match(["v"], [(None,)], ["v"], [(None,)])
    assert not results_match(["v"], [(None,)], ["v"], [(0,)])


def test_text_values_must_be_equal():
    assert not results_match(["v"], [("2025",)], ["v"], [(2025,)])


def test_clarification_case_passes_on_clarify_with_no_sql():
    assert outcome_matches("clarification", "clarify", 0) is True


def test_declined_case_passes_on_declined_with_no_sql():
    assert outcome_matches("declined", "declined", 0) is True


def test_outcome_case_fails_if_any_sql_ran():
    assert outcome_matches("declined", "declined", 1) is False


def test_outcome_case_fails_on_the_wrong_outcome():
    assert outcome_matches("declined", "answer", 0) is False
