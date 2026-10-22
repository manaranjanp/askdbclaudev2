from pathlib import Path

import pytest

from askdb.appdb import init_schema, open_appdb
from askdb.auth import create_user

PASSWORD = "correct horse battery"


@pytest.fixture
def app_db(tmp_path) -> Path:
    path = tmp_path / "app.db"
    init_schema(path)
    return path


@pytest.fixture
def config_dir(tmp_path, app_db) -> Path:
    """A config directory with no databases; app settings point at a temp app DB."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "settings.yaml").write_text(f"app_db_path: {app_db}\n", encoding="utf-8")
    return cfg


@pytest.fixture
def add_user(app_db):
    def add(username: str, role: str = "analyst", password: str = PASSWORD) -> None:
        with open_appdb(app_db) as conn:
            create_user(conn, username, password, role)

    return add
