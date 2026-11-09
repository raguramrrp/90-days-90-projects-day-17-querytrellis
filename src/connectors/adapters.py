"""Unified database connector, schema inspector, and safe multi-engine executor.

Supports:
- Built-in Demo DuckDB sandbox & uploaded isolated DuckDB sandboxes
- Live PostgreSQL (via psycopg, reusing QueryTrellis error translation)
- Live MySQL (via pymysql)
- Live SQLite (file path with read-only URI support when in read-only mode)
- Live Microsoft SQL Server (via python-tds)
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import psycopg
import pymysql
import pytds

from src.config.settings import ConnectionConfig
from src.connectors.demo_sandbox import ensure_demo_duckdb
from src.context.models import (
    ColumnSchema,
    ConstraintSchema,
    DatabaseContextSnapshot,
    IndexSchema,
    RelationshipSchema,
    TableSchema,
)
from src.db.connection_manager import ConnectionManager, DatabaseCatalog
from src.dialects.sqlglot_engine import normalize_dialect, transpile_for_duckdb
from src.security.guardrails import (
    SafetyEvaluation,
    evaluate_sql_safety,
    sanitize_error_message,
)


def _json_safe_cell(val: Any) -> Any:
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (datetime, date, dt_time)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (bytes, bytearray)):
        return f"<bytes len={len(val)}>"
    return str(val)


@dataclass(slots=True)
class LiveConnectionRequest:
    """In-memory connection parameters (password NEVER serialized back to UI or storage)."""

    engine: str  # postgresql | mysql | sqlite | sqlserver
    host: str = "localhost"
    port: int = 5432
    database: str = ""
    username: str = ""
    password: str = field(default="", repr=False)
    sqlite_path: str = ""
    ssl_mode: str = "prefer"
    connect_timeout: int = 5
    allow_write_opt_in: bool = False

    def safe_label(self) -> str:
        if self.engine == "sqlite":
            return f"sqlite://{Path(self.sqlite_path).name}"
        return f"{self.engine}://{self.host}:{self.port}/{self.database}"


@dataclass(slots=True)
class ExecutionResponse:
    """Actual execution result or safety/validation block details."""

    success: bool
    executed_dialect: str
    user_dialect: str
    statement_type: str
    columns: list[str] = field(default_factory=list)
    column_types: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    rows_returned: int = 0
    rows_affected: int | None = None
    was_truncated: bool = False
    max_rows_applied: int = 500
    duration_ms: float = 0.0
    is_read_only: bool = True
    requires_write_confirmation: bool = False
    confirmation_challenge: dict[str, Any] | None = None
    error_message: str = ""
    error_line: int | None = None
    error_column: int | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "executed_dialect": self.executed_dialect,
            "user_dialect": self.user_dialect,
            "statement_type": self.statement_type,
            "columns": self.columns,
            "column_types": self.column_types,
            "rows": self.rows,
            "rows_returned": self.rows_returned,
            "rows_affected": self.rows_affected,
            "was_truncated": self.was_truncated,
            "max_rows_applied": self.max_rows_applied,
            "duration_ms": self.duration_ms,
            "is_read_only": self.is_read_only,
            "requires_write_confirmation": self.requires_write_confirmation,
            "confirmation_challenge": self.confirmation_challenge,
            "error_message": self.error_message,
            "error_line": self.error_line,
            "error_column": self.error_column,
            "notes": self.notes,
        }


def catalog_to_context(
    catalog: DatabaseCatalog,
    label: str,
    allow_write_opt_in: bool = False,
) -> DatabaseContextSnapshot:
    """Convert preserved PostgreSQL DatabaseCatalog into canonical DatabaseContextSnapshot."""
    tables: list[TableSchema] = []
    relationships: list[RelationshipSchema] = []

    for tbl in catalog.tables:
        pk_cols = {
            c.lower()
            for idx in tbl.indexes
            if idx.is_primary
            for c in idx.key_columns
        }
        fk_cols = {
            c.lower()
            for fk in tbl.foreign_keys
            for c in fk.columns
        }
        cols = [
            ColumnSchema(
                name=col.column_name,
                data_type=col.data_type,
                nullable=col.is_nullable,
                is_primary_key=col.column_name.lower() in pk_cols,
                is_foreign_key=col.column_name.lower() in fk_cols,
                default_value=col.column_default,
                ordinal_position=col.ordinal_position,
            )
            for col in tbl.columns
        ]
        idxs = [
            IndexSchema(
                name=i.index_name,
                table_name=tbl.table_name,
                columns=i.key_columns,
                is_unique=i.is_unique,
                is_primary=i.is_primary,
                predicate=i.predicate,
                definition=i.definition,
            )
            for i in tbl.indexes
        ]
        constraints: list[ConstraintSchema] = []
        for idx in tbl.indexes:
            if idx.is_primary:
                constraints.append(
                    ConstraintSchema(
                        name=idx.index_name,
                        table_name=tbl.table_name,
                        constraint_type="PRIMARY KEY",
                        definition=f"PRIMARY KEY ({', '.join(idx.key_columns)})",
                    )
                )
        for fk in tbl.foreign_keys:
            relationships.append(
                RelationshipSchema(
                    constraint_name=fk.constraint_name,
                    source_table=tbl.table_name,
                    source_columns=fk.columns,
                    target_table=fk.referenced_table,
                    target_columns=fk.referenced_columns,
                    verified=True,
                )
            )
            constraints.append(
                ConstraintSchema(
                    name=fk.constraint_name,
                    table_name=tbl.table_name,
                    constraint_type="FOREIGN KEY",
                    definition=f"FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {fk.referenced_table}({', '.join(fk.referenced_columns)})",
                )
            )

        tables.append(
            TableSchema(
                name=tbl.table_name,
                schema_name=tbl.schema_name,
                table_type=tbl.table_type,
                row_count=tbl.estimated_rows,
                row_count_is_estimated=True,
                columns=cols,
                indexes=idxs,
                constraints=constraints,
            )
        )

    return DatabaseContextSnapshot(
        context_id=f"pg:{catalog.database_name}",
        label=label,
        source_kind="live_postgres",
        engine="postgresql",
        dialect="postgresql",
        read_only_default=True,
        allow_write_opt_in=allow_write_opt_in,
        can_execute=True,
        supports_explain=True,
        supports_explain_analyze=True,
        tables=tables,
        relationships=relationships,
        notes=[f"Connected PostgreSQL server: {catalog.server_version}"],
    )


class MultiDBConnector:
    """Manages active engine connections, schema discovery, and safe query execution."""

    def __init__(self) -> None:
        self._duckdb_path: Path | None = None
        self._active_kind: str = "demo_duckdb"
        self._active_engine: str = "duckdb"
        self._active_dialect: str = "postgresql"
        self._active_label: str = "Enterprise HR & Sales Demo (Built-in Sandbox)"
        self._allow_write_opt_in: bool = False
        self._pg_manager: ConnectionManager | None = None
        self._live_req: LiveConnectionRequest | None = None
        self._context_id: str = "demo_enterprise"
        self._notes: list[str] = [
            "Built-in zero-config demo dataset active inside isolated local DuckDB sandbox."
        ]
        self._warnings: list[str] = []
        self._cached_snapshot: DatabaseContextSnapshot | None = None

    @property
    def active_dialect(self) -> str:
        return self._active_dialect

    def set_dialect(self, dialect: str) -> str:
        self._active_dialect = normalize_dialect(dialect)
        if self._cached_snapshot is not None:
            self._cached_snapshot.dialect = self._active_dialect
        return self._active_dialect

    def set_allow_write_opt_in(self, allow_write: bool) -> None:
        self._allow_write_opt_in = bool(allow_write)
        if self._cached_snapshot is not None:
            self._cached_snapshot.allow_write_opt_in = self._allow_write_opt_in

    def activate_demo_sandbox(self, dialect: str | None = None) -> DatabaseContextSnapshot:
        """Activate built-in deterministic DuckDB demo dataset."""
        self.disconnect_live()
        demo_path = ensure_demo_duckdb()
        self._duckdb_path = demo_path
        self._active_kind = "demo_duckdb"
        self._active_engine = "duckdb"
        if dialect:
            self._active_dialect = normalize_dialect(dialect)
        self._active_label = "Enterprise HR & Sales Demo (DuckDB Sandbox)"
        self._context_id = "demo_enterprise"
        self._allow_write_opt_in = False
        self._notes = [
            "Demo Mode active: isolated local DuckDB dataset with departments, employees, regions, customers, products, orders, and order_items.",
            "Supports all 4 SQL dialects (PostgreSQL, MySQL, SQLite, SQL Server) via AST transpilation inside the sandbox.",
        ]
        self._warnings = []
        self._cached_snapshot = None
        return self.inspect_schema(force_refresh=True)

    def activate_uploaded_duckdb(
        self,
        duckdb_path: Path,
        label: str,
        *,
        context_id: str,
        source_dialect: str = "postgresql",
        relationships: list[RelationshipSchema] | None = None,
        warnings: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> DatabaseContextSnapshot:
        """Switch active workspace to a freshly imported isolated DuckDB sandbox file."""
        self.disconnect_live()
        self._duckdb_path = duckdb_path
        self._active_kind = "uploaded_sandbox"
        self._active_engine = "duckdb"
        self._active_dialect = normalize_dialect(source_dialect)
        self._active_label = label
        self._context_id = context_id
        self._allow_write_opt_in = False
        self._warnings = list(warnings or [])
        self._notes = list(notes or [])
        self._cached_snapshot = None
        snap = self.inspect_schema(force_refresh=True)
        if relationships:
            snap.relationships = relationships
            # Mark FK flags on matching columns
            fk_lookup = {
                (r.source_table.lower(), c.lower())
                for r in relationships
                for c in r.source_columns
            }
            for tbl in snap.tables:
                for col in tbl.columns:
                    if (tbl.name.lower(), col.name.lower()) in fk_lookup:
                        col.is_foreign_key = True
        return snap

    def disconnect_live(self) -> None:
        if self._pg_manager is not None:
            self._pg_manager.disconnect()
            self._pg_manager = None
        self._live_req = None

    def connect_live(self, req: LiveConnectionRequest) -> DatabaseContextSnapshot:
        """Connect to live PostgreSQL, MySQL, SQLite, or SQL Server and inspect schema."""
        engine = req.engine.strip().lower()
        if engine not in {"postgresql", "mysql", "sqlite", "sqlserver"}:
            raise ValueError(f"Unsupported database engine '{req.engine}'.")

        self.disconnect_live()
        self._allow_write_opt_in = bool(req.allow_write_opt_in)

        if engine == "postgresql":
            cfg = ConnectionConfig(
                host=req.host,
                port=int(req.port or 5432),
                database=req.database,
                username=req.username,
                password=req.password,
                sslmode=req.ssl_mode or "prefer",
                connect_timeout=max(1, min(30, int(req.connect_timeout or 5))),
            )
            mgr = ConnectionManager(cfg)
            st = mgr.connect(cfg)
            if not st.connected:
                raise ConnectionError(st.error_message or "PostgreSQL connection failed.")
            self._pg_manager = mgr
            self._live_req = req
            self._active_kind = "live_postgres"
            self._active_engine = "postgresql"
            self._active_dialect = "postgresql"
            self._active_label = cfg.display_label()
            self._context_id = f"pg:{cfg.database}"
            self._notes = [f"Live PostgreSQL connection active ({st.current_user}@{cfg.host}:{cfg.port})."]
            self._warnings = []
            self._cached_snapshot = None
            return self.inspect_schema(force_refresh=True)

        # Validate SQLite / MySQL / SQL Server connectivity cleanly before switching
        self._test_non_pg_connection(req)
        self._live_req = req
        self._duckdb_path = None
        self._active_kind = f"live_{engine}" if engine != "sqlserver" else "live_mssql"
        self._active_engine = engine
        self._active_dialect = engine
        self._active_label = req.safe_label()
        self._context_id = req.safe_label()
        self._notes = [f"Live {engine.upper()} connection verified ({req.safe_label()})."]
        self._warnings = []
        self._cached_snapshot = None
        return self.inspect_schema(force_refresh=True)

    @staticmethod
    def _test_non_pg_connection(req: LiveConnectionRequest) -> None:
        engine = req.engine.strip().lower()
        try:
            if engine == "sqlite":
                db_path = Path(req.sqlite_path)
                if not db_path.exists():
                    raise FileNotFoundError(f"SQLite file not found: {db_path.name}")
                con = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=req.connect_timeout)
                try:
                    con.execute("SELECT 1").fetchone()
                finally:
                    con.close()
            elif engine == "mysql":
                con = pymysql.connect(
                    host=req.host,
                    port=int(req.port or 3306),
                    user=req.username,
                    password=req.password,
                    database=req.database,
                    connect_timeout=max(1, min(30, int(req.connect_timeout or 5))),
                    read_timeout=10,
                    write_timeout=10,
                )
                try:
                    with con.cursor() as cur:
                        cur.execute("SELECT 1")
                finally:
                    con.close()
            elif engine == "sqlserver":
                con = pytds.connect(
                    server=req.host,
                    port=int(req.port or 1433),
                    database=req.database,
                    user=req.username,
                    password=req.password,
                    timeout=max(1, min(30, int(req.connect_timeout or 5))),
                )
                try:
                    with con.cursor() as cur:
                        cur.execute("SELECT 1")
                finally:
                    con.close()
        except Exception as exc:
            raise ConnectionError(sanitize_error_message(f"Connection to {req.safe_label()} failed: {exc}")) from exc

    def inspect_schema(self, force_refresh: bool = False) -> DatabaseContextSnapshot:
        """Return full active database schema & verified relationship metadata."""
        if self._cached_snapshot is not None and not force_refresh:
            return self._cached_snapshot

        if self._active_engine == "postgresql" and self._pg_manager is not None:
            catalog = self._pg_manager.fetch_catalog(force_refresh=force_refresh)
            snap = catalog_to_context(catalog, self._active_label, allow_write_opt_in=self._allow_write_opt_in)
            snap.notes = list(self._notes) + snap.notes
            snap.warnings = list(self._warnings)
            self._cached_snapshot = snap
            return snap

        if self._active_engine == "duckdb":
            if self._duckdb_path is None:
                self._duckdb_path = ensure_demo_duckdb()
            snap = self._inspect_duckdb_schema(self._duckdb_path)
            self._cached_snapshot = snap
            return snap

        if self._active_engine == "sqlite" and self._live_req:
            snap = self._inspect_sqlite_schema(Path(self._live_req.sqlite_path))
            self._cached_snapshot = snap
            return snap

        if self._active_engine == "mysql" and self._live_req:
            snap = self._inspect_mysql_schema(self._live_req)
            self._cached_snapshot = snap
            return snap

        if self._active_engine == "sqlserver" and self._live_req:
            snap = self._inspect_mssql_schema(self._live_req)
            self._cached_snapshot = snap
            return snap

        return self.activate_demo_sandbox()

    def _inspect_duckdb_schema(self, db_path: Path) -> DatabaseContextSnapshot:
        con = duckdb.connect(str(db_path), read_only=True)
        tables: list[TableSchema] = []
        relationships: list[RelationshipSchema] = []
        try:
            tbl_rows = con.execute(
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
                """
            ).fetchall()

            # Try duckdb_constraints for PK & FK inspection
            fk_by_table: dict[str, set[str]] = {}
            pk_by_table: dict[str, set[str]] = {}
            cons_by_table: dict[str, list[ConstraintSchema]] = {}
            try:
                cons_rows = con.execute(
                    """
                    SELECT table_name, constraint_type, constraint_text, constraint_column_names
                    FROM duckdb_constraints()
                    WHERE schema_name = 'main'
                    """
                ).fetchall()
                for tname, ctype, ctext, ccols in cons_rows:
                    col_list = [str(c) for c in (ccols or [])]
                    cons_by_table.setdefault(tname, []).append(
                        ConstraintSchema(
                            name=f"{tname}_{ctype.lower().replace(' ', '_')}",
                            table_name=tname,
                            constraint_type=ctype,
                            definition=str(ctext or ""),
                        )
                    )
                    if ctype == "PRIMARY KEY":
                        pk_by_table.setdefault(tname, set()).update(c.lower() for c in col_list)
                    elif ctype == "FOREIGN KEY":
                        fk_by_table.setdefault(tname, set()).update(c.lower() for c in col_list)
                        # Parse REFERENCES tgt(col) when present in constraint_text
                        txt = str(ctext or "")
                        if "REFERENCES" in txt.upper() and "(" in txt:
                            after_ref = txt.split("REFERENCES", 1)[1].strip()
                            ref_tbl = after_ref.split("(", 1)[0].strip().strip('"')
                            ref_cols_part = after_ref.split("(", 1)[1].split(")", 1)[0]
                            ref_cols = [c.strip().strip('"') for c in ref_cols_part.split(",") if c.strip()]
                            if ref_tbl and col_list and ref_cols:
                                relationships.append(
                                    RelationshipSchema(
                                        constraint_name=f"fk_{tname}_{'_'.join(col_list)}",
                                        source_table=tname,
                                        source_columns=col_list,
                                        target_table=ref_tbl,
                                        target_columns=ref_cols,
                                        verified=True,
                                    )
                                )
            except Exception:
                pass

            for sch, tname, ttype in tbl_rows:
                col_rows = con.execute(
                    """
                    SELECT column_name, data_type, is_nullable, ordinal_position, column_default
                    FROM information_schema.columns
                    WHERE table_schema = ? AND table_name = ?
                    ORDER BY ordinal_position
                    """,
                    [sch, tname],
                ).fetchall()
                cnt_row = con.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()
                rc = int(cnt_row[0]) if cnt_row else 0

                sample_cur = con.execute(f'SELECT * FROM "{tname}" LIMIT 3')
                scols = [d[0] for d in (sample_cur.description or [])]
                srows = [
                    {scols[i]: _json_safe_cell(val) for i, val in enumerate(row)}
                    for row in sample_cur.fetchall()
                ]

                pk_set = pk_by_table.get(tname, set())
                fk_set = fk_by_table.get(tname, set())
                cols = [
                    ColumnSchema(
                        name=str(cname),
                        data_type=str(dtype),
                        nullable=(str(is_null).upper() == "YES"),
                        is_primary_key=str(cname).lower() in pk_set,
                        is_foreign_key=str(cname).lower() in fk_set,
                        default_value=str(cdef) if cdef is not None else None,
                        ordinal_position=int(ord_pos),
                        sample_values=[r.get(str(cname)) for r in srows if r.get(str(cname)) is not None][:3],
                    )
                    for cname, dtype, is_null, ord_pos, cdef in col_rows
                ]
                tables.append(
                    TableSchema(
                        name=str(tname),
                        schema_name=str(sch),
                        table_type=str(ttype),
                        row_count=rc,
                        row_count_is_estimated=False,
                        columns=cols,
                        constraints=cons_by_table.get(str(tname), []),
                        sample_rows=srows,
                    )
                )
        finally:
            con.close()

        return DatabaseContextSnapshot(
            context_id=self._context_id,
            label=self._active_label,
            source_kind=self._active_kind,
            engine="duckdb",
            dialect=self._active_dialect,
            read_only_default=True,
            allow_write_opt_in=self._allow_write_opt_in,
            can_execute=True,
            supports_explain=True,
            supports_explain_analyze=False,
            tables=tables,
            relationships=relationships,
            warnings=list(self._warnings),
            notes=list(self._notes),
        )

    def _inspect_sqlite_schema(self, db_path: Path) -> DatabaseContextSnapshot:
        con = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=5)
        tables: list[TableSchema] = []
        relationships: list[RelationshipSchema] = []
        try:
            tbls = con.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            for tname, ttype in tbls:
                info_rows = con.execute(f'PRAGMA table_info("{tname}")').fetchall()
                fk_rows = con.execute(f'PRAGMA foreign_key_list("{tname}")').fetchall()
                idx_rows = con.execute(f'PRAGMA index_list("{tname}")').fetchall()

                fk_cols = {str(r[3]).lower() for r in fk_rows}
                for fkid, _seq, ref_tbl, from_col, to_col, *_rest in fk_rows:
                    relationships.append(
                        RelationshipSchema(
                            constraint_name=f"fk_{tname}_{fkid}_{from_col}",
                            source_table=tname,
                            source_columns=[str(from_col)],
                            target_table=str(ref_tbl),
                            target_columns=[str(to_col or from_col)],
                            verified=True,
                        )
                    )

                indexes: list[IndexSchema] = []
                for _seq, iname, is_uniq, origin, _partial in idx_rows:
                    icols = [str(r[2]) for r in con.execute(f'PRAGMA index_info("{iname}")').fetchall() if r[2]]
                    indexes.append(
                        IndexSchema(
                            name=str(iname),
                            table_name=tname,
                            columns=icols,
                            is_unique=bool(is_uniq),
                            is_primary=(origin == "pk"),
                        )
                    )

                cnt_row = con.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()
                rc = int(cnt_row[0]) if cnt_row else 0
                cur = con.execute(f'SELECT * FROM "{tname}" LIMIT 3')
                scols = [d[0] for d in (cur.description or [])]
                srows = [{scols[i]: _json_safe_cell(v) for i, v in enumerate(row)} for row in cur.fetchall()]

                cols = [
                    ColumnSchema(
                        name=str(cname),
                        data_type=str(ctype or "TEXT"),
                        nullable=(notnull == 0),
                        is_primary_key=(pk > 0),
                        is_foreign_key=(str(cname).lower() in fk_cols),
                        default_value=str(dflt) if dflt is not None else None,
                        ordinal_position=int(cid) + 1,
                        sample_values=[r.get(str(cname)) for r in srows if r.get(str(cname)) is not None][:3],
                    )
                    for cid, cname, ctype, notnull, dflt, pk in info_rows
                ]
                tables.append(
                    TableSchema(
                        name=tname,
                        schema_name="main",
                        table_type="VIEW" if ttype == "view" else "BASE TABLE",
                        row_count=rc,
                        row_count_is_estimated=False,
                        columns=cols,
                        indexes=indexes,
                        sample_rows=srows,
                    )
                )
        finally:
            con.close()

        return DatabaseContextSnapshot(
            context_id=self._context_id,
            label=self._active_label,
            source_kind="live_sqlite",
            engine="sqlite",
            dialect="sqlite",
            read_only_default=True,
            allow_write_opt_in=self._allow_write_opt_in,
            can_execute=True,
            supports_explain=True,
            supports_explain_analyze=False,
            tables=tables,
            relationships=relationships,
            warnings=list(self._warnings),
            notes=list(self._notes),
        )

    def _inspect_mysql_schema(self, req: LiveConnectionRequest) -> DatabaseContextSnapshot:
        con = pymysql.connect(
            host=req.host,
            port=int(req.port or 3306),
            user=req.username,
            password=req.password,
            database=req.database,
            connect_timeout=max(1, min(30, int(req.connect_timeout or 5))),
        )
        tables: list[TableSchema] = []
        relationships: list[RelationshipSchema] = []
        try:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT TABLE_NAME, TABLE_TYPE, TABLE_ROWS
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s
                    ORDER BY TABLE_NAME
                    """,
                    (req.database,),
                )
                tbl_rows = cur.fetchall()
                tbl_map: dict[str, TableSchema] = {}
                for tname, ttype, est_rows in tbl_rows:
                    ts = TableSchema(
                        name=str(tname),
                        schema_name=req.database,
                        table_type=str(ttype),
                        row_count=int(est_rows or 0),
                        row_count_is_estimated=True,
                    )
                    tbl_map[str(tname)] = ts
                    tables.append(ts)

                cur.execute(
                    """
                    SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY, COLUMN_DEFAULT, ORDINAL_POSITION
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s
                    ORDER BY TABLE_NAME, ORDINAL_POSITION
                    """,
                    (req.database,),
                )
                for tname, cname, ctype, is_null, ckey, cdef, ord_pos in cur.fetchall():
                    if tname in tbl_map:
                        tbl_map[tname].columns.append(
                            ColumnSchema(
                                name=str(cname),
                                data_type=str(ctype),
                                nullable=(str(is_null).upper() == "YES"),
                                is_primary_key=(str(ckey).upper() == "PRI"),
                                is_foreign_key=(str(ckey).upper() == "MUL"),
                                default_value=str(cdef) if cdef is not None else None,
                                ordinal_position=int(ord_pos),
                            )
                        )

                cur.execute(
                    """
                    SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                    ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION
                    """,
                    (req.database,),
                )
                for cname, tname, col, rt, rc in cur.fetchall():
                    relationships.append(
                        RelationshipSchema(
                            constraint_name=str(cname),
                            source_table=str(tname),
                            source_columns=[str(col)],
                            target_table=str(rt),
                            target_columns=[str(rc)],
                            verified=True,
                        )
                    )
        finally:
            con.close()

        return DatabaseContextSnapshot(
            context_id=self._context_id,
            label=self._active_label,
            source_kind="live_mysql",
            engine="mysql",
            dialect="mysql",
            read_only_default=True,
            allow_write_opt_in=self._allow_write_opt_in,
            can_execute=True,
            supports_explain=True,
            supports_explain_analyze=True,
            tables=tables,
            relationships=relationships,
            warnings=list(self._warnings),
            notes=list(self._notes),
        )

    def _inspect_mssql_schema(self, req: LiveConnectionRequest) -> DatabaseContextSnapshot:
        con = pytds.connect(
            server=req.host,
            port=int(req.port or 1433),
            database=req.database,
            user=req.username,
            password=req.password,
            timeout=max(1, min(30, int(req.connect_timeout or 5))),
        )
        tables: list[TableSchema] = []
        relationships: list[RelationshipSchema] = []
        try:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
                    FROM INFORMATION_SCHEMA.TABLES
                    ORDER BY TABLE_SCHEMA, TABLE_NAME
                    """
                )
                tbl_map: dict[tuple[str, str], TableSchema] = {}
                for sch, tname, ttype in cur.fetchall():
                    ts = TableSchema(name=str(tname), schema_name=str(sch), table_type=str(ttype))
                    tbl_map[(str(sch), str(tname))] = ts
                    tables.append(ts)

                cur.execute(
                    """
                    SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, ORDINAL_POSITION
                    FROM INFORMATION_SCHEMA.COLUMNS
                    ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
                    """
                )
                for sch, tname, cname, dtype, is_null, cdef, ord_pos in cur.fetchall():
                    key = (str(sch), str(tname))
                    if key in tbl_map:
                        tbl_map[key].columns.append(
                            ColumnSchema(
                                name=str(cname),
                                data_type=str(dtype),
                                nullable=(str(is_null).upper() == "YES"),
                                default_value=str(cdef) if cdef is not None else None,
                                ordinal_position=int(ord_pos),
                            )
                        )
        finally:
            con.close()

        return DatabaseContextSnapshot(
            context_id=self._context_id,
            label=self._active_label,
            source_kind="live_mssql",
            engine="sqlserver",
            dialect="sqlserver",
            read_only_default=True,
            allow_write_opt_in=self._allow_write_opt_in,
            can_execute=True,
            supports_explain=False,
            supports_explain_analyze=False,
            tables=tables,
            relationships=relationships,
            warnings=list(self._warnings),
            notes=list(self._notes),
        )

    def execute_sql(
        self,
        sql: str,
        *,
        dialect: str | None = None,
        max_rows: int = 500,
        timeout_ms: int = 5000,
        allow_write_opt_in: bool | None = None,
        confirmed_write: bool = False,
        confirmation_token: str | None = None,
    ) -> ExecutionResponse:
        """Validate safety rules and execute SQL against active sandbox or live engine."""
        user_dialect = normalize_dialect(dialect or self._active_dialect)
        safe_limit = max(1, min(5000, int(max_rows)))
        safe_timeout = max(200, min(60000, int(timeout_ms)))
        write_flag = self._allow_write_opt_in if allow_write_opt_in is None else bool(allow_write_opt_in)

        safety: SafetyEvaluation = evaluate_sql_safety(
            sql,
            dialect=user_dialect,
            target_database=self._active_label,
            allow_write_opt_in=write_flag,
            confirmed_write=confirmed_write,
            confirmation_token=confirmation_token,
        )

        if not safety.allowed:
            return ExecutionResponse(
                success=False,
                executed_dialect=user_dialect,
                user_dialect=user_dialect,
                statement_type=safety.operation_name,
                max_rows_applied=safe_limit,
                is_read_only=safety.is_read_only,
                requires_write_confirmation=safety.requires_write_confirmation,
                confirmation_challenge=(
                    safety.confirmation_challenge.to_dict() if safety.confirmation_challenge else None
                ),
                error_message=safety.error_message,
                notes=safety.warnings,
            )

        notes: list[str] = list(safety.warnings)
        if self._active_engine == "duckdb":
            return self._exec_duckdb(sql, user_dialect, safety, safe_limit, notes)
        if self._active_engine == "postgresql" and self._pg_manager is not None:
            return self._exec_postgres(sql, user_dialect, safety, safe_limit, safe_timeout, notes)
        if self._active_engine == "sqlite" and self._live_req:
            return self._exec_sqlite(sql, user_dialect, safety, safe_limit, safe_timeout, notes)
        if self._active_engine == "mysql" and self._live_req:
            return self._exec_mysql(sql, user_dialect, safety, safe_limit, safe_timeout, notes)
        if self._active_engine == "sqlserver" and self._live_req:
            return self._exec_mssql(sql, user_dialect, safety, safe_limit, notes)

        return ExecutionResponse(
            success=False,
            executed_dialect=user_dialect,
            user_dialect=user_dialect,
            statement_type=safety.operation_name,
            error_message="No active database target configured.",
        )

    def _exec_duckdb(
        self,
        sql: str,
        user_dialect: str,
        safety: SafetyEvaluation,
        max_rows: int,
        notes: list[str],
    ) -> ExecutionResponse:
        if self._duckdb_path is None:
            self._duckdb_path = ensure_demo_duckdb()

        target_sql, trans_notes, err = transpile_for_duckdb(sql, user_dialect)
        notes.extend(trans_notes)
        if err:
            return ExecutionResponse(
                success=False,
                executed_dialect="duckdb",
                user_dialect=user_dialect,
                statement_type=safety.operation_name,
                error_message=err,
                notes=notes,
            )

        t0 = time.perf_counter()
        con = duckdb.connect(str(self._duckdb_path), read_only=safety.is_read_only)
        try:
            cur = con.execute(target_sql)
            cols = [str(d[0]) for d in (cur.description or [])]
            types = [str(d[1]) for d in (cur.description or [])] if cur.description else []
            if safety.is_read_only or cols:
                fetched = cur.fetchmany(max_rows + 1)
                was_truncated = len(fetched) > max_rows
                trimmed = fetched[:max_rows]
                rows = [
                    {cols[i]: _json_safe_cell(val) for i, val in enumerate(row)}
                    for row in trimmed
                ]
                dur_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                if not safety.is_read_only:
                    self._cached_snapshot = None
                return ExecutionResponse(
                    success=True,
                    executed_dialect="duckdb",
                    user_dialect=user_dialect,
                    statement_type=safety.operation_name,
                    columns=cols,
                    column_types=types,
                    rows=rows,
                    rows_returned=len(rows),
                    was_truncated=was_truncated,
                    max_rows_applied=max_rows,
                    duration_ms=dur_ms,
                    is_read_only=safety.is_read_only,
                    notes=notes,
                )
            else:
                dur_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                self._cached_snapshot = None
                return ExecutionResponse(
                    success=True,
                    executed_dialect="duckdb",
                    user_dialect=user_dialect,
                    statement_type=safety.operation_name,
                    rows_affected=cur.rowcount if cur.rowcount >= 0 else None,
                    duration_ms=dur_ms,
                    is_read_only=False,
                    notes=notes + [f"Executed confirmed write operation ({safety.operation_name})."],
                )
        except Exception as exc:
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            return ExecutionResponse(
                success=False,
                executed_dialect="duckdb",
                user_dialect=user_dialect,
                statement_type=safety.operation_name,
                duration_ms=dur_ms,
                is_read_only=safety.is_read_only,
                error_message=sanitize_error_message(str(exc)),
                notes=notes,
            )
        finally:
            con.close()

    def _exec_postgres(
        self,
        sql: str,
        user_dialect: str,
        safety: SafetyEvaluation,
        max_rows: int,
        timeout_ms: int,
        notes: list[str],
    ) -> ExecutionResponse:
        assert self._pg_manager is not None
        conn = self._pg_manager.get_connection()
        t0 = time.perf_counter()
        try:
            if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                conn.rollback()
            with conn.transaction():
                with conn.cursor() as guard:
                    if safety.is_read_only:
                        guard.execute("SET TRANSACTION READ ONLY")
                    guard.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
                with conn.cursor() as cur:
                    cur.execute(sql)
                    if cur.description:
                        cols = [d.name for d in cur.description]
                        types = [str(d.type_code) for d in cur.description]
                        fetched = cur.fetchmany(max_rows + 1)
                        was_truncated = len(fetched) > max_rows
                        trimmed = fetched[:max_rows]
                        rows = [{cols[i]: _json_safe_cell(v) for i, v in enumerate(r)} for r in trimmed]
                        dur_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                        return ExecutionResponse(
                            success=True,
                            executed_dialect="postgresql",
                            user_dialect=user_dialect,
                            statement_type=safety.operation_name,
                            columns=cols,
                            column_types=types,
                            rows=rows,
                            rows_returned=len(rows),
                            was_truncated=was_truncated,
                            max_rows_applied=max_rows,
                            duration_ms=dur_ms,
                            is_read_only=safety.is_read_only,
                            notes=notes,
                        )
                    else:
                        dur_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                        self._cached_snapshot = None
                        return ExecutionResponse(
                            success=True,
                            executed_dialect="postgresql",
                            user_dialect=user_dialect,
                            statement_type=safety.operation_name,
                            rows_affected=cur.rowcount,
                            duration_ms=dur_ms,
                            is_read_only=False,
                            notes=notes,
                        )
        except Exception as exc:
            dur_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            try:
                conn.rollback()
            except Exception:
                pass
            return ExecutionResponse(
                success=False,
                executed_dialect="postgresql",
                user_dialect=user_dialect,
                statement_type=safety.operation_name,
                duration_ms=dur_ms,
                is_read_only=safety.is_read_only,
                error_message=sanitize_error_message(str(exc)),
                notes=notes,
            )

    def _exec_sqlite(
        self,
        sql: str,
        user_dialect: str,
        safety: SafetyEvaluation,
        max_rows: int,
        timeout_ms: int,
        notes: list[str],
    ) -> ExecutionResponse:
        assert self._live_req is not None
        p = Path(self._live_req.sqlite_path).resolve()
        uri = f"file:{p}?mode=ro" if safety.is_read_only else f"file:{p}"
        t0 = time.perf_counter()
        con = sqlite3.connect(uri, uri=True, timeout=timeout_ms / 1000.0)
        try:
            if safety.is_read_only:
                con.execute("PRAGMA query_only = ON")
            cur = con.execute(sql)
            if cur.description:
                cols = [d[0] for d in cur.description]
                fetched = cur.fetchmany(max_rows + 1)
                was_truncated = len(fetched) > max_rows
                trimmed = fetched[:max_rows]
                rows = [{cols[i]: _json_safe_cell(v) for i, v in enumerate(r)} for r in trimmed]
                dur_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                return ExecutionResponse(
                    success=True,
                    executed_dialect="sqlite",
                    user_dialect=user_dialect,
                    statement_type=safety.operation_name,
                    columns=cols,
                    column_types=["TEXT" for _ in cols],
                    rows=rows,
                    rows_returned=len(rows),
                    was_truncated=was_truncated,
                    max_rows_applied=max_rows,
                    duration_ms=dur_ms,
                    is_read_only=safety.is_read_only,
                    notes=notes,
                )
            else:
                con.commit()
                self._cached_snapshot = None
                dur_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                return ExecutionResponse(
                    success=True,
                    executed_dialect="sqlite",
                    user_dialect=user_dialect,
                    statement_type=safety.operation_name,
                    rows_affected=cur.rowcount,
                    duration_ms=dur_ms,
                    is_read_only=False,
                    notes=notes,
                )
        except Exception as exc:
            return ExecutionResponse(
                success=False,
                executed_dialect="sqlite",
                user_dialect=user_dialect,
                statement_type=safety.operation_name,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                error_message=sanitize_error_message(str(exc)),
                notes=notes,
            )
        finally:
            con.close()

    def _exec_mysql(
        self,
        sql: str,
        user_dialect: str,
        safety: SafetyEvaluation,
        max_rows: int,
        timeout_ms: int,
        notes: list[str],
    ) -> ExecutionResponse:
        assert self._live_req is not None
        req = self._live_req
        t0 = time.perf_counter()
        con = pymysql.connect(
            host=req.host,
            port=int(req.port or 3306),
            user=req.username,
            password=req.password,
            database=req.database,
            connect_timeout=max(1, min(30, int(req.connect_timeout or 5))),
            read_timeout=max(1, int(timeout_ms // 1000) or 5),
        )
        try:
            with con.cursor() as cur:
                if safety.is_read_only:
                    cur.execute("SET SESSION TRANSACTION READ ONLY")
                cur.execute(sql)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    fetched = cur.fetchmany(max_rows + 1)
                    was_truncated = len(fetched) > max_rows
                    rows = [{cols[i]: _json_safe_cell(v) for i, v in enumerate(r)} for r in fetched[:max_rows]]
                    return ExecutionResponse(
                        success=True,
                        executed_dialect="mysql",
                        user_dialect=user_dialect,
                        statement_type=safety.operation_name,
                        columns=cols,
                        column_types=[str(d[1]) for d in cur.description],
                        rows=rows,
                        rows_returned=len(rows),
                        was_truncated=was_truncated,
                        max_rows_applied=max_rows,
                        duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                        is_read_only=True,
                        notes=notes,
                    )
                else:
                    con.commit()
                    self._cached_snapshot = None
                    return ExecutionResponse(
                        success=True,
                        executed_dialect="mysql",
                        user_dialect=user_dialect,
                        statement_type=safety.operation_name,
                        rows_affected=cur.rowcount,
                        duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                        is_read_only=False,
                        notes=notes,
                    )
        except Exception as exc:
            return ExecutionResponse(
                success=False,
                executed_dialect="mysql",
                user_dialect=user_dialect,
                statement_type=safety.operation_name,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                error_message=sanitize_error_message(str(exc)),
                notes=notes,
            )
        finally:
            con.close()

    def _exec_mssql(
        self,
        sql: str,
        user_dialect: str,
        safety: SafetyEvaluation,
        max_rows: int,
        notes: list[str],
    ) -> ExecutionResponse:
        assert self._live_req is not None
        req = self._live_req
        t0 = time.perf_counter()
        con = pytds.connect(
            server=req.host,
            port=int(req.port or 1433),
            database=req.database,
            user=req.username,
            password=req.password,
            timeout=max(1, min(30, int(req.connect_timeout or 5))),
        )
        try:
            with con.cursor() as cur:
                cur.execute(sql)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    fetched = cur.fetchmany(max_rows + 1)
                    was_truncated = len(fetched) > max_rows
                    rows = [{cols[i]: _json_safe_cell(v) for i, v in enumerate(r)} for r in fetched[:max_rows]]
                    return ExecutionResponse(
                        success=True,
                        executed_dialect="sqlserver",
                        user_dialect=user_dialect,
                        statement_type=safety.operation_name,
                        columns=cols,
                        column_types=["SQL_VARIANT" for _ in cols],
                        rows=rows,
                        rows_returned=len(rows),
                        was_truncated=was_truncated,
                        max_rows_applied=max_rows,
                        duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                        is_read_only=safety.is_read_only,
                        notes=notes,
                    )
                else:
                    con.commit()
                    self._cached_snapshot = None
                    return ExecutionResponse(
                        success=True,
                        executed_dialect="sqlserver",
                        user_dialect=user_dialect,
                        statement_type=safety.operation_name,
                        rows_affected=cur.rowcount,
                        duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                        is_read_only=False,
                        notes=notes,
                    )
        except Exception as exc:
            return ExecutionResponse(
                success=False,
                executed_dialect="sqlserver",
                user_dialect=user_dialect,
                statement_type=safety.operation_name,
                duration_ms=round((time.perf_counter() - t0) * 1000.0, 3),
                error_message=sanitize_error_message(str(exc)),
                notes=notes,
            )
        finally:
            con.close()

    def run_explain(
        self,
        sql: str,
        *,
        dialect: str | None = None,
        analyze: bool = False,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        """Run non-executing estimated EXPLAIN (or explicit opt-in EXPLAIN ANALYZE where supported)."""
        user_dialect = normalize_dialect(dialect or self._active_dialect)
        safety = evaluate_sql_safety(sql, dialect=user_dialect, allow_write_opt_in=False)
        if not safety.allowed or not safety.is_read_only:
            return {
                "success": False,
                "error_message": safety.error_message or "EXPLAIN requires a valid read-only SELECT query.",
                "plan_kind": "blocked",
            }

        if self._active_engine == "postgresql" and self._pg_manager is not None:
            from src.db.safe_executor import run_explain_plan
            from src.explain.plan_analyzer import analyze_explain_plan
            from src.explain.plan_parser import parse_explain_json

            res = run_explain_plan(
                self._pg_manager.get_connection(),
                sql,
                analyze=analyze,
                buffers=analyze,
                timeout_ms=timeout_ms,
            )
            if not res.success or res.raw_plan_json is None:
                return {
                    "success": False,
                    "error_message": res.error_message,
                    "plan_kind": "measured_performance" if analyze else "estimated_plan",
                }
            parsed = parse_explain_json(res.raw_plan_json)
            catalog = self._pg_manager.fetch_catalog()
            insights = analyze_explain_plan(parsed, catalog=catalog)
            return {
                "success": True,
                "engine": "postgresql",
                "plan_kind": "measured_performance" if analyze else "estimated_plan",
                "text_tree": parsed.to_text_tree(),
                "summary": parsed.to_summary_dict(),
                "insights": [
                    {
                        "insight_id": i.insight_id,
                        "title": i.title,
                        "severity": i.severity,
                        "node_label": i.node_label,
                        "observation": i.observation,
                        "interpretation": i.interpretation,
                        "recommendation": i.recommendation,
                    }
                    for i in insights
                ],
                "client_duration_ms": res.client_duration_ms,
            }

        if self._active_engine == "duckdb":
            if self._duckdb_path is None:
                self._duckdb_path = ensure_demo_duckdb()
            duck_sql, notes, err = transpile_for_duckdb(sql, user_dialect)
            if err:
                return {"success": False, "error_message": err, "plan_kind": "estimated_plan"}
            t0 = time.perf_counter()
            con = duckdb.connect(str(self._duckdb_path), read_only=True)
            try:
                prefix = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
                rows = con.execute(f"{prefix} {duck_sql}").fetchall()
                plan_text = "\n".join(str(r[-1]) for r in rows)
                return {
                    "success": True,
                    "engine": "duckdb",
                    "plan_kind": "measured_performance" if analyze else "estimated_plan",
                    "text_tree": plan_text,
                    "client_duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                    "notes": notes,
                }
            except Exception as exc:
                return {
                    "success": False,
                    "error_message": sanitize_error_message(str(exc)),
                    "plan_kind": "measured_performance" if analyze else "estimated_plan",
                }
            finally:
                con.close()

        if self._active_engine == "sqlite" and self._live_req:
            p = Path(self._live_req.sqlite_path).resolve()
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            try:
                rows = con.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
                plan_text = "\n".join(" | ".join(str(x) for x in r) for r in rows)
                return {
                    "success": True,
                    "engine": "sqlite",
                    "plan_kind": "estimated_plan",
                    "text_tree": plan_text,
                    "notes": ["SQLite provides EXPLAIN QUERY PLAN (estimated plan only; no EXPLAIN ANALYZE timing)."],
                }
            except Exception as exc:
                return {"success": False, "error_message": sanitize_error_message(str(exc)), "plan_kind": "estimated_plan"}
            finally:
                con.close()

        if self._active_engine == "mysql" and self._live_req:
            req = self._live_req
            con = pymysql.connect(
                host=req.host,
                port=int(req.port or 3306),
                user=req.username,
                password=req.password,
                database=req.database,
                connect_timeout=5,
            )
            try:
                with con.cursor() as cur:
                    stmt = f"EXPLAIN ANALYZE {sql}" if analyze else f"EXPLAIN FORMAT=JSON {sql}"
                    cur.execute(stmt)
                    rows = cur.fetchall()
                    txt = "\n".join(str(r[0]) for r in rows)
                return {
                    "success": True,
                    "engine": "mysql",
                    "plan_kind": "measured_performance" if analyze else "estimated_plan",
                    "text_tree": txt,
                }
            except Exception as exc:
                return {
                    "success": False,
                    "error_message": sanitize_error_message(str(exc)),
                    "plan_kind": "measured_performance" if analyze else "estimated_plan",
                }
            finally:
                con.close()

        return {
            "success": False,
            "error_message": f"Execution plan inspection is unavailable for engine '{self._active_engine}'.",
            "plan_kind": "unavailable",
        }
