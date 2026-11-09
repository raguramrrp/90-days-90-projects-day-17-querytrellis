"""E. Benchmark Lab & Before/After Query Comparison page."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.sidebar import render_page_header
from src.benchmark.comparator import QueryComparisonResult, QuerySnapshot, compare_queries
from src.benchmark.runner import METHODOLOGY_NOTES, BenchmarkSummary, run_query_benchmark
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.services.workbench_service import analyze_query_end_to_end
from src.sql_analysis.sample_queries import SAMPLE_QUERIES


def _render_benchmark_stats_and_chart(bench: BenchmarkSummary) -> None:
    if not bench.success:
        st.error(bench.error_message)
        return

    if bench.interrupted:
        st.warning(bench.error_message)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "PG Exec Median",
        f"{bench.pg_exec_median_ms:.3f} ms" if bench.pg_exec_median_ms is not None else "Unavailable",
    )
    c2.metric(
        "PG Exec Mean",
        f"{bench.pg_exec_mean_ms:.3f} ms" if bench.pg_exec_mean_ms is not None else "Unavailable",
    )
    c3.metric("Client Median", f"{bench.median_ms:.3f} ms")
    c4.metric("Client Min / Max", f"{bench.min_ms:.2f} / {bench.max_ms:.2f} ms")
    c5.metric("Client Mean (Stdev)", f"{bench.mean_ms:.2f} (±{bench.stdev_ms:.2f}) ms")

    all_its = ([bench.warmup_iteration] if bench.warmup_iteration else []) + bench.iterations
    df = pd.DataFrame(
        [
            {
                "Run": "Warmup (Excluded)" if it.is_warmup else f"Run {it.run_index}",
                "Client Wall (ms)": it.client_wall_ms,
                "PG Execution (ms)": it.pg_execution_ms if it.pg_execution_ms is not None else 0.0,
                "PG Planning (ms)": it.pg_planning_ms if it.pg_planning_ms is not None else 0.0,
                "Rows": it.rows_returned,
                "Shared Hits": it.shared_hit_blocks,
                "Shared Reads": it.shared_read_blocks,
            }
            for it in all_its
        ]
    )

    col_tbl, col_fig = st.columns([1.05, 1.15])
    with col_tbl:
        st.dataframe(df, width="stretch", hide_index=True)
    with col_fig:
        measured_df = df[df["Run"] != "Warmup (Excluded)"]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=measured_df["Run"],
                y=measured_df["PG Execution (ms)"],
                mode="lines+markers",
                name="PostgreSQL Execution Time (ms)",
                line=dict(color="#0F766E", width=2.5),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=measured_df["Run"],
                y=measured_df["Client Wall (ms)"],
                mode="lines+markers",
                name="Client-Observed Duration (ms)",
                line=dict(color="#0369A1", width=2, dash="dash"),
            )
        )
        fig.update_layout(
            title=dict(text=f"Per-Run Duration Profile — {bench.label}", y=0.96),
            yaxis_title="Duration (ms)",
            height=320,
            margin=dict(l=10, r=15, t=68, b=30),
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#F8FAFC",
            font=dict(color="#0F172A", size=11),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        )
        st.plotly_chart(fig, width="stretch")


def render_benchmark_lab_page() -> None:
    render_page_header(
        "Benchmark Lab & Query Comparison",
        "Run repeatable query benchmarks, distinguish client vs. PostgreSQL server execution times, and compare before/after rewrites.",
    )

    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    max_repeats = st.session_state["qt_settings"].benchmark_max_repeats

    st.markdown(
        "<div class='qt-caveat'><strong>Measurement Methodology &amp; Caveats:</strong><br/>"
        + "<br/>".join(f"&bull; {n}" for n in METHODOLOGY_NOTES)
        + "</div>",
        unsafe_allow_html=True,
    )

    tab_single, tab_compare = st.tabs(
        ["Single Query Benchmark", "Before & After Optimization Comparison"]
    )

    # ------------------------------------------------------------------
    # Tab 1: Single Query Multi-Run Benchmark
    # ------------------------------------------------------------------
    with tab_single:
        if "qt_pending_single_bench_sql" in st.session_state:
            st.session_state["qt_single_bench_input"] = st.session_state.pop("qt_pending_single_bench_sql")
        elif "qt_single_bench_input" not in st.session_state:
            st.session_state["qt_single_bench_input"] = st.session_state.get("qt_editor_sql", "")

        b_col1, b_col2 = st.columns([2.2, 1.0])
        with b_col1:
            if st.button("Load Current Editor SQL", key="btn_load_editor_to_bench"):
                st.session_state["qt_pending_single_bench_sql"] = st.session_state.get("qt_editor_sql", "")
                st.rerun()
        bench_sql = st.text_area(
            "SQL to Benchmark",
            height=170,
            key="qt_single_bench_input",
        )

        c_lbl, c_rep, c_warm, c_go = st.columns([1.6, 0.8, 1.0, 1.0])
        bench_label = c_lbl.text_input("Benchmark Label", value="Current Query Run")
        repeats = c_rep.number_input("Repeat Count", min_value=2, max_value=max_repeats, value=5, step=1)
        include_warmup = c_warm.checkbox("Include 1 Warmup Run (Excluded)", value=True)
        run_btn = c_go.button(
            "Run Benchmark",
            type="primary",
            width="stretch",
            disabled=not conn_mgr.is_connected,
        )

        if not conn_mgr.is_connected:
            st.info("Connect PostgreSQL in Settings to execute live benchmarks.")

        if run_btn and conn_mgr.is_connected:
            prog = st.progress(0.0, text="Starting benchmark iterations...")
            def _update_prog(step: int, total: int) -> None:
                prog.progress(step / max(total, 1), text=f"Running iteration {step} of {total}...")

            summary = run_query_benchmark(
                conn_mgr.get_connection(),
                bench_sql,
                label=bench_label.strip() or "Query Benchmark",
                repeat_count=int(repeats),
                include_warmup=include_warmup,
                timeout_ms=st.session_state["qt_timeout_ms"],
                on_progress=_update_prog,
            )
            prog.empty()
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
            st.divider()
            _render_benchmark_stats_and_chart(last_bench)

    # ------------------------------------------------------------------
    # Tab 2: Before & After Query Comparison Workflow
    # ------------------------------------------------------------------
    with tab_compare:
        paired_samples = [s for s in SAMPLE_QUERIES if s.suggested_optimization]
        pair_titles = [s.title for s in paired_samples]

        p_col1, p_col2 = st.columns([2.6, 1.0])
        chosen_pair_title = p_col1.selectbox(
            "Load Built-in Before/After Optimization Pair",
            options=pair_titles,
            key="qt_pair_picker",
        )
        if p_col2.button("Load Pair", width="stretch"):
            pair = next(s for s in paired_samples if s.title == chosen_pair_title)
            st.session_state["qt_pending_bench_a"] = pair.sql
            st.session_state["qt_pending_bench_b"] = pair.suggested_optimization or pair.sql
            st.rerun()

        if "qt_pending_bench_a" in st.session_state:
            st.session_state["qt_cmp_sql_a"] = st.session_state.pop("qt_pending_bench_a")
        elif "qt_cmp_sql_a" not in st.session_state:
            st.session_state["qt_cmp_sql_a"] = st.session_state.get("qt_bench_sql_a", "")

        if "qt_pending_bench_b" in st.session_state:
            st.session_state["qt_cmp_sql_b"] = st.session_state.pop("qt_pending_bench_b")
        elif "qt_cmp_sql_b" not in st.session_state:
            st.session_state["qt_cmp_sql_b"] = st.session_state.get("qt_bench_sql_b", "")

        col_a, col_b = st.columns(2)
        with col_a:
            sql_a = st.text_area("Original Query (Baseline A)", height=210, key="qt_cmp_sql_a")
            st.session_state["qt_bench_sql_a"] = sql_a
        with col_b:
            sql_b = st.text_area("Optimized Query (Candidate B)", height=210, key="qt_cmp_sql_b")
            st.session_state["qt_bench_sql_b"] = sql_b

        c_title, c_reps, c_run_cmp, c_snap_cmp = st.columns([1.8, 0.8, 1.2, 1.2])
        cmp_title = c_title.text_input("Comparison Title", value="Optimization A/B Comparison")
        cmp_reps = c_reps.number_input("Runs per Query", min_value=2, max_value=15, value=4, step=1)
        run_both_btn = c_run_cmp.button(
            "Analyze & Benchmark Both",
            type="primary",
            width="stretch",
            disabled=not conn_mgr.is_connected,
        )
        compare_saved_btn = c_snap_cmp.button(
            "Compare Saved A & B Snapshots",
            width="stretch",
            disabled=(
                st.session_state.get("qt_baseline_snapshot") is None
                or st.session_state.get("qt_candidate_snapshot") is None
            ),
        )

        if run_both_btn and conn_mgr.is_connected:
            with st.spinner("Analyzing and benchmarking Baseline (A) and Candidate (B)..."):
                bundle_a = analyze_query_end_to_end(
                    sql_a,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    analyze_explain=True,
                    buffers=True,
                    timeout_ms=st.session_state["qt_timeout_ms"],
                    persist=True,
                )
                bench_a = run_query_benchmark(
                    conn_mgr.get_connection(),
                    sql_a,
                    label="Baseline (A)",
                    repeat_count=int(cmp_reps),
                    include_warmup=True,
                    timeout_ms=st.session_state["qt_timeout_ms"],
                )
                bundle_b = analyze_query_end_to_end(
                    sql_b,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    analyze_explain=True,
                    buffers=True,
                    timeout_ms=st.session_state["qt_timeout_ms"],
                    persist=True,
                )
                bench_b = run_query_benchmark(
                    conn_mgr.get_connection(),
                    sql_b,
                    label="Optimized (B)",
                    repeat_count=int(cmp_reps),
                    include_warmup=True,
                    timeout_ms=st.session_state["qt_timeout_ms"],
                )

                if not bundle_a.validation.is_read_only or not bundle_b.validation.is_read_only:
                    st.error(bundle_a.error_message or bundle_b.error_message)
                elif not bench_a.success or not bench_b.success:
                    st.error(bench_a.error_message or bench_b.error_message)
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
            comp = compare_queries(snap_a, snap_b)
            st.session_state["qt_last_comparison"] = comp

        comp_res: QueryComparisonResult | None = st.session_state.get("qt_last_comparison")
        if comp_res is not None:
            st.divider()
            st.subheader(f"Comparison Result — Verdict: {comp_res.verdict}")
            if comp_res.verdict == "Improved":
                st.success(comp_res.verdict_summary)
            elif comp_res.verdict in ("Regressed", "Row Count Mismatch"):
                st.error(comp_res.verdict_summary)
            else:
                st.info(comp_res.verdict_summary)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric(
                "Baseline Exec Time",
                f"{comp_res.baseline_time_ms:.3f} ms" if comp_res.baseline_time_ms is not None else "Unavailable",
            )
            m2.metric(
                "Optimized Exec Time",
                f"{comp_res.optimized_time_ms:.3f} ms" if comp_res.optimized_time_ms is not None else "Unavailable",
                delta=(
                    f"{comp_res.pct_change:+.1f}% ({comp_res.time_diff_ms:+.3f} ms)"
                    if comp_res.pct_change is not None and comp_res.time_diff_ms is not None
                    else None
                ),
                delta_color="inverse",
            )
            m3.metric(
                "Plan Cost Delta",
                f"{comp_res.optimized_cost:,.2f}" if comp_res.optimized_cost is not None else "Unavailable",
                delta=(
                    f"{comp_res.cost_pct_change:+.1f}%"
                    if comp_res.cost_pct_change is not None
                    else None
                ),
                delta_color="inverse",
            )
            m4.metric(
                "Rows Returned (A vs B)",
                (
                    f"{comp_res.baseline_rows:,} vs {comp_res.optimized_rows:,}"
                    if comp_res.baseline_rows is not None and comp_res.optimized_rows is not None
                    else "Unavailable"
                ),
            )

            col_chart, col_delta = st.columns([1.0, 1.1])
            with col_chart:
                if comp_res.baseline_time_ms is not None and comp_res.optimized_time_ms is not None:
                    fig_ab = go.Figure(
                        go.Bar(
                            x=[comp_res.baseline_label, comp_res.optimized_label],
                            y=[comp_res.baseline_time_ms, comp_res.optimized_time_ms],
                            marker_color=["#64748B", "#0F766E"],
                            text=[f"{comp_res.baseline_time_ms:.3f} ms", f"{comp_res.optimized_time_ms:.3f} ms"],
                            textposition="auto",
                        )
                    )
                    fig_ab.update_layout(
                        title="Measured Execution Time Comparison (Lower is Faster)",
                        yaxis_title="Time (ms)",
                        height=290,
                        margin=dict(l=10, r=15, t=40, b=30),
                        paper_bgcolor="#FFFFFF",
                        plot_bgcolor="#F8FAFC",
                        font=dict(color="#0F172A", size=12),
                    )
                    st.plotly_chart(fig_ab, width="stretch")

            with col_delta:
                st.markdown("**Plan & Index Structural Changes**")
                st.markdown(f"- **Plan Nodes Added:** {', '.join(comp_res.nodes_added) or 'None'}")
                st.markdown(f"- **Plan Nodes Removed:** {', '.join(comp_res.nodes_removed) or 'None'}")
                st.markdown(f"- **Indexes Added in Plan:** {', '.join(comp_res.indexes_added) or 'None'}")
                st.markdown(f"- **Indexes Removed in Plan:** {', '.join(comp_res.indexes_removed) or 'None'}")
                st.markdown(f"- **Anti-Patterns Resolved:** {', '.join(comp_res.resolved_antipatterns) or 'None'}")
                st.markdown(f"- **Remaining Anti-Patterns:** {', '.join(comp_res.remaining_antipatterns) or 'None'}")
                if comp_res.introduced_antipatterns:
                    st.warning(f"Newly introduced anti-patterns: {', '.join(comp_res.introduced_antipatterns)}")
