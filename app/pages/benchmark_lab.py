"""Benchmark Lab & Before/After Query Comparison page for QueryTrellis."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.topbar import render_topbar
from app.components.ui_primitives import (
    TelemetryCardData,
    render_copy_button,
    render_empty_state,
    render_error_state,
    render_section_header,
    render_telemetry_row,
)
from app.state import navigate_to
from app.theme import apply_plotly_theme, get_active_theme
from src.benchmark.comparator import QueryComparisonResult, QuerySnapshot, compare_queries
from src.benchmark.runner import METHODOLOGY_NOTES, BenchmarkSummary, run_query_benchmark
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.services.workbench_service import analyze_query_end_to_end
from src.sql_analysis.sample_queries import SAMPLE_QUERIES


def _render_benchmark_stats_and_chart(bench: BenchmarkSummary) -> None:
    if not bench.success:
        render_error_state("Benchmark Failed", bench.error_message)
        return

    if bench.interrupted:
        st.warning(bench.error_message)

    theme = get_active_theme()

    render_telemetry_row(
        [
            TelemetryCardData(
                label="PG Exec Median",
                value=f"{bench.pg_exec_median_ms:.3f} ms" if bench.pg_exec_median_ms is not None else "Unavailable",
                subtext="Server-side EXPLAIN ANALYZE",
                accent=True,
                tone="ok" if bench.pg_exec_median_ms is not None else "neutral",
            ),
            TelemetryCardData(
                label="PG Exec Mean",
                value=f"{bench.pg_exec_mean_ms:.3f} ms" if bench.pg_exec_mean_ms is not None else "Unavailable",
                subtext=(
                    f"Min {bench.pg_exec_min_ms:.2f} / Max {bench.pg_exec_max_ms:.2f}"
                    if bench.pg_exec_min_ms is not None and bench.pg_exec_max_ms is not None
                    else "Server min/max unavailable"
                ),
            ),
            TelemetryCardData(
                label="Client Median",
                value=f"{bench.median_ms:.3f} ms",
                subtext=f"P95: {bench.p95_ms:.3f} ms",
            ),
            TelemetryCardData(
                label="Client Range",
                value=f"{bench.min_ms:.2f} – {bench.max_ms:.2f} ms",
                subtext=f"{bench.repeat_count} measured iteration(s)",
            ),
            TelemetryCardData(
                label="Client Mean (Stdev)",
                value=f"{bench.mean_ms:.2f} ms",
                subtext=f"±{bench.stdev_ms:.3f} ms variance",
            ),
        ]
    )

    all_its = ([bench.warmup_iteration] if bench.warmup_iteration else []) + bench.iterations
    tbl_rows = [
        {
            "Run": "Warmup (Excluded)" if it.is_warmup else f"Run {it.run_index}",
            "Client Wall (ms)": round(it.client_wall_ms, 3),
            "PG Execution (ms)": (
                f"{it.pg_execution_ms:.3f}" if it.pg_execution_ms is not None else "Unavailable"
            ),
            "PG Planning (ms)": (
                f"{it.pg_planning_ms:.3f}" if it.pg_planning_ms is not None else "Unavailable"
            ),
            "Rows": it.rows_returned if it.rows_returned is not None else "Unavailable",
            "Shared Hits": it.shared_hit_blocks if it.shared_hit_blocks is not None else "Unavailable",
            "Shared Reads": it.shared_read_blocks if it.shared_read_blocks is not None else "Unavailable",
        }
        for it in all_its
    ]

    col_tbl, col_fig = st.columns([1.05, 1.15], gap="medium")
    with col_tbl:
        st.dataframe(pd.DataFrame(tbl_rows), width="stretch", hide_index=True)

    with col_fig:
        measured = bench.iterations
        x_labels = [f"Run {it.run_index}" for it in measured]
        pg_y = [it.pg_execution_ms for it in measured]
        cli_y = [it.client_wall_ms for it in measured]

        fig = go.Figure()
        if any(v is not None for v in pg_y):
            fig.add_trace(
                go.Scatter(
                    x=x_labels,
                    y=pg_y,
                    mode="lines+markers",
                    name="PostgreSQL Exec (ms)",
                    line={"color": theme.accent, "width": 2.4},
                    marker={"size": 7, "color": theme.accent},
                    connectgaps=False,
                )
            )
        fig.add_trace(
            go.Scatter(
                x=x_labels,
                y=cli_y,
                mode="lines+markers",
                name="Client Duration (ms)",
                line={"color": theme.bar_secondary, "width": 2.0, "dash": "dash"},
                marker={"size": 6, "color": theme.bar_secondary},
            )
        )
        fig.update_xaxes(title_text="Iteration")
        fig.update_yaxes(title_text="Duration (ms)")
        apply_plotly_theme(
            fig,
            theme,
            height=305,
            title=f"Per-Run Latency Profile — {bench.label}",
            margin={"l": 12, "r": 16, "t": 62, "b": 38},
            show_legend=True,
        )
        st.plotly_chart(fig, width="stretch")


def _build_ab_comparison_bar(comp: QueryComparisonResult) -> go.Figure:
    theme = get_active_theme()
    fig = go.Figure(
        go.Bar(
            x=[comp.baseline_label, comp.optimized_label],
            y=[comp.baseline_time_ms, comp.optimized_time_ms],
            marker_color=[theme.bar_secondary, theme.accent],
            text=[
                f"{comp.baseline_time_ms:.3f} ms" if comp.baseline_time_ms is not None else "Unavailable",
                f"{comp.optimized_time_ms:.3f} ms" if comp.optimized_time_ms is not None else "Unavailable",
            ],
            textposition="auto",
        )
    )
    fig.update_yaxes(title_text="Measured Time (ms)")
    return apply_plotly_theme(
        fig,
        theme,
        height=285,
        title="Baseline vs. Candidate Execution Time (Lower is Faster)",
        show_legend=False,
    )


def _build_ab_trajectory_or_cost_chart(
    comp: QueryComparisonResult,
    snap_a: QuerySnapshot | None,
    snap_b: QuerySnapshot | None,
) -> go.Figure | None:
    theme = get_active_theme()
    has_bench_runs = (
        snap_a is not None
        and snap_b is not None
        and snap_a.benchmark is not None
        and snap_b.benchmark is not None
        and snap_a.benchmark.success
        and snap_b.benchmark.success
        and snap_a.sql_text == comp.baseline_sql
        and snap_b.sql_text == comp.optimized_sql
    )
    if has_bench_runs:
        assert snap_a and snap_b and snap_a.benchmark and snap_b.benchmark
        its_a = snap_a.benchmark.iterations
        its_b = snap_b.benchmark.iterations
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=[f"Run {i.run_index}" for i in its_a],
                y=[i.pg_execution_ms if i.pg_execution_ms is not None else i.client_wall_ms for i in its_a],
                mode="lines+markers",
                name=comp.baseline_label,
                line={"color": theme.bar_secondary, "width": 2.2},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[f"Run {i.run_index}" for i in its_b],
                y=[i.pg_execution_ms if i.pg_execution_ms is not None else i.client_wall_ms for i in its_b],
                mode="lines+markers",
                name=comp.optimized_label,
                line={"color": theme.accent, "width": 2.5},
            )
        )
        fig.update_xaxes(title_text="Measured Run")
        fig.update_yaxes(title_text="Execution Time (ms)")
        return apply_plotly_theme(
            fig,
            theme,
            height=285,
            title="Per-Iteration Execution Profile (A vs B)",
            margin={"l": 12, "r": 16, "t": 62, "b": 38},
            show_legend=True,
        )

    if comp.baseline_cost is not None and comp.optimized_cost is not None:
        fig = go.Figure(
            go.Bar(
                x=[comp.baseline_label, comp.optimized_label],
                y=[comp.baseline_cost, comp.optimized_cost],
                marker_color=[theme.bar_secondary, theme.info],
                text=[f"{comp.baseline_cost:,.1f}", f"{comp.optimized_cost:,.1f}"],
                textposition="auto",
            )
        )
        fig.update_yaxes(title_text="Estimated Planner Cost")
        return apply_plotly_theme(
            fig,
            theme,
            height=285,
            title="Estimated Planner Cost Comparison",
            show_legend=False,
        )
    return None


def render_benchmark_lab_page() -> None:
    """Render repeatable query benchmark runner and Before/After optimization comparison studio."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    max_repeats = int(st.session_state["qt_settings"].benchmark_max_repeats)
    timeout_ms = int(st.session_state.get("qt_timeout_ms", 5000))

    render_topbar(
        "Benchmark Lab",
        right_meta=f"Max repeats: {max_repeats} · Warmup supported",
        action_label="Open Query Editor",
        action_icon="code",
        on_action=lambda: (navigate_to("Query Editor"), st.rerun()),
    )

    with st.expander("Measurement Methodology & Cache Caveats", expanded=False):
        bullets = "".join(f"<li>{html.escape(note)}</li>" for note in METHODOLOGY_NOTES)
        st.markdown(
            f"<ul style='margin:0;padding-left:1.2rem;font-size:0.79rem;color:var(--qt-text-secondary);line-height:1.5;'>{bullets}</ul>",
            unsafe_allow_html=True,
        )

    tab_compare, tab_single = st.tabs(
        ["Before & After Optimization Comparison", "Single Query Benchmark"]
    )

    # ------------------------------------------------------------------
    # Tab 1: Before & After Optimization Comparison
    # ------------------------------------------------------------------
    with tab_compare:
        paired_samples = [s for s in SAMPLE_QUERIES if s.suggested_optimization]
        pair_titles = [s.title for s in paired_samples]

        p_col1, p_col2 = st.columns([2.6, 1.0], vertical_alignment="bottom")
        chosen_pair_title = p_col1.selectbox(
            "Built-in Before / After Optimization Pair",
            options=pair_titles,
            key="qt_pair_picker",
        )
        if p_col2.button("Load Pair into A/B Editors", key="qt_bl_load_pair", width="stretch"):
            pair = next(s for s in paired_samples if s.title == chosen_pair_title)
            opt_sql = pair.suggested_optimization or pair.sql
            st.session_state["qt_pending_bench_a"] = pair.sql
            st.session_state["qt_pending_bench_b"] = opt_sql
            st.session_state["qt_bench_sql_a"] = pair.sql
            st.session_state["qt_bench_sql_b"] = opt_sql
            st.rerun()

        # Always apply pending A/B updates BEFORE instantiating text_areas
        if "qt_pending_bench_a" in st.session_state:
            st.session_state["qt_cmp_sql_a"] = st.session_state.pop("qt_pending_bench_a")
        elif "qt_cmp_sql_a" not in st.session_state:
            st.session_state["qt_cmp_sql_a"] = st.session_state.get("qt_bench_sql_a", "")

        if "qt_pending_bench_b" in st.session_state:
            st.session_state["qt_cmp_sql_b"] = st.session_state.pop("qt_pending_bench_b")
        elif "qt_cmp_sql_b" not in st.session_state:
            st.session_state["qt_cmp_sql_b"] = st.session_state.get("qt_bench_sql_b", "")

        col_a, col_b = st.columns(2, gap="medium")
        with col_a:
            ca_hdr, ca_cpy = st.columns([2.2, 1.0], vertical_alignment="center")
            ca_hdr.markdown("**Original Query (Baseline A)**")
            sql_a = st.text_area(
                "Original Query (Baseline A)",
                height=210,
                key="qt_cmp_sql_a",
                label_visibility="collapsed",
            )
            st.session_state["qt_bench_sql_a"] = sql_a
            with ca_cpy:
                render_copy_button(sql_a, key="qt_bl_copy_a", label="Copy A")

        with col_b:
            cb_hdr, cb_cpy = st.columns([2.2, 1.0], vertical_alignment="center")
            cb_hdr.markdown("**Candidate Rewrite (Optimized B)**")
            sql_b = st.text_area(
                "Candidate Rewrite (Optimized B)",
                height=210,
                key="qt_cmp_sql_b",
                label_visibility="collapsed",
            )
            st.session_state["qt_bench_sql_b"] = sql_b
            with cb_cpy:
                render_copy_button(sql_b, key="qt_bl_copy_b", label="Copy B")

        c_title, c_reps, c_run_cmp, c_snap_cmp = st.columns([1.85, 0.75, 1.25, 1.2], vertical_alignment="bottom")
        cmp_title = c_title.text_input("Comparison Label", value="Optimization A/B Comparison", key="qt_bl_cmp_title")
        cmp_reps = c_reps.number_input("Runs per Query", min_value=2, max_value=15, value=4, step=1, key="qt_bl_cmp_reps")
        run_both_btn = c_run_cmp.button(
            "Analyze & Benchmark Both",
            key="qt_bl_run_both",
            type="primary",
            width="stretch",
            disabled=not conn_mgr.is_connected,
        )
        compare_saved_btn = c_snap_cmp.button(
            "Compare Saved Snapshots",
            key="qt_bl_cmp_saved",
            width="stretch",
            disabled=(
                st.session_state.get("qt_baseline_snapshot") is None
                or st.session_state.get("qt_candidate_snapshot") is None
            ),
        )

        if not conn_mgr.is_connected:
            st.markdown(
                "<div class='qt-banner qt-banner-warn'>Connect PostgreSQL in Settings to execute live A/B benchmarks.</div>",
                unsafe_allow_html=True,
            )

        if run_both_btn and conn_mgr.is_connected:
            with st.spinner("Running EXPLAIN ANALYZE & multi-run timings on Baseline (A) and Candidate (B)..."):
                bundle_a = analyze_query_end_to_end(
                    sql_a,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    analyze_explain=True,
                    buffers=True,
                    timeout_ms=timeout_ms,
                    persist=True,
                )
                bench_a = run_query_benchmark(
                    conn_mgr.get_connection(),
                    sql_a,
                    label="Baseline (A)",
                    repeat_count=int(cmp_reps),
                    include_warmup=True,
                    timeout_ms=timeout_ms,
                )
                bundle_b = analyze_query_end_to_end(
                    sql_b,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    analyze_explain=True,
                    buffers=True,
                    timeout_ms=timeout_ms,
                    persist=True,
                )
                bench_b = run_query_benchmark(
                    conn_mgr.get_connection(),
                    sql_b,
                    label="Optimized (B)",
                    repeat_count=int(cmp_reps),
                    include_warmup=True,
                    timeout_ms=timeout_ms,
                )

                if not bundle_a.validation.is_read_only or not bundle_b.validation.is_read_only:
                    render_error_state("Validation Error", bundle_a.error_message or bundle_b.error_message)
                elif not bench_a.success or not bench_b.success:
                    render_error_state("Benchmark Error", bench_a.error_message or bench_b.error_message)
                else:
                    snap_a = QuerySnapshot(
                        label="Baseline (A)",
                        sql_text=sql_a,
                        plan=bundle_a.parsed_plan,
                        benchmark=bench_a,
                        antipatterns=bundle_a.antipatterns,
                    )
                    snap_b = QuerySnapshot(
                        label="Optimized (B)",
                        sql_text=sql_b,
                        plan=bundle_b.parsed_plan,
                        benchmark=bench_b,
                        antipatterns=bundle_b.antipatterns,
                    )
                    comp = compare_queries(snap_a, snap_b)
                    st.session_state["qt_baseline_snapshot"] = snap_a
                    st.session_state["qt_candidate_snapshot"] = snap_b
                    st.session_state["qt_last_comparison"] = comp
                    store.save_comparison(
                        title=cmp_title.strip() or "Query Comparison",
                        database_name=conn_mgr.status.current_database,
                        baseline_sql=sql_a,
                        optimized_sql=sql_b,
                        comparison_data=comp.to_dict(),
                        baseline_analysis_id=bundle_a.analysis_id,
                        optimized_analysis_id=bundle_b.analysis_id,
                    )

        if compare_saved_btn:
            snap_a = st.session_state["qt_baseline_snapshot"]
            snap_b = st.session_state["qt_candidate_snapshot"]
            st.session_state["qt_last_comparison"] = compare_queries(snap_a, snap_b)

        comp_res: QueryComparisonResult | None = st.session_state.get("qt_last_comparison")
        if comp_res is not None:
            render_section_header("Comparison Verdict & Timing Delta", comp_res.verdict)
            v_cls = (
                "qt-banner"
                if comp_res.verdict == "Improved"
                else (
                    "qt-banner qt-banner-err"
                    if comp_res.verdict in ("Regressed", "Row Count Mismatch")
                    else "qt-banner qt-banner-warn"
                )
            )
            st.markdown(
                f"<div class='{v_cls}'><strong>{html.escape(comp_res.verdict)}:</strong> {html.escape(comp_res.verdict_summary)}</div>",
                unsafe_allow_html=True,
            )

            speedup_txt = f"{comp_res.speedup_factor:.2f}x" if comp_res.speedup_factor is not None else "Unavailable"
            pct_txt = f"{comp_res.pct_change:+.1f}%" if comp_res.pct_change is not None else "Unavailable"
            row_eq_txt = (
                "Exact Match"
                if comp_res.row_count_matches is True
                else ("Mismatch" if comp_res.row_count_matches is False else "Unavailable")
            )
            render_telemetry_row(
                [
                    TelemetryCardData(
                        label="Baseline Exec",
                        value=f"{comp_res.baseline_time_ms:.3f} ms" if comp_res.baseline_time_ms is not None else "Unavailable",
                        subtext="PG median / exec timing",
                    ),
                    TelemetryCardData(
                        label="Candidate Exec",
                        value=f"{comp_res.optimized_time_ms:.3f} ms" if comp_res.optimized_time_ms is not None else "Unavailable",
                        subtext=f"Delta: {pct_txt}",
                        accent=True,
                        tone="ok" if comp_res.verdict == "Improved" else ("err" if comp_res.verdict == "Regressed" else "neutral"),
                    ),
                    TelemetryCardData(
                        label="Speedup Factor",
                        value=speedup_txt,
                        subtext=f"Diff: {comp_res.time_diff_ms:+.3f} ms" if comp_res.time_diff_ms is not None else "No diff available",
                    ),
                    TelemetryCardData(
                        label="Planner Cost B",
                        value=f"{comp_res.optimized_cost:,.2f}" if comp_res.optimized_cost is not None else "Unavailable",
                        subtext=(
                            f"Cost delta: {comp_res.cost_pct_change:+.1f}%"
                            if comp_res.cost_pct_change is not None
                            else "Cost delta unavailable"
                        ),
                    ),
                    TelemetryCardData(
                        label="Row Equivalence",
                        value=row_eq_txt,
                        subtext=(
                            f"{comp_res.baseline_rows:,} vs {comp_res.optimized_rows:,} row(s)"
                            if comp_res.baseline_rows is not None and comp_res.optimized_rows is not None
                            else "Row counts unavailable"
                        ),
                        tone="ok" if comp_res.row_count_matches is True else ("err" if comp_res.row_count_matches is False else "neutral"),
                    ),
                ]
            )

            snap_a = st.session_state.get("qt_baseline_snapshot")
            snap_b = st.session_state.get("qt_candidate_snapshot")
            c_ch1, c_ch2 = st.columns(2, gap="medium")
            with c_ch1:
                if comp_res.baseline_time_ms is not None and comp_res.optimized_time_ms is not None:
                    st.plotly_chart(_build_ab_comparison_bar(comp_res), width="stretch")
                else:
                    render_empty_state("Timing Chart Unavailable", "Run live benchmark to compare execution timings.")
            with c_ch2:
                sec_fig = _build_ab_trajectory_or_cost_chart(comp_res, snap_a, snap_b)
                if sec_fig is not None:
                    st.plotly_chart(sec_fig, width="stretch")

            render_section_header("Plan, Index & Anti-Pattern Structural Diff")
            esc = html.escape
            diff_rows = [
                ("Plan Nodes Added", ", ".join(comp_res.nodes_added) or "None"),
                ("Plan Nodes Removed", ", ".join(comp_res.nodes_removed) or "None"),
                ("Indexes Added in Candidate", ", ".join(comp_res.indexes_added) or "None"),
                ("Indexes Removed in Candidate", ", ".join(comp_res.indexes_removed) or "None"),
                ("Anti-Patterns Resolved", ", ".join(comp_res.resolved_antipatterns) or "None"),
                ("Remaining Anti-Patterns", ", ".join(comp_res.remaining_antipatterns) or "None"),
                ("Newly Introduced Anti-Patterns", ", ".join(comp_res.introduced_antipatterns) or "None"),
            ]
            trs = "".join(
                f"<tr><td style='width:34%;font-weight:600;color:var(--qt-text-secondary);'>{esc(k)}</td>"
                f"<td class='qt-mono' style='font-size:0.79rem;'>{esc(v)}</td></tr>"
                for k, v in diff_rows
            )
            st.markdown(
                f"<div class='qt-table-wrap'><table class='qt-table'><tbody>{trs}</tbody></table></div>",
                unsafe_allow_html=True,
            )

    # ------------------------------------------------------------------
    # Tab 2: Single Query Multi-Run Benchmark
    # ------------------------------------------------------------------
    with tab_single:
        if "qt_pending_single_bench_sql" in st.session_state:
            st.session_state["qt_single_bench_input"] = st.session_state.pop("qt_pending_single_bench_sql")
        elif "qt_single_bench_input" not in st.session_state:
            st.session_state["qt_single_bench_input"] = st.session_state.get("qt_editor_sql", "")

        b_col1, b_col2 = st.columns([2.5, 1.0], vertical_alignment="center")
        with b_col1:
            if st.button("Load Active Query Editor SQL", key="btn_load_editor_to_bench"):
                st.session_state["qt_pending_single_bench_sql"] = st.session_state.get("qt_editor_sql", "")
                st.rerun()
        bench_sql = st.text_area(
            "SQL Statement to Benchmark",
            height=180,
            key="qt_single_bench_input",
        )
        with b_col2:
            render_copy_button(bench_sql, key="qt_bl_copy_single", label="Copy SQL")

        c_lbl, c_rep, c_warm, c_go = st.columns([1.6, 0.75, 1.05, 1.05], vertical_alignment="bottom")
        bench_label = c_lbl.text_input("Benchmark Label", value="Current Query Run", key="qt_bl_single_label")
        repeats = c_rep.number_input("Repeat Count", min_value=2, max_value=max_repeats, value=5, step=1, key="qt_bl_single_reps")
        include_warmup = c_warm.checkbox("Exclude 1 Warmup Run", value=True, key="qt_bl_single_warm")
        run_btn = c_go.button(
            "Run Benchmark",
            key="qt_bl_single_run",
            type="primary",
            width="stretch",
            disabled=not conn_mgr.is_connected,
        )

        if not conn_mgr.is_connected:
            st.markdown(
                "<div class='qt-banner qt-banner-warn'>Connect PostgreSQL in Settings to execute multi-run benchmarks.</div>",
                unsafe_allow_html=True,
            )

        if run_btn and conn_mgr.is_connected:
            with st.spinner(f"Executing {int(repeats)} timed read-only benchmark runs..."):
                summary = run_query_benchmark(
                    conn_mgr.get_connection(),
                    bench_sql,
                    label=bench_label.strip() or "Query Benchmark",
                    repeat_count=int(repeats),
                    include_warmup=include_warmup,
                    timeout_ms=timeout_ms,
                )
            st.session_state["qt_last_benchmark"] = summary
            if summary.success:
                store.save_benchmark(
                    label=summary.label,
                    database_name=conn_mgr.status.current_database,
                    sql_text=summary.sql_text,
                    sql_hash=summary.sql_hash,
                    repeat_count=summary.repeat_count,
                    warmup_used=summary.warmup_used,
                    min_ms=summary.min_ms,
                    max_ms=summary.max_ms,
                    mean_ms=summary.mean_ms,
                    median_ms=summary.median_ms,
                    p95_ms=summary.p95_ms,
                    pg_exec_median_ms=summary.pg_exec_median_ms,
                    iterations=[
                        {
                            "run_index": i.run_index,
                            "client_wall_ms": i.client_wall_ms,
                            "pg_planning_ms": i.pg_planning_ms,
                            "pg_execution_ms": i.pg_execution_ms,
                            "rows_returned": i.rows_returned,
                            "shared_hit_blocks": i.shared_hit_blocks,
                            "shared_read_blocks": i.shared_read_blocks,
                        }
                        for i in summary.iterations
                    ],
                )

        last_bench: BenchmarkSummary | None = st.session_state.get("qt_last_benchmark")
        if last_bench is not None:
            render_section_header("Single Query Benchmark Summary", last_bench.label)
            _render_benchmark_stats_and_chart(last_bench)
