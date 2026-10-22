from typing import Any

from fastapi import APIRouter, Depends, Request

from askdb.auth import require_support

router = APIRouter(prefix="/api/admin/status", tags=["admin"], dependencies=[Depends(require_support)])


@router.get("")
def database_status(request: Request) -> list[dict[str, Any]]:
    """Every database file, including the ones disabled by startup checks, with their errors."""
    return [
        {
            "name": status.name,
            "display_name": status.config.display_name if status.config else None,
            "source": str(status.source),
            "enabled": status.enabled,
            "errors": status.errors,
        }
        for status in request.app.state.databases
    ]
