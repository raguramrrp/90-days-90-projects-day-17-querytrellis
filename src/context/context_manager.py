"""Active database context manager tying connectors, uploads, and demo mode together."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.connectors.adapters import LiveConnectionRequest, MultiDBConnector
from src.connectors.demo_sandbox import SANDBOX_DIR
from src.context.models import DatabaseContextSnapshot
from src.importers.sql_dump_importer import ImportPreview, accept_sql_import, preview_sql_import
from src.importers.tabular_importer import (
    TabularDataset,
    accept_tabular_import,
    preview_csv_import,
    preview_excel_import,
    preview_json_import,
)


class ActiveContextManager:
    """Coordinates active DB connections, uploaded dataset previews, and dialected state."""

    def __init__(self, sandbox_dir: Path | None = None) -> None:
        self.sandbox_dir = sandbox_dir or SANDBOX_DIR
        self.connector = MultiDBConnector()
        self._pending_previews: dict[str, tuple[ImportPreview, list[TabularDataset] | None]] = {}
        self.connector.activate_demo_sandbox("postgresql")

    def get_snapshot(self, force_refresh: bool = False) -> DatabaseContextSnapshot:
        return self.connector.inspect_schema(force_refresh=force_refresh)

    def set_dialect(self, dialect: str) -> DatabaseContextSnapshot:
        self.connector.set_dialect(dialect)
        return self.get_snapshot()

    def set_allow_write(self, allow_write: bool) -> DatabaseContextSnapshot:
        self.connector.set_allow_write_opt_in(allow_write)
        return self.get_snapshot()

    def switch_to_demo(self, dialect: str | None = None) -> DatabaseContextSnapshot:
        return self.connector.activate_demo_sandbox(dialect)

    def connect_live(self, req: LiveConnectionRequest) -> DatabaseContextSnapshot:
        return self.connector.connect_live(req)

    def create_import_preview(
        self,
        file_name: str,
        raw_bytes: bytes,
        sql_dialect: str = "postgresql",
    ) -> ImportPreview:
        ext = Path(file_name).suffix.lower()
        if ext in {".sql", ".ddl", ".dump"}:
            text = raw_bytes.decode("utf-8-sig", errors="replace")
            prev = preview_sql_import(text, file_name, dialect=sql_dialect)
            self._pending_previews[prev.preview_id] = (prev, None)
            return prev
        if ext == ".csv":
            prev, datasets = preview_csv_import(raw_bytes, file_name)
            self._pending_previews[prev.preview_id] = (prev, datasets)
            return prev
        if ext in {".xlsx", ".xlsm"}:
            prev, datasets = preview_excel_import(raw_bytes, file_name)
            self._pending_previews[prev.preview_id] = (prev, datasets)
            return prev
        if ext in {".json", ".ndjson"}:
            prev, datasets = preview_json_import(raw_bytes, file_name)
            self._pending_previews[prev.preview_id] = (prev, datasets)
            return prev
        raise ValueError(
            f"Unsupported upload extension '{ext}'. Supported types: .sql, .dump, .csv, .xlsx, .json."
        )

    def get_preview(self, preview_id: str) -> ImportPreview | None:
        item = self._pending_previews.get(preview_id)
        return item[0] if item else None

    def accept_import(self, preview_id: str) -> DatabaseContextSnapshot:
        item = self._pending_previews.get(preview_id)
        if not item:
            raise KeyError(f"Import preview '{preview_id}' expired or was not found.")
        preview, tabular_datasets = item
        if not preview.tables:
            raise ValueError("Cannot load upload because no valid tables were discovered.")

        if tabular_datasets is not None:
            db_path = accept_tabular_import(preview, tabular_datasets, self.sandbox_dir)
        else:
            db_path = accept_sql_import(preview, self.sandbox_dir)

        return self.connector.activate_uploaded_duckdb(
            db_path,
            label=f"Uploaded: {preview.file_name}",
            context_id=f"upload:{preview.preview_id}",
            source_dialect=preview.detected_dialect,
            relationships=preview.relationships,
            warnings=preview.warnings + preview.ambiguous_or_unsupported,
            notes=preview.notes,
        )
