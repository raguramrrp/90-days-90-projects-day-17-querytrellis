"""Complete SQL Debugging Assistant with schema verification and safe candidate testing."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from src.connectors.adapters import MultiDBConnector
from src.context.models import DatabaseContextSnapshot
from src.db.connection_manager import (
    ColumnMetadata,
    DatabaseCatalog,
    ForeignKeyMetadata,
    IndexMetadata,
    TableMetadata,
)
from src.dialects.sqlglot_engine import parse_sql_ast, to_sqlglot_read_write
from src.sql_analysis.antipattern_detector import detect_antipatterns
from src.sql_analysis.parser_validator import validate_read_only_sql


@dataclass(slots=True)
class DebugDiagnostic:
    """Single confirmed error, logical warning, or advisory anti-pattern finding."""

    code: str
    category: str  # confirmed_error | logical_warning | performance_warning
    severity: str  # Error | High | Medium | Low
    title: str
    message: str
    line: int | None = None
    column: int | None = None
    fragment: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "fragment": self.fragment,
            "suggestion": self.suggestion,
        }


@dataclass(slots=True)
class DebugFixCandidate:
    """Proposed corrected SQL alternative with safe verification status and explanation."""

    fix_id: str
    title: str
    kind: str  # confirmed_error_fix | logical_improvement
    corrected_sql: str
    explanation: str
    tested: bool = False
    test_passed: bool | None = None
    test_rows: int | None = None
    test_duration_ms: float | None = None
    test_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fix_id": self.fix_id,
            "title": self.title,
            "kind": self.kind,
            "corrected_sql": self.corrected_sql,
            "explanation": self.explanation,
            "tested": self.tested,
            "test_passed": self.test_passed,
            "test_rows": self.test_rows,
            "test_duration_ms": self.test_duration_ms,
            "test_error": self.test_error,
        }


def context_to_pg_catalog(ctx: DatabaseContextSnapshot) -> DatabaseCatalog:
    """Bridge canonical DatabaseContextSnapshot into existing QueryTrellis DatabaseCatalog."""
    tbls: list[TableMetadata] = []
    for t in ctx.tables:
        cols = [
            ColumnMetadata(
                table_schema=t.schema_name,
                table_name=t.name,
                column_name=c.name,
                data_type=c.data_type,
                is_nullable=c.nullable,
                ordinal_position=c.ordinal_position,
                column_default=c.default_value,
            )
            for c in t.columns
        ]
        idxs = [
            IndexMetadata(
                schema_name=t.schema_name,
                table_name=t.name,
                index_name=i.name,
                access_method="btree",
                key_columns=i.columns,
                include_columns=[],
                is_unique=i.is_unique,
                is_primary=i.is_primary,
                predicate=i.predicate,
                definition=i.definition,
            )
            for i in t.indexes
        ]
        fks = [
            ForeignKeyMetadata(
                schema_name=t.schema_name,
                table_name=t.name,
                constraint_name=r.constraint_name,
                columns=r.source_columns,
                referenced_schema=t.schema_name,
                referenced_table=r.target_table,
                referenced_columns=r.target_columns,
            )
            for r in ctx.relationships
            if r.source_table.lower() == t.name.lower()
        ]
        tbls.append(
            TableMetadata(
                schema_name=t.schema_name,
                table_name=t.name,
                table_type=t.table_type,
                estimated_rows=t.row_count or 0,
                total_size_bytes=0,
                table_size_bytes=0,
                index_size_bytes=0,
                columns=cols,
                indexes=idxs,
                foreign_keys=fks,
            )
        )
    return DatabaseCatalog(
        database_name=ctx.label,
        server_version=ctx.engine,
        server_version_num=160000,
        schemas=["main", "public"],
        tables=tbls,
    )


def _find_fragment_line(sql: str, token: str) -> int | None:
    if not token:
        return None
    low_tok = token.lower()
    for idx, line in enumerate(sql.splitlines(), start=1):
        if low_tok in line.lower():
            return idx
    return None


def _is_num_type(dtype: str) -> bool:
    low = dtype.lower()
    return any(k in low for k in ("int", "double", "float", "numeric", "decimal", "real", "bigint", "smallint"))


def _is_date_type(dtype: str) -> bool:
    low = dtype.lower()
    return "date" in low or "timestamp" in low or "time" in low


def _is_bool_type(dtype: str) -> bool:
    return "bool" in dtype.lower()


def _attempt_syntax_repairs(sql: str, dialect: str) -> list[tuple[str, str]]:
    """Heuristic syntax cleanups checked strictly by parser + execution afterward."""
    repairs: list[tuple[str, str]] = []
    # 1. Trailing comma before FROM / WHERE / GROUP BY / ORDER BY / LIMIT
    cleaned = re.sub(r",\s*(FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT)\b", r"\n\1", sql, flags=re.IGNORECASE)
    if cleaned != sql and parse_sql_ast(cleaned, dialect).is_valid:
        repairs.append(("Removed trailing comma before SQL clause keyword", cleaned))

    # 2. Missing equals or common typo 'SELCT' / 'FORM' / 'WHER'
    typo_fixed = sql
    for bad, good in ((r"\bSELCT\b", "SELECT"), (r"\bFORM\b", "FROM"), (r"\bWHER\b", "WHERE"), (r"\bGROPU\b", "GROUP"), (r"\bODRER\b", "ORDER")):
        typo_fixed = re.sub(bad, good, typo_fixed, flags=re.IGNORECASE)
    if typo_fixed != sql and parse_sql_ast(typo_fixed, dialect).is_valid:
        repairs.append(("Fixed misspelled SQL keyword", typo_fixed))

    # 3. Unbalanced parentheses at end
    if sql.count("(") > sql.count(")"):
        cand = sql.rstrip().rstrip(";") + (")" * (sql.count("(") - sql.count(")"))) + (";" if sql.rstrip().endswith(";") else "")
        if parse_sql_ast(cand, dialect).is_valid:
            repairs.append(("Closed unclosed parenthesis", cand))

    return repairs


def analyze_and_debug_sql(
    sql: str,
    context: DatabaseContextSnapshot,
    *,
    dialect: str | None = None,
    connector: MultiDBConnector | None = None,
    captured_error: str | None = None,
    test_fixes: bool = True,
) -> dict[str, Any]:
    """Perform deep static, schema, logical, and execution-verified SQL debugging."""
    d = dialect or context.dialect
    sg_dialect = to_sqlglot_read_write(d)
    raw_sql = (sql or "").strip()
    diagnostics: list[DebugDiagnostic] = []
    candidates: list[DebugFixCandidate] = []

    if not raw_sql:
        return {
            "dialect": d,
            "has_errors": True,
            "diagnostics": [
                DebugDiagnostic(
                    code="DBG000",
                    category="confirmed_error",
                    severity="Error",
                    title="Empty SQL Input",
                    message="Enter or paste a SQL query to debug.",
                ).to_dict()
            ],
            "fix_candidates": [],
        }

    # If user didn't pass an error yet and connector can run read-only check, probe live execution if SELECT
    live_exec_error = captured_error or ""
    parsed = parse_sql_ast(raw_sql, d)

    if not parsed.is_valid or parsed.root is None:
        diagnostics.append(
            DebugDiagnostic(
                code="DBG_SYNTAX",
                category="confirmed_error",
                severity="Error",
                title="SQL Syntax Error",
                message=parsed.error_message or "SQL failed to parse.",
                line=parsed.error_line or 1,
                column=parsed.error_column,
                suggestion="Check missing commas, unmatched quotes/parentheses, or misspelled SQL keywords near the highlighted line.",
            )
        )
        for idx, (desc, fixed_sql) in enumerate(_attempt_syntax_repairs(raw_sql, d), start=1):
            candidates.append(
                DebugFixCandidate(
                    fix_id=f"FIX_SYNTAX_{idx}",
                    title=desc,
                    kind="confirmed_error_fix",
                    corrected_sql=fixed_sql,
                    explanation=f"{desc} and re-validated syntax with SQLGlot ({d}).",
                )
            )
    else:
        root = parsed.root
        if live_exec_error:
            err_line = _find_fragment_line(raw_sql, "") or None
            m_line = re.search(r"line\s+(\d+)", live_exec_error, re.IGNORECASE)
            if m_line:
                err_line = int(m_line.group(1))
            diagnostics.append(
                DebugDiagnostic(
                    code="DBG_RUNTIME",
                    category="confirmed_error",
                    severity="Error",
                    title="Captured Database Execution Error",
                    message=live_exec_error,
                    line=err_line,
                )
            )

        # Schema-aware inspection
        cte_names = {c.alias_or_name.lower() for c in root.find_all(exp.CTE) if c.alias_or_name}
        sub_aliases = {s.alias.lower() for s in root.find_all(exp.Subquery) if s.alias}
        alias_to_tbl: dict[str, str] = {}
        referenced_tables: list[str] = []
        table_names_all = context.all_table_names()

        working_sql_for_missing_fixes = raw_sql
        table_renames: dict[str, str] = {}
        col_renames: dict[str, str] = {}
        ambiguous_qualifies: list[tuple[str, str]] = []

        for tbl_node in root.find_all(exp.Table):
            tname = tbl_node.name
            if not tname or tname.lower() in cte_names or tname.lower() in sub_aliases:
                continue
            tschema = context.find_table(tname)
            if tschema is None:
                close = difflib.get_close_matches(tname.lower(), [t.lower() for t in table_names_all], n=2, cutoff=0.55)
                matched_real = next((t for t in table_names_all if close and t.lower() == close[0]), None)
                diagnostics.append(
                    DebugDiagnostic(
                        code="DBG_MISSING_TABLE",
                        category="confirmed_error",
                        severity="Error",
                        title=f"Missing Table '{tname}'",
                        message=(
                            f"Table '{tname}' does not exist in active schema."
                            + (f" Did you mean '{matched_real}'?" if matched_real else f" Available: {', '.join(table_names_all)}")
                        ),
                        line=_find_fragment_line(raw_sql, tname),
                        fragment=tname,
                        suggestion=f"Replace '{tname}' with '{matched_real}'." if matched_real else "Select a valid table from Schema Explorer.",
                    )
                )
                if matched_real:
                    table_renames[tname] = matched_real
            else:
                if tschema.name not in referenced_tables:
                    referenced_tables.append(tschema.name)
                alias_to_tbl[tname.lower()] = tschema.name
                if tbl_node.alias:
                    alias_to_tbl[tbl_node.alias.lower()] = tschema.name

        # Build column map across all referenced tables
        select_aliases = {al.alias.lower() for al in root.find_all(exp.Alias) if al.alias}
        for col_node in root.find_all(exp.Column):
            cname = col_node.name
            if not cname or cname == "*":
                continue
            qual = (col_node.table or "").lower()
            if qual in cte_names or qual in sub_aliases:
                continue

            if qual:
                if qual not in alias_to_tbl:
                    # Unknown qualifier
                    close_q = difflib.get_close_matches(qual, list(alias_to_tbl.keys()), n=1, cutoff=0.6)
                    diagnostics.append(
                        DebugDiagnostic(
                            code="DBG_UNKNOWN_ALIAS",
                            category="confirmed_error",
                            severity="Error",
                            title=f"Unrecognized Table Alias '{col_node.table}'",
                            message=f"Column '{col_node.table}.{cname}' references alias or table '{col_node.table}' not in FROM/JOIN.",
                            line=_find_fragment_line(raw_sql, f"{col_node.table}.{cname}"),
                            fragment=f"{col_node.table}.{cname}",
                            suggestion=(f"Use '{close_q[0]}.{cname}' instead." if close_q else "Verify FROM and JOIN aliases."),
                        )
                    )
                else:
                    real_t = context.find_table(alias_to_tbl[qual])
                    if real_t and real_t.get_column(cname) is None:
                        all_cols_on_t = real_t.column_names()
                        close_c = difflib.get_close_matches(cname.lower(), [c.lower() for c in all_cols_on_t], n=2, cutoff=0.55)
                        sug_c = next((c for c in all_cols_on_t if close_c and c.lower() == close_c[0]), None)
                        other_hits = [
                            t.name for t in context.tables if t.name != real_t.name and t.get_column(cname) is not None
                        ]
                        hint_msg = f" Did you mean '{sug_c}'?" if sug_c else ""
                        if not sug_c and other_hits:
                            hint_msg = f" Note: column '{cname}' exists on table(s): {', '.join(other_hits)}."
                        diagnostics.append(
                            DebugDiagnostic(
                                code="DBG_MISSING_COLUMN",
                                category="confirmed_error",
                                severity="Error",
                                title=f"Missing Column '{col_node.table}.{cname}'",
                                message=f"Table '{real_t.name}' has no column named '{cname}'.{hint_msg}",
                                line=_find_fragment_line(raw_sql, cname),
                                fragment=f"{col_node.table}.{cname}",
                                suggestion=f"Replace '{cname}' with '{sug_c}'." if sug_c else "Check table columns in Schema Explorer.",
                            )
                        )
                        if sug_c:
                            col_renames[cname] = sug_c
            else:
                if cname.lower() in select_aliases or cte_names:
                    continue
                owners = [
                    tname
                    for tname in referenced_tables
                    if (ts := context.find_table(tname)) is not None and ts.get_column(cname) is not None
                ]
                if not owners and referenced_tables:
                    cand_pool = [
                        c.name
                        for tname in referenced_tables
                        if (ts := context.find_table(tname)) is not None
                        for c in ts.columns
                    ]
                    close_c = difflib.get_close_matches(cname.lower(), [c.lower() for c in cand_pool], n=1, cutoff=0.55)
                    sug_c = next((c for c in cand_pool if close_c and c.lower() == close_c[0]), None)
                    other_tbls = [t.name for t in context.tables if t.get_column(cname) is not None]
                    extra = (
                        f" Did you mean '{sug_c}'?"
                        if sug_c
                        else (f" Found '{cname}' on {', '.join(other_tbls)}." if other_tbls else "")
                    )
                    diagnostics.append(
                        DebugDiagnostic(
                            code="DBG_MISSING_COLUMN",
                            category="confirmed_error",
                            severity="Error",
                            title=f"Missing Column '{cname}'",
                            message=f"Column '{cname}' was not found in {', '.join(referenced_tables)}.{extra}",
                            line=_find_fragment_line(raw_sql, cname),
                            fragment=cname,
                            suggestion=f"Use '{sug_c}'." if sug_c else "Verify column name against active schema.",
                        )
                    )
                    if sug_c:
                        col_renames[cname] = sug_c
                elif len(owners) > 1 and not isinstance(col_node.parent, exp.Order):
                    # Ambiguous unqualified column across multiple joined tables
                    # Pick canonical alias/table matching owner[0]
                    first_owner = owners[0]
                    first_alias = next(
                        (k for k, v in alias_to_tbl.items() if v.lower() == first_owner.lower() and k != first_owner.lower()),
                        first_owner,
                    )
                    ambiguous_qualifies.append((cname, f"{first_alias}.{cname}"))
                    diagnostics.append(
                        DebugDiagnostic(
                            code="DBG_AMBIGUOUS_COLUMN",
                            category="confirmed_error",
                            severity="Error",
                            title=f"Ambiguous Column '{cname}'",
                            message=f"Column '{cname}' exists in multiple referenced tables ({', '.join(owners)}) without a table qualifier.",
                            line=_find_fragment_line(raw_sql, cname),
                            fragment=cname,
                            suggestion=f"Qualify unambiguously, e.g. '{first_alias}.{cname}'.",
                        )
                    )

        # Datatype mismatch checks on binary comparisons
        for comp in root.find_all((exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
            left, right = comp.left, comp.right
            col_part, lit_part = (left, right) if isinstance(left, exp.Column) else ((right, left) if isinstance(right, exp.Column) else (None, None))
            if isinstance(col_part, exp.Column) and isinstance(lit_part, exp.Literal):
                t_key = alias_to_tbl.get((col_part.table or "").lower()) if col_part.table else (referenced_tables[0] if len(referenced_tables) == 1 else None)
                if t_key and (ts := context.find_table(t_key)) and (cdef := ts.get_column(col_part.name)):
                    if _is_num_type(cdef.data_type) and lit_part.is_string and not re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", str(lit_part.this)):
                        diagnostics.append(
                            DebugDiagnostic(
                                code="DBG_DATATYPE",
                                category="confirmed_error",
                                severity="Error",
                                title=f"Datatype Conflict on '{ts.name}.{cdef.name}'",
                                message=f"Numeric column '{cdef.name}' ({cdef.data_type}) is compared with non-numeric string literal '{lit_part.this}'.",
                                line=_find_fragment_line(raw_sql, comp.sql(dialect=sg_dialect)),
                                fragment=comp.sql(dialect=sg_dialect),
                                suggestion="Provide a valid numeric value or fix the column being filtered.",
                            )
                        )
                    elif _is_date_type(cdef.data_type) and not lit_part.is_string:
                        diagnostics.append(
                            DebugDiagnostic(
                                code="DBG_DATATYPE_DATE",
                                category="confirmed_error",
                                severity="Error",
                                title=f"Date Comparison Type Conflict on '{cdef.name}'",
                                message=f"Temporal column '{cdef.name}' ({cdef.data_type}) is compared against an unquoted numeric literal '{lit_part.this}'.",
                                line=_find_fragment_line(raw_sql, comp.sql(dialect=sg_dialect)),
                                fragment=comp.sql(dialect=sg_dialect),
                                suggestion=f"Use a quoted ISO date string (e.g. '2026-01-01') or EXTRACT(YEAR FROM {cdef.name}).",
                            )
                        )
                    elif _is_bool_type(cdef.data_type) and lit_part.is_string and str(lit_part.this).lower() not in {"true", "false"}:
                        diagnostics.append(
                            DebugDiagnostic(
                                code="DBG_DATATYPE_BOOL",
                                category="confirmed_error",
                                severity="Error",
                                title=f"Boolean Comparison Conflict on '{cdef.name}'",
                                message=f"Boolean column '{cdef.name}' is compared with '{lit_part.this}'.",
                                line=_find_fragment_line(raw_sql, comp.sql(dialect=sg_dialect)),
                                fragment=comp.sql(dialect=sg_dialect),
                                suggestion=f"Compare boolean columns directly (`{cdef.name} = TRUE`).",
                            )
                        )

        # Logical checks: NULL equality (= NULL / <> NULL), GROUP BY mismatch, HAVING without GROUP BY
        null_eq_fixes: list[tuple[str, str]] = []
        for eq in root.find_all((exp.EQ, exp.NEQ)):
            if isinstance(eq.right, exp.Null) or isinstance(eq.left, exp.Null):
                frag = eq.sql(dialect=sg_dialect)
                is_neq = isinstance(eq, exp.NEQ)
                col_sql = (eq.left if isinstance(eq.right, exp.Null) else eq.right).sql(dialect=sg_dialect)
                fixed_frag = f"{col_sql} {'IS NOT NULL' if is_neq else 'IS NULL'}"
                null_eq_fixes.append((frag, fixed_frag))
                diagnostics.append(
                    DebugDiagnostic(
                        code="DBG_LOGIC_NULL",
                        category="logical_warning",
                        severity="High",
                        title="Null Comparison Using '=' or '<>'",
                        message=f"In SQL three-valued logic, `{frag}` always evaluates to UNKNOWN (never true).",
                        line=_find_fragment_line(raw_sql, "NULL"),
                        fragment=frag,
                        suggestion=f"Rewrite as `{fixed_frag}`.",
                    )
                )

        # GROUP BY validation on Select nodes
        missing_group_by_cols: list[str] = []
        for sel in root.find_all(exp.Select):
            has_agg = any(
                not any(isinstance(anc, exp.Window) for anc in agg.walk())
                and not isinstance(agg.parent, exp.Window)
                for agg in sel.find_all(exp.AggFunc)
            )
            grp_node = sel.args.get("group")
            having_node = sel.args.get("having")
            if having_node and not grp_node and not has_agg:
                diagnostics.append(
                    DebugDiagnostic(
                        code="DBG_LOGIC_HAVING",
                        category="logical_warning",
                        severity="High",
                        title="HAVING Without GROUP BY or Aggregation",
                        message="HAVING filters post-aggregation groups, but query has neither GROUP BY nor aggregate expressions.",
                        line=_find_fragment_line(raw_sql, "HAVING"),
                        suggestion="Use WHERE for row-level filtering or add GROUP BY.",
                    )
                )
            if has_agg:
                grp_cols = {g.sql(dialect=sg_dialect).lower() for g in grp_node.expressions} if grp_node else set()
                missing_grp: list[str] = []
                for proj in sel.expressions:
                    inner = proj.this if isinstance(proj, exp.Alias) else proj
                    if isinstance(inner, exp.Column) and not isinstance(inner.parent, exp.AggFunc):
                        csql = inner.sql(dialect=sg_dialect)
                        if csql.lower() not in grp_cols:
                            missing_grp.append(csql)
                if missing_grp:
                    missing_group_by_cols.extend(c for c in missing_grp if c not in missing_group_by_cols)
                    diagnostics.append(
                        DebugDiagnostic(
                            code="DBG_GROUP_BY_MISMATCH",
                            category="confirmed_error",
                            severity="Error",
                            title="Unaggregated Column Missing From GROUP BY",
                            message=f"Selected non-aggregated column(s) ({', '.join(missing_grp)}) must appear in GROUP BY.",
                            line=_find_fragment_line(raw_sql, missing_grp[0]),
                            fragment=", ".join(missing_grp),
                            suggestion=f"Add `GROUP BY {', '.join(missing_grp)}` or wrap in an aggregate function.",
                        )
                    )

        # Join validation: Join conditions missing or joining unrelated columns of different types
        join_on_fixes: list[tuple[str, str]] = []
        for jnode in root.find_all(exp.Join):
            if not jnode.args.get("on") and not jnode.args.get("using") and (jnode.kind or "").upper() != "CROSS":
                j_tbl_raw = jnode.this.name if isinstance(jnode.this, exp.Table) else jnode.this.sql(dialect=sg_dialect)
                j_alias = jnode.this.alias or j_tbl_raw if isinstance(jnode.this, exp.Table) else j_tbl_raw
                fk_hint = ""
                for rel in context.relationships:
                    st_l, tt_l = rel.source_table.lower(), rel.target_table.lower()
                    if st_l == j_tbl_raw.lower() and any(rt.lower() == tt_l for rt in referenced_tables):
                        other_alias = next(
                            (k for k, v in alias_to_tbl.items() if v.lower() == tt_l and k != tt_l),
                            rel.target_table,
                        )
                        fk_hint = f"{j_alias}.{rel.source_columns[0]} = {other_alias}.{rel.target_columns[0]}"
                        join_on_fixes.append((j_tbl_raw, fk_hint))
                        break
                    if tt_l == j_tbl_raw.lower() and any(rt.lower() == st_l for rt in referenced_tables):
                        other_alias = next(
                            (k for k, v in alias_to_tbl.items() if v.lower() == st_l and k != st_l),
                            rel.source_table,
                        )
                        fk_hint = f"{j_alias}.{rel.target_columns[0]} = {other_alias}.{rel.source_columns[0]}"
                        join_on_fixes.append((j_tbl_raw, fk_hint))
                        break
                diagnostics.append(
                    DebugDiagnostic(
                        code="DBG_JOIN_MISSING_ON",
                        category="confirmed_error",
                        severity="Error",
                        title=f"JOIN Against '{j_tbl_raw}' Missing ON Clause",
                        message=f"Joining '{j_tbl_raw}' without an ON/USING predicate creates a Cartesian product (or fails SQL validation).",
                        line=_find_fragment_line(raw_sql, j_tbl_raw),
                        fragment=jnode.sql(dialect=sg_dialect),
                        suggestion=(
                            f"Add foreign-key predicate `ON {fk_hint}`."
                            if fk_hint
                            else f"Specify an equality condition (`ON ... = ...`) joining '{j_tbl_raw}' via key columns."
                        ),
                    )
                )

        # Probe live read-only test execution if not already given an error and syntax/schema had no obvious blockers
        if connector is not None and not live_exec_error:
            val_ro = validate_read_only_sql(raw_sql) if d == "postgresql" else None
            # Safe read-only check on active connector (only executes read-only statements!)
            probe = connector.execute_sql(raw_sql, dialect=d, max_rows=5, allow_write_opt_in=False)
            if not probe.success and "read-only" not in probe.error_message.lower():
                diagnostics.append(
                    DebugDiagnostic(
                        code="DBG_EXECUTION",
                        category="confirmed_error",
                        severity="Error",
                        title="Execution Error Caught on Active Database",
                        message=probe.error_message,
                        line=_find_fragment_line(raw_sql, ""),
                    )
                )

        # Reuse QueryTrellis AST + Catalog Anti-Pattern Detector!
        if d == "postgresql" or (val_check := parse_sql_ast(raw_sql, d)).is_valid:
            pg_cat = context_to_pg_catalog(context)
            ro_val = validate_read_only_sql(raw_sql)
            if ro_val.is_valid and ro_val.is_read_only:
                for ap in detect_antipatterns(ro_val, catalog=pg_cat):
                    diagnostics.append(
                        DebugDiagnostic(
                            code=ap.rule_id,
                            category="performance_warning",
                            severity=ap.severity,
                            title=ap.issue_name,
                            message=f"{ap.explanation} {ap.performance_impact}",
                            line=_find_fragment_line(raw_sql, ap.affected_fragment[:24]),
                            fragment=ap.affected_fragment,
                            suggestion=ap.suggested_improvement,
                        )
                    )

        # Build Concrete Corrected SQL Candidates
        repaired_sql = raw_sql
        fix_notes: list[str] = []
        if table_renames:
            for old_t, new_t in table_renames.items():
                repaired_sql = re.sub(rf"\b{re.escape(old_t)}\b", new_t, repaired_sql)
                fix_notes.append(f"table `{old_t}` -> `{new_t}`")
        if col_renames:
            for old_c, new_c in col_renames.items():
                repaired_sql = re.sub(rf"\b{re.escape(old_c)}\b", new_c, repaired_sql)
                fix_notes.append(f"column `{old_c}` -> `{new_c}`")
        if null_eq_fixes:
            repaired_sql = re.sub(r"([a-zA-Z0-9_.]+)\s*!=\s*NULL\b|([a-zA-Z0-9_.]+)\s*<>\s*NULL\b", lambda m: f"{m.group(1) or m.group(2)} IS NOT NULL", repaired_sql, flags=re.IGNORECASE)
            repaired_sql = re.sub(r"([a-zA-Z0-9_.]+)\s*=\s*NULL\b", r"\1 IS NULL", repaired_sql, flags=re.IGNORECASE)
            fix_notes.append("null comparison (`= NULL` -> `IS NULL`)")
        if ambiguous_qualifies:
            for raw_col, qual_col in ambiguous_qualifies:
                repaired_sql = re.sub(rf"(?<![.\w]){re.escape(raw_col)}\b", qual_col, repaired_sql)
                fix_notes.append(f"qualified ambiguous `{raw_col}` -> `{qual_col}`")
        if join_on_fixes:
            for j_tbl_raw, fk_hint in join_on_fixes:
                repaired_sql = re.sub(
                    rf"(JOIN\s+{re.escape(j_tbl_raw)}(?:\s+(?:AS\s+)?[a-zA-Z_][a-zA-Z0-9_]*)?)",
                    rf"\1 ON {fk_hint}",
                    repaired_sql,
                    count=1,
                    flags=re.IGNORECASE,
                )
                fix_notes.append(f"added JOIN predicate `ON {fk_hint}`")
        if missing_group_by_cols:
            try:
                rep_ast = sqlglot.parse_one(repaired_sql, read=sg_dialect)
                if isinstance(rep_ast, exp.Select):
                    rep_ast = rep_ast.group_by(*missing_group_by_cols)
                    repaired_sql = rep_ast.sql(dialect=sg_dialect, pretty=True)
                    fix_notes.append(f"added GROUP BY ({', '.join(missing_group_by_cols)})")
            except Exception:
                pass

        if repaired_sql != raw_sql:
            candidates.append(
                DebugFixCandidate(
                    fix_id="FIX_SCHEMA_LOGIC",
                    title="Resolve Confirmed Schema & Logic Issues",
                    kind="confirmed_error_fix",
                    corrected_sql=repaired_sql,
                    explanation="Applied targeted repairs: " + "; ".join(fix_notes) + ".",
                )
            )

    # Safely test every generated candidate fix against active DB before recommending!
    if test_fixes and connector is not None:
        for cand in candidates:
            cand.tested = True
            res = connector.execute_sql(cand.corrected_sql, dialect=d, max_rows=20, allow_write_opt_in=False)
            cand.test_passed = res.success
            cand.test_rows = res.rows_returned if res.success else None
            cand.test_duration_ms = res.duration_ms
            cand.test_error = res.error_message

    return {
        "dialect": d,
        "original_sql": raw_sql,
        "has_errors": any(x.category == "confirmed_error" for x in diagnostics),
        "diagnostics": [x.to_dict() for x in diagnostics],
        "fix_candidates": [c.to_dict() for c in candidates],
    }
