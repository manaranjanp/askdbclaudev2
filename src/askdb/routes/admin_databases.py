from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from askdb.auth import require_support
from askdb.config import ConfigError, parse_database_text
from askdb.registry import DatabaseRegistry, ValidationFailed
from askdb.startup import DatabaseStatus

router = APIRouter(prefix="/api/admin/databases", tags=["admin"], dependencies=[Depends(require_support)])


class Draft(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    schema_yaml: str = Field(min_length=1)


class Validation(Draft):
    file: str | None = None


def _registry(request: Request) -> DatabaseRegistry:
    return request.app.state.registry


def _describe(status: DatabaseStatus) -> dict[str, Any]:
    text = status.source.read_text(encoding="utf-8") if status.source.exists() else ""
    try:
        raw_path = parse_database_text(text, status.source.stem).get("path")
    except ConfigError:
        raw_path = None
    return {
        "file": status.source.stem,
        "name": status.config.name if status.config else status.source.stem,
        "display_name": status.config.display_name if status.config else None,
        "path": raw_path,
        "enabled": status.enabled,
        "errors": status.errors,
        "schema_yaml": text,
    }


def _reject(errors: list[str]) -> None:
    raise HTTPException(status_code=422, detail={"errors": errors})


@router.get("")
def list_databases(request: Request) -> list[dict[str, Any]]:
    return [_describe(s) for s in _registry(request).statuses()]


@router.post("/validate")
def validate(body: Validation, request: Request) -> dict[str, Any]:
    """Dry run: the same checks as a save, with nothing written."""
    try:
        _registry(request).check_draft(body.file, body.path, body.schema_yaml)
    except ValidationFailed as exc:
        return {"ok": False, "errors": exc.errors}
    return {"ok": True, "errors": []}


@router.post("", status_code=201)
def create(body: Draft, request: Request) -> dict[str, Any]:
    try:
        status = _registry(request).save(None, body.path, body.schema_yaml)
    except ValidationFailed as exc:
        _reject(exc.errors)
    return _describe(status)


@router.put("/{file}")
def update(file: str, body: Draft, request: Request) -> dict[str, Any]:
    registry = _registry(request)
    if registry.find(file) is None:
        raise HTTPException(status_code=404, detail="Database not found")
    try:
        status = registry.save(file, body.path, body.schema_yaml)
    except ValidationFailed as exc:
        _reject(exc.errors)
    return _describe(status)


@router.post("/{file}/recheck")
def recheck(file: str, request: Request) -> dict[str, Any]:
    try:
        status = _registry(request).recheck(file)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Database not found") from exc
    return _describe(status)


@router.delete("/{file}", status_code=204)
def delete(file: str, request: Request) -> Response:
    try:
        _registry(request).delete(file)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Database not found") from exc
    return Response(status_code=204)
