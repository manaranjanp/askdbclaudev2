"""FastAPI application. Run with: uv run uvicorn askdb.main:app"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI

from askdb.appdb import init_schema
from askdb.auth import User, current_user
from askdb.config import load_settings
from askdb.llm import LLM
from askdb.registry import DatabaseRegistry
from askdb.retention import run_daily
from askdb.routes import admin_audit, admin_databases, admin_users, ask, auth, conversations
from askdb.startup import load_databases

CONFIG_DIR_ENV = "ASKDB_CONFIG_DIR"


def create_app(config_dir: Path | None = None) -> FastAPI:
    if config_dir is None:
        config_dir = Path(os.environ.get(CONFIG_DIR_ENV, "config"))

    settings = load_settings(config_dir / "settings.yaml")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_schema(app.state.appdb_path)
        retention = asyncio.create_task(
            run_daily(app.state.appdb_path, settings.limits.audit_retention_days)
        )
        try:
            yield
        finally:
            retention.cancel()

    app = FastAPI(title="AskDB", lifespan=lifespan)
    app.state.settings = settings
    app.state.appdb_path = Path(settings.app_db_path)
    app.state.registry = DatabaseRegistry(config_dir, load_databases(config_dir))
    app.state.llm = LLM(settings.llm)

    app.include_router(auth.router)
    app.include_router(admin_users.router)
    app.include_router(ask.router)
    app.include_router(conversations.router)
    app.include_router(admin_databases.router)
    app.include_router(admin_audit.router)

    @app.get("/api/databases")
    def list_databases(user: User = Depends(current_user)) -> list[dict[str, str]]:
        return [
            {"name": status.config.name, "display_name": status.config.display_name}
            for status in app.state.registry.statuses()
            if status.enabled
        ]

    return app


app = create_app()
