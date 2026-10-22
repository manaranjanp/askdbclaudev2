"""FastAPI application. Run with: uv run uvicorn askdb.main:app"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from askdb.config import load_settings
from askdb.startup import load_databases

CONFIG_DIR_ENV = "ASKDB_CONFIG_DIR"


def create_app(config_dir: Path | None = None) -> FastAPI:
    if config_dir is None:
        config_dir = Path(os.environ.get(CONFIG_DIR_ENV, "config"))

    app = FastAPI(title="AskDB")
    app.state.settings = load_settings(config_dir / "settings.yaml")
    app.state.databases = load_databases(config_dir)

    @app.get("/api/databases")
    def list_databases() -> list[dict[str, str]]:
        return [
            {"name": status.config.name, "display_name": status.config.display_name}
            for status in app.state.databases
            if status.enabled
        ]

    return app


app = create_app()
