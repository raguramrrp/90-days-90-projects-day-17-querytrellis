"""Centralized Streamlit session state management for QueryTrellis."""
from __future__ import annotations

import streamlit as st

from src.advisor.index_recommender import IndexRecommendation
from src.config.settings import load_settings
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.explain.plan_analyzer import analyze_explain_plan
from src.explain.plan_parser import parse_explain_json
from src.services.workbench_service import FullAnalysisBundle
from src.sql_analysis.antipattern_detector import AntiPatternFinding
from src.sql_analysis.parser_validator import validate_read_only_sql
from src.sql_analysis.sample_queries import SAMPLE_QUERIES

NAV_PAGES = [
    "Overview",
    "Query Editor",
    "Explain Plan",
    "Recommendations",
    "Benchmark Lab",
    "Query History",
    "Reports",
    "Settings",
]


def init_session_state() -> None:
    """Initialize settings, connection manager, SQLite metadata store, and workspace state."""
    if "qt_initialized" in st.session_state:
        return

    settings = load_settings()
    store = MetadataStore(settings.metadata_db_path)
    conn_mgr = ConnectionManager(settings.connection)

    # Load user preferences if stored
    saved_timeout = store.get_preference("statement_timeout_ms")
    saved_rows = store.get_preference("max_rows")
    saved_explain_mode = store.get_preference("explain_analyze_default")

    st.session_state["qt_settings"] = settings
    st.session_state["qt_store"] = store
    st.session_state["qt_conn_mgr"] = conn_mgr

    qp_page = st.query_params.get("page")
    initial_page = qp_page if qp_page in NAV_PAGES else "Overview"
    st.session_state["qt_nav_page"] = initial_page

    st.session_state["qt_timeout_ms"] = (
        int(saved_timeout) if saved_timeout and saved_timeout.isdigit() else settings.default_statement_timeout_ms
    )
    st.session_state["qt_max_rows"] = (
        int(saved_rows) if saved_rows and saved_rows.isdigit() else settings.default_max_rows
    )
    st.session_state["qt_explain_analyze"] = saved_explain_mode != "false"

    st.session_state["qt_editor_sql"] = SAMPLE_QUERIES[0].sql
    st.session_state["qt_last_exec"] = None
    st.session_state["qt_last_analysis"] = None
    st.session_state["qt_last_benchmark"] = None
    st.session_state["qt_baseline_snapshot"] = None
    st.session_state["qt_candidate_snapshot"] = None
    st.session_state["qt_last_comparison"] = None
    st.session_state["qt_bench_sql_a"] = SAMPLE_QUERIES[6].sql
    st.session_state["qt_bench_sql_b"] = SAMPLE_QUERIES[6].suggested_optimization or SAMPLE_QUERIES[6].sql
    st.session_state["qt_initialized"] = True

    # Attempt silent initial auto-connect ONLY if credentials are configured in .env
    if settings.connection.password or settings.connection.host:
        status = conn_mgr.connect(settings.connection)
        if status.connected:
            try:
                conn_mgr.fetch_catalog()
            except Exception:
                pass

    # Hydrate most recent successful analysis & benchmark/comparison if stored in SQLite
    recent_success = store.list_analyses(limit=1, status_filter="success")
    if recent_success and recent_success[0].get("plan_json"):
        load_history_record_into_state(recent_success[0])

    recent_bench = store.list_benchmarks(limit=1)
    if recent_bench:
        from src.benchmark.runner import BenchmarkIteration, BenchmarkSummary
        b = recent_bench[0]
        its = [
            BenchmarkIteration(
                run_index=it.get("run_index", idx + 1),
                is_warmup=False,
                client_wall_ms=float(it.get("client_wall_ms", 0.0)),
                pg_planning_ms=it.get("pg_planning_ms"),
                pg_execution_ms=it.get("pg_execution_ms"),
                rows_returned=it.get("rows_returned"),
                shared_hit_blocks=it.get("shared_hit_blocks"),
                shared_read_blocks=it.get("shared_read_blocks"),
            )
            for idx, it in enumerate(b.get("iterations") or [])
        ]
        pg_vals = [it.pg_execution_ms for it in its if it.pg_execution_ms is not None]
        st.session_state["qt_last_benchmark"] = BenchmarkSummary(
            success=True,
            label=b["label"],
            sql_text=b["sql_text"],
            sql_hash=b["sql_hash"],
            repeat_count=b["repeat_count"],
            warmup_used=bool(b["warmup_used"]),
            min_ms=b["min_ms"],
            max_ms=b["max_ms"],
            mean_ms=b["mean_ms"],
            median_ms=b["median_ms"],
            p95_ms=b["p95_ms"],
            stdev_ms=0.0,
            pg_exec_min_ms=min(pg_vals) if pg_vals else None,
            pg_exec_max_ms=max(pg_vals) if pg_vals else None,
            pg_exec_mean_ms=(sum(pg_vals) / len(pg_vals)) if pg_vals else None,
            pg_exec_median_ms=b["pg_exec_median_ms"],
            iterations=its,
        )

    recent_cmp = store.list_comparisons(limit=1)
    if recent_cmp:
        from src.benchmark.comparator import QueryComparisonResult
        cd = recent_cmp[0].get("comparison") or {}
        if cd:
            st.session_state["qt_last_comparison"] = QueryComparisonResult(
                baseline_label=cd.get("baseline_label", "Baseline (A)"),
                optimized_label=cd.get("optimized_label", "Optimized (B)"),
                baseline_sql=cd.get("baseline_sql", ""),
                optimized_sql=cd.get("optimized_sql", ""),
                baseline_time_ms=cd.get("baseline_time_ms"),
                optimized_time_ms=cd.get("optimized_time_ms"),
                time_diff_ms=cd.get("time_diff_ms"),
                pct_change=cd.get("pct_change"),
                speedup_factor=cd.get("speedup_factor"),
                baseline_cost=cd.get("baseline_cost"),
                optimized_cost=cd.get("optimized_cost"),
                cost_diff=cd.get("cost_diff"),
                cost_pct_change=cd.get("cost_pct_change"),
                baseline_rows=cd.get("baseline_rows"),
                optimized_rows=cd.get("optimized_rows"),
                row_count_matches=cd.get("row_count_matches"),
                baseline_nodes=[],
                optimized_nodes=[],
                nodes_added=cd.get("nodes_added", []),
                nodes_removed=cd.get("nodes_removed", []),
                baseline_indexes=[],
                optimized_indexes=[],
                indexes_added=cd.get("indexes_added", []),
                indexes_removed=cd.get("indexes_removed", []),
                resolved_antipatterns=cd.get("resolved_antipatterns", []),
                remaining_antipatterns=cd.get("remaining_antipatterns", []),
                introduced_antipatterns=cd.get("introduced_antipatterns", []),
                verdict=cd.get("verdict", "Inconclusive"),
                verdict_summary=cd.get("verdict_summary", ""),
            )


