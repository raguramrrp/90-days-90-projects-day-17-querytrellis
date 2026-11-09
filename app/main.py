"""QueryTrellis — PostgreSQL Query Performance & Optimization Workbench.

Streamlit application entrypoint.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.components.sidebar import render_sidebar
from app.pages.benchmark_lab import render_benchmark_lab_page
from app.pages.explain_plan import render_explain_plan_page
from app.pages.overview import render_overview_page
from app.pages.query_editor import render_query_editor_page
from app.pages.query_history import render_query_history_page
from app.pages.recommendations import render_recommendations_page
from app.pages.reports import render_reports_page
from app.pages.settings import render_settings_page
from app.state import init_session_state
from app.styles import inject_workstation_css

PAGE_ROUTER = {
    "Overview": render_overview_page,
    "Query Editor": render_query_editor_page,
    "Explain Plan": render_explain_plan_page,
    "Recommendations": render_recommendations_page,
    "Benchmark Lab": render_benchmark_lab_page,
    "Query History": render_query_history_page,
    "Reports": render_reports_page,
    "Settings": render_settings_page,
}


def main() -> None:
    st.set_page_config(
        page_title="QueryTrellis — PostgreSQL Performance Workbench",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_workstation_css()
    init_session_state()
    selected_page = render_sidebar()
    renderer = PAGE_ROUTER.get(selected_page, render_overview_page)
    renderer()


if __name__ == "__main__":
    main()
