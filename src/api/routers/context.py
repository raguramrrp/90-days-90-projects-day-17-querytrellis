"""Database Manager & Active Context FastAPI router."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from src.api.schemas import (
    AcceptImportRequest,
    DialectUpdateRequest,
    LiveConnectRequest,
    WriteModeRequest,
)
from src.api.state import get_container
from src.connectors.adapters import LiveConnectionRequest
from src.connectors.demo_sandbox import ensure_sample_export_files
from src.security.guardrails import sanitize_error_message

router = APIRouter(prefix="/api/context", tags=["Database Context & Manager"])


@router.get("")
def get_active_context(refresh: bool = False):
    c = get_container()
    return c.context_manager.get_snapshot(force_refresh=refresh).to_dict()


@router.post("/dialect")
def update_dialect(payload: DialectUpdateRequest):
    c = get_container()
    try:
        return c.context_manager.set_dialect(payload.dialect).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/write-mode")
def update_write_mode(payload: WriteModeRequest):
    c = get_container()
    return c.context_manager.set_allow_write(payload.allow_write_opt_in).to_dict()


@router.post("/demo")
def activate_demo_mode(dialect: str | None = None):
    c = get_container()
    return c.context_manager.switch_to_demo(dialect).to_dict()


@router.post("/connect")
def connect_live_database(payload: LiveConnectRequest):
    c = get_container()
    try:
        req = LiveConnectionRequest(
            engine=payload.engine,
            host=payload.host,
            port=payload.port,
            database=payload.database,
            username=payload.username,
            password=payload.password,
            sqlite_path=payload.sqlite_path,
            ssl_mode=payload.ssl_mode,
            connect_timeout=payload.connect_timeout,
            allow_write_opt_in=payload.allow_write_opt_in,
        )
        return c.context_manager.connect_live(req).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=sanitize_error_message(str(exc))) from exc


@router.post("/upload/preview")
async def preview_uploaded_dataset(
    file: UploadFile = File(...),
    sql_dialect: str = Form("postgresql"),
):
    c = get_container()
    raw_bytes = await file.read()
    if len(raw_bytes) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Upload exceeds 15 MB workbench limit.")
    try:
        preview = c.context_manager.create_import_preview(
            file.filename or "uploaded_file.csv",
            raw_bytes,
            sql_dialect=sql_dialect,
        )
        return preview.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=sanitize_error_message(str(exc))) from exc


@router.post("/upload/accept")
def accept_uploaded_dataset(payload: AcceptImportRequest):
    c = get_container()
    try:
        return c.context_manager.accept_import(payload.preview_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=sanitize_error_message(str(exc))) from exc


@router.get("/sample-files")
def list_bundled_sample_files():
    paths = ensure_sample_export_files()
    return {
        "samples": [
            {
                "key": k,
                "file_name": p.name,
                "size_bytes": p.stat().st_size,
            }
            for k, p in paths.items()
        ]
    }


@router.post("/sample-files/{sample_key}/preview")
def preview_bundled_sample(sample_key: str):
    c = get_container()
    paths = ensure_sample_export_files()
    if sample_key not in paths:
        raise HTTPException(status_code=404, detail=f"Unknown sample file key '{sample_key}'.")
    target = paths[sample_key]
    preview = c.context_manager.create_import_preview(target.name, target.read_bytes(), sql_dialect="postgresql")
    return preview.to_dict()
