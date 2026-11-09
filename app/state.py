"""Centralized Streamlit session state management and navigation metadata for QueryTrellis."""
from __future__ import annotations

import os
import statistics
from dataclasses import dataclass

import streamlit as st

from src.advisor.index_recommender import IndexRecommendation
from src.config.settings import ConnectionConfig, PROJECT_ROOT, load_settings
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.explain.plan_analyzer import analyze_explain_plan
from src.explain.plan_parser import parse_explain_json
from src.services.workbench_service import FullAnalysisBundle
from src.sql_analysis.antipattern_detector import AntiPatternFinding
from src.sql_analysis.parser_validator import validate_read_only_sql
from src.sql_analysis.sample_queries import SAMPLE_QUERIES


@dataclass(frozen=True, slots=True)
class NavItem:
    page: str
    group: str
    icon: str
    subtitle: str


NAV_GROUPS: list[tuple[str, str, list[NavItem]]] = [
    (
        "WORKSPACE",
        "qt_nav_grp_workspace",
        [
            NavItem("Overview", "Workspace", "dashboard", "Database performance and query analysis workspace."),
            NavItem("Query Editor", "Workspace", "code", "PostgreSQL SQL development, safe execution, and schema explorer."),
            NavItem("Explain Plan", "Workspace", "account_tree", "Interactive execution plan tree, node metrics, and estimate calibration."),
        ],
    ),
    (
        "OPTIMIZATION",
        "qt_nav_grp_optimization",
        [
            NavItem("Recommendations", "Optimization", "lightbulb", "Grouped SQL anti-patterns, advisory indexes, and plan findings."),
            NavItem("Benchmark Lab", "Optimization", "speed", "Repeatable multi-run timings and before-and-after SQL comparison."),
            NavItem("Query History", "Optimization", "history", "Search, filter, and reopen historical query analyses."),
        ],
    ),
    (
        "MANAGEMENT",
        "qt_nav_grp_management",
        [
            NavItem("Reports", "Management", "description", "Manage optimization reports, benchmark summaries, and sanitized exports."),
            NavItem("Settings", "Management", "settings", "Database connection, execution guardrails, theme, and local storage."),
        ],
    ),
]

NAV_ITEMS_BY_PAGE: dict[str, NavItem] = {
    item.page: item
    for _, _, items in NAV_GROUPS
    for item in items
}
NAV_PAGES: list[str] = list(NAV_ITEMS_BY_PAGE.keys())


def navigate_to(page: str) -> None:
    """Switch active workbench page cleanly."""
    if page in NAV_ITEMS_BY_PAGE:
        st.session_state["qt_nav_page"] = page


def set_active_editor_sql(sql_text: str) -> None:
    """Update active SQL tab content and bump sync sequence for the IDE widget."""
    tabs = st.session_state.get("qt_sql_tabs")
    idx = int(st.session_state.get("qt_active_sql_tab", 0))
    if isinstance(tabs, list) and 0 <= idx < len(tabs):
        tabs[idx]["sql"] = sql_text
    st.session_state["qt_editor_sql"] = sql_text
    st.session_state["qt_editor_seq"] = int(st.session_state.get("qt_editor_seq", 0)) + 1


def _hydrate_saved_benchmark(store: MetadataStore) -> None:
    recent_bench = store.list_benchmarks(limit=1)
    if not recent_bench:
        return
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
    wall_vals = [it.client_wall_ms for it in its]
    pg_vals = [it.pg_execution_ms for it in its if it.pg_execution_ms is not None]
    stdev_val = round(statistics.stdev(wall_vals), 3) if len(wall_vals) >= 2 else 0.0

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
        stdev_ms=stdev_val,
        pg_exec_min_ms=min(pg_vals) if pg_vals else None,
        pg_exec_max_ms=max(pg_vals) if pg_vals else None,
        pg_exec_mean_ms=(sum(pg_vals) / len(pg_vals)) if pg_vals else None,
        pg_exec_median_ms=b["pg_exec_median_ms"],
        iterations=its,
    )


def _hydrate_saved_comparison(store: MetadataStore) -> None:
    recent_cmp = store.list_comparisons(limit=1)
    if not recent_cmp:
        return
    from src.benchmark.comparator import QueryComparisonResult

    cd = recent_cmp[0].get("comparison") or {}
    if not cd:
        return

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


