"""AST-safe SQL schema and database dump importer with mandatory preview before execution.

Security guarantees:
- NEVER runs uploaded `.sql` dumps blindly through PostgreSQL/SQLite/DuckDB `executescript`.
- Parses statements cleanly via SQLGlot, extracts DDL tables/columns/PK/FK/UNIQUE/CHECK constraints
  and static literal INSERT rows into structured metadata.
- Flags unsupported dump directives (`SET`, `LOCK TABLES`, triggers, procedures, `COPY ... FROM stdin`
  or ``\\connect`` meta-commands) transparently in ``ambiguous_or_unsupported``.
- Loads only validated CREATE TABLE schemas and static INSERT literals into an isolated DuckDB sandbox.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from src.context.models import (
    ColumnSchema,
    ConstraintSchema,
    RelationshipSchema,
    TableSchema,
)
from src.dialects.sqlglot_engine import normalize_dialect, to_sqlglot_read_write


@dataclass(slots=True)
class ParsedSqlTableData:
    """Extracted table DDL and static INSERT rows ready for isolated loading."""

    schema: TableSchema
    insert_columns: list[str] = field(default_factory=list)
    insert_rows: list[list[Any]] = field(default_factory=list)


@dataclass(slots=True)
class ImportPreview:
    """Two-stage preview returned to Database Manager before accepting dataset into workspace."""

    preview_id: str
    file_name: str
    file_kind: str  # sql | dump | csv | xlsx | json
    detected_dialect: str
    tables: list[TableSchema] = field(default_factory=list)
    relationships: list[RelationshipSchema] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ambiguous_or_unsupported: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    _prepared_tables: dict[str, ParsedSqlTableData] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview_id": self.preview_id,
            "file_name": self.file_name,
            "file_kind": self.file_kind,
            "detected_dialect": self.detected_dialect,
            "tables": [t.to_dict() for t in self.tables],
            "relationships": [r.to_dict() for r in self.relationships],
            "warnings": self.warnings,
            "ambiguous_or_unsupported": self.ambiguous_or_unsupported,
            "notes": self.notes,
        }


def _strip_pg_psql_metacommands(sql_text: str) -> tuple[str, list[str]]:
    """Strip psql/mysqldump shell metacommands and flag them safely."""
    kept: list[str] = []
    notes: list[str] = []
    in_copy_stdin = False
    for raw_line in sql_text.splitlines():
        s = raw_line.strip()
        if in_copy_stdin:
            if s == r"\.":
                in_copy_stdin = False
            continue
        if s.startswith("\\"):
            notes.append(f"Skipped SQL shell meta-command: {s[:60]}")
            continue
        if re.match(r"^DELIMITER\b", s, re.IGNORECASE):
            notes.append(f"Skipped client DELIMITER directive: {s}")
            continue
        if re.match(r"^COPY\s+.+\s+FROM\s+stdin\s*;?", s, re.IGNORECASE):
            in_copy_stdin = True
            notes.append(f"Detected COPY ... FROM stdin block ({s[:60]}); plain INSERT dumps or CSV recommended for row import.")
            continue
        kept.append(raw_line)
    return "\n".join(kept), notes


def _literal_to_python(expr: exp.Expression) -> Any:
    if isinstance(expr, exp.Null):
        return None
    if isinstance(expr, exp.Boolean):
        return bool(expr.this)
    if isinstance(expr, exp.Neg) and isinstance(expr.this, exp.Literal):
        val = str(expr.this.this)
        return -int(val) if val.isdigit() else -float(val)
    if isinstance(expr, exp.Literal):
        if expr.is_string:
            return str(expr.this)
        raw = str(expr.this)
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        try:
            return float(raw)
        except ValueError:
            return raw
    if isinstance(expr, exp.Cast):
        return _literal_to_python(expr.this)
    if isinstance(expr, exp.CurrentTimestamp):
        return "2026-01-01T00:00:00Z"
    return expr.sql()


def _map_type_to_duckdb(raw_type: str) -> str:
    low = raw_type.lower()
    if any(k in low for k in ("serial", "bigserial", "bigint", "int8")):
        return "BIGINT"
    if any(k in low for k in ("smallint", "tinyint", "int", "integer")):
        return "INTEGER"
    if any(k in low for k in ("numeric", "decimal", "money")):
        return "DOUBLE"
    if any(k in low for k in ("float", "real", "double")):
        return "DOUBLE"
    if "bool" in low or low == "bit":
        return "BOOLEAN"
    if "timestamp" in low or "datetime" in low:
        return "TIMESTAMP"
    if low == "date":
        return "DATE"
    return "VARCHAR"


def preview_sql_import(
    raw_text: str,
    file_name: str,
    dialect: str = "postgresql",
) -> ImportPreview:
    """Inspect .sql or dump text via SQLGlot without executing untrusted commands."""
    norm_dialect = normalize_dialect(dialect)
    sg_dialect = to_sqlglot_read_write(norm_dialect)
    cleaned_sql, meta_notes = _strip_pg_psql_metacommands(raw_text)

    # Pre-split statements safely so partial dump errors don't abort whole file
    preview_id = uuid.uuid4().hex[:12]
    tables_map: dict[str, ParsedSqlTableData] = {}
    relationships: list[RelationshipSchema] = []
    warnings: list[str] = []
    unsupported: list[str] = list(meta_notes)

    try:
        statements = [s for s in sqlglot.parse(cleaned_sql, read=sg_dialect, error_level=sqlglot.ErrorLevel.IGNORE) if s is not None]
    except SqlglotError as exc:
        return ImportPreview(
            preview_id=preview_id,
            file_name=file_name,
            file_kind="dump" if "dump" in file_name.lower() else "sql",
            detected_dialect=norm_dialect,
            warnings=[f"SQL parsing failed: {exc}"],
            ambiguous_or_unsupported=[str(exc)],
        )

    ignored_cmd_prefixes = {
        "SET", "LOCK", "UNLOCK", "USE", "START", "BEGIN", "COMMIT",
        "PRAGMA", "COMMENT", "SELECT", "SHOW",
    }

    for stmt in statements:
        if isinstance(stmt, exp.Create):
            kind = str(stmt.args.get("kind") or "").upper()
            if kind == "TABLE":
                schema_expr = stmt.this
                tbl_node = schema_expr.this if isinstance(schema_expr, exp.Schema) else schema_expr
                tname = tbl_node.name if isinstance(tbl_node, exp.Table) else str(tbl_node)
                tname = re.sub(r"[^a-zA-Z0-9_]", "_", tname).strip("_") or "imported_table"

                columns: list[ColumnSchema] = []
                constraints: list[ConstraintSchema] = []
                pk_cols: set[str] = set()
                fk_cols: set[str] = set()

                expressions = schema_expr.expressions if isinstance(schema_expr, exp.Schema) else []
                ord_idx = 1
                for item in expressions:
                    if isinstance(item, exp.ColumnDef):
                        cname = re.sub(r"[^a-zA-Z0-9_]", "_", item.name).strip("_") or f"col_{ord_idx}"
                        dtype = item.kind.sql(dialect=sg_dialect) if item.kind else "VARCHAR"
                        nullable = True
                        is_pk = False
                        is_fk = False
                        default_val: str | None = None

                        for cons in item.constraints or []:
                            c_kind = cons.kind
                            if isinstance(c_kind, exp.PrimaryKeyColumnConstraint):
                                is_pk = True
                                nullable = False
                                pk_cols.add(cname.lower())
                                constraints.append(
                                    ConstraintSchema(
                                        name=f"pk_{tname}",
                                        table_name=tname,
                                        constraint_type="PRIMARY KEY",
                                        definition=f"PRIMARY KEY ({cname})",
                                    )
                                )
                            elif isinstance(c_kind, exp.NotNullColumnConstraint):
                                nullable = False
                            elif isinstance(c_kind, exp.UniqueColumnConstraint):
                                constraints.append(
                                    ConstraintSchema(
                                        name=f"uq_{tname}_{cname}",
                                        table_name=tname,
                                        constraint_type="UNIQUE",
                                        definition=f"UNIQUE ({cname})",
                                    )
                                )
                            elif isinstance(c_kind, exp.DefaultColumnConstraint):
                                default_val = c_kind.this.sql(dialect=sg_dialect) if c_kind.this else None
                            elif isinstance(c_kind, exp.CheckColumnConstraint):
                                constraints.append(
                                    ConstraintSchema(
                                        name=f"chk_{tname}_{cname}",
                                        table_name=tname,
                                        constraint_type="CHECK",
                                        definition=cons.sql(dialect=sg_dialect),
                                    )
                                )
                            elif isinstance(c_kind, exp.Reference):
                                ref_schema = c_kind.this
                                ref_tbl = ""
                                ref_cols: list[str] = []
                                if isinstance(ref_schema, exp.Schema) and isinstance(ref_schema.this, exp.Table):
                                    ref_tbl = ref_schema.this.name
                                    ref_cols = [c.name for c in ref_schema.expressions if hasattr(c, "name")]
                                elif isinstance(ref_schema, exp.Table):
                                    ref_tbl = ref_schema.name
                                    ref_cols = [cname]
                                if ref_tbl:
                                    is_fk = True
                                    fk_cols.add(cname.lower())
                                    relationships.append(
                                        RelationshipSchema(
                                            constraint_name=f"fk_{tname}_{cname}",
                                            source_table=tname,
                                            source_columns=[cname],
                                            target_table=ref_tbl,
                                            target_columns=ref_cols or [cname],
                                            verified=True,
                                        )
                                    )

                        if "SERIAL" in dtype.upper() and is_pk:
                            pk_cols.add(cname.lower())

                        columns.append(
                            ColumnSchema(
                                name=cname,
                                data_type=dtype,
                                nullable=nullable,
                                is_primary_key=is_pk,
                                is_foreign_key=is_fk,
                                default_value=default_val,
                                ordinal_position=ord_idx,
                            )
                        )
                        ord_idx += 1

                    elif isinstance(item, exp.PrimaryKey):
                        cols = [c.name for c in item.expressions if hasattr(c, "name")]
                        pk_cols.update(c.lower() for c in cols)
                        constraints.append(
                            ConstraintSchema(
                                name=f"pk_{tname}",
                                table_name=tname,
                                constraint_type="PRIMARY KEY",
                                definition=f"PRIMARY KEY ({', '.join(cols)})",
                            )
                        )
                    elif isinstance(item, exp.ForeignKey):
                        scols = [c.name for c in item.expressions if hasattr(c, "name")]
                        ref = item.args.get("reference")
                        if isinstance(ref, exp.Reference):
                            ref_sch = ref.this
                            if isinstance(ref_sch, exp.Schema) and isinstance(ref_sch.this, exp.Table):
                                rt = ref_sch.this.name
                                rcols = [c.name for c in ref_sch.expressions if hasattr(c, "name")]
                                fk_cols.update(c.lower() for c in scols)
                                relationships.append(
                                    RelationshipSchema(
                                        constraint_name=f"fk_{tname}_{'_'.join(scols)}",
                                        source_table=tname,
                                        source_columns=scols,
                                        target_table=rt,
                                        target_columns=rcols or scols,
                                        verified=True,
                                    )
                                )
                                constraints.append(
                                    ConstraintSchema(
                                        name=f"fk_{tname}_{'_'.join(scols)}",
                                        table_name=tname,
                                        constraint_type="FOREIGN KEY",
                                        definition=item.sql(dialect=sg_dialect),
                                    )
                                )
                    elif isinstance(item, (exp.Check, exp.UniqueColumnConstraint, exp.Constraint)):
                        constraints.append(
                            ConstraintSchema(
                                name=f"cons_{tname}_{ord_idx}",
                                table_name=tname,
                                constraint_type="CONSTRAINT",
                                definition=item.sql(dialect=sg_dialect),
                            )
                        )

                for col in columns:
                    if col.name.lower() in pk_cols:
                        col.is_primary_key = True
                        col.nullable = False
                    if col.name.lower() in fk_cols:
                        col.is_foreign_key = True

                ts = TableSchema(
                    name=tname,
                    schema_name="main",
                    table_type="BASE TABLE",
                    row_count=0,
                    row_count_is_estimated=False,
                    columns=columns,
                    constraints=constraints,
                )
                tables_map[tname.lower()] = ParsedSqlTableData(schema=ts)
            else:
                unsupported.append(
                    f"Skipped non-table DDL object ({kind or 'DDL'}): {stmt.sql(dialect=sg_dialect)[:80]}"
                )

        elif isinstance(stmt, exp.Insert):
            target = stmt.this
            cols_order: list[str] = []
            if isinstance(target, exp.Schema) and isinstance(target.this, exp.Table):
                tname = target.this.name.lower()
                cols_order = [c.name for c in target.expressions if hasattr(c, "name")]
            elif isinstance(target, exp.Table):
                tname = target.name.lower()
            else:
                continue

            if tname not in tables_map:
                warnings.append(f"INSERT references table '{tname}' whose CREATE TABLE wasn't found earlier in file.")
                continue

            pt = tables_map[tname]
            values_node = stmt.expression
            if isinstance(values_node, exp.Values):
                col_names = cols_order or pt.schema.column_names()
                pt.insert_columns = col_names
                for tup in values_node.expressions:
                    if isinstance(tup, exp.Tuple):
                        row_vals = [_literal_to_python(val_expr) for val_expr in tup.expressions]
                        pt.insert_rows.append(row_vals)
                pt.schema.row_count = len(pt.insert_rows)
                pt.schema.sample_rows = [
                    {
                        col_names[i]: row[i]
                        for i in range(min(len(col_names), len(row)))
                    }
                    for row in pt.insert_rows[:5]
                ]
            else:
                unsupported.append(f"Skipped dynamic INSERT ... SELECT on '{tname}' for untrusted script safety.")

        elif isinstance(stmt, exp.Alter):
            unsupported.append(f"Skipped ALTER statement during safe preview: {stmt.sql(dialect=sg_dialect)[:70]}")
        elif isinstance(stmt, exp.Command):
            kw = stmt.sql().strip().split()[0].upper() if stmt.sql().strip() else "CMD"
            if kw in ignored_cmd_prefixes:
                unsupported.append(f"Ignored dump header/transaction command: {kw}")
            else:
                unsupported.append(f"Blocked/skipped arbitrary command '{kw}' for upload isolation.")

    tables = [pt.schema for pt in tables_map.values()]
    notes = [
        "Parsed statically with SQLGlot AST inspection before touching any database.",
        f"Discovered {len(tables)} table(s) and {len(relationships)} verified foreign-key relationship(s).",
    ]
    if not tables:
        warnings.append("No CREATE TABLE definitions were detected in the uploaded SQL file.")

    return ImportPreview(
        preview_id=preview_id,
        file_name=file_name,
        file_kind="dump" if any(k in file_name.lower() for k in ("dump", "backup")) else "sql",
        detected_dialect=norm_dialect,
        tables=tables,
        relationships=relationships,
        warnings=warnings,
        ambiguous_or_unsupported=unsupported,
        notes=notes,
        _prepared_tables=tables_map,
    )


def accept_sql_import(preview: ImportPreview, sandbox_dir: Path) -> Path:
    """Create isolated DuckDB database containing validated imported tables & static literal rows."""
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    db_file = sandbox_dir / f"import_{preview.preview_id}.duckdb"
    if db_file.exists():
        db_file.unlink()

    con = duckdb.connect(str(db_file))
    try:
        for pt in preview._prepared_tables.values():
            tbl = pt.schema
            col_defs: list[str] = []
            for col in tbl.columns:
                duck_type = _map_type_to_duckdb(col.data_type)
                parts = [f'"{col.name}" {duck_type}']
                if col.is_primary_key:
                    parts.append("PRIMARY KEY")
                elif not col.nullable:
                    parts.append("NOT NULL")
                col_defs.append(" ".join(parts))
            create_sql = f'CREATE TABLE "{tbl.name}" ({", ".join(col_defs)})'
            con.execute(create_sql)

            if pt.insert_rows:
                cols = pt.insert_columns or tbl.column_names()
                placeholders = ", ".join(["?"] * len(cols))
                quoted_cols = ", ".join(f'"{c}"' for c in cols)
                insert_sql = f'INSERT INTO "{tbl.name}" ({quoted_cols}) VALUES ({placeholders})'
                normalized_rows = []
                for r in pt.insert_rows:
                    padded = list(r[: len(cols)]) + [None] * max(0, len(cols) - len(r))
                    normalized_rows.append(padded)
                con.executemany(insert_sql, normalized_rows)
    finally:
        con.close()

    return db_file
