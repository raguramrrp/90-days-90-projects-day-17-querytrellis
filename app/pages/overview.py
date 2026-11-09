"""Overview page for QueryTrellis PostgreSQL Performance Workbench."""
from __future__ import annotations

import html
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.components.topbar import render_topbar
from app.components.ui_primitives import (
    TelemetryCardData,
    render_empty_state,
    render_section_header,
    render_telemetry_row,
)
from app.state import load_history_record_into_state, navigate_to
from app.theme import apply_plotly_theme, get_active_theme
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore


def _build_latency_activity_chart(recent: list[dict[str, Any]]) -> go.Figure:
    """Plot PostgreSQL execution time vs client round-trip duration across recent runs."""
    t = get_active_theme()
    ordered = list(reversed(recent[:12]))
    labels = [f"#{r['id']}" for r in ordered]
    pg_vals = [r["pg_execution_ms"] for r in ordered]
    client_vals = [r["client_duration_ms"] for r in ordered]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="PostgreSQL Exec (ms)",
            x=labels,
            y=pg_vals,
            marker_color=t.accent,
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Client Duration (ms)",
            x=labels,
            y=client_vals,
            mode="lines+markers",
            line={"color": t.bar_secondary, "width": 2},
            marker={"size": 6, "color": t.bar_secondary},
        )
    )
    fig.update_layout(barmode="group")
    fig.update_xaxes(title_text="Analysis ID")
    fig.update_yaxes(title_text="Duration (ms)")
    return apply_plotly_theme(
        fig,
        t,
        height=280,
        title="Recent Query Latency Profile (PG Server vs Client)",
        margin={"l": 12, "r": 16, "t": 62, "b": 38},
        show_legend=True,
    )


def _build_antipattern_chart(common_issues: list[dict[str, Any]]) -> go.Figure:
    """Plot frequency of detected SQL anti-patterns across recorded analyses."""
    t = get_active_theme()
    top = list(reversed(common_issues[:8]))
    fig = go.Figure(
        go.Bar(
            x=[item["count"] for item in top],
            y=[item["issue_name"][:38] for item in top],
            orientation="h",
            marker_color=t.warning,
            text=[str(item["count"]) for item in top],
            textposition="auto",
        )
    )
    fig.update_xaxes(title_text="Occurrences")
    fig.update_yaxes(title_text="")
    return apply_plotly_theme(
        fig,
        t,
        height=280,
        title="Top Detected SQL Anti-Patterns",
        margin={"l": 12, "r": 18, "t": 48, "b": 38},
        show_legend=False,
    )


def _status_pill(status_val: str) -> str:
    cls = {
        "success": "qt-pill qt-pill-ok",
        "rejected": "qt-pill qt-pill-warn",
        "error": "qt-pill qt-pill-err",
    }.get(status_val.lower(), "qt-pill")
    return f"<span class='{cls}'>{html.escape(status_val)}</span>"