def init_session_state() -> None:
    """Initialize settings, theme, connection manager, SQLite metadata store, and workspace state."""
    if "qt_initialized" in st.session_state:
        return

    settings = load_settings()
    store = MetadataStore(settings.metadata_db_path)
    conn_mgr = ConnectionManager(settings.connection)

    saved_timeout = store.get_preference("statement_timeout_ms")
    saved_rows = store.get_preference("max_rows")
    saved_explain_mode = store.get_preference("explain_analyze_default")
    saved_theme = store.get_preference("ui_theme", "dark")
    saved_hist_limit = store.get_preference("history_display_limit")

    st.session_state["qt_settings"] = settings
    st.session_state["qt_store"] = store
    st.session_state["qt_conn_mgr"] = conn_mgr
    st.session_state["qt_theme"] = "light" if saved_theme == "light" else "dark"

    qp_page = st.query_params.get("page")
    qp_theme = st.query_params.get("theme")
    if qp_theme in ("dark", "light"):
        st.session_state["qt_theme"] = qp_theme
    st.session_state["qt_nav_page"] = qp_page if qp_page in NAV_ITEMS_BY_PAGE else "Overview"

    st.session_state["qt_timeout_ms"] = (
        int(saved_timeout) if saved_timeout and saved_timeout.isdigit() else settings.default_statement_timeout_ms
    )
    st.session_state["qt_max_rows"] = (
        int(saved_rows) if saved_rows and saved_rows.isdigit() else settings.default_max_rows
    )
    st.session_state["qt_explain_analyze"] = saved_explain_mode != "false"
    st.session_state["qt_history_limit"] = (
        int(saved_hist_limit) if saved_hist_limit and saved_hist_limit.isdigit() else 200
    )

    st.session_state["qt_sql_tabs"] = [
        {"name": "Query 1", "sql": SAMPLE_QUERIES[0].sql},
        {"name": "Query 2 (Baseline)", "sql": SAMPLE_QUERIES[6].sql},
        {"name": "Query 3 (Optimized)", "sql": SAMPLE_QUERIES[6].suggested_optimization or SAMPLE_QUERIES[1].sql},
    ]
    st.session_state["qt_active_sql_tab"] = 0
    st.session_state["qt_editor_sql"] = SAMPLE_QUERIES[0].sql
    st.session_state["qt_editor_seq"] = 1
    st.session_state["qt_editor_view_tab"] = 0

    st.session_state["qt_last_exec"] = None
    st.session_state["qt_last_analysis"] = None
    st.session_state["qt_selected_plan_node_id"] = 0
    st.session_state["qt_last_benchmark"] = None
    st.session_state["qt_baseline_snapshot"] = None
    st.session_state["qt_candidate_snapshot"] = None
    st.session_state["qt_last_comparison"] = None
    st.session_state["qt_bench_sql_a"] = SAMPLE_QUERIES[6].sql
    st.session_state["qt_bench_sql_b"] = SAMPLE_QUERIES[6].suggested_optimization or SAMPLE_QUERIES[6].sql
    st.session_state["qt_initialized"] = True

    # Attempt fast silent initial connect ONLY if env vars or .env configured explicitly
    has_env_target = bool(
        (PROJECT_ROOT / ".env").exists()
        or os.getenv("PGHOST")
        or os.getenv("PGPORT")
        or os.getenv("PGUSER")
        or settings.connection.password
    )
    if has_env_target:
        boot_cfg = ConnectionConfig(
            host=settings.connection.host,
            port=settings.connection.port,
            database=settings.connection.database,
            username=settings.connection.username,
            password=settings.connection.password,
            sslmode=settings.connection.sslmode,
            connect_timeout=min(settings.connection.connect_timeout, 2),
        )
        status = conn_mgr.connect(boot_cfg)
        if status.connected:
            try:
                conn_mgr.fetch_catalog()
            except Exception:
                pass

    recent_success = store.list_analyses(limit=1, status_filter="success")
    if recent_success and recent_success[0].get("plan_json"):
        load_history_record_into_state(recent_success[0])

    _hydrate_saved_benchmark(store)
    _hydrate_saved_comparison(store)


def load_history_record_into_state(record: dict) -> None:
    """Hydrate a historical SQLite analysis row back into active workspace views."""
    sql_text = record.get("sql_text", "")
    set_active_editor_sql(sql_text)
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
    st.session_state["qt_selected_plan_node_id"] = 0
