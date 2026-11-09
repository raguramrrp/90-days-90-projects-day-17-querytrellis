"""Grouped Recommendations Workbench page for QueryTrellis."""
from __future__ import annotations

import html

import streamlit as st

from app.components.topbar import render_topbar
from app.components.ui_primitives import (
    TelemetryCardData,
    render_copy_button,
    render_empty_state,
    render_section_header,
    render_severity_pill,
    render_sql_panel,
    render_telemetry_row,
)
from app.state import navigate_to, set_active_editor_sql
from src.db.connection_manager import ConnectionManager
from src.db.metadata_store import MetadataStore
from src.services.workbench_service import FullAnalysisBundle, analyze_query_end_to_end
from src.sql_analysis.sample_queries import SAMPLE_QUERIES


def _normalize_sql_compact(s: str) -> str:
    return " ".join((s or "").strip().rstrip(";").split()).lower()


def _find_matching_sample_pair(sql_text: str):
    target = _normalize_sql_compact(sql_text)
    if not target:
        return None
    for s in SAMPLE_QUERIES:
        if s.suggested_optimization and _normalize_sql_compact(s.sql) == target:
            return s
    return None


def render_recommendations_page() -> None:
    """Render grouped index recommendations, anti-patterns, plan findings, and rewrite opportunities."""
    conn_mgr: ConnectionManager = st.session_state["qt_conn_mgr"]
    store: MetadataStore = st.session_state["qt_store"]
    bundle: FullAnalysisBundle | None = st.session_state.get("qt_last_analysis")

    if bundle is None:
        sql_text = st.session_state.get("qt_editor_sql", "")
        if sql_text.strip():
            with st.spinner("Evaluating AST anti-patterns and advisory recommendations..."):
                bundle = analyze_query_end_to_end(
                    sql_text,
                    conn_manager=conn_mgr,
                    metadata_store=store,
                    analyze_explain=conn_mgr.is_connected,
                    buffers=conn_mgr.is_connected,
                    timeout_ms=int(st.session_state.get("qt_timeout_ms", 5000)),
                    persist=False,
                )
            st.session_state["qt_last_analysis"] = bundle

    def _open_editor() -> None:
        navigate_to("Query Editor")
        st.rerun()

    render_topbar(
        "Recommendations",
        right_meta=(
            f"Analysis #{bundle.analysis_id}" if (bundle and bundle.analysis_id) else "Session evaluation"
        ),
        action_label="Open in Editor",
        action_icon="code",
        on_action=_open_editor,
    )

    if bundle is None:
        render_empty_state(
            "No Query Available to Inspect",
            "Write or load a SQL query in Query Editor to review anti-patterns, execution findings, and index suggestions.",
            action_label="Go to Query Editor",
            action_key="qt_rec_empty_editor",
            on_action=_open_editor,
        )
        return

    aps = bundle.antipatterns
    recs = bundle.index_recommendations
    insights = bundle.plan_insights
    high_cnt = sum(1 for a in aps if a.severity == "High") + sum(1 for i in insights if i.severity == "High")
    matched_pair = _find_matching_sample_pair(bundle.sql_text)

    render_telemetry_row(
        [
            TelemetryCardData(
                label="Advisory Indexes",
                value=f"{len(recs)}",
                subtext="DDL recommendations (never auto-applied)",
                accent=True,
                tone="ok" if recs else "neutral",
            ),
            TelemetryCardData(
                label="SQL Anti-Patterns",
                value=f"{len(aps)}",
                subtext="AST & schema heuristics",
                tone="warn" if aps else "ok",
            ),
            TelemetryCardData(
                label="Plan Bottlenecks",
                value=f"{len(insights)}",
                subtext="From EXPLAIN operator tree" if bundle.parsed_plan else "Connect PG for plan findings",
            ),
            TelemetryCardData(
                label="High Severity",
                value=f"{high_cnt}",
                subtext="Priority tuning signals",
                tone="err" if high_cnt > 0 else "ok",
            ),
            TelemetryCardData(
                label="Evidence Scope",
                value="Plan + AST" if bundle.parsed_plan else "Static AST",
                subtext="Catalog + EXPLAIN" if (conn_mgr.is_connected and bundle.parsed_plan) else "Offline rule checks",
            ),
        ]
    )

    st.markdown(
        "<div class='qt-banner'>"
        "<strong>Advisory Guarantee:</strong> All DDL and rewrite suggestions below are informational engineering guidance. "
        "QueryTrellis never executes <code>CREATE INDEX</code> or modifies database objects automatically. Always measure "
        "write amplification, storage footprint, and before/after execution latency in Benchmark Lab."
        "</div>",
        unsafe_allow_html=True,
    )

    f_col, sql_col = st.columns([1.4, 2.2], vertical_alignment="center")
    with f_col:
        sev_filter = st.multiselect(
            "Filter Findings by Severity",
            options=["High", "Medium", "Low", "Info"],
            default=["High", "Medium", "Low", "Info"],
            key="qt_rec_sev_filter",
        )
    with sql_col:
        with st.expander("Analyzed SQL Statement", expanded=False):
            st.code(bundle.formatted_sql or bundle.sql_text, language="sql")

    filtered_aps = [a for a in aps if a.severity in sev_filter]
    filtered_ins = [i for i in insights if i.severity in sev_filter]

    tab_idx, tab_ap, tab_plan, tab_opp = st.tabs(
        [
            f"Index Recommendations ({len(recs)})",
            f"Query Anti-Patterns ({len(filtered_aps)})",
            f"Execution-Plan Findings ({len(filtered_ins)})",
            f"Optimization Opportunities ({(1 if matched_pair else 0) + len(aps)})",
        ]
    )

    # ------------------------------------------------------------------
    # 1. Index Recommendations
    # ------------------------------------------------------------------
    with tab_idx:
        if not recs:
            render_empty_state(
                "No Additional Index Suggestions",
                "Existing indexes already cover detected filters/joins, tables are small, or predicates are non-sargable before rewriting.",
            )
        else:
            all_ddl = "\n".join(r.suggested_sql for r in recs)
            st.download_button(
                "Download All Advisory DDL (.sql)",
                data=(
                    "-- Advisory Index Recommendations generated by QueryTrellis\n"
                    "-- Review write overhead and disk usage carefully before running manually.\n\n"
                    + all_ddl
                    + "\n"
                ).encode("utf-8"),
                file_name="querytrellis_index_recommendations.sql",
                mime="text/sql",
                key="qt_rec_dl_all_ddl",
            )
            esc = html.escape
            for i_rec, r in enumerate(recs):
                conf_cls = "qt-pill qt-pill-ok" if r.confidence == "High" else ("qt-pill qt-pill-warn" if r.confidence == "Medium" else "qt-pill")
                st.markdown(
                    f"""
                    <div class="qt-surface-card" style="margin-top:6px;">
                        <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;">
                            <div>
                                <span class="qt-pill qt-pill-accent">{esc(r.rec_id)} &middot; {esc(r.index_type)}</span>
                                <span class="qt-mono" style="font-weight:700;font-size:0.88rem;margin-left:6px;">{esc(r.table_name)}({esc(', '.join(r.columns))})</span>
                            </div>
                            <span class="{conf_cls}">{esc(r.confidence)} Confidence</span>
                        </div>
                        <div style="font-size:0.78rem;color:var(--qt-text-secondary);margin-bottom:4px;">
                            <strong>Condition:</strong> <code class="qt-mono">{esc(r.related_condition)}</code> &bull;
                            <strong>Evidence:</strong> {esc(', '.join(r.evidence_sources))}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                render_sql_panel(
                    r.suggested_sql,
                    copy_key=f"qt_rec_copy_idx_{i_rec}",
                    title=f"Advisory CREATE INDEX Statement ({r.index_type})",
                )
                d1, d2 = st.columns(2)
                d1.markdown(f"**Why It May Help:** {r.why_it_helps}\n\n**Existing Index Check:** {r.existing_index_status}")
                d2.markdown(f"**Write & Storage Overhead:** {r.write_and_storage_overhead}\n\n**When Not Helpful:** {r.when_not_helpful}")

    # ------------------------------------------------------------------
    # 2. Query Anti-Patterns
    # ------------------------------------------------------------------
    with tab_ap:
        if not filtered_aps:
            render_empty_state(
                "No Matching Anti-Pattern Findings",
                "Adjust the severity filter above or analyze another query in Query Editor.",
            )
        else:
            esc = html.escape
            for i_ap, f in enumerate(filtered_aps):
                st.markdown(
                    f"""
                    <div class="qt-surface-card" style="margin-bottom:6px;">
                        <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;">
                            <div>
                                <span class="qt-mono" style="font-weight:700;color:var(--qt-accent-text);">{esc(f.rule_id)}</span>
                                <span style="font-weight:700;font-size:0.90rem;margin-left:6px;">{esc(f.issue_name)}</span>
                            </div>
                            <div style="display:flex;gap:6px;align-items:center;">
                                {render_severity_pill(f.severity)}
                                <span class="qt-pill">{esc(f.confidence)} Conf &middot; {esc(f.evidence_basis)}</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                c_frag, c_detail = st.columns([1.0, 1.45])
                with c_frag:
                    st.markdown("**Affected SQL Fragment**")
                    st.code(f.affected_fragment, language="sql")
                with c_detail:
                    st.markdown(f"**Explanation:** {f.explanation}")
                    st.markdown(f"**Performance Impact:** {f.performance_impact}")
                    st.markdown(f"**When Acceptable:** {f.when_acceptable}")
                    st.markdown(f"**Suggested Improvement:** {f.suggested_improvement}")

    # ------------------------------------------------------------------
    # 3. Execution-Plan Findings
    # ------------------------------------------------------------------
    with tab_plan:
        if not bundle.parsed_plan:
            render_empty_state(
                "No Execution Plan Attached",
                "Run EXPLAIN ANALYZE on PostgreSQL to surface runtime operator bottlenecks (Seq Scans, Sorts, Nested Loop counts, Buffers).",
                action_label="Open Explain Plan",
                action_key="qt_rec_goto_plan_empty",
                on_action=lambda: (navigate_to("Explain Plan"), st.rerun()),
            )
        elif not filtered_ins:
            render_empty_state(
                "No Plan Findings Match Severity Filter",
                "Zero bottlenecks exceeded PostgreSQL thresholds for this execution plan.",
            )
        else:
            esc = html.escape
            for idx_ins, ins in enumerate(filtered_ins):
                c_card, c_jump = st.columns([3.2, 0.9], vertical_alignment="center")
                with c_card:
                    st.markdown(
                        f"""
                        <div class="qt-surface-card">
                            <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:6px;">
                                <span style="font-weight:700;font-size:0.88rem;">
                                    {esc(ins.insight_id)} &middot; {esc(ins.title)}
                                </span>
                                <div style="display:flex;gap:5px;align-items:center;">
                                    {render_severity_pill(ins.severity)}
                                    <span class="qt-pill">Node #{ins.node_id} &middot; {esc(ins.node_label)}</span>
                                </div>
                            </div>
                            <div style="font-size:0.79rem;color:var(--qt-text-primary);margin-top:5px;"><strong>Observation:</strong> {esc(ins.observation)}</div>
                            <div style="font-size:0.78rem;color:var(--qt-text-secondary);margin-top:3px;"><strong>Interpretation:</strong> {esc(ins.interpretation)}</div>
                            <div style="font-size:0.78rem;color:var(--qt-accent-text);margin-top:3px;"><strong>Recommendation:</strong> {esc(ins.recommendation)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c_jump:
                    if st.button(
                        f"Inspect Node #{ins.node_id}",
                        key=f"qt_rec_jump_node_{idx_ins}_{ins.node_id}",
                        icon=":material/account_tree:",
                        width="stretch",
                    ):
                        st.session_state["qt_selected_plan_node_id"] = ins.node_id
                        navigate_to("Explain Plan")
                        st.rerun()

    # ------------------------------------------------------------------
    # 4. Optimization Opportunities
    # ------------------------------------------------------------------
    with tab_opp:
        render_section_header("Actionable Query Optimization Checklist", "Prioritized by rule severity & plan evidence")
        if matched_pair and matched_pair.suggested_optimization:
            st.markdown(
                f"""
                <div class="qt-surface-card" style="border-left:3px solid var(--qt-accent);margin-bottom:8px;">
                    <div style="font-weight:700;font-size:0.90rem;">Matched Built-In Optimization Pair: {html.escape(matched_pair.title)}</div>
                    <div style="font-size:0.79rem;color:var(--qt-text-secondary);margin-top:3px;">{html.escape(matched_pair.description)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_sql_panel(
                matched_pair.suggested_optimization,
                copy_key="qt_rec_copy_rewrite",
                title="Recommended Semantic Rewrite Candidate (B)",
            )
            cb1, cb2 = st.columns(2)
            if cb1.button("Load Rewrite into Query Editor", key="qt_rec_load_rewrite", type="primary", width="stretch"):
                set_active_editor_sql(matched_pair.suggested_optimization)
                navigate_to("Query Editor")
                st.rerun()
            if cb2.button("Compare Baseline vs Rewrite in Benchmark Lab", key="qt_rec_send_ab", width="stretch"):
                st.session_state["qt_pending_bench_a"] = matched_pair.sql
                st.session_state["qt_pending_bench_b"] = matched_pair.suggested_optimization
                st.session_state["qt_bench_sql_a"] = matched_pair.sql
                st.session_state["qt_bench_sql_b"] = matched_pair.suggested_optimization
                navigate_to("Benchmark Lab")
                st.rerun()

        if not aps and not recs and not insights and not matched_pair:
            render_empty_state(
                "Query Follows Best Practices",
                "No anti-pattern rewrites, missing indexes, or major plan bottlenecks were flagged.",
            )
        else:
            steps: list[tuple[str, str, str]] = []
            for a in aps:
                steps.append((a.severity, f"Refactor {a.issue_name} ({a.rule_id})", a.suggested_improvement))
            for r in recs:
                steps.append((r.confidence, f"Evaluate {r.index_type} index on {r.table_name}({', '.join(r.columns)})", r.suggested_sql))
            for i in insights:
                if i.severity in ("High", "Medium"):
                    steps.append((i.severity, f"Resolve {i.title} on Node #{i.node_id}", i.recommendation))

            if steps:
                esc = html.escape
                rows_html = "".join(
                    "<tr>"
                    f"<td>{render_severity_pill(sev)}</td>"
                    f"<td style='font-weight:600;'>{esc(action)}</td>"
                    f"<td class='qt-mono' style='font-size:0.75rem;'>{esc(detail)}</td>"
                    "</tr>"
                    for sev, action, detail in steps
                )
                st.markdown(
                    "<div class='qt-table-wrap'><table class='qt-table'>"
                    "<thead><tr><th>Priority / Conf</th><th>Optimization Opportunity</th><th>Action / Target DDL</th></tr></thead>"
                    f"<tbody>{rows_html}</tbody></table></div>",
                    unsafe_allow_html=True,
                )
