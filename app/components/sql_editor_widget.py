"""Reusable SQL editor and syntax preview component."""
from __future__ import annotations

import streamlit as st


def render_sql_editor_box(
    *,
    label: str = "PostgreSQL SQL Editor",
    key: str = "qt_editor_textarea",
    height: int = 230,
    show_highlight_preview: bool = True,
) -> str:
    """Render monospace SQL editor safely synchronizing programmatic updates before widget creation."""
    if "qt_pending_editor_sql" in st.session_state:
        pending = st.session_state.pop("qt_pending_editor_sql")
        st.session_state["qt_editor_sql"] = pending
        st.session_state[key] = pending
    elif key not in st.session_state:
        st.session_state[key] = st.session_state.get("qt_editor_sql", "")

    sql_val = st.text_area(
        label,
        height=height,
        key=key,
        help="Enter a single read-only PostgreSQL SELECT query (CTEs, joins, aggregates, and window functions supported).",
    )
    st.session_state["qt_editor_sql"] = sql_val

    if show_highlight_preview and sql_val.strip():
        with st.expander("Syntax-Highlighted SQL Preview", expanded=False):
            st.code(sql_val, language="sql")
    return sql_val
