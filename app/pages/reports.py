"""Optimization Reports, Benchmark Exports & Export History page for QueryTrellis."""
from __future__ import annotations

import html
import json
import statistics
from typing import Any

import pandas as pd
import streamlit as st

from app.components.topbar import render_topbar
from app.components.ui_primitives import (
    TelemetryCardData,
    render_empty_state,
    render_section_header,
    render_telemetry_row,
)
from app.state import load_history_record_into_state, navigate_to
from src.advisor.index_recommender import IndexRecommendation
from src.benchmark.comparator import QueryComparisonResult
from src.benchmark.runner import BenchmarkIteration, BenchmarkSummary
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.explain.plan_analyzer import analyze_explain_plan
from src.explain.plan_parser import parse_explain_json
from src.reporting.report_generator import (
    build_benchmark_csv,
    build_html_report,
    build_json_report,
    build_plan_nodes_csv,
)
from src.services.workbench_service import FullAnalysisBundle
from src.sql_analysis.antipattern_detector import AntiPatternFinding
from src.sql_analysis.parser_validator import validate_read_only_sql


def _bundle_from_record(record: dict[str, Any], conn_mgr: ConnectionManager) -> FullAnalysisBundle:
    sql_text = record.get("sql_text", "")
    validation = validate_read_only_sql(sql_text)
    parsed_plan = None
    insights = []
    if record.get("plan_json"):
        try:
            parsed_plan = parse_explain_json(record["plan_json"])
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
    return FullAnalysisBundle(
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


def _benchmark_from_record(b: dict[str, Any]) -> BenchmarkSummary:
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
    return BenchmarkSummary(
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


def _comparison_from_record(c: dict[str, Any]) -> QueryComparisonResult:
    cd = c.get("comparison") or {}
    return QueryComparisonResult(
        baseline_label=cd.get("baseline_label", "Baseline (A)"),
        optimized_label=cd.get("optimized_label", "Optimized (B)"),
        baseline_sql=cd.get("baseline_sql", c.get("baseline_sql", "")),
        optimized_sql=cd.get("optimized_sql", c.get("optimized_sql", "")),
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


def render_reports_page() -> None:
    """Render report builder, benchmark/comparison exports, and audit log."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]

    rep_history = store.list_reports(limit=100)
    bench_history = store.list_benchmarks(limit=50)
    comp_history = store.list_comparisons(limit=50)

    render_topbar(
        "Reports",
        right_meta=f"{len(rep_history)} exported log(s)",
        action_label="Open Query Editor",
        action_icon="code",
        on_action=lambda: (navigate_to("Query Editor"), st.rerun()),
    )

    tab_gen, tab_bench, tab_log = st.tabs(
        [
            "Optimization Reports",
            f"Benchmark & A/B Exports ({len(bench_history) + len(comp_history)})",
            f"Export History Log ({len(rep_history)})",
        ]
    )

    # ------------------------------------------------------------------
    # Tab 1: Optimization Reports
    # ------------------------------------------------------------------
    with tab_gen:
        history_rows = store.list_analyses(limit=60, status_filter="success")
        source_options = ["Current Active Session Analysis"] + [
            f"History #{r['id']} ({r['created_at']}) — {(r['sql_text'] or '').splitlines()[0][:46]}"
            for r in history_rows
        ]
        bench_options = ["None / Current Session Benchmark"] + [
            f"Benchmark #{b['id']} — {b['label']} ({b['repeat_count']} runs)"
            for b in bench_history
        ]
        comp_options = ["None / Current Session Comparison"] + [
            f"Comparison #{c['id']} — {c['title']}"
            for c in comp_history
        ]

        s1, s2, s3 = st.columns([1.4, 1.0, 1.0])
        chosen_src = s1.selectbox("Analysis Source", options=source_options, key="qt_rep_src")
        chosen_bench = s2.selectbox("Attach Benchmark", options=bench_options, key="qt_rep_bench_src")
        chosen_comp = s3.selectbox("Attach A/B Comparison", options=comp_options, key="qt_rep_comp_src")

        active_bundle: FullAnalysisBundle | None = st.session_state.get("qt_last_analysis")
        chosen_record: dict[str, Any] | None = None
        if chosen_src != "Current Active Session Analysis":
            chosen_id = int(chosen_src.split("#", 1)[1].split(" ", 1)[0])
            chosen_record = store.get_analysis(chosen_id)
            if chosen_record:
                active_bundle = _bundle_from_record(chosen_record, conn_mgr)

        if active_bundle is None:
            render_empty_state(
                "No Active Query Analysis Selected",
                "Run an analysis in Query Editor or pick a historical record from Analysis Source above.",
                action_label="Open Query Editor",
                action_key="qt_rep_empty_editor",
                on_action=lambda: (navigate_to("Query Editor"), st.rerun()),
            )
            return

        benchmark = st.session_state.get("qt_last_benchmark")
        if chosen_bench != "None / Current Session Benchmark":
            bid = int(chosen_bench.split("#", 1)[1].split(" ", 1)[0])
            b_rec = next((b for b in bench_history if b["id"] == bid), None)
            if b_rec:
                benchmark = _benchmark_from_record(b_rec)

        comparison = st.session_state.get("qt_last_comparison")
        if chosen_comp != "None / Current Session Comparison":
            cid = int(chosen_comp.split("#", 1)[1].split(" ", 1)[0])
            c_rec = next((c for c in comp_history if c["id"] == cid), None)
            if c_rec:
                comparison = _comparison_from_record(c_rec)

        c_title, c_notes = st.columns([1.15, 1.85])
        report_title = c_title.text_input(
            "Report Title",
            value=f"QueryTrellis Optimization Report (Analysis #{active_bundle.analysis_id or 'Session'})",
            key="qt_rep_title_input",
        )
        opt_notes = c_notes.text_area(
            "Engineering Notes (Optional)",
            value="Generated via QueryTrellis local workbench. All credentials omitted.",
            height=78,
            key="qt_rep_notes_input",
        )

        status = conn_mgr.status
        safe_conn_dict = (
            status.config
            if status.connected
            else {"database": "offline_static", "host": "N/A", "port": "N/A", "username": "N/A"}
        )

        html_str = build_html_report(
            title=report_title,
            sql_text=active_bundle.sql_text,
            formatted_sql=active_bundle.formatted_sql,
            connection_info=safe_conn_dict,
            server_version=status.server_version,
            plan=active_bundle.parsed_plan,
            plan_insights=active_bundle.plan_insights,
            antipatterns=active_bundle.antipatterns,
            index_recommendations=active_bundle.index_recommendations,
            benchmark=benchmark,
            comparison=comparison,
            optimization_notes=opt_notes,
        )
        json_str = build_json_report(
            title=report_title,
            sql_text=active_bundle.sql_text,
            formatted_sql=active_bundle.formatted_sql,
            connection_info=safe_conn_dict,
            server_version=status.server_version,
            plan=active_bundle.parsed_plan,
            plan_insights=active_bundle.plan_insights,
            antipatterns=active_bundle.antipatterns,
            index_recommendations=active_bundle.index_recommendations,
            benchmark=benchmark,
            comparison=comparison,
            optimization_notes=opt_notes,
        )

        db_label = status.current_database if status.connected else "offline"

        render_telemetry_row(
            [
                TelemetryCardData(
                    label="Report Scope",
                    value=f"Analysis #{active_bundle.analysis_id or 'Live'}",
                    subtext="Sanitized (zero passwords)",
                    accent=True,
                ),
                TelemetryCardData(
                    label="Plan Nodes",
                    value=f"{len(active_bundle.parsed_plan.all_nodes)}" if active_bundle.parsed_plan else "None",
                    subtext="EXPLAIN JSON included" if active_bundle.parsed_plan else "No plan attached",
                ),
                TelemetryCardData(
                    label="Anti-Patterns",
                    value=f"{len(active_bundle.antipatterns)}",
                    subtext="Static + catalog checks",
                ),
                TelemetryCardData(
                    label="Advisory Indexes",
                    value=f"{len(active_bundle.index_recommendations)}",
                    subtext="Copyable CREATE INDEX DDL",
                ),
                TelemetryCardData(
                    label="Benchmark / A-B",
                    value="Attached" if (benchmark or comparison) else "None",
                    subtext=f"{benchmark.label if benchmark else ''}{' + A/B' if comparison else ''}".strip(" +") or "Optional",
                ),
            ]
        )

        d1, d2, d3, d4 = st.columns(4)
        if d1.download_button(
            "Download HTML Report",
            data=html_str.encode("utf-8"),
            file_name="querytrellis_report.html",
            mime="text/html",
            type="primary",
            width="stretch",
            key="qt_rep_dl_html",
        ):
            store.save_report_record(
                title=report_title,
                database_name=db_label,
                fmt="HTML",
                analysis_id=active_bundle.analysis_id,
            )

        if d2.download_button(
            "Download JSON Report",
            data=json_str.encode("utf-8"),
            file_name="querytrellis_report.json",
            mime="application/json",
            width="stretch",
            key="qt_rep_dl_json",
        ):
            store.save_report_record(
                title=report_title,
                database_name=db_label,
                fmt="JSON",
                analysis_id=active_bundle.analysis_id,
            )

        if active_bundle.parsed_plan is not None:
            plan_csv = build_plan_nodes_csv(active_bundle.parsed_plan)
            if d3.download_button(
                "Download Plan Nodes CSV",
                data=plan_csv.encode("utf-8"),
                file_name="querytrellis_plan_nodes.csv",
                mime="text/csv",
                width="stretch",
                key="qt_rep_dl_plancsv",
            ):
                store.save_report_record(
                    title=report_title,
                    database_name=db_label,
                    fmt="PLAN_CSV",
                    analysis_id=active_bundle.analysis_id,
                )
        else:
            d3.button("Plan Nodes CSV (Unavailable)", disabled=True, width="stretch", key="qt_rep_no_plancsv")

        if benchmark is not None and benchmark.success:
            bench_csv = build_benchmark_csv(benchmark)
            if d4.download_button(
                "Download Benchmark CSV",
                data=bench_csv.encode("utf-8"),
                file_name="querytrellis_benchmark.csv",
                mime="text/csv",
                width="stretch",
                key="qt_rep_dl_benchcsv",
            ):
                store.save_report_record(
                    title=report_title,
                    database_name=db_label,
                    fmt="BENCHMARK_CSV",
                    analysis_id=active_bundle.analysis_id,
                )
        else:
            d4.button("Benchmark CSV (Unavailable)", disabled=True, width="stretch", key="qt_rep_no_benchcsv")

        if chosen_record is not None:
            if st.button("Set This Analysis as Active Workspace Query", key="qt_rep_pin_active"):
                load_history_record_into_state(chosen_record)
                st.toast(f"Loaded Analysis #{chosen_record['id']} into active workspace.")

        render_section_header("Sanitized HTML Report Preview")
        st.components.v1.html(html_str, height=620, scrolling=True)

    # ------------------------------------------------------------------
    # Tab 2: Benchmark & Comparison Exports
    # ------------------------------------------------------------------
    with tab_bench:
        render_section_header("Recorded Multi-Run Benchmarks", f"{len(bench_history)} stored run(s)")
        if not bench_history:
            render_empty_state(
                "No Benchmark Runs Stored",
                "Execute a benchmark in Benchmark Lab to archive multi-run timings and buffer metrics.",
                action_label="Open Benchmark Lab",
                action_key="qt_rep_open_bl",
                on_action=lambda: (navigate_to("Benchmark Lab"), st.rerun()),
            )
        else:
            b_df = pd.DataFrame(
                [
                    {
                        "ID": b["id"],
                        "Created": b["created_at"],
                        "Label": b["label"],
                        "Database": b["database_name"],
                        "Runs": b["repeat_count"],
                        "PG Median (ms)": f"{b['pg_exec_median_ms']:.3f}" if b.get("pg_exec_median_ms") is not None else "Unavailable",
                        "Client Median (ms)": f"{b['median_ms']:.3f}",
                        "Client P95 (ms)": f"{b['p95_ms']:.3f}",
                    }
                    for b in bench_history
                ]
            )
            st.dataframe(b_df, width="stretch", hide_index=True)

            pick_b = st.selectbox(
                "Export Benchmark Iterations CSV",
                options=[f"#{b['id']} — {b['label']}" for b in bench_history],
                key="qt_rep_export_bench_pick",
            )
            sel_bid = int(pick_b.split("#", 1)[1].split(" ", 1)[0])
            sel_b_rec = next(b for b in bench_history if b["id"] == sel_bid)
            sel_b_summary = _benchmark_from_record(sel_b_rec)
            st.download_button(
                f"Download Benchmark #{sel_bid} CSV",
                data=build_benchmark_csv(sel_b_summary).encode("utf-8"),
                file_name=f"querytrellis_benchmark_{sel_bid}.csv",
                mime="text/csv",
                key="qt_rep_dl_specific_b",
            )

        render_section_header("Saved Before & After Comparisons", f"{len(comp_history)} comparison(s)")
        if not comp_history:
            render_empty_state(
                "No Saved Comparisons",
                "Compare baseline vs rewritten SQL statements in Benchmark Lab to generate exportable diffs.",
            )
        else:
            c_df = pd.DataFrame(
                [
                    {
                        "ID": c["id"],
                        "Created": c["created_at"],
                        "Title": c["title"],
                        "Database": c["database_name"],
                        "Verdict": (c.get("comparison") or {}).get("verdict", "Inconclusive"),
                        "Baseline (ms)": (c.get("comparison") or {}).get("baseline_time_ms") or "Unavailable",
                        "Optimized (ms)": (c.get("comparison") or {}).get("optimized_time_ms") or "Unavailable",
                        "Change (%)": (
                            f"{(c.get('comparison') or {})['pct_change']:+.1f}%"
                            if (c.get("comparison") or {}).get("pct_change") is not None
                            else "Unavailable"
                        ),
                    }
                    for c in comp_history
                ]
            )
            st.dataframe(c_df, width="stretch", hide_index=True)

            pick_c = st.selectbox(
                "Export Comparison Diff JSON",
                options=[f"#{c['id']} — {c['title']}" for c in comp_history],
                key="qt_rep_export_comp_pick",
            )
            sel_cid = int(pick_c.split("#", 1)[1].split(" ", 1)[0])
            sel_c_rec = next(c for c in comp_history if c["id"] == sel_cid)
            st.download_button(
                f"Download Comparison #{sel_cid} JSON",
                data=json.dumps(sel_c_rec, indent=2, default=str).encode("utf-8"),
                file_name=f"querytrellis_comparison_{sel_cid}.json",
                mime="application/json",
                key="qt_rep_dl_specific_c",
            )

    # ------------------------------------------------------------------
    # Tab 3: Export History Log
    # ------------------------------------------------------------------
    with tab_log:
        render_section_header("Logged Report Exports", f"{len(rep_history)} export(s) recorded")
        if not rep_history:
            render_empty_state(
                "No Exports Recorded Yet",
                "Download an HTML, JSON, or CSV report from the Optimization Reports tab to record it here.",
            )
        else:
            esc = html.escape
            rows_html = "".join(
                "<tr>"
                f"<td class='qt-mono'>#{r['id']}</td>"
                f"<td class='qt-mono'>{esc(str(r['created_at']))}</td>"
                f"<td>{esc(str(r['title']))}</td>"
                f"<td class='qt-mono'>{esc(str(r['database_name']))}</td>"
                f"<td><span class='qt-pill qt-pill-accent'>{esc(str(r['format']))}</span></td>"
                f"<td class='qt-mono'>{esc(str(r['analysis_id'])) if r.get('analysis_id') else 'Session'}</td>"
                "</tr>"
                for r in rep_history
            )
            st.markdown(
                "<div class='qt-table-wrap'><table class='qt-table'>"
                "<thead><tr><th>ID</th><th>Exported At</th><th>Report Title</th><th>Database</th><th>Format</th><th>Analysis ID</th></tr></thead>"
                f"<tbody>{rows_html}</tbody></table></div>",
                unsafe_allow_html=True,
            )
