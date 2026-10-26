from pathlib import Path

import pytest

from askdb.config import (
    ConfigError,
    expand_env,
    load_database_config,
    load_settings,
)

FIXTURE = Path(__file__).resolve().parents[1] / "cloudmetrics" / "cloudmetrics.yaml"

MINIMAL_DB = """\
name: demo
display_name: Demo
path: /tmp/demo.db
calendar:
  fiscal_year_start_month: 1
description: Demo database.
tables:
  - name: t
    description: A table.
    columns:
      - { name: id, type: INTEGER, primary_key: true }
"""


def write(tmp_path: Path, text: str, name: str = "db.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_invalid_yaml_raises_clear_error(tmp_path):
    path = write(tmp_path, "name: [unclosed\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_database_config(path)


def test_top_level_must_be_mapping(tmp_path):
    path = write(tmp_path, "- just\n- a list\n")
    with pytest.raises(ConfigError, match="top level must be a mapping"):
        load_database_config(path)


def test_missing_required_key_is_named(tmp_path):
    path = write(tmp_path, MINIMAL_DB.replace("display_name: Demo\n", ""))
    with pytest.raises(ConfigError, match="display_name"):
        load_database_config(path)


def test_unknown_key_is_rejected(tmp_path):
    path = write(tmp_path, MINIMAL_DB + "colour: blue\n")
    with pytest.raises(ConfigError, match="colour"):
        load_database_config(path)


def test_bad_references_format_is_rejected(tmp_path):
    text = MINIMAL_DB.replace(
        "primary_key: true }", "primary_key: true, references: customers }"
    )
    path = write(tmp_path, text)
    with pytest.raises(ConfigError, match="references"):
        load_database_config(path)


def test_valid_config_loads(tmp_path):
    config = load_database_config(write(tmp_path, MINIMAL_DB))
    assert config.name == "demo"
    assert config.tables[0].columns[0].primary_key is True


def test_fixture_parses_with_path_from_environment(monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", "/data/cloudmetrics.db")
    config = load_database_config(FIXTURE)
    assert config.name == "cloudmetrics"
    assert config.path == "/data/cloudmetrics.db"
    assert [t.name for t in config.tables] == [
        "customers",
        "plans",
        "subscriptions",
        "invoices",
        "support_tickets",
    ]


def test_unset_environment_variable_is_an_error(monkeypatch):
    monkeypatch.delenv("CLOUDMETRICS_DB_PATH", raising=False)
    with pytest.raises(ConfigError, match="CLOUDMETRICS_DB_PATH is not set"):
        load_database_config(FIXTURE)


def test_expand_env_leaves_plain_text_alone(monkeypatch):
    monkeypatch.setenv("SOME_DIR", "/x")
    assert expand_env("/plain/path.db") == "/plain/path.db"
    assert expand_env("${SOME_DIR}/a.db") == "/x/a.db"


def test_settings_default_when_file_is_missing(tmp_path):
    settings = load_settings(tmp_path / "settings.yaml")
    assert settings.llm.sql_model == "claude-sonnet-5-5"
    assert settings.limits.display_rows == 500
    assert settings.limits.query_timeout_seconds == 60
    assert settings.limits.audit_retention_days == 30
    assert settings.limits.explain_token_budget == 4000


def test_settings_file_overrides_defaults(tmp_path):
    path = write(
        tmp_path,
        "limits:\n  display_rows: 100\n  explain_token_budget: 4000\n",
        name="settings.yaml",
    )
    settings = load_settings(path)
    assert settings.limits.display_rows == 100
    assert settings.limits.explain_token_budget == 4000


def test_invalid_settings_value_is_an_error(tmp_path):
    path = write(tmp_path, "limits:\n  display_rows: -1\n", name="settings.yaml")
    with pytest.raises(ConfigError, match="display_rows"):
        load_settings(path)


def test_dump_then_parse_gives_back_the_same_mapping():
    from askdb.config import dump_database_yaml, parse_database_text

    original = parse_database_text(FIXTURE.read_text(encoding="utf-8"), "fixture")
    text = dump_database_yaml(original)
    assert parse_database_text(text, "dumped") == original


def test_dump_keeps_multi_line_descriptions_as_literal_blocks_and_env_paths_unexpanded():
    from askdb.config import dump_database_yaml, parse_database_text

    original = parse_database_text(FIXTURE.read_text(encoding="utf-8"), "fixture")
    text = dump_database_yaml(original)
    assert "description: |" in text
    assert "path: ${CLOUDMETRICS_DB_PATH}" in text


def test_database_from_dict_expands_the_path_and_reports_a_missing_variable(monkeypatch):
    from askdb.config import database_from_dict, parse_database_text

    data = parse_database_text(FIXTURE.read_text(encoding="utf-8"), "fixture")
    monkeypatch.delenv("CLOUDMETRICS_DB_PATH", raising=False)
    with pytest.raises(ConfigError, match="CLOUDMETRICS_DB_PATH is not set"):
        database_from_dict(data, "fixture")
    data["path"] = "/literal/path.db"
    assert database_from_dict(data, "fixture").path == "/literal/path.db"
