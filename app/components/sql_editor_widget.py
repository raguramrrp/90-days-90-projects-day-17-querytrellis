"""IDE-grade PostgreSQL SQL Editor v2 component for QueryTrellis."""
from __future__ import annotations

import streamlit as st

from app.theme import ThemeTokens, get_active_theme


_IDE_CSS = """
.qt-ide-root {
    border: 1px solid var(--ide-border);
    border-radius: 5px;
    background: var(--ide-surface);
    overflow: hidden;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    color: var(--ide-fg);
    box-sizing: border-box;
    width: 100%;
}

.qt-ide-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 10px;
    background: var(--ide-bar);
    border-bottom: 1px solid var(--ide-border-subtle);
}

.qt-ide-btn-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
}

.qt-ide-btn {
    appearance: none;
    cursor: pointer;
    padding: 4px 10px;
    min-height: 28px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    font-family: inherit;
    border: 1px solid var(--ide-border);
    background: var(--ide-btn-bg);
    color: var(--ide-fg);
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition: background-color 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}

.qt-ide-btn:hover {
    background: var(--ide-btn-hover);
    border-color: var(--ide-accent);
}

.qt-ide-btn-primary {
    background: var(--ide-accent);
    border-color: var(--ide-accent);
    color: #FFFFFF;
    font-weight: 600;
}

.qt-ide-btn-primary:hover {
    background: var(--ide-accent-hover);
    border-color: var(--ide-accent-hover);
}

.qt-ide-btn-accent {
    border-color: var(--ide-accent);
    color: var(--ide-accent-text);
    background: var(--ide-accent-soft);
    font-weight: 600;
}

.qt-ide-btn-accent:hover {
    background: var(--ide-accent);
    color: #FFFFFF;
}

.qt-ide-shortcut {
    font-size: 11px;
    color: var(--ide-muted);
    font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
}

.qt-ide-body {
    position: relative;
    display: flex;
    width: 100%;
    height: var(--ide-height, 270px);
    background: var(--ide-bg);
    overflow: hidden;
}

.qt-ide-gutter {
    width: 44px;
    min-width: 44px;
    background: var(--ide-gutter);
    border-right: 1px solid var(--ide-border-subtle);
    overflow: hidden;
    user-select: none;
    position: relative;
}

.qt-ide-gutter-inner {
    padding: 12px 8px 12px 4px;
    text-align: right;
    font-family: 'JetBrains Mono', 'Cascadia Mono', 'Cascadia Code', Consolas, monospace;
    font-size: 12px;
    line-height: 20px;
    color: var(--ide-muted);
    font-variant-ligatures: none;
    will-change: transform;
}

.qt-ide-gutter-ln {
    height: 20px;
    line-height: 20px;
}

.qt-ide-code-wrap {
    position: relative;
    flex: 1 1 auto;
    height: 100%;
    overflow: hidden;
    background: var(--ide-bg);
}

.qt-ide-highlight,
.qt-ide-textarea {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    border: 0;
    padding: 12px 14px;
    box-sizing: border-box;
    font-family: 'JetBrains Mono', 'Cascadia Mono', 'Cascadia Code', Consolas, monospace;
    font-size: 13px;
    line-height: 20px;
    letter-spacing: 0px;
    tab-size: 4;
    font-variant-ligatures: none;
    white-space: pre;
    word-wrap: normal;
    overflow-wrap: normal;
    overflow: auto;
}

.qt-ide-highlight {
    pointer-events: none;
    color: var(--ide-fg);
    background: transparent;
    z-index: 1;
}

.qt-ide-textarea {
    z-index: 2;
    resize: none;
    outline: none;
    background: transparent;
    color: transparent;
    caret-color: var(--ide-fg);
    -webkit-text-fill-color: transparent;
}

.qt-ide-textarea::selection {
    background: var(--ide-sel);
}

.qt-tok-kw { color: var(--ide-kw); font-weight: 600; }
.qt-tok-fn { color: var(--ide-fn); }
.qt-tok-str { color: var(--ide-str); }
.qt-tok-num { color: var(--ide-num); }
.qt-tok-cmt { color: var(--ide-cmt); font-style: italic; }
.qt-tok-id { color: var(--ide-fg); }
.qt-tok-op { color: var(--ide-op); }

.qt-ide-footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 5px 10px;
    background: var(--ide-bar);
    border-top: 1px solid var(--ide-border-subtle);
    font-size: 11px;
    color: var(--ide-sec);
    font-family: 'JetBrains Mono', 'Cascadia Mono', Consolas, monospace;
}

.qt-ide-footer-left,
.qt-ide-footer-right {
    display: flex;
    align-items: center;
    gap: 12px;
}

.qt-ide-status-msg {
    color: var(--ide-accent-text);
    font-weight: 600;
}
"""

