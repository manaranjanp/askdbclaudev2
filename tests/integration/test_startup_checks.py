import shutil
import sqlite3
from pathlib import Path

import pytest

from askdb.adapters.sqlite import SqliteAdapter
from askdb.startup import load_databases

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "cloudmetrics"
FIXTURE_YAML = (FIXTURE_DIR / "cloudmetrics.yaml").read_text(encoding="utf-8")


@pytest.fixture
def db_copy(tmp_path) -> Path:
    """A private copy of the fixture database, safe to alter."""
    path = tmp_path / "cloudmetrics.db"
    shutil.copy(FIXTURE_DIR / "cloudmetrics.db", path)
    return path


def make_config_dir(tmp_path: Path, databases: dict[str, str]) -> Path:
    config_dir = tmp_path / "config"
    (config_dir / "databases").mkdir(parents=True)
    for filename, text in databases.items():
        (config_dir / "databases" / filename).write_text(text, encoding="utf-8")
    return config_dir


def load_one(config_dir: Path):
    statuses = load_databases(config_dir)
    assert len(statuses) == 1
    return statuses[0]


def test_fixture_passes_all_checks(tmp_path, db_copy, monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db_copy))
    config_dir = make_config_dir(tmp_path, {"cloudmetrics.yaml": FIXTURE_YAML})
    status = load_one(config_dir)
    assert status.enabled
    assert status.errors == []


def test_renamed_column_disables_database(tmp_path, db_copy, monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db_copy))
    with sqlite3.connect(db_copy) as conn:
        conn.execute("ALTER TABLE customers RENAME COLUMN industry TO sector")
    config_dir = make_config_dir(tmp_path, {"cloudmetrics.yaml": FIXTURE_YAML})
    status = load_one(config_dir)
    assert not status.enabled
    assert "column customers.industry not found" in status.errors


def test_wrong_type_disables_database(tmp_path, db_copy, monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db_copy))
    text = FIXTURE_YAML.replace(
        "monthly_price, type: REAL", "monthly_price, type: TEXT"
    )
    assert text != FIXTURE_YAML
    config_dir = make_config_dir(tmp_path, {"cloudmetrics.yaml": text})
    status = load_one(config_dir)
    assert not status.enabled
    assert any(
        "plans.monthly_price has type REAL, config says TEXT" in e
        for e in status.errors
    )


def test_bad_references_target_disables_database(tmp_path, db_copy, monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db_copy))
    text = FIXTURE_YAML.replace(
        "references: plans.plan_id", "references: plans.plan_code"
    )
    assert text != FIXTURE_YAML
    config_dir = make_config_dir(tmp_path, {"cloudmetrics.yaml": text})
    status = load_one(config_dir)
    assert not status.enabled
    assert any("references missing column plans.plan_code" in e for e in status.errors)


def test_missing_file_disables_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(tmp_path / "nope.db"))
    config_dir = make_config_dir(tmp_path, {"cloudmetrics.yaml": FIXTURE_YAML})
    status = load_one(config_dir)
    assert not status.enabled
    assert any("database file not found" in e for e in status.errors)


def test_broken_database_does_not_stop_the_others(tmp_path, db_copy, monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db_copy))
    broken = FIXTURE_YAML.replace("name: cloudmetrics", "name: broken").replace(
        "${CLOUDMETRICS_DB_PATH}", str(tmp_path / "missing.db")
    )
    config_dir = make_config_dir(
        tmp_path,
        {"a_broken.yaml": broken, "b_cloudmetrics.yaml": FIXTURE_YAML},
    )
    statuses = {s.name: s for s in load_databases(config_dir)}
    assert not statuses["broken"].enabled
    assert statuses["cloudmetrics"].enabled


def test_invalid_file_is_reported_and_others_still_load(tmp_path, db_copy, monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db_copy))
    config_dir = make_config_dir(
        tmp_path,
        {"a_garbage.yaml": "name: [oops\n", "b_cloudmetrics.yaml": FIXTURE_YAML},
    )
    statuses = {s.source.name: s for s in load_databases(config_dir)}
    assert not statuses["a_garbage.yaml"].enabled
    assert "invalid YAML" in statuses["a_garbage.yaml"].errors[0]
    assert statuses["b_cloudmetrics.yaml"].enabled


def test_duplicate_name_disables_the_second_file(tmp_path, db_copy, monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db_copy))
    config_dir = make_config_dir(
        tmp_path,
        {"a.yaml": FIXTURE_YAML, "b.yaml": FIXTURE_YAML},
    )
    statuses = load_databases(config_dir)
    assert [s.enabled for s in statuses] == [True, False]
    assert "duplicate database name cloudmetrics" in statuses[1].errors[0]


def test_adapter_refuses_writes(db_copy):
    adapter = SqliteAdapter(db_copy)
    with adapter.connect() as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM customers")
