"""The database list, changed at runtime from the admin screen (SPEC §16.4).

Readers take the current list object; writers hold a lock, validate a draft
completely, write the YAML file atomically, and then replace the whole list.
A rejected save writes nothing.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path

from askdb.config import ConfigError, database_from_dict, dump_database_yaml, parse_database_text
from askdb.config import DatabaseConfig
from askdb.startup import DatabaseStatus, check_database, load_status

# Letters, digits, underscore and hyphen. The same rule names both the database and its file.
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_SCHEMA_BYTES = 1_000_000


class ValidationFailed(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class DatabaseRegistry:
    def __init__(self, config_dir: Path, statuses: list[DatabaseStatus]) -> None:
        self.databases_dir = config_dir / "databases"
        self._lock = threading.Lock()
        self._statuses: list[DatabaseStatus] = list(statuses)

    # --- reads -----------------------------------------------------------

    def statuses(self) -> list[DatabaseStatus]:
        return self._statuses

    def enabled(self, name: str) -> DatabaseStatus | None:
        return next(
            (s for s in self._statuses if s.enabled and s.config is not None and s.config.name == name),
            None,
        )

    def find(self, file: str) -> DatabaseStatus | None:
        return next((s for s in self._statuses if s.source.stem == file), None)

    # --- validation ------------------------------------------------------

    def check_draft(self, file: str | None, path: str, schema_yaml: str) -> tuple[dict, DatabaseConfig]:
        """Validate a draft without writing. ``file`` is None for a new database."""
        if len(schema_yaml.encode("utf-8")) > MAX_SCHEMA_BYTES:
            raise ValidationFailed(["the schema is larger than 1 MB"])
        if not path.strip():
            raise ValidationFailed(["the database file path is required"])
        try:
            data = parse_database_text(schema_yaml, "schema")
            data["path"] = path.strip()
            config = database_from_dict(data, "schema")
        except ConfigError as exc:
            raise ValidationFailed([str(exc)]) from exc

        errors: list[str] = []
        if not ID_PATTERN.match(config.name):
            errors.append("name may use only letters, digits, _ and -")

        existing = self.find(file) if file else None
        if file is None:
            if (self.databases_dir / f"{config.name}.yaml").exists():
                errors.append(f"a database named {config.name} already exists")
        else:
            expected = existing.config.name if existing and existing.config else file
            if config.name != expected:
                errors.append(f"the name cannot change; this database is named {expected}")

        if any(
            s.config is not None and s.config.name == config.name and s.source.stem != file
            for s in self._statuses
        ):
            errors.append(f"another database already uses the name {config.name}")

        errors.extend(check_database(config))
        if errors:
            raise ValidationFailed(errors)
        return data, config

    # --- writes ----------------------------------------------------------

    def save(self, file: str | None, path: str, schema_yaml: str) -> DatabaseStatus:
        with self._lock:
            data, config = self.check_draft(file, path, schema_yaml)
            stem = file or config.name
            target = self.databases_dir / f"{stem}.yaml"
            _write_atomic(target, dump_database_yaml(data))
            status = DatabaseStatus(config.name, target, config, [])
            self._replace(stem, status)
            return status

    def recheck(self, file: str) -> DatabaseStatus:
        with self._lock:
            current = self._require(file)
            status = load_status(current.source)
            self._replace(file, status)
            return status

    def delete(self, file: str) -> None:
        with self._lock:
            current = self._require(file)
            current.source.unlink(missing_ok=True)
            self._statuses = [s for s in self._statuses if s.source.stem != file]

    # --- helpers ---------------------------------------------------------

    def _require(self, file: str) -> DatabaseStatus:
        if not ID_PATTERN.match(file):
            raise KeyError(file)
        status = self.find(file)
        if status is None:
            raise KeyError(file)
        return status

    def _replace(self, file: str, status: DatabaseStatus) -> None:
        kept = [s for s in self._statuses if s.source.stem != file]
        self._statuses = sorted([*kept, status], key=lambda s: s.source.stem)


def _write_atomic(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
