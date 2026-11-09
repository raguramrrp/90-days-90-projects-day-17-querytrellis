"""End-to-end query analysis workflow orchestrator for QueryTrellis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.advisor.index_recommender import IndexRecommendation, recommend_indexes
from src.db.connection_manager import ConnectionManager, DatabaseCatalog
from src.db.metadata_store import MetadataStore
from src.db.safe_executor import (
    ExplainExecutionResult,
    QueryExecutionResult,
    execute_safe_query,
    run_explain_plan,
)
from src.explain.plan_analyzer import PlanInsight, analyze_explain_plan
from src.explain.plan_parser import ParsedExplainPlan, parse_explain_json
from src.sql_analysis.antipattern_detector import AntiPatternFinding, detect_antipatterns
from src.sql_analysis.formatter import format_sql
from src.sql_analysis.parser_validator import ValidationResult, validate_read_only_sql


@dataclass(slots=True)
class FullAnalysisBundle:
    """Combined SQL validation, EXPLAIN plan, anti-pattern, and index recommendation output."""

    sql_text: str
    formatted_sql: str
    validation: ValidationResult
    explain_exec: ExplainExecutionResult | None = None
    parsed_plan: ParsedExplainPlan | None = None
    plan_insights: list[PlanInsight] = field(default_factory=list)
    antipatterns: list[AntiPatternFinding] = field(default_factory=list)
    index_recommendations: list[IndexRecommendation] = field(default_factory=list)
    analysis_id: int | None = None
    error_message: str = ""


def analyze_query_end_to_end(
    sql: str,
    *,
    conn_manager: ConnectionManager | None = None,
    metadata_store: MetadataStore | None = None,
    analyze_explain: bool = True,
    buffers: bool = True,
    timeout_ms: int = 5000,
    persist: bool = True,
) -> FullAnalysisBundle:
    """Validate SQL, detect anti-patterns, run EXPLAIN (if connected), and recommend indexes."""
    validation = validate_read_only_sql(sql)
    formatted_sql, _ = format_sql(sql)

    if not validation.is_valid or not validation.is_read_only:
        err = validation.error_message or "SQL validation failed."
        if persist and metadata_store is not None and sql.strip():
            db_name = conn_manager.status.current_database if conn_manager and conn_manager.is_connected else "offline"
            metadata_store.save_analysis(
                database_name=db_name or "offline",
                sql_text=sql,
                sql_hash="invalid",
                status="rejected",
                execution_mode="validate",
                error_message=err,
            )
        return FullAnalysisBundle(
            sql_text=sql,
            formatted_sql=formatted_sql,
            validation=validation,
            error_message=err,
        )

    catalog: DatabaseCatalog | None = None
    explain_exec: ExplainExecutionResult | None = None
    parsed_plan: ParsedExplainPlan | None = None
    plan_insights: list[PlanInsight] = []
    err_msg = ""

    if conn_manager is not None and conn_manager.is_connected:
        try:
            catalog = conn_manager.fetch_catalog()
        except Exception:
            catalog = None

        conn = conn_manager.get_connection()
        explain_exec = run_explain_plan(
            conn,
            validation.clean_sql,
            analyze=analyze_explain,
            buffers=buffers,
            timeout_ms=timeout_ms,
        )
        if explain_exec.success and explain_exec.raw_plan_json is not None:
            try:
                parsed_plan = parse_explain_json(explain_exec.raw_plan_json)
                plan_insights = analyze_explain_plan(parsed_plan, catalog=catalog)
            except Exception as exc:
                err_msg = f"Failed to parse EXPLAIN output: {exc}"
        elif not explain_exec.success:
            err_msg = explain_exec.error_message

    antipatterns = detect_antipatterns(validation, catalog=catalog)
    recommendations = recommend_indexes(validation, catalog=catalog, plan=parsed_plan)

    analysis_id: int | None = None
    if persist and metadata_store is not None:
        db_name = (
            conn_manager.status.current_database
            if (conn_manager is not None and conn_manager.is_connected)
            else "offline_static"
        )
        mode_label = (
            "explain_analyze"
            if (conn_manager is not None and conn_manager.is_connected and analyze_explain)
            else ("explain_estimate" if (conn_manager is not None and conn_manager.is_connected) else "static_only")
        )
        status = "success" if not err_msg else "error"
        analysis_id = metadata_store.save_analysis(
            database_name=db_name,
            sql_text=sql,
            sql_hash=validation.parsed_info.normalized_hash if validation.parsed_info else "",
            formatted_sql=formatted_sql,
            status=status,
            execution_mode=mode_label,
            client_duration_ms=explain_exec.client_duration_ms if explain_exec else None,
            pg_planning_ms=parsed_plan.planning_time_ms if parsed_plan else None,
            pg_execution_ms=parsed_plan.execution_time_ms if parsed_plan else None,
            rows_returned=parsed_plan.root_actual_rows if parsed_plan else None,
            total_cost=parsed_plan.total_cost if parsed_plan else None,
            plan_json=explain_exec.raw_plan_json if explain_exec else None,
            summary_json=parsed_plan.to_summary_dict() if parsed_plan else None,
            antipatterns_json=[
                {
                    "rule_id": f.rule_id,
                    "issue_name": f.issue_name,
                    "severity": f.severity,
                    "affected_fragment": f.affected_fragment,
                    "explanation": f.explanation,
                    "performance_impact": f.performance_impact,
                    "when_acceptable": f.when_acceptable,
                    "suggested_improvement": f.suggested_improvement,
                    "confidence": f.confidence,
                    "evidence_basis": f.evidence_basis,
                }
                for f in antipatterns
            ],
            recommendations_json=[
                {
                    "rec_id": r.rec_id,
                    "table_name": r.table_name,
                    "columns": r.columns,
                    "include_columns": r.include_columns,
                    "partial_predicate": r.partial_predicate,
                    "index_type": r.index_type,
                    "suggested_sql": r.suggested_sql,
                    "related_condition": r.related_condition,
                    "why_it_helps": r.why_it_helps,
                    "existing_index_status": r.existing_index_status,
                    "write_and_storage_overhead": r.write_and_storage_overhead,
                    "when_not_helpful": r.when_not_helpful,
                    "confidence": r.confidence,
                    "evidence_sources": r.evidence_sources,
                }
                for r in recommendations
            ],
            error_message=err_msg or None,
        )

    return FullAnalysisBundle(
        sql_text=sql,
        formatted_sql=formatted_sql,
        validation=validation,
        explain_exec=explain_exec,
        parsed_plan=parsed_plan,
        plan_insights=plan_insights,
        antipatterns=antipatterns,
        index_recommendations=recommendations,
        analysis_id=analysis_id,
        error_message=err_msg,
    )


def execute_and_record_query(
    sql: str,
    *,
    conn_manager: ConnectionManager,
    metadata_store: MetadataStore | None = None,
    timeout_ms: int = 5000,
    max_rows: int = 500,
    persist: bool = True,
) -> QueryExecutionResult:
    """Execute a safe read-only query and log its outcome in SQLite query history."""
    conn = conn_manager.get_connection()
    result = execute_safe_query(conn, sql, timeout_ms=timeout_ms, max_rows=max_rows)
    if persist and metadata_store is not None:
        db_name = conn_manager.status.current_database or conn_manager.config.database
        formatted_sql, _ = format_sql(sql)
        metadata_store.save_analysis(
            database_name=db_name,
            sql_text=sql,
            sql_hash=(
                result.validation.parsed_info.normalized_hash
                if result.validation.parsed_info
                else "invalid"
            ),
            formatted_sql=formatted_sql,
            status="success" if result.success else ("rejected" if not result.validation.is_read_only else "error"),
            execution_mode="execute_preview",
            client_duration_ms=result.client_duration_ms,
            rows_returned=result.rows_returned if result.success else None,
            error_message=result.error_message or None,
        )
    return result