def render_overview_page() -> None:
    """Render primary database performance & optimization workspace overview."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    status = conn_mgr.status
    stats = store.get_overview_stats()

    def _open_editor() -> None:
        navigate_to("Query Editor")
        st.rerun()

    render_topbar(
        "Overview",
        right_meta=f"History: {stats['total_analyses']} analyses",
        action_label="Open Query Editor",
        action_icon="code",
        on_action=_open_editor,
    )

    catalog = None
    if status.connected:
        try:
            catalog = conn_mgr.fetch_catalog()
        except Exception as exc:
            st.warning(f"Connected, but unable to inspect catalog metadata: {exc}")

    common_issues = stats["common_issues"]
    total_ap_findings = sum(int(i["count"]) for i in common_issues)
    avg_exec = stats["avg_execution_ms"]

    render_telemetry_row(
        [
            TelemetryCardData(
                label="PostgreSQL Engine",
                value="Connected" if status.connected else "Disconnected",
                subtext=(
                    f"{status.current_database} on {status.config.host}:{status.config.port}"
                    if status.connected
                    else "Offline AST & rule mode"
                ),
                accent=True,
                tone="ok" if status.connected else "warn",
            ),
            TelemetryCardData(
                label="Schema Objects",
                value=f"{len(catalog.tables):,} / {catalog.total_indexes():,}" if catalog else "Unavailable",
                subtext=(
                    f"{len(catalog.schemas)} schema(s) indexed"
                    if catalog
                    else "Tables / indexes unavailable offline"
                ),
            ),
            TelemetryCardData(
                label="Analyses Recorded",
                value=f"{stats['total_analyses']:,}",
                subtext=f"{stats['successful_analyses']:,} succeeded · {stats['total_benchmarks']:,} benchmarks",
            ),
            TelemetryCardData(
                label="Avg Observed Exec",
                value=f"{avg_exec:.2f} ms" if avg_exec is not None else "No runs yet",
                subtext="Across recorded successful queries",
            ),
            TelemetryCardData(
                label="Anti-Pattern Hits",
                value=f"{total_ap_findings:,}",
                subtext=(
                    f"{len(common_issues)} rule(s) triggered"
                    if common_issues
                    else "No SQL anti-patterns recorded"
                ),
                tone="warn" if total_ap_findings > 0 else "ok",
            ),
        ]
    )

    recent = stats["recent_analyses"]

    render_section_header(
        "Execution Telemetry & Anti-Pattern Distribution",
        f"{stats['total_comparisons']} saved comparison(s)",
    )
    col_chart_l, col_chart_r = st.columns([1.22, 1.0], gap="medium")
    with col_chart_l:
        timed_runs = [
            r for r in recent if r.get("pg_execution_ms") is not None or r.get("client_duration_ms") is not None
        ]
        if not timed_runs:
            render_empty_state(
                "No Execution Timings Yet",
                "Execute or run EXPLAIN ANALYZE on a query in Query Editor to populate latency telemetry.",
                action_label="Open Query Editor",
                action_key="qt_ov_empty_exec_cta",
                on_action=_open_editor,
            )
        else:
            st.plotly_chart(_build_latency_activity_chart(timed_runs), width="stretch")

    with col_chart_r:
        if not common_issues:
            render_empty_state(
                "No Anti-Patterns Recorded",
                "Queries analyzed through QueryTrellis will summarize recurring SQL issues here.",
            )
        else:
            st.plotly_chart(_build_antipattern_chart(common_issues), width="stretch")

    # Recent Analyses with click-to-inspect interaction
    render_section_header("Recent Query Analyses", "Click any row to open in Editor or Explain Plan")
    if not recent:
        render_empty_state(
            "Analysis Queue Empty",
            "Analyze your first PostgreSQL statement in Query Editor to record plans, issues, and index hints.",
            action_label="Go to Query Editor",
            action_key="qt_ov_empty_recent_cta",
            on_action=_open_editor,
        )
    else:
        rec_df = pd.DataFrame(
            [
                {
                    "ID": r["id"],
                    "Timestamp": r["created_at"],
                    "Database": r["database_name"],
                    "Mode": r["execution_mode"],
                    "Status": r["status"],
                    "PG Exec (ms)": f"{r['pg_execution_ms']:.3f}" if r["pg_execution_ms"] is not None else "Unavailable",
                    "Client (ms)": f"{r['client_duration_ms']:.3f}" if r["client_duration_ms"] is not None else "Unavailable",
                    "SQL Preview": (r["sql_text"] or "").replace("\n", " ")[:76],
                }
                for r in recent
            ]
        )
        sel_evt = st.dataframe(
            rec_df,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="qt_ov_recent_table",
        )
        selected_rows = list(getattr(getattr(sel_evt, "selection", None), "rows", []) or [])
        if selected_rows:
            chosen = recent[selected_rows[0]]
            a_col1, a_col2, a_col3, a_col4 = st.columns([2.1, 0.9, 0.95, 0.95], vertical_alignment="center")
            preview_short = html.escape((chosen["sql_text"] or "").replace("\n", " ")[:70])
            a_col1.markdown(
                f"<div class='qt-surface-card' style='padding:0.42rem 0.65rem;font-size:0.78rem;'>"
                f"{_status_pill(chosen['status'])} "
                f"<span class='qt-mono' style='margin-left:6px;'>#{chosen['id']} &middot; {preview_short}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if a_col2.button("Open in Editor", key="qt_ov_load_editor", type="primary", width="stretch"):
                full_rec = store.get_analysis(chosen["id"]) or chosen
                load_history_record_into_state(full_rec)
                navigate_to("Query Editor")
                st.rerun()
            if a_col3.button(
                "Inspect Plan",
                key="qt_ov_open_plan",
                width="stretch",
                disabled=chosen["execution_mode"] not in ("explain_analyze", "explain_estimate"),
            ):
                full_rec = store.get_analysis(chosen["id"]) or chosen
                load_history_record_into_state(full_rec)
                navigate_to("Explain Plan")
                st.rerun()
            if a_col4.button("Recommendations", key="qt_ov_open_recs", width="stretch"):
                full_rec = store.get_analysis(chosen["id"]) or chosen
                load_history_record_into_state(full_rec)
                navigate_to("Recommendations")
                st.rerun()

    # Before & After Optimization Comparisons Strip
    render_section_header("Recent Before & After Comparisons", "Measured optimization verdicts")
    comps = store.list_comparisons(limit=8)
    if not comps:
        render_empty_state(
            "No Saved Query Comparisons",
            "Compare baseline and rewritten SQL statements in Benchmark Lab to track measured speedups.",
            action_label="Open Benchmark Lab",
            action_key="qt_ov_open_bench_cta",
            on_action=lambda: (navigate_to("Benchmark Lab"), st.rerun()),
        )
    else:
        esc = html.escape
        rows_html = []
        for c in comps:
            cdata = c.get("comparison") or {}
            verdict = str(cdata.get("verdict", "Inconclusive"))
            v_cls = (
                "qt-pill qt-pill-ok"
                if verdict == "Improved"
                else ("qt-pill qt-pill-err" if verdict in ("Regressed", "Row Count Mismatch") else "qt-pill qt-pill-warn")
            )
            t_a = f"{cdata['baseline_time_ms']:.3f} ms" if cdata.get("baseline_time_ms") is not None else "Unavailable"
            t_b = f"{cdata['optimized_time_ms']:.3f} ms" if cdata.get("optimized_time_ms") is not None else "Unavailable"
            pct = f"{cdata['pct_change']:+.1f}%" if cdata.get("pct_change") is not None else "Unavailable"
            idx_add = ", ".join(cdata.get("indexes_added") or []) or "None"
            rows_html.append(
                "<tr>"
                f"<td class='qt-mono'>#{c['id']}</td>"
                f"<td>{esc(str(c['title']))}</td>"
                f"<td class='qt-mono'>{esc(str(c['database_name']))}</td>"
                f"<td><span class='{v_cls}'>{esc(verdict)}</span></td>"
                f"<td class='qt-num'>{esc(t_a)}</td>"
                f"<td class='qt-num'>{esc(t_b)}</td>"
                f"<td class='qt-num'>{esc(pct)}</td>"
                f"<td class='qt-mono' style='font-size:0.74rem;'>{esc(idx_add)}</td>"
                "</tr>"
            )
        st.markdown(
            "<div class='qt-table-wrap'><table class='qt-table'>"
            "<thead><tr>"
            "<th>ID</th><th>Comparison Title</th><th>Database</th><th>Verdict</th>"
            "<th class='qt-num'>Baseline</th><th class='qt-num'>Optimized</th>"
            "<th class='qt-num'>Delta</th><th>New Indexes Used</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table></div>",
            unsafe_allow_html=True,
        )

    # Compact collapsible Catalog Footprint
    if catalog and catalog.tables:
        with st.expander(f"Database Table & Index Footprint ({len(catalog.tables)} objects in '{catalog.database_name}')", expanded=False):
            tbl_rows = [
                {
                    "Schema": tbl.schema_name,
                    "Table": tbl.table_name,
                    "Type": tbl.table_type,
                    "Est. Rows": tbl.estimated_rows,
                    "Indexes": len(tbl.indexes),
                    "Total Size (MB)": round(tbl.total_size_bytes / (1024 * 1024), 2),
                    "Seq Scans": tbl.seq_scan,
                    "Index Scans": tbl.idx_scan,
                }
                for tbl in catalog.tables
            ]
            st.dataframe(pd.DataFrame(tbl_rows), width="stretch", hide_index=True)