_IDE_JS = """
const PG_KEYWORDS = new Set([
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN", "LIKE", "ILIKE",
    "IS", "NULL", "TRUE", "FALSE", "AS", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS",
    "OUTER", "ON", "USING", "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC", "NULLS", "FIRST",
    "LAST", "LIMIT", "OFFSET", "FETCH", "WITH", "RECURSIVE", "MATERIALIZED", "DISTINCT", "ALL",
    "UNION", "INTERSECT", "EXCEPT", "CASE", "WHEN", "THEN", "ELSE", "END", "CAST", "OVER",
    "PARTITION", "ROWS", "RANGE", "UNBOUNDED", "PRECEDING", "FOLLOWING", "CURRENT", "ROW",
    "EXPLAIN", "ANALYZE", "BUFFERS", "FILTER", "LATERAL", "VALUES", "ANY", "SOME",
    "INTERVAL", "TIMESTAMP", "TIMESTAMPTZ", "DATE", "NUMERIC", "INTEGER", "BIGINT", "TEXT",
    "VARCHAR", "BOOLEAN", "CREATE", "INDEX", "CONCURRENTLY", "INCLUDE", "BTREE", "GIN", "BRIN"
]);

const PG_FUNCTIONS = new Set([
    "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "NULLIF", "GREATEST", "LEAST",
    "ROW_NUMBER", "RANK", "DENSE_RANK", "LAG", "LEAD", "FIRST_VALUE", "LAST_VALUE",
    "LOWER", "UPPER", "TRIM", "SUBSTRING", "LENGTH", "REPLACE", "CONCAT", "SPLIT_PART",
    "EXTRACT", "DATE_TRUNC", "AGE", "NOW", "CURRENT_TIMESTAMP", "CURRENT_DATE",
    "ROUND", "FLOOR", "CEIL", "ABS", "POWER", "SQRT", "STRING_AGG", "ARRAY_AGG",
    "JSON_AGG", "JSONB_AGG", "TO_CHAR", "TO_DATE", "TO_TIMESTAMP"
]);

const SQL_TOKEN_RE = /(\\/\\*[\\s\\S]*?\\*\\/|--[^\\n]*|'(?:''|[^'])*'|"(?:""|[^"])*"|\\b\\d+(?:\\.\\d+)?\\b|\\b[A-Za-z_][A-Za-z0-9_]*\\b|<>|!=|<=|>=|::|\\|\\||[=<>+\\-*\\/%(),.;])/g;

function escHtml(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function highlightSql(src) {
    const text = src.endsWith("\\n") ? src + " " : src;
    let out = "";
    let lastIndex = 0;
    SQL_TOKEN_RE.lastIndex = 0;
    let m;
    while ((m = SQL_TOKEN_RE.exec(text)) !== null) {
        if (m.index > lastIndex) {
            out += escHtml(text.slice(lastIndex, m.index));
        }
        const tok = m[0];
        if (tok.startsWith("/*") || tok.startsWith("--")) {
            out += '<span class="qt-tok-cmt">' + escHtml(tok) + "</span>";
        } else if (tok.startsWith("'")) {
            out += '<span class="qt-tok-str">' + escHtml(tok) + "</span>";
        } else if (tok.startsWith('"')) {
            out += '<span class="qt-tok-id">' + escHtml(tok) + "</span>";
        } else if (/^\\d/.test(tok)) {
            out += '<span class="qt-tok-num">' + escHtml(tok) + "</span>";
        } else if (/^[A-Za-z_]/.test(tok)) {
            const up = tok.toUpperCase();
            if (PG_KEYWORDS.has(up)) {
                out += '<span class="qt-tok-kw">' + escHtml(tok) + "</span>";
            } else if (PG_FUNCTIONS.has(up)) {
                out += '<span class="qt-tok-fn">' + escHtml(tok) + "</span>";
            } else {
                out += escHtml(tok);
            }
        } else {
            out += '<span class="qt-tok-op">' + escHtml(tok) + "</span>";
        }
        lastIndex = SQL_TOKEN_RE.lastIndex;
    }
    if (lastIndex < text.length) {
        out += escHtml(text.slice(lastIndex));
    }
    return out;
}

function computeCursorPos(text, caretIdx) {
    const before = text.slice(0, caretIdx);
    const lines = before.split("\\n");
    return { ln: lines.length, col: lines[lines.length - 1].length + 1 };
}

export default function(component) {
    const { data, setStateValue, setTriggerValue, parentElement } = component;
    if (!data) return;

    let root = parentElement.querySelector(".qt-ide-root");
    if (!root) {
        root = document.createElement("div");
        root.className = "qt-ide-root";
        root.innerHTML = `
            <div class="qt-ide-toolbar">
                <div class="qt-ide-btn-group">
                    <button type="button" class="qt-ide-btn qt-ide-btn-primary" data-act="execute" title="Run read-only SELECT (Ctrl+Enter)">Execute</button>
                    <button type="button" class="qt-ide-btn qt-ide-btn-accent" data-act="analyze" title="Run AST analysis + EXPLAIN ANALYZE (Shift+Enter)">Explain Analyze</button>
                    <button type="button" class="qt-ide-btn" data-act="explain" title="Run estimate-only EXPLAIN without executing">Explain</button>
                    <button type="button" class="qt-ide-btn" data-act="validate" title="Validate read-only PostgreSQL AST">Validate</button>
                    <button type="button" class="qt-ide-btn" data-act="format" title="Format SQL">Format</button>
                    <button type="button" class="qt-ide-btn" data-act="copy" title="Copy SQL to clipboard">Copy</button>
                    <button type="button" class="qt-ide-btn" data-act="clear" title="Clear active editor tab">Clear</button>
                </div>
                <div class="qt-ide-shortcut">Ctrl+Enter Execute &middot; Shift+Enter Analyze</div>
            </div>
            <div class="qt-ide-body">
                <div class="qt-ide-gutter"><div class="qt-ide-gutter-inner"></div></div>
                <div class="qt-ide-code-wrap">
                    <pre class="qt-ide-highlight" aria-hidden="true"></pre>
                    <textarea class="qt-ide-textarea" spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off" aria-label="PostgreSQL SQL Editor"></textarea>
                </div>
            </div>
            <div class="qt-ide-footer">
                <div class="qt-ide-footer-left">
                    <span class="qt-ide-cursor">Ln 1, Col 1</span>
                    <span class="qt-ide-chars">0 chars</span>
                    <span class="qt-ide-policy">READ-ONLY GUARDED</span>
                </div>
                <div class="qt-ide-footer-right">
                    <span class="qt-ide-status-msg"></span>
                </div>
            </div>
        `;
        parentElement.appendChild(root);

        const ta = root.querySelector(".qt-ide-textarea");
        const pre = root.querySelector(".qt-ide-highlight");
        const gutterInner = root.querySelector(".qt-ide-gutter-inner");
        const cursorEl = root.querySelector(".qt-ide-cursor");
        const charsEl = root.querySelector(".qt-ide-chars");
        const statusEl = root.querySelector(".qt-ide-status-msg");

        root._qtState = {
            seq: String(data.seq ?? 0),
            rev: 0,
            actionId: 0,
            lastSyncedSql: String(data.sql ?? ""),
            debounceTimer: null,
            suppressBlurSync: false
        };

        const renderSurface = () => {
            const val = ta.value;
            pre.innerHTML = highlightSql(val);
            const linesCount = val.length === 0 ? 1 : val.split("\\n").length;
            let gHtml = "";
            for (let i = 1; i <= linesCount; i++) {
                gHtml += '<div class="qt-ide-gutter-ln">' + i + "</div>";
            }
            gutterInner.innerHTML = gHtml;
            charsEl.textContent = val.length + " chars";
            const pos = computeCursorPos(val, ta.selectionStart || 0);
            cursorEl.textContent = "Ln " + pos.ln + ", Col " + pos.col;
            pre.scrollTop = ta.scrollTop;
            pre.scrollLeft = ta.scrollLeft;
            gutterInner.style.transform = "translateY(" + (-ta.scrollTop) + "px)";
        };

        const syncDraftState = () => {
            const st = root._qtState;
            if (ta.value === st.lastSyncedSql) return;
            st.lastSyncedSql = ta.value;
            st.rev += 1;
            setStateValue("draft", {
                sql: ta.value,
                seq: Number(st.seq),
                rev: st.rev
            });
        };

        const fireAction = (actName) => {
            const st = root._qtState;
            if (st.debounceTimer) {
                clearTimeout(st.debounceTimer);
                st.debounceTimer = null;
            }
            if (actName === "clear") {
                ta.value = "";
                renderSurface();
            }
            st.lastSyncedSql = ta.value;
            st.rev += 1;
            st.actionId += 1;
            setTriggerValue("action", {
                type: actName,
                sql: ta.value,
                seq: Number(st.seq),
                id: String(Date.now()) + ":" + st.actionId
            });
        };

        root._qtRenderSurface = renderSurface;

        ta.value = String(data.sql ?? "");
        renderSurface();

        ta.addEventListener("input", () => {
            renderSurface();
            const st = root._qtState;
            if (st.debounceTimer) clearTimeout(st.debounceTimer);
            st.debounceTimer = setTimeout(() => {
                syncDraftState();
            }, 420);
        });

        ta.addEventListener("scroll", () => {
            pre.scrollTop = ta.scrollTop;
            pre.scrollLeft = ta.scrollLeft;
            gutterInner.style.transform = "translateY(" + (-ta.scrollTop) + "px)";
        });

        ta.addEventListener("click", renderSurface);
        ta.addEventListener("keyup", renderSurface);
        ta.addEventListener("select", renderSurface);

        ta.addEventListener("blur", () => {
            const st = root._qtState;
            if (st.suppressBlurSync) {
                st.suppressBlurSync = false;
                return;
            }
            if (st.debounceTimer) {
                clearTimeout(st.debounceTimer);
                st.debounceTimer = null;
            }
            syncDraftState();
        });

        ta.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault();
                fireAction("execute");
                return;
            }
            if (e.shiftKey && e.key === "Enter") {
                e.preventDefault();
                fireAction("analyze");
                return;
            }
            if (e.key === "Tab") {
                e.preventDefault();
                const start = ta.selectionStart;
                const end = ta.selectionEnd;
                if (!e.shiftKey) {
                    const nextVal = ta.value.slice(0, start) + "    " + ta.value.slice(end);
                    ta.value = nextVal;
                    ta.selectionStart = ta.selectionEnd = start + 4;
                } else {
                    const lineStart = ta.value.lastIndexOf("\\n", start - 1) + 1;
                    const slice = ta.value.slice(lineStart, start);
                    const removeMatch = slice.match(/^ {1,4}/);
                    if (removeMatch) {
                        const nRem = removeMatch[0].length;
                        ta.value = ta.value.slice(0, lineStart) + ta.value.slice(lineStart + nRem);
                        ta.selectionStart = ta.selectionEnd = Math.max(lineStart, start - nRem);
                    }
                }
                renderSurface();
                const st = root._qtState;
                if (st.debounceTimer) clearTimeout(st.debounceTimer);
                st.debounceTimer = setTimeout(syncDraftState, 420);
            }
        });

        root.querySelectorAll("button[data-act]").forEach((btn) => {
            btn.addEventListener("mousedown", () => {
                root._qtState.suppressBlurSync = true;
            });
            btn.addEventListener("click", async () => {
                const act = btn.getAttribute("data-act");
                if (act === "copy") {
                    try {
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            await navigator.clipboard.writeText(ta.value);
                        } else {
                            const tmp = document.createElement("textarea");
                            tmp.value = ta.value;
                            document.body.appendChild(tmp);
                            tmp.select();
                            document.execCommand("copy");
                            tmp.remove();
                        }
                        statusEl.textContent = "Copied SQL";
                        setTimeout(() => { statusEl.textContent = ""; }, 1800);
                    } catch (_err) {
                        statusEl.textContent = "Clipboard unavailable";
                        setTimeout(() => { statusEl.textContent = ""; }, 1800);
                    }
                    ta.focus();
                    return;
                }
                fireAction(act);
            });
        });
    }

    // Apply active theme palette tokens & height
    const pal = data.palette || {};
    root.style.setProperty("--ide-bg", pal.bg || "#0E141B");
    root.style.setProperty("--ide-bar", pal.bar || "#1B2530");
    root.style.setProperty("--ide-gutter", pal.gutter || "#111820");
    root.style.setProperty("--ide-surface", pal.surface || "#1B2530");
    root.style.setProperty("--ide-border", pal.border || "#34414D");
    root.style.setProperty("--ide-border-subtle", pal.borderSubtle || "#25313D");
    root.style.setProperty("--ide-fg", pal.fg || "#E8EDF2");
    root.style.setProperty("--ide-sec", pal.sec || "#9BA9B7");
    root.style.setProperty("--ide-muted", pal.muted || "#738292");
    root.style.setProperty("--ide-accent", pal.accent || "#35A99B");
    root.style.setProperty("--ide-accent-hover", pal.accentHover || "#2C9185");
    root.style.setProperty("--ide-accent-soft", pal.accentSoft || "rgba(53,169,155,0.14)");
    root.style.setProperty("--ide-accent-text", pal.accentText || "#58C4B6");
    root.style.setProperty("--ide-btn-bg", pal.btnBg || "#202C38");
    root.style.setProperty("--ide-btn-hover", pal.btnHover || "#273545");
    root.style.setProperty("--ide-sel", pal.selection || "rgba(53,169,155,0.28)");
    root.style.setProperty("--ide-kw", pal.kw || "#56B6C2");
    root.style.setProperty("--ide-fn", pal.fn || "#D4A656");
    root.style.setProperty("--ide-str", pal.str || "#78B87E");
    root.style.setProperty("--ide-num", pal.num || "#C98D68");
    root.style.setProperty("--ide-cmt", pal.cmt || "#687889");
    root.style.setProperty("--ide-op", pal.op || "#9BA9B7");
    root.style.setProperty("--ide-height", String(data.height || 270) + "px");

    const ta = root.querySelector(".qt-ide-textarea");
    const policyEl = root.querySelector(".qt-ide-policy");
    if (policyEl && data.policyLabel) {
        policyEl.textContent = data.policyLabel;
    }

    const incomingSeq = String(data.seq ?? 0);
    if (root._qtState.seq !== incomingSeq) {
        root._qtState.seq = incomingSeq;
        const nextSql = String(data.sql ?? "");
        if (ta.value !== nextSql) {
            ta.value = nextSql;
        }
        root._qtState.lastSyncedSql = nextSql;
        root._qtState.rev = 0;
        root._qtRenderSurface();
    }
}
"""


