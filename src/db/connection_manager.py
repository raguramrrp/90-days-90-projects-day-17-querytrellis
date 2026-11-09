"""PostgreSQL connection lifecycle and catalog metadata introspection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.conninfo import make_conninfo

from src.config.settings import ConnectionConfig


def translate_pg_error(exc: Exception, config: ConnectionConfig | None = None) -> str:
    """Convert raw psycopg exceptions into helpful, credential-free diagnostics."""
    msg = str(exc).strip()
    lower = msg.lower()
    host_info = f"{config.host}:{config.port}" if config else "PostgreSQL server"
    db_info = config.database if config else "target database"

    if "password authentication failed" in lower or "fe_sendauth" in lower or "no password supplied" in lower:
        return (
            f"Authentication failed for user '{config.username if config else 'unknown'}' "
            f"on {host_info}. Verify your username and password in Settings or .env."
        )
    if "does not exist" in lower and "database" in lower:
        return (
            f"Database '{db_info}' does not exist on {host_info}. "
            "Run scripts/setup_sample_db.py or switch to an existing database."
        )
    if "connection refused" in lower or "could not connect" in lower or "no response" in lower:
        return (
            f"Cannot reach PostgreSQL at {host_info}. Confirm the PostgreSQL service is running "
            "and listening on the configured host and port."
        )
    if "timeout expired" in lower or "timed out" in lower:
        return (
            f"Connection to {host_info} timed out. Check network connectivity, firewall rules, "
            "or increase the connect timeout."
        )
    if "statement timeout" in lower or "canceling statement due to statement timeout" in lower:
        return (
            "Query exceeded the configured statement timeout and was safely canceled by PostgreSQL. "
            "Consider adding filters, indexes, or increasing the timeout in Settings."
        )
    if "read-only transaction" in lower:
        return "Blocked write or schema-modifying operation inside QueryTrellis read-only transaction."
    if "permission denied" in lower:
        return f"PostgreSQL permission denied: {msg.splitlines()[0]}"

    # Sanitize potential DSN leaks just in case
    first_line = msg.splitlines()[0] if msg else "Unknown database error."
    return first_line


@dataclass(slots=True)
class ColumnMetadata:
    """Column metadata for a PostgreSQL table or view."""

    table_schema: str
    table_name: str
    column_name: str
    data_type: str
    is_nullable: bool
    ordinal_position: int
    column_default: str | None = None


@dataclass(slots=True)
class IndexMetadata:
    """Detailed PostgreSQL index metadata from pg_catalog."""

    schema_name: str
    table_name: str
    index_name: str
    access_method: str
    key_columns: list[str]
    include_columns: list[str]
    is_unique: bool
    is_primary: bool
    predicate: str | None
    definition: str
    size_bytes: int = 0
    idx_scan: int = 0


@dataclass(slots=True)
class ForeignKeyMetadata:
    """Foreign key constraint metadata."""

    schema_name: str
    table_name: str
    constraint_name: str
    columns: list[str]
    referenced_schema: str
    referenced_table: str
    referenced_columns: list[str]


@dataclass(slots=True)
class TableMetadata:
    """PostgreSQL table or view metadata and planner statistics."""

    schema_name: str
    table_name: str
    table_type: str  # "BASE TABLE" | "VIEW" | "MATERIALIZED VIEW"
    estimated_rows: int
    total_size_bytes: int
    table_size_bytes: int
    index_size_bytes: int
    seq_scan: int = 0
    idx_scan: int = 0
    columns: list[ColumnMetadata] = field(default_factory=list)
    indexes: list[IndexMetadata] = field(default_factory=list)
    foreign_keys: list[ForeignKeyMetadata] = field(default_factory=list)


@dataclass(slots=True)
class DatabaseCatalog:
    """Complete schema, table, column, and index snapshot for a PostgreSQL database."""

    database_name: str
    server_version: str
    server_version_num: int
    schemas: list[str] = field(default_factory=list)
    tables: list[TableMetadata] = field(default_factory=list)

    def find_table(self, name: str, schema: str | None = None) -> TableMetadata | None:
        """Look up a table case-insensitively by table name and optional schema."""
        target = name.lower().strip('"')
        target_schema = schema.lower().strip('"') if schema else None
        candidates = [
            t
            for t in self.tables
            if t.table_name.lower() == target
            and (target_schema is None or t.schema_name.lower() == target_schema)
        ]
        if not candidates:
            return None
        for c in candidates:
            if c.schema_name == "public":
                return c
        return candidates[0]

    def total_indexes(self) -> int:
        """Return total number of indexes across inspected tables."""
        return sum(len(t.indexes) for t in self.tables)

    def get_column_type(self, table_name: str, column_name: str, schema: str | None = None) -> str | None:
        """Return PostgreSQL data type for a column if known."""
        tbl = self.find_table(table_name, schema=schema)
        if not tbl:
            return None
        col_low = column_name.lower().strip('"')
        for col in tbl.columns:
            if col.column_name.lower() == col_low:
                return col.data_type
        return None


@dataclass(slots=True)
class ConnectionStatus:
    """Result of a connection attempt or active connection status."""

    connected: bool
    config: ConnectionConfig
    server_version: str = ""
    server_version_num: int = 0
    current_database: str = ""
    current_user: str = ""
    available_databases: list[str] = field(default_factory=list)
    available_schemas: list[str] = field(default_factory=list)
    error_message: str = ""


def build_conninfo(config: ConnectionConfig) -> str:
    """Construct a psycopg conninfo string safely without logging secrets."""
    params: dict[str, Any] = {
        "host": config.host,
        "port": config.port,
        "dbname": config.database,
        "user": config.username,
        "sslmode": config.sslmode,
        "connect_timeout": config.connect_timeout,
        "application_name": "QueryTrellis",
    }
    if config.password:
        params["password"] = config.password
    return make_conninfo(**params)


class ConnectionManager:
    """Manages PostgreSQL connections, database switching, and catalog inspection."""

    def __init__(self, config: ConnectionConfig | None = None) -> None:
        self._config: ConnectionConfig = config or ConnectionConfig()
        self._conn: psycopg.Connection[Any] | None = None
        self._status: ConnectionStatus = ConnectionStatus(connected=False, config=self._config)
        self._catalog_cache: DatabaseCatalog | None = None

    @property
    def config(self) -> ConnectionConfig:
        """Return the current connection configuration."""
        return self._config

    @property
    def status(self) -> ConnectionStatus:
        """Return current connection status."""
        if self._conn is not None and self._conn.closed:
            self._status.connected = False
            self._conn = None
        return self._status

    @property
    def is_connected(self) -> bool:
        """Whether an active PostgreSQL connection is open."""
        return self._conn is not None and not self._conn.closed and self._status.connected

    def get_connection(self) -> psycopg.Connection[Any]:
        """Return the active psycopg connection or raise a clear RuntimeError."""
        if not self.is_connected or self._conn is None:
            raise RuntimeError("No active PostgreSQL connection. Connect via Settings first.")
        # Quick health check and recover cleanly if transaction was left aborted
        if self._conn.info.transaction_status == psycopg.pq.TransactionStatus.INERROR:
            self._conn.rollback()
        return self._conn

    @staticmethod
    def test_connection(config: ConnectionConfig) -> ConnectionStatus:
        """Open a short-lived connection to verify credentials and gather server info."""
        conninfo = build_conninfo(config)
        try:
            with psycopg.connect(conninfo, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT version(), current_setting('server_version_num')::int, "
                        "current_database(), current_user"
                    )
                    row = cur.fetchone()
                    version_str, version_num, db_name, user_name = row  # type: ignore[misc]

                    cur.execute(
                        "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
                    )
                    databases = [r[0] for r in cur.fetchall()]

                    cur.execute(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema' "
                        "ORDER BY schema_name"
                    )
                    schemas = [r[0] for r in cur.fetchall()]

            return ConnectionStatus(
                connected=True,
                config=config,
                server_version=str(version_str),
                server_version_num=int(version_num),
                current_database=str(db_name),
                current_user=str(user_name),
                available_databases=databases,
                available_schemas=schemas,
            )
        except Exception as exc:
            return ConnectionStatus(
                connected=False,
                config=config,
                error_message=translate_pg_error(exc, config),
            )

    def connect(self, config: ConnectionConfig | None = None) -> ConnectionStatus:
        """Establish and store an active PostgreSQL connection."""
        target_config = config or self._config
        self.disconnect()
        conninfo = build_conninfo(target_config)
        try:
            conn = psycopg.connect(conninfo, autocommit=False)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT version(), current_setting('server_version_num')::int, "
                    "current_database(), current_user"
                )
                version_str, version_num, db_name, user_name = cur.fetchone()  # type: ignore[misc]
                cur.execute(
                    "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
                )
                databases = [r[0] for r in cur.fetchall()]
                cur.execute(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema' "
                    "ORDER BY schema_name"
                )
                schemas = [r[0] for r in cur.fetchall()]
            conn.rollback()

            self._config = target_config
            self._conn = conn
            self._catalog_cache = None
            self._status = ConnectionStatus(
                connected=True,
                config=target_config,
                server_version=str(version_str),
                server_version_num=int(version_num),
                current_database=str(db_name),
                current_user=str(user_name),
                available_databases=databases,
                available_schemas=schemas,
            )
            return self._status
        except Exception as exc:
            self._config = target_config
            self._conn = None
            self._catalog_cache = None
            self._status = ConnectionStatus(
                connected=False,
                config=target_config,
                error_message=translate_pg_error(exc, target_config),
            )
            return self._status

    def disconnect(self) -> None:
        """Close the active PostgreSQL connection if open."""
        if self._conn is not None:
            try:
                if not self._conn.closed:
                    self._conn.close()
            except Exception:
                pass
        self._conn = None
        self._catalog_cache = None
        self._status = ConnectionStatus(connected=False, config=self._config)

    def switch_database(self, database_name: str) -> ConnectionStatus:
        """Reconnect to another database on the same PostgreSQL server."""
        new_cfg = ConnectionConfig(
            host=self._config.host,
            port=self._config.port,
            database=database_name,
            username=self._config.username,
            password=self._config.password,
            sslmode=self._config.sslmode,
            connect_timeout=self._config.connect_timeout,
        )
        return self.connect(new_cfg)

    def fetch_catalog(self, force_refresh: bool = False, include_system: bool = False) -> DatabaseCatalog:
        """Inspect schemas, tables, columns, indexes, and foreign keys for the active database."""
        if self._catalog_cache is not None and not force_refresh:
            return self._catalog_cache

        conn = self.get_connection()
        schema_clause = (
            ""
            if include_system
            else "AND n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'"
        )

        tables_map: dict[tuple[str, str], TableMetadata] = {}
        try:
            with conn.cursor() as cur:
                # 1. Schemas
                if include_system:
                    cur.execute("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name")
                else:
                    cur.execute(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema' "
                        "ORDER BY schema_name"
                    )
                schemas = [r[0] for r in cur.fetchall()]

                # 2. Tables, views, materialized views + pg_stat_user_tables metrics
                cur.execute(
                    f"""
                    SELECT
                        n.nspname AS schema_name,
                        c.relname AS table_name,
                        CASE c.relkind
                            WHEN 'r' THEN 'BASE TABLE'
                            WHEN 'p' THEN 'PARTITIONED TABLE'
                            WHEN 'v' THEN 'VIEW'
                            WHEN 'm' THEN 'MATERIALIZED VIEW'
                            ELSE c.relkind::text
                        END AS table_type,
                        GREATEST(c.reltuples::bigint, 0) AS estimated_rows,
                        pg_total_relation_size(c.oid) AS total_size_bytes,
                        pg_relation_size(c.oid) AS table_size_bytes,
                        pg_indexes_size(c.oid) AS index_size_bytes,
                        COALESCE(s.seq_scan, 0) AS seq_scan,
                        COALESCE(s.idx_scan, 0) AS idx_scan
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                    WHERE c.relkind IN ('r', 'p', 'v', 'm')
                    {schema_clause}
                    ORDER BY n.nspname, c.relname
                    """
                )
                for row in cur.fetchall():
                    tmeta = TableMetadata(
                        schema_name=row[0],
                        table_name=row[1],
                        table_type=row[2],
                        estimated_rows=int(row[3] or 0),
                        total_size_bytes=int(row[4] or 0),
                        table_size_bytes=int(row[5] or 0),
                        index_size_bytes=int(row[6] or 0),
                        seq_scan=int(row[7] or 0),
                        idx_scan=int(row[8] or 0),
                    )
                    tables_map[(tmeta.schema_name, tmeta.table_name)] = tmeta

                # 3. Columns
                cur.execute(
                    f"""
                    SELECT
                        n.nspname AS table_schema,
                        c.relname AS table_name,
                        a.attname AS column_name,
                        pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                        NOT a.attnotnull AS is_nullable,
                        a.attnum AS ordinal_position,
                        pg_get_expr(ad.adbin, ad.adrelid) AS column_default
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
                    WHERE c.relkind IN ('r', 'p', 'v', 'm')
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                      {schema_clause}
                    ORDER BY n.nspname, c.relname, a.attnum
                    """
                )
                for row in cur.fetchall():
                    key = (row[0], row[1])
                    if key in tables_map:
                        tables_map[key].columns.append(
                            ColumnMetadata(
                                table_schema=row[0],
                                table_name=row[1],
                                column_name=row[2],
                                data_type=row[3],
                                is_nullable=bool(row[4]),
                                ordinal_position=int(row[5]),
                                column_default=row[6],
                            )
                        )

                # 4. Indexes (ordered key columns + INCLUDE columns + predicate)
                cur.execute(
                    f"""
                    SELECT
                        n.nspname AS schema_name,
                        t.relname AS table_name,
                        i.relname AS index_name,
                        am.amname AS access_method,
                        ARRAY(
                            SELECT COALESCE(a.attname, '<expr>')
                            FROM unnest(ix.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord)
                            LEFT JOIN pg_attribute a
                              ON a.attrelid = t.oid AND a.attnum = k.attnum
                            WHERE k.ord <= ix.indnkeyatts
                            ORDER BY k.ord
                        ) AS key_columns,
                        ARRAY(
                            SELECT COALESCE(a.attname, '<expr>')
                            FROM unnest(ix.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord)
                            LEFT JOIN pg_attribute a
                              ON a.attrelid = t.oid AND a.attnum = k.attnum
                            WHERE k.ord > ix.indnkeyatts
                            ORDER BY k.ord
                        ) AS include_columns,
                        ix.indisunique,
                        ix.indisprimary,
                        pg_get_expr(ix.indpred, ix.indrelid) AS predicate,
                        pg_get_indexdef(i.oid) AS definition,
                        pg_relation_size(i.oid) AS size_bytes,
                        COALESCE(si.idx_scan, 0) AS idx_scan
                    FROM pg_index ix
                    JOIN pg_class t ON t.oid = ix.indrelid
                    JOIN pg_class i ON i.oid = ix.indexrelid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    JOIN pg_am am ON am.oid = i.relam
                    LEFT JOIN pg_stat_user_indexes si ON si.indexrelid = i.oid
                    WHERE t.relkind IN ('r', 'p', 'm')
                    {schema_clause}
                    ORDER BY n.nspname, t.relname, i.relname
                    """
                )
                for row in cur.fetchall():
                    key = (row[0], row[1])
                    if key in tables_map:
                        tables_map[key].indexes.append(
                            IndexMetadata(
                                schema_name=row[0],
                                table_name=row[1],
                                index_name=row[2],
                                access_method=row[3],
                                key_columns=list(row[4] or []),
                                include_columns=list(row[5] or []),
                                is_unique=bool(row[6]),
                                is_primary=bool(row[7]),
                                predicate=row[8],
                                definition=row[9],
                                size_bytes=int(row[10] or 0),
                                idx_scan=int(row[11] or 0),
                            )
                        )

                # 5. Foreign keys
                cur.execute(
                    f"""
                    SELECT
                        n.nspname AS schema_name,
                        t.relname AS table_name,
                        con.conname AS constraint_name,
                        ARRAY(
                            SELECT a.attname
                            FROM unnest(con.conkey) WITH ORDINALITY AS c(attnum, ord)
                            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.attnum
                            ORDER BY c.ord
                        ) AS columns,
                        rn.nspname AS ref_schema,
                        rt.relname AS ref_table,
                        ARRAY(
                            SELECT a.attname
                            FROM unnest(con.confkey) WITH ORDINALITY AS c(attnum, ord)
                            JOIN pg_attribute a ON a.attrelid = rt.oid AND a.attnum = c.attnum
                            ORDER BY c.ord
                        ) AS ref_columns
                    FROM pg_constraint con
                    JOIN pg_class t ON t.oid = con.conrelid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    JOIN pg_class rt ON rt.oid = con.confrelid
                    JOIN pg_namespace rn ON rn.oid = rt.relnamespace
                    WHERE con.contype = 'f'
                    {schema_clause}
                    ORDER BY n.nspname, t.relname, con.conname
                    """
                )
                for row in cur.fetchall():
                    key = (row[0], row[1])
                    if key in tables_map:
                        tables_map[key].foreign_keys.append(
                            ForeignKeyMetadata(
                                schema_name=row[0],
                                table_name=row[1],
                                constraint_name=row[2],
                                columns=list(row[3] or []),
                                referenced_schema=row[4],
                                referenced_table=row[5],
                                referenced_columns=list(row[6] or []),
                            )
                        )
            conn.rollback()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

        catalog = DatabaseCatalog(
            database_name=self._status.current_database or self._config.database,
            server_version=self._status.server_version,
            server_version_num=self._status.server_version_num,
            schemas=schemas,
            tables=list(tables_map.values()),
        )
        self._catalog_cache = catalog
        return catalog
