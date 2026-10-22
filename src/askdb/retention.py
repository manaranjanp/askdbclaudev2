"""Audit retention: entries older than the configured number of days are purged (SPEC §10)."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from askdb.appdb import open_appdb

log = logging.getLogger("askdb.retention")

DAY_SECONDS = 24 * 60 * 60


def purge_expired(conn: sqlite3.Connection, now: datetime, retention_days: int) -> int:
    """Delete audit entries created before ``now - retention_days``. Returns how many."""
    cutoff = (now - timedelta(days=retention_days)).astimezone(timezone.utc)
    cursor = conn.execute(
        "DELETE FROM audit_log WHERE created_at < ?",
        (cutoff.isoformat(timespec="seconds"),),
    )
    return cursor.rowcount


def purge_now(appdb_path: Path, retention_days: int) -> int:
    with open_appdb(appdb_path) as conn:
        removed = purge_expired(conn, datetime.now(timezone.utc), retention_days)
    log.info("audit retention removed %d entries", removed)
    return removed


async def run_daily(appdb_path: Path, retention_days: int) -> None:
    """Purge now, then once a day, until cancelled."""
    while True:
        try:
            purge_now(appdb_path, retention_days)
        except sqlite3.Error:
            log.exception("audit retention failed; will retry tomorrow")
        await asyncio.sleep(DAY_SECONDS)
