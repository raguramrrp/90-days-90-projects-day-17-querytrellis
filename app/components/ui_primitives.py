"""Shared UI primitives and reusable workstation panels for QueryTrellis."""
from __future__ import annotations

import html
import json
from dataclasses import dataclass
from typing import Any, Callable

import streamlit as st

from app.theme import get_active_theme


@dataclass(frozen=True, slots=True)
class TelemetryCardData:
    label: str
    value: str
    subtext: str
    accent: bool = False
    tone: str = "neutral"  # neutral | ok | warn | err


def _tone_dot_class(tone: str) -> str:
    return {
        "ok": "qt-dot qt-dot-ok",
        "warn": "qt-dot qt-dot-warn",
        "err": "qt-dot qt-dot-err",
    }.get(tone, "")


def render_telemetry_row(cards: list[TelemetryCardData]) -> None:
    """Render compact rectangular telemetry panels without oversized generic padding."""
    esc = html.escape
    parts = ["<div class='qt-telemetry-grid'>"]
    for c in cards:
        cls = "qt-tele-panel qt-tele-panel-accent" if c.accent else "qt-tele-panel"
        dot_cls = _tone_dot_class(c.tone)
        dot_html = f"<span class='{dot_cls}'></span>" if dot_cls else ""
        parts.append(
            f"<div class='{cls}'>"
            f"<div class='qt-tele-label'>{esc(c.label)}</div>"
            f"<div class='qt-tele-val'>{dot_html}{esc(c.value)}</div>"
            f"<div class='qt-tele-sub' title='{esc(c.subtext)}'>{esc(c.subtext)}</div>"
            f"</div>"
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_section_header(title: str, meta: str = "") -> None:
    """Render a compact uppercase section divider with optional right-aligned metadata."""
    esc = html.escape
    meta_html = f"<span class='qt-sec-meta'>{esc(meta)}</span>" if meta else ""
    st.markdown(
        f"<div class='qt-sec-head'><span class='qt-sec-title'>{esc(title)}</span>{meta_html}</div>",
        unsafe_allow_html=True,
    )


def render_severity_pill(severity: str) -> str:
    """Return escaped HTML severity badge with restrained engineering palette."""
    sev = severity.strip().title()
    cls = {
        "High": "qt-pill qt-pill-err",
        "Medium": "qt-pill qt-pill-warn",
        "Low": "qt-pill qt-pill-accent",
        "Info": "qt-pill qt-pill-ok",
    }.get(sev, "qt-pill")
    return f"<span class='{cls}'>{html.escape(sev)}</span>"


def render_empty_state(
    title: str,
    description: str,
    *,
    action_label: str | None = None,
    action_key: str | None = None,
    on_action: Callable[[], None] | None = None,
) -> None:
    """Render a crisp empty state container with optional primary recovery action."""
    esc = html.escape
    st.markdown(
        f"""
        <div class="qt-empty-box">
            <div class="qt-empty-title">{esc(title)}</div>
            <div class="qt-empty-desc">{esc(description)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if action_label and on_action and action_key:
        _, c_mid, _ = st.columns([1.2, 1.0, 1.2])
        if c_mid.button(action_label, key=action_key, width="stretch"):
            on_action()


def render_error_state(title: str, message: str) -> None:
    """Render structured non-crashing error feedback panel."""
    esc = html.escape
    st.markdown(
        f"<div class='qt-banner qt-banner-err'>"
        f"<strong>{esc(title)}:</strong> {esc(message)}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------
# Isolated v2 Clipboard Copy Button (registered ONCE at import time)
# ------------------------------------------------------------------
_COPY_CSS = """
.qt-copy-wrap {
    display: inline-flex;
    align-items: center;
    gap: 8px;
}
.qt-copy-btn {
    appearance: none;
    cursor: pointer;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    border: 1px solid var(--btn-border, #34414D);
    background: var(--btn-bg, #202C38);
    color: var(--btn-fg, #E8EDF2);
    transition: border-color 0.12s ease, background 0.12s ease;
}
.qt-copy-btn:hover {
    border-color: var(--btn-accent, #35A99B);
}
.qt-copy-msg {
    font-size: 11px;
    color: var(--btn-accent, #35A99B);
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}
"""

_COPY_JS = """
export default function(component) {
    const { data, parentElement } = component;
    parentElement.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'qt-copy-wrap';
    wrap.style.setProperty('--btn-bg', data.bg);
    wrap.style.setProperty('--btn-fg', data.fg);
    wrap.style.setProperty('--btn-border', data.border);
    wrap.style.setProperty('--btn-accent', data.accent);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'qt-copy-btn';
    btn.textContent = data.label || 'Copy SQL';

    const status = document.createElement('span');
    status.className = 'qt-copy-msg';

    btn.onclick = async () => {
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(data.text || '');
            } else {
                const ta = document.createElement('textarea');
                ta.value = data.text || '';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                ta.remove();
            }
            status.textContent = 'Copied to clipboard';
            setTimeout(() => { status.textContent = ''; }, 1800);
        } catch (err) {
            status.textContent = 'Clipboard unavailable';
        }
    };

    wrap.appendChild(btn);
    wrap.appendChild(status);
    parentElement.appendChild(wrap);
}
"""

_COPY_BTN_COMPONENT = st.components.v2.component(
    "qt_clipboard_copy_btn",
    css=_COPY_CSS,
    js=_COPY_JS,
)


def render_copy_button(text: str, *, key: str, label: str = "Copy SQL") -> None:
    """Render an authentic client-side clipboard copy button styled with active theme tokens."""
    t = get_active_theme()
    _COPY_BTN_COMPONENT(
        key=key,
        data={
            "text": text,
            "label": label,
            "bg": t.bg_elevated,
            "fg": t.text_primary,
            "border": t.border,
            "accent": t.accent,
        },
    )


def render_sql_panel(
    sql_text: str,
    *,
    copy_key: str | None = None,
    title: str | None = None,
) -> None:
    """Render clean SQL code block with optional header and clipboard copy button."""
    if title or copy_key:
        c_title, c_copy = st.columns([3.0, 1.0], vertical_alignment="center")
        if title:
            c_title.markdown(
                f"<div style='font-size:0.76rem;font-weight:600;color:var(--qt-text-secondary);'>{html.escape(title)}</div>",
                unsafe_allow_html=True,
            )
        if copy_key:
            with c_copy:
                render_copy_button(sql_text, key=copy_key, label="Copy SQL")
    st.code(sql_text, language="sql")
