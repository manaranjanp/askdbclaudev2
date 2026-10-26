import json

from askdb.prompts import fit_rows_to_budget


def test_rows_are_cut_to_the_budget_in_order():
    rows = [(i, "x" * 40) for i in range(100)]
    kept = fit_rows_to_budget(rows, token_budget=200)
    assert 0 < len(kept) < len(rows)
    assert kept == rows[: len(kept)]


def test_estimated_tokens_of_kept_rows_stay_within_budget():
    rows = [(i, "y" * 60) for i in range(500)]
    budget = 1000
    kept = fit_rows_to_budget(rows, token_budget=budget)
    used = sum(len(json.dumps(r)) // 4 + 1 for r in kept)
    assert used <= budget


def test_everything_is_kept_when_it_fits():
    rows = [(1,), (2,), (3,)]
    assert fit_rows_to_budget(rows, token_budget=10_000) == rows


def test_nothing_is_kept_when_one_row_is_larger_than_the_budget():
    assert fit_rows_to_budget([("z" * 1000,)], token_budget=10) == []
