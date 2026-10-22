"""Load and validate the database and app-settings YAML files (SPEC §16)."""

from __future__ import annotations

import os
import re
from pathlib import Path

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


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_rows: int = Field(default=500, gt=0)
    # None until it is measured during build (SPEC §22 item 3).
    explain_token_budget: int | None = Field(default=None, gt=0)
    query_timeout_seconds: int = Field(default=60, gt=0)
    audit_retention_days: int = Field(default=30, gt=0)


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


def _read_mapping(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read file: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def _describe(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in err['loc']) or '(root)'}: {err['msg']}"
        for err in exc.errors()
    )


def load_database_config(path: Path) -> DatabaseConfig:
    data = _read_mapping(path)
    if isinstance(data.get("path"), str):
        try:
            data["path"] = expand_env(data["path"])
        except ConfigError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
    try:
        return DatabaseConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path}: {_describe(exc)}") from exc


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
