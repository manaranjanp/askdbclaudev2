"""Startup checks for each configured database (SPEC §16.3)."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from askdb.adapters.base import ColumnInfo
from askdb.adapters.sqlite import SqliteAdapter
from askdb.config import ConfigError, DatabaseConfig, database_files, load_database_config

log = logging.getLogger("askdb.startup")


@dataclass
class DatabaseStatus:
    name: str
    source: Path
    config: DatabaseConfig | None
    errors: list[str] = field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return self.config is not None and not self.errors


def _check_schema(
    config: DatabaseConfig, tables: dict[str, list[ColumnInfo]]
) -> list[str]:
    errors: list[str] = []
    for table in config.tables:
        if table.name not in tables:
            errors.append(f"table {table.name} not found")
            continue
        found = {col.name: col for col in tables[table.name]}
        for column in table.columns:
            ref = f"{table.name}.{column.name}"
            if column.name not in found:
                errors.append(f"column {ref} not found")
            elif found[column.name].type.strip().upper() != column.type.strip().upper():
                errors.append(
                    f"column {ref} has type {found[column.name].type}, "
                    f"config says {column.type}"
                )
    for table in config.tables:
        for column in table.columns:
            if column.references is None:
                continue
            target_table, target_column = column.references.split(".")
            ref = f"{table.name}.{column.name}"
            if target_table not in tables:
                errors.append(f"{ref} references missing table {target_table}")
            elif target_column not in {c.name for c in tables[target_table]}:
                errors.append(
                    f"{ref} references missing column {column.references}"
                )
    return errors


def check_database(config: DatabaseConfig) -> list[str]:
    """Return every failed check for one database. An empty list means it passes."""
    path = Path(config.path)
    if not path.is_file():
        return [f"database file not found: {path}"]
    try:
        tables = SqliteAdapter(path).introspect()
    except sqlite3.Error as exc:
        return [f"cannot open database read-only: {exc}"]
    return _check_schema(config, tables)


def load_databases(config_dir: Path) -> list[DatabaseStatus]:
    """Load every database file. A failing file is disabled; the others still load."""
    statuses: list[DatabaseStatus] = []
    seen: set[str] = set()
    for source in database_files(config_dir):
        try:
            config = load_database_config(source)
        except ConfigError as exc:
            statuses.append(DatabaseStatus(source.stem, source, None, [str(exc)]))
            continue
        if config.name in seen:
            statuses.append(
                DatabaseStatus(
                    config.name,
                    source,
                    None,
                    [f"duplicate database name {config.name}"],
                )
            )
            continue
        seen.add(config.name)
        statuses.append(
            DatabaseStatus(config.name, source, config, check_database(config))
        )
    for status in statuses:
        for error in status.errors:
            log.error("database %s disabled: %s", status.name, error)
    return statuses