_SQL_IDE_COMPONENT = st.components.v2.component(
    "qt_sql_ide_editor",
    css=_IDE_CSS,
    js=_IDE_JS,
)


def _palette_from_theme(t: ThemeTokens) -> dict[str, str]:
    return {
        "bg": t.bg_code,
        "bar": t.bg_elevated,
        "gutter": t.bg_sidebar,
        "surface": t.bg_surface,
        "border": t.border,
        "borderSubtle": t.border_subtle,
        "fg": t.text_primary,
        "sec": t.text_secondary,
        "muted": t.text_muted,
        "accent": t.accent,
        "accentHover": t.accent_hover,
        "accentSoft": t.accent_soft,
        "accentText": t.accent_text,
        "btnBg": t.bg_surface,
        "btnHover": t.bg_elevated,
        "selection": "rgba(53, 169, 155, 0.28)" if t.is_dark else "rgba(30, 138, 126, 0.22)",
        "kw": t.tok_keyword,
        "fn": t.tok_function,
        "str": t.tok_string,
        "num": t.tok_number,
        "cmt": t.tok_comment,
        "op": t.tok_operator,
    }


def render_sql_ide(
    *,
    key: str = "qt_sql_ide_instance",
    height: int = 270,
    policy_label: str = "READ-ONLY GUARDED",
) -> tuple[str, str | None]:
    """Render the line-numbered, syntax-highlighted PostgreSQL IDE editor.

    Returns ``(current_sql, triggered_action)`` where ``triggered_action`` is one of
    ``'execute'``, ``'analyze'``, ``'explain'``, ``'validate'``, ``'format'``, ``'clear'``,
    or ``None``.
    """
    theme = get_active_theme()
    seq = int(st.session_state.get("qt_editor_seq", 1))
    current_sql = str(st.session_state.get("qt_editor_sql", ""))

    result = _SQL_IDE_COMPONENT(
        key=key,
        data={
            "sql": current_sql,
            "seq": seq,
            "height": int(height),
            "policyLabel": policy_label,
            "palette": _palette_from_theme(theme),
        },
        on_draft_change=lambda: None,
        on_action_change=lambda: None,
    )

    triggered_action: str | None = None

    action_payload = getattr(result, "action", None)
    if isinstance(action_payload, dict):
        act_id = str(action_payload.get("id", ""))
        act_seq = action_payload.get("seq")
        if act_id and act_id != st.session_state.get("qt_editor_last_action_id") and act_seq == seq:
            st.session_state["qt_editor_last_action_id"] = act_id
            act_sql = str(action_payload.get("sql", current_sql))
            st.session_state["qt_editor_sql"] = act_sql
            tabs = st.session_state.get("qt_sql_tabs")
            tab_idx = int(st.session_state.get("qt_active_sql_tab", 0))
            if isinstance(tabs, list) and 0 <= tab_idx < len(tabs):
                tabs[tab_idx]["sql"] = act_sql
            current_sql = act_sql
            triggered_action = str(action_payload.get("type", "")) or None

    if triggered_action is None:
        draft_payload = getattr(result, "draft", None)
        if isinstance(draft_payload, dict) and draft_payload.get("seq") == seq:
            rev = int(draft_payload.get("rev", 0))
            last_seq_rev = st.session_state.get("qt_editor_consumed_rev", (0, 0))
            if last_seq_rev[0] != seq or rev > last_seq_rev[1]:
                st.session_state["qt_editor_consumed_rev"] = (seq, rev)
                draft_sql = str(draft_payload.get("sql", current_sql))
                st.session_state["qt_editor_sql"] = draft_sql
                tabs = st.session_state.get("qt_sql_tabs")
                tab_idx = int(st.session_state.get("qt_active_sql_tab", 0))
                if isinstance(tabs, list) and 0 <= tab_idx < len(tabs):
                    tabs[tab_idx]["sql"] = draft_sql
                current_sql = draft_sql

    return current_sql, triggered_action


def render_sql_editor_box(
    *,
    label: str = "PostgreSQL SQL Editor",
    key: str = "qt_sql_ide_instance",
    height: int = 260,
    show_highlight_preview: bool = False,
) -> str:
    """Backward-compatible wrapper returning current SQL from the IDE editor."""
    del label, show_highlight_preview
    sql_val, _ = render_sql_ide(key=key, height=height)
    return sql_val
