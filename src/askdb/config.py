"""Load, validate and write the database and app-settings YAML files (SPEC §16)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(Exception):
    """A config file cannot be read, parsed, or validated."""


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    primary_key: bool = False
    references: str | None = Field(default=None, pattern=r"^\w+\.\w+$")
    description: str | None = None


class Table(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str
    columns: list[Column] = Field(min_length=1)


class Calendar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fiscal_year_start_month: int = Field(ge=1, le=12)


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    calendar: Calendar
    description: str
    tables: list[Table] = Field(min_length=1)


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql_model: str = "claude-sonnet-5-5"
    explain_model: str = "claude-sonnet-5-5"
    api_key_env: str = "ANTHROPIC_API_KEY"
    # Optional. Sent as the anthropic-workspace-id header when set; needed for keys not scoped to a workspace.
    workspace_id_env: str = "ANTHROPIC_WORKSPACE_ID"


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_rows: int = Field(default=500, gt=0)
    # Provisional until measured from real row sizes in slice 7 (SPEC §22 item 3).
    explain_token_budget: int = Field(default=4000, gt=0)
    query_timeout_seconds: int = Field(default=60, gt=0)
    audit_retention_days: int = Field(default=30, gt=0)


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_db_path: str = "data/app.db"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    limits: Limits = Field(default_factory=Limits)


def expand_env(value: str) -> str:
    """Replace each ``${NAME}`` with the value of that environment variable."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in os.environ:
            raise ConfigError(f"environment variable {name} is not set")
        return os.environ[name]

    return _ENV_REF.sub(replace, value)


def _describe(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in err['loc']) or '(root)'}: {err['msg']}"
        for err in exc.errors()
    )


def parse_database_text(text: str, label: str) -> dict[str, Any]:
    """Parse YAML text into a mapping. ``label`` prefixes every error message."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{label}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{label}: top level must be a mapping")
    return data


def database_from_dict(data: dict[str, Any], label: str) -> DatabaseConfig:
    """Validate a parsed database mapping. The ``path`` may use ``${NAME}``."""
    data = dict(data)
    if isinstance(data.get("path"), str):
        try:
            data["path"] = expand_env(data["path"])
        except ConfigError as exc:
            raise ConfigError(f"{label}: {exc}") from exc
    try:
        return DatabaseConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{label}: {_describe(exc)}") from exc


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read file: {exc}") from exc
    return parse_database_text(text, str(path))


def load_database_config(path: Path) -> DatabaseConfig:
    return database_from_dict(_read_mapping(path), str(path))


class _LiteralDumper(yaml.SafeDumper):
    """Writes multi-line strings as literal blocks, so descriptions stay readable."""


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_LiteralDumper.add_representer(str, _represent_str)


def dump_database_yaml(data: dict[str, Any]) -> str:
    """Canonical YAML for a validated database mapping. Keeps ``path`` as written (e.g. ``${NAME}``)."""
    return yaml.dump(data, Dumper=_LiteralDumper, sort_keys=False, allow_unicode=True, width=100)


def load_settings(path: Path) -> AppSettings:
    """Missing file means defaults; a present but invalid file is an error."""
    if not path.exists():
        return AppSettings()
    data = _read_mapping(path)
    try:
        return AppSettings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {_describe(exc)}") from exc


def database_files(config_dir: Path) -> list[Path]:
    """Database config files, sorted. Only ``databases/*.yaml`` is read."""
    directory = config_dir / "databases"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.yaml"))
