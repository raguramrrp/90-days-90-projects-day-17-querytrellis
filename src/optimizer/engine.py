"""Query Optimizer integrating QueryTrellis anti-patterns, index advisor, rewrites, and EXPLAIN plans.

Strictly separates:
1. Static optimization suggestions (AST + schema heuristics)
2. Estimated query plans (EXPLAIN without execution)
3. Actual measured execution performance (opt-in EXPLAIN ANALYZE + benchmark comparison)
"""
from __future__ import annotations

import re
from typing import Any

from sqlglot import exp

from src.advisor.index_recommender import recommend_indexes
from src.connectors.adapters import MultiDBConnector
from src.context.models import DatabaseContextSnapshot
from src.debugger.assistant import context_to_pg_catalog
from src.dialects.sqlglot_engine import convert_sql_dialect, normalize_dialect, parse_sql_ast
from src.sql_analysis.antipattern_detector import detect_antipatterns
from src.sql_analysis.parser_validator import validate_read_only_sql


def _build_rewrite_alternatives(
    sql: str,
    context: DatabaseContextSnapshot,
    dialect: str,
) -> list[dict[str, str]]:
    """Generate concrete optimized SQL rewrites when static bottlenecks exist."""
    alternatives: list[dict[str, str]] = []
    # 1. Non-sargable LOWER(col) = 'literal' -> direct col = 'literal' or case note
    if re.search(r"LOWER\s*\(\s*([a-zA-Z0-9_.]+)\s*\)\s*=\s*'([^']+)'", sql, re.IGNORECASE):
        rw = re.sub(
            r"LOWER\s*\(\s*([a-zA-Z0-9_.]+)\s*\)\s*=\s*'([^']+)'",
            lambda m: f"{m.group(1)} = '{m.group(2).lower()}'",
            sql,
            flags=re.IGNORECASE,
        )
        alternatives.append(
            {
                "title": "Remove function wrapper around filtered column (Sargable Predicate)",
                "rewritten_sql": rw,
                "rationale": "Allows standard B-tree index seeks when stored values match casing or paired with CITEXT / expression index.",
                "category": "static_rewrite",
            }
        )

    # 2. Non-sargable EXTRACT(YEAR FROM col) = 2025 -> half-open date range
    m_yr = re.search(
        r"EXTRACT\s*\(\s*YEAR\s+FROM\s+([a-zA-Z0-9_.]+)\s*\)\s*=\s*(\d{4})",
        sql,
        re.IGNORECASE,
    )
    if m_yr:
        col, yr = m_yr.group(1), int(m_yr.group(2))
        rw = re.sub(
            r"EXTRACT\s*\(\s*YEAR\s+FROM\s+([a-zA-Z0-9_.]+)\s*\)\s*=\s*\d{4}",
            f"{col} >= '{yr}-01-01' AND {col} < '{yr + 1}-01-01'",
            sql,
            flags=re.IGNORECASE,
        )
        alternatives.append(
            {
                "title": "Rewrite EXTRACT(YEAR FROM col) as half-open range",
                "rewritten_sql": rw,
                "rationale": "Avoids per-row date extraction and unlocks index range scans on temporal columns.",
                "category": "static_rewrite",
            }
        )

    # 3. SELECT * -> explicit columns from active schema
    parsed = parse_sql_ast(sql, dialect)
    if parsed.is_valid and parsed.root is not None:
        for sel in parsed.root.find_all(exp.Select):
            has_star = any(isinstance(p, exp.Star) for p in sel.expressions)
            from_node = sel.args.get("from_") or sel.args.get("from")
            if has_star and from_node and not (sel.args.get("joins")):
                tbl_node = next(from_node.find_all(exp.Table), None)
                if tbl_node and (tschema := context.find_table(tbl_node.name)):
                    explicit_cols = ", ".join(c.name for c in tschema.columns[:6])
                    rw = re.sub(r"SELECT\s+\*", f"SELECT {explicit_cols}", sql, count=1, flags=re.IGNORECASE)
                    if rw != sql:
                        alternatives.append(
                            {
                                "title": f"Replace SELECT * with explicit column projection ({tschema.name})",
                                "rewritten_sql": rw,
                                "rationale": "Reduces I/O, sort/hash memory width, and network serialization; enables Index-Only Scans.",
                                "category": "static_rewrite",
                            }
                        )
                    break

    return alternatives


