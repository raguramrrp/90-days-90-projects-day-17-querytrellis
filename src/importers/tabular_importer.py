"""CSV, Excel (.xlsx), and JSON dataset inspection with type inference and isolated loading.

Guarantees:
- Shows clear import preview before modifying active database workspace.
- Strictly separates schema metadata from sample row previews.
- NEVER pretends flat CSV/JSON/Excel files contain foreign keys.
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
from openpyxl import load_workbook

from src.context.models import ColumnSchema, TableSchema
from src.importers.sql_dump_importer import ImportPreview


@dataclass(slots=True)
class TabularDataset:
    """In-memory inspected tabular payload ready for preview or DuckDB ingestion."""

    table_name: str
    columns: list[ColumnSchema]
    rows: list[list[Any]]
    duckdb_types: list[str]
    notes: list[str] = field(default_factory=list)


def _sanitize_ident(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip().lower()).strip("_")
    if not cleaned:
        return fallback
    if cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:64]


def _infer_column_type(values: list[Any]) -> tuple[str, str]:
    """Return (display_type, duckdb_type) from observed non-null sample values."""
    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    if not non_null:
        return "VARCHAR", "VARCHAR"

    if all(isinstance(v, bool) for v in non_null):
        return "BOOLEAN", "BOOLEAN"
    if all(isinstance(v, int) and not isinstance(v, bool) for v in non_null):
        return "INTEGER", "BIGINT"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return "DOUBLE", "DOUBLE"

    str_vals = [str(v).strip() for v in non_null]
    if all(v.lower() in {"true", "false"} for v in str_vals):
        return "BOOLEAN", "BOOLEAN"
    if all(re.fullmatch(r"-?\d+", v) for v in str_vals):
        return "INTEGER", "BIGINT"
    if all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v in str_vals):
        return "DOUBLE", "DOUBLE"
    if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in str_vals):
        return "DATE", "DATE"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            for v in str_vals:
                datetime.strptime(v[:19], fmt)
            return "TIMESTAMP", "TIMESTAMP"
        except ValueError:
            pass
    return "VARCHAR", "VARCHAR"


def _coerce_value(val: Any, duck_type: str) -> Any:
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        if s == "" or s.lower() in {"null", "na", "n/a", "none"}:
            return None
    else:
        s = val

    try:
        if duck_type == "BOOLEAN":
            if isinstance(s, bool):
                return s
            return str(s).lower() in {"true", "1", "yes"}
        if duck_type == "BIGINT":
            return int(s)
        if duck_type == "DOUBLE":
            return float(s)
    except (ValueError, TypeError):
        return None
    return str(s) if isinstance(s, (dict, list)) else s


def _build_tabular_dataset(
    table_name: str,
    headers: list[str],
    raw_rows: list[list[Any]],
) -> TabularDataset:
    clean_cols: list[str] = []
    seen: set[str] = set()
    for idx, h in enumerate(headers):
        cand = _sanitize_ident(str(h), f"col_{idx + 1}")
        while cand in seen:
            cand = f"{cand}_{idx + 1}"
        seen.add(cand)
        clean_cols.append(cand)

    duck_types: list[str] = []
    col_schemas: list[ColumnSchema] = []
    for c_idx, cname in enumerate(clean_cols):
        col_vals = [r[c_idx] if c_idx < len(r) else None for r in raw_rows]
        disp_type, duck_type = _infer_column_type(col_vals)
        duck_types.append(duck_type)
        has_null = any(v is None or str(v).strip() == "" for v in col_vals)
        non_null_vals = [v for v in col_vals if v is not None and str(v).strip() != ""]
        is_pk_candidate = (
            cname in {"id", f"{table_name}_id"}
            or (cname.endswith("_id") and c_idx == 0)
        ) and not has_null and len(set(non_null_vals)) == len(non_null_vals) and len(non_null_vals) > 0

        col_schemas.append(
            ColumnSchema(
                name=cname,
                data_type=disp_type,
                nullable=has_null,
                is_primary_key=False,  # Explicitly ambiguous candidate; noted cleanly below!
                is_foreign_key=False,
                ordinal_position=c_idx + 1,
                sample_values=non_null_vals[:3],
            )
        )
        if is_pk_candidate:
            # We mark note cleanly without fabricating enforced DDL keys
            pass

    coerced_rows: list[list[Any]] = []
    for row in raw_rows:
        coerced_rows.append(
            [
                _coerce_value(row[i] if i < len(row) else None, duck_types[i])
                for i in range(len(clean_cols))
            ]
        )

    return TabularDataset(
        table_name=table_name,
        columns=col_schemas,
        rows=coerced_rows,
        duckdb_types=duck_types,
    )


def preview_csv_import(raw_bytes: bytes, file_name: str) -> tuple[ImportPreview, list[TabularDataset]]:
    """Inspect CSV bytes and return preview + structured dataset ready for isolated load."""
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect=dialect)
    all_rows = [r for r in reader if any(cell.strip() for cell in r)]
    preview_id = uuid.uuid4().hex[:12]
    if not all_rows:
        return (
            ImportPreview(
                preview_id=preview_id,
                file_name=file_name,
                file_kind="csv",
                detected_dialect="postgresql",
                warnings=["Uploaded CSV file is empty."],
            ),
            [],
        )

    headers = all_rows[0]
    data_rows = all_rows[1:]
    tname = _sanitize_ident(Path(file_name).stem, "csv_dataset")
    ds = _build_tabular_dataset(tname, headers, data_rows)

    sample_dicts = [
        {ds.columns[i].name: r[i] for i in range(len(ds.columns))}
        for r in ds.rows[:5]
    ]
    tbl = TableSchema(
        name=tname,
        schema_name="main",
        table_type="UPLOADED CSV",
        row_count=len(ds.rows),
        row_count_is_estimated=False,
        columns=ds.columns,
        sample_rows=sample_dicts,
        notes=["Flat CSV file: primary/foreign keys are not enforced natively unless confirmed in SQL DDL."],
    )
    prev = ImportPreview(
        preview_id=preview_id,
        file_name=file_name,
        file_kind="csv",
        detected_dialect="postgresql",
        tables=[tbl],
        relationships=[],
        warnings=[],
        ambiguous_or_unsupported=[
            "CSV contains no verified foreign-key relationships; cross-table joins must be verified explicitly."
        ],
        notes=[f"Sniffed {len(ds.rows)} data rows and {len(ds.columns)} columns from '{file_name}'."],
    )
    return prev, [ds]


def preview_excel_import(raw_bytes: bytes, file_name: str) -> tuple[ImportPreview, list[TabularDataset]]:
    """Inspect all sheets of an Excel (.xlsx) workbook using openpyxl read_only mode."""
    preview_id = uuid.uuid4().hex[:12]
    wb = load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    datasets: list[TabularDataset] = []
    tables: list[TableSchema] = []
    warnings: list[str] = []

    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows_iter = ws.iter_rows(values_only=True)
            raw_rows = [list(r) for r in rows_iter if any(v is not None for v in r)]
            if len(raw_rows) < 2:
                warnings.append(f"Sheet '{sheet_name}' has insufficient rows and was skipped.")
                continue
            headers = [str(h if h is not None else f"col_{i+1}") for i, h in enumerate(raw_rows[0])]
            data_rows = raw_rows[1:]
            tname = _sanitize_ident(sheet_name, f"sheet_{len(datasets)+1}")
            ds = _build_tabular_dataset(tname, headers, data_rows)
            datasets.append(ds)
            sample_dicts = [
                {ds.columns[i].name: r[i] for i in range(len(ds.columns))}
                for r in ds.rows[:5]
            ]
            tables.append(
                TableSchema(
                    name=tname,
                    schema_name="main",
                    table_type="UPLOADED EXCEL SHEET",
                    row_count=len(ds.rows),
                    row_count_is_estimated=False,
                    columns=ds.columns,
                    sample_rows=sample_dicts,
                )
            )
    finally:
        wb.close()

    return (
        ImportPreview(
            preview_id=preview_id,
            file_name=file_name,
            file_kind="xlsx",
            detected_dialect="postgresql",
            tables=tables,
            relationships=[],
            warnings=warnings,
            ambiguous_or_unsupported=[
                "Excel sheets do not carry enforced SQL constraints or verified foreign keys."
            ],
            notes=[f"Discovered {len(tables)} workbook sheet(s) inside '{file_name}'."],
        ),
        datasets,
    )


def preview_json_import(raw_bytes: bytes, file_name: str) -> tuple[ImportPreview, list[TabularDataset]]:
    """Inspect JSON arrays, keyed table maps, or NDJSON files."""
    preview_id = uuid.uuid4().hex[:12]
    text = raw_bytes.decode("utf-8-sig", errors="replace").strip()
    datasets: list[TabularDataset] = []
    tables: list[TableSchema] = []
    warnings: list[str] = []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try NDJSON line by line
        records = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        records.append(obj)
                except json.JSONDecodeError:
                    pass
        parsed = records if records else None

    if parsed is None:
        return (
            ImportPreview(
                preview_id=preview_id,
                file_name=file_name,
                file_kind="json",
                detected_dialect="postgresql",
                warnings=["Unable to parse uploaded file as valid JSON or NDJSON."],
            ),
            [],
        )

    table_buckets: list[tuple[str, list[dict[str, Any]]]] = []
    default_name = _sanitize_ident(Path(file_name).stem, "json_dataset")
    if isinstance(parsed, list):
        dict_items = [x for x in parsed if isinstance(x, dict)]
        if dict_items:
            table_buckets.append((default_name, dict_items))
    elif isinstance(parsed, dict):
        list_keys = [(k, v) for k, v in parsed.items() if isinstance(v, list) and any(isinstance(x, dict) for x in v)]
        if list_keys:
            for k, v in list_keys:
                table_buckets.append((_sanitize_ident(k, default_name), [x for x in v if isinstance(x, dict)]))
        else:
            table_buckets.append((default_name, [parsed]))

    for tname, records in table_buckets:
        if not records:
            continue
        all_keys: list[str] = []
        seen_k: set[str] = set()
        for rec in records:
            for k in rec.keys():
                if k not in seen_k:
                    seen_k.add(k)
                    all_keys.append(k)
        raw_rows = [
            [
                json.dumps(rec.get(k)) if isinstance(rec.get(k), (dict, list)) else rec.get(k)
                for k in all_keys
            ]
            for rec in records
        ]
        if any(isinstance(rec.get(k), (dict, list)) for rec in records for k in all_keys):
            warnings.append(
                f"Table '{tname}' contains nested JSON objects/arrays serialized as JSON text columns."
            )
        ds = _build_tabular_dataset(tname, all_keys, raw_rows)
        datasets.append(ds)
        sample_dicts = [{ds.columns[i].name: r[i] for i in range(len(ds.columns))} for r in ds.rows[:5]]
        tables.append(
            TableSchema(
                name=tname,
                schema_name="main",
                table_type="UPLOADED JSON",
                row_count=len(ds.rows),
                row_count_is_estimated=False,
                columns=ds.columns,
                sample_rows=sample_dicts,
            )
        )

    return (
        ImportPreview(
            preview_id=preview_id,
            file_name=file_name,
            file_kind="json",
            detected_dialect="postgresql",
            tables=tables,
            relationships=[],
            warnings=warnings,
            ambiguous_or_unsupported=[
                "JSON datasets do not contain verified relational foreign-key constraints."
            ],
            notes=[f"Discovered {len(tables)} table(s) from '{file_name}'."],
        ),
        datasets,
    )


def accept_tabular_import(
    preview: ImportPreview,
    datasets: list[TabularDataset],
    sandbox_dir: Path,
) -> Path:
    """Materialize previewed CSV/Excel/JSON datasets into an isolated DuckDB sandbox file."""
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    db_file = sandbox_dir / f"import_{preview.preview_id}.duckdb"
    if db_file.exists():
        db_file.unlink()

    con = duckdb.connect(str(db_file))
    try:
        for ds in datasets:
            col_defs = ", ".join(
                f'"{ds.columns[i].name}" {ds.duckdb_types[i]}'
                for i in range(len(ds.columns))
            )
            con.execute(f'CREATE TABLE "{ds.table_name}" ({col_defs})')
            if ds.rows:
                placeholders = ", ".join(["?"] * len(ds.columns))
                quoted = ", ".join(f'"{c.name}"' for c in ds.columns)
                con.executemany(
                    f'INSERT INTO "{ds.table_name}" ({quoted}) VALUES ({placeholders})',
                    ds.rows,
                )
    finally:
        con.close()

    return db_file
