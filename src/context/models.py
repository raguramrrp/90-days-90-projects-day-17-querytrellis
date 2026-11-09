"""Canonical multi-dialect database context models.

Provides a dialect-neutral representation of tables, columns, primary/foreign
keys, constraints, indexes, sample rows, and connection safety posture used
across NL-to-SQL generation, debugging, optimization, and schema browsing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ColumnSchema:
    """Single column within a table or view."""

    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    default_value: str | None = None
    ordinal_position: int = 1
    sample_values: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "nullable": self.nullable,
            "is_primary_key": self.is_primary_key,
            "is_foreign_key": self.is_foreign_key,
            "default_value": self.default_value,
            "ordinal_position": self.ordinal_position,
            "sample_values": self.sample_values,
        }


@dataclass(slots=True)
class RelationshipSchema:
    """Explicit foreign-key relationship (never fabricated from column names alone)."""

    constraint_name: str
    source_table: str
    source_columns: list[str]
    target_table: str
    target_columns: list[str]
    verified: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_name": self.constraint_name,
            "source_table": self.source_table,
            "source_columns": self.source_columns,
            "target_table": self.target_table,
            "target_columns": self.target_columns,
            "verified": self.verified,
            "note": self.note,
        }


@dataclass(slots=True)
class ConstraintSchema:
    """Table constraint metadata (PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK)."""

    name: str
    table_name: str
    constraint_type: str
    definition: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "table_name": self.table_name,
            "constraint_type": self.constraint_type,
            "definition": self.definition,
        }


@dataclass(slots=True)
class IndexSchema:
    """Index metadata for an inspected table."""

    name: str
    table_name: str
    columns: list[str]
    is_unique: bool = False
    is_primary: bool = False
    predicate: str | None = None
    definition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "table_name": self.table_name,
            "columns": self.columns,
            "is_unique": self.is_unique,
            "is_primary": self.is_primary,
            "predicate": self.predicate,
            "definition": self.definition,
        }


@dataclass(slots=True)
class TableSchema:
    """Complete table or view metadata plus optional small sample-row preview."""

    name: str
    schema_name: str = "main"
    table_type: str = "BASE TABLE"
    row_count: int | None = None
    row_count_is_estimated: bool = False
    columns: list[ColumnSchema] = field(default_factory=list)
    indexes: list[IndexSchema] = field(default_factory=list)
    constraints: list[ConstraintSchema] = field(default_factory=list)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def get_column(self, col_name: str) -> ColumnSchema | None:
        target = col_name.lower().strip().strip('"').strip("`").strip("[]")
        for c in self.columns:
            if c.name.lower() == target:
                return c
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema_name": self.schema_name,
            "table_type": self.table_type,
            "row_count": self.row_count,
            "row_count_is_estimated": self.row_count_is_estimated,
            "columns": [c.to_dict() for c in self.columns],
            "indexes": [i.to_dict() for i in self.indexes],
            "constraints": [c.to_dict() for c in self.constraints],
            "sample_rows": self.sample_rows,
            "notes": self.notes,
        }


@dataclass(slots=True)
class DatabaseContextSnapshot:
    """Active database context shared across NL2SQL, Editor, Debugger, and Optimizer."""

    context_id: str
    label: str
    source_kind: str  # demo_duckdb | uploaded_sandbox | live_postgres | live_mysql | live_sqlite | live_mssql | schema_only
    engine: str  # duckdb | postgresql | mysql | sqlite | sqlserver | virtual
    dialect: str  # postgresql | mysql | sqlite | sqlserver
    read_only_default: bool = True
    allow_write_opt_in: bool = False
    can_execute: bool = True
    supports_explain: bool = True
    supports_explain_analyze: bool = True
    restricted_account_advisory: str = (
        "Connect using a least-privilege / read-only database user whenever analyzing "
        "production or staging systems."
    )
    tables: list[TableSchema] = field(default_factory=list)
    relationships: list[RelationshipSchema] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def find_table(self, name: str) -> TableSchema | None:
        target = name.lower().strip().strip('"').strip("`").strip("[]")
        for tbl in self.tables:
            if tbl.name.lower() == target:
                return tbl
        return None

    def all_table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def schema_prompt_summary(self, include_samples: bool = False) -> str:
        """Render an accurate, strictly factual schema description for prompts & UI."""
        lines: list[str] = [
            f"Target SQL Dialect: {self.dialect}",
            f"Source: {self.label} ({self.engine})",
            "Tables:",
        ]
        for tbl in self.tables:
            rc = f" (~{tbl.row_count:,} rows)" if tbl.row_count is not None else ""
            lines.append(f"- {tbl.name}{rc}:")
            for col in tbl.columns:
                flags: list[str] = []
                if col.is_primary_key:
                    flags.append("PK")
                if col.is_foreign_key:
                    flags.append("FK")
                if not col.nullable:
                    flags.append("NOT NULL")
                flag_txt = f" [{', '.join(flags)}]" if flags else ""
                lines.append(f"    * {col.name}: {col.data_type}{flag_txt}")
            if include_samples and tbl.sample_rows:
                lines.append(f"    Sample rows (max 2): {tbl.sample_rows[:2]}")
        if self.relationships:
            lines.append("Verified Foreign Key Relationships:")
            for rel in self.relationships:
                scols = ", ".join(rel.source_columns)
                tcols = ", ".join(rel.target_columns)
                lines.append(f"- {rel.source_table}({scols}) -> {rel.target_table}({tcols})")
        else:
            lines.append("Verified Foreign Key Relationships: None declared in this schema.")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "label": self.label,
            "source_kind": self.source_kind,
            "engine": self.engine,
            "dialect": self.dialect,
            "read_only_default": self.read_only_default,
            "allow_write_opt_in": self.allow_write_opt_in,
            "can_execute": self.can_execute,
            "supports_explain": self.supports_explain,
            "supports_explain_analyze": self.supports_explain_analyze,
            "restricted_account_advisory": self.restricted_account_advisory,
            "tables": [t.to_dict() for t in self.tables],
            "relationships": [r.to_dict() for r in self.relationships],
            "warnings": self.warnings,
            "notes": self.notes,
        }