def load_history_record_into_state(record: dict) -> None:
    """Hydrate a historical SQLite analysis row back into active workspace views."""
    sql_text = record.get("sql_text", "")
    st.session_state["qt_editor_sql"] = sql_text
    validation = validate_read_only_sql(sql_text)

    parsed_plan = None
    insights = []
    if record.get("plan_json"):
        try:
            parsed_plan = parse_explain_json(record["plan_json"])
            conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
            cat = conn_mgr.fetch_catalog() if conn_mgr.is_connected else None
            insights = analyze_explain_plan(parsed_plan, catalog=cat)
        except Exception:
            parsed_plan = None

    antipatterns = [
        AntiPatternFinding(
            rule_id=ap.get("rule_id", "AP"),
            issue_name=ap.get("issue_name", "Issue"),
            severity=ap.get("severity", "Low"),
            affected_fragment=ap.get("affected_fragment", ""),
            explanation=ap.get("explanation", ""),
            performance_impact=ap.get("performance_impact", ""),
            when_acceptable=ap.get("when_acceptable", ""),
            suggested_improvement=ap.get("suggested_improvement", ""),
            confidence=ap.get("confidence", "Medium"),
            evidence_basis=ap.get("evidence_basis", "Stored History"),
        )
        for ap in (record.get("antipatterns_json") or [])
    ]

    recs = [
        IndexRecommendation(
            rec_id=r.get("rec_id", "IDX"),
            table_name=r.get("table_name", ""),
            columns=r.get("columns", []),
            include_columns=r.get("include_columns", []),
            partial_predicate=r.get("partial_predicate"),
            index_type=r.get("index_type", "B-tree"),
            suggested_sql=r.get("suggested_sql", ""),
            related_condition=r.get("related_condition", ""),
            why_it_helps=r.get("why_it_helps", ""),
            existing_index_status=r.get("existing_index_status", ""),
            write_and_storage_overhead=r.get("write_and_storage_overhead", ""),
            when_not_helpful=r.get("when_not_helpful", ""),
            confidence=r.get("confidence", "Medium"),
            evidence_sources=r.get("evidence_sources", []),
        )
        for r in (record.get("recommendations_json") or [])
    ]

    st.session_state["qt_last_analysis"] = FullAnalysisBundle(
        sql_text=sql_text,
        formatted_sql=record.get("formatted_sql") or sql_text,
        validation=validation,
        explain_exec=None,
        parsed_plan=parsed_plan,
        plan_insights=insights,
        antipatterns=antipatterns,
        index_recommendations=recs,
        analysis_id=record.get("id"),
        error_message=record.get("error_message") or "",
    )