def optimize_sql_query(
    sql: str,
    context: DatabaseContextSnapshot,
    *,
    dialect: str | None = None,
    connector: MultiDBConnector | None = None,
    include_estimated_plan: bool = True,
    allow_explain_analyze: bool = False,
    benchmark_candidate_sql: str | None = None,
) -> dict[str, Any]:
    """Produce three-tier optimization diagnostics: static, estimated plan, and optional measured runs."""
    d = normalize_dialect(dialect or context.dialect)
    raw_sql = (sql or "").strip()
    if not raw_sql:
        return {"success": False, "error_message": "Provide a SQL query to analyze and optimize."}

    # Transpile safely to postgres AST when needed so QueryTrellis rule engine inspects accurately
    pg_conv = convert_sql_dialect(raw_sql, d, "postgresql", pretty=False) if d != "postgresql" else None
    inspect_sql = pg_conv.converted_sql if (pg_conv and pg_conv.success) else raw_sql
    validation = validate_read_only_sql(inspect_sql)

    pg_cat = context_to_pg_catalog(context)
    antipatterns = detect_antipatterns(validation, catalog=pg_cat) if validation.is_read_only else []
    index_recs = recommend_indexes(validation, catalog=pg_cat) if validation.is_read_only else []
    rewrites = _build_rewrite_alternatives(raw_sql, context, d)

    # Filter dialect nuances on index DDL (INCLUDE syntax is PostgreSQL/SQL Server specific)
    formatted_indexes = []
    for rec in index_recs:
        ddl = rec.suggested_sql
        dialect_note = ""
        if rec.include_columns and d in {"mysql", "sqlite"}:
            ddl = f"CREATE INDEX idx_{rec.table_name}_{'_'.join(rec.columns)} ON {rec.table_name}({', '.join(rec.columns)});"
            dialect_note = f"{d.upper()} does not support INCLUDE covering syntax; converted to key-only index."
        if rec.partial_predicate and d == "mysql":
            ddl = f"CREATE INDEX idx_{rec.table_name}_{'_'.join(rec.columns)} ON {rec.table_name}({', '.join(rec.columns)});"
            dialect_note = "MySQL does not support partial WHERE indexes natively; converted to full B-tree index."
        formatted_indexes.append(
            {
                "rec_id": rec.rec_id,
                "table_name": rec.table_name,
                "columns": rec.columns,
                "index_type": rec.index_type,
                "suggested_sql": ddl,
                "related_condition": rec.related_condition,
                "why_it_helps": rec.why_it_helps,
                "existing_index_status": rec.existing_index_status,
                "write_and_storage_overhead": rec.write_and_storage_overhead,
                "when_not_helpful": rec.when_not_helpful,
                "confidence": rec.confidence,
                "dialect_note": dialect_note,
            }
        )

    estimated_plan: dict[str, Any] | None = None
    measured_performance: dict[str, Any] | None = None

    if connector is not None and validation.is_read_only:
        if include_estimated_plan:
            estimated_plan = connector.run_explain(raw_sql, dialect=d, analyze=False)

        if allow_explain_analyze:
            orig_run = connector.run_explain(raw_sql, dialect=d, analyze=True)
            orig_exec = connector.execute_sql(raw_sql, dialect=d, max_rows=500, allow_write_opt_in=False)
            measured_performance = {
                "executed": True,
                "warning_acknowledged": True,
                "original": {
                    "explain": orig_run,
                    "duration_ms": orig_exec.duration_ms,
                    "rows_returned": orig_exec.rows_returned,
                },
            }
            if benchmark_candidate_sql and benchmark_candidate_sql.strip():
                cand_run = connector.run_explain(benchmark_candidate_sql, dialect=d, analyze=True)
                cand_exec = connector.execute_sql(
                    benchmark_candidate_sql, dialect=d, max_rows=500, allow_write_opt_in=False
                )
                delta_ms = round(orig_exec.duration_ms - cand_exec.duration_ms, 3)
                measured_performance["candidate"] = {
                    "explain": cand_run,
                    "duration_ms": cand_exec.duration_ms,
                    "rows_returned": cand_exec.rows_returned,
                    "duration_delta_ms": delta_ms,
                    "row_count_matches": orig_exec.rows_returned == cand_exec.rows_returned,
                }

    return {
        "success": True,
        "dialect": d,
        "static_suggestions": {
            "evidence_tier": "Static AST + Schema Analysis (Non-Executing)",
            "antipatterns": [
                {
                    "rule_id": a.rule_id,
                    "issue_name": a.issue_name,
                    "severity": a.severity,
                    "affected_fragment": a.affected_fragment,
                    "explanation": a.explanation,
                    "performance_impact": a.performance_impact,
                    "when_acceptable": a.when_acceptable,
                    "suggested_improvement": a.suggested_improvement,
                    "confidence": a.confidence,
                    "evidence_basis": a.evidence_basis,
                }
                for a in antipatterns
            ],
            "index_recommendations": formatted_indexes,
            "rewrite_alternatives": rewrites,
        },
        "estimated_plan": estimated_plan,
        "measured_performance": measured_performance
        or {
            "executed": False,
            "notice": (
                "Actual runtime timings and EXPLAIN ANALYZE are omitted until you explicitly enable "
                "EXPLAIN ANALYZE execution confirmation (never fabricated)."
            ),
        },
    }
