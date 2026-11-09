"""Restrained, developer-workstation CSS styling for QueryTrellis."""
from __future__ import annotations

import streamlit as st


WORKSTATION_CSS = """
<style>
/* Compact layout and professional technical typography */
.block-container,
div[data-testid="stMainBlockContainer"] {
    padding-top: 3.25rem !important;
    padding-bottom: 2rem;
    padding-left: 2rem;
    padding-right: 2rem;
    max-width: 1400px;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #F8FAFC;
    border-right: 1px solid #E2E8F0;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1rem;
    padding-left: 1rem;
    padding-right: 1rem;
}

/* Top header strip */
.qt-topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 14px;
    margin-bottom: 16px;
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #0F766E;
}

.qt-topbar-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0F172A;
    margin: 0;
    letter-spacing: -0.01em;
}

.qt-topbar-sub {
    font-size: 0.80rem;
    color: #475569;
    margin: 2px 0 0 0;
}

.qt-status-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    font-size: 0.78rem;
}

.qt-pill {
    display: inline-block;
    padding: 3px 9px;
    border: 1px solid #CBD5E1;
    background: #FFFFFF;
    color: #0F172A;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.76rem;
}

.qt-pill-connected {
    border-color: #0F766E;
    background: #F0FDFA;
    color: #115E59;
    font-weight: 600;
}

.qt-pill-offline {
    border-color: #B45309;
    background: #FFFBEB;
    color: #92400E;
    font-weight: 600;
}

/* Monospace SQL textarea */
textarea[aria-label="PostgreSQL SQL Editor"],
textarea[aria-label="Original Query (Baseline A)"],
textarea[aria-label="Optimized Query (Candidate B)"] {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Courier New", monospace !important;
    font-size: 0.88rem !important;
    line-height: 1.5 !important;
    background-color: #FFFFFF !important;
    color: #0F172A !important;
    border: 1px solid #CBD5E1 !important;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    padding: 10px 12px;
}

div[data-testid="stMetric"] label {
    font-size: 0.76rem !important;
    color: #475569 !important;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    font-size: 1.25rem !important;
    color: #0F172A !important;
}

/* Subtle info / advisory box */
.qt-advisory {
    background-color: #F0FDFA;
    border: 1px solid #99F6E4;
    border-left: 4px solid #0F766E;
    padding: 10px 14px;
    font-size: 0.86rem;
    color: #0F172A;
    margin: 8px 0 14px 0;
}

.qt-caveat {
    background-color: #F8FAFC;
    border: 1px solid #CBD5E1;
    border-left: 4px solid #0369A1;
    padding: 10px 14px;
    font-size: 0.84rem;
    color: #334155;
    margin: 10px 0;
}

/* Severity tags */
.qt-sev-high { color: #991B1B; font-weight: 700; }
.qt-sev-medium { color: #B45309; font-weight: 700; }
.qt-sev-low { color: #0369A1; font-weight: 700; }
.qt-sev-info { color: #0F766E; font-weight: 700; }

/* Hide default Streamlit deploy toolbar chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
</style>
"""


def inject_workstation_css() -> None:
    """Inject crisp technical workstation styling."""
    st.markdown(WORKSTATION_CSS, unsafe_allow_html=True)
