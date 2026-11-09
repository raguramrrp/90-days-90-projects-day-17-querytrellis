"use client";

import React, { useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  Columns3,
  Copy,
  Download,
  Search,
  Wrench,
} from "lucide-react";
import type { ExecutionResponse } from "@/lib/types";

interface ResultsExplorerProps {
  result: ExecutionResponse | null;
  loading?: boolean;
  onSendToDebug?: () => void;
}

function escapeCsvCell(val: unknown): string {
  if (val === null || val === undefined) return "";
  const s = String(val);
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function ResultsExplorer({ result, loading = false, onSendToDebug }: ResultsExplorerProps) {
  const [filterText, setFilterText] = useState("");
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [showColInspector, setShowColInspector] = useState(false);
  const [copiedMode, setCopiedMode] = useState<string | null>(null);

  const columns = result?.columns || [];
  const columnTypes = result?.column_types || [];
  const rawRows = result?.rows || [];

  const filteredAndSortedRows = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    let rows = q
      ? rawRows.filter((r) =>
          columns.some((c) => {
            const val = r[c];
            return val !== null && val !== undefined && String(val).toLowerCase().includes(q);
          })
        )
      : rawRows;

    if (sortCol && columns.includes(sortCol)) {
      rows = [...rows].sort((a, b) => {
        const av = a[sortCol];
        const bv = b[sortCol];
        if (av === bv) return 0;
        if (av === null || av === undefined) return 1;
        if (bv === null || bv === undefined) return -1;
        if (typeof av === "number" && typeof bv === "number") {
          return sortDir === "asc" ? av - bv : bv - av;
        }
        const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
        return sortDir === "asc" ? cmp : -cmp;
      });
    }
    return rows;
  }, [rawRows, columns, filterText, sortCol, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filteredAndSortedRows.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pagedRows = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return filteredAndSortedRows.slice(start, start + pageSize);
  }, [filteredAndSortedRows, safePage, pageSize]);

  const columnStats = useMemo(() => {
    return columns.map((col, idx) => {
      let nulls = 0;
      const distinct = new Set<string>();
      const nums: number[] = [];
      for (const r of rawRows) {
        const v = r[col];
        if (v === null || v === undefined) {
          nulls += 1;
        } else {
          distinct.add(String(v));
          if (typeof v === "number" && Number.isFinite(v)) nums.push(v);
        }
      }
      return {
        name: col,
        type: columnTypes[idx] || "unknown",
        nonNull: rawRows.length - nulls,
        nulls,
        distinctCount: distinct.size,
        minNum: nums.length > 0 ? Math.min(...nums) : null,
        maxNum: nums.length > 0 ? Math.max(...nums) : null,
      };
    });
  }, [columns, columnTypes, rawRows]);

  const toggleSort = (col: string) => {
    setPage(1);
    if (sortCol === col) {
      if (sortDir === "asc") setSortDir("desc");
      else setSortCol(null);
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  };

  const handleCopy = async (mode: "tsv" | "json") => {
    if (!result) return;
    let text = "";
    if (mode === "json") {
      text = JSON.stringify(filteredAndSortedRows, null, 2);
    } else {
      const header = columns.join("\t");
      const lines = filteredAndSortedRows.map((r) =>
        columns.map((c) => (r[c] === null || r[c] === undefined ? "" : String(r[c]))).join("\t")
      );
      text = [header, ...lines].join("\n");
    }
    await navigator.clipboard.writeText(text);
    setCopiedMode(mode);
    setTimeout(() => setCopiedMode(null), 1500);
  };

  const handleDownloadCsv = () => {
    if (!result || columns.length === 0) return;
    const header = columns.map(escapeCsvCell).join(",");
    const body = filteredAndSortedRows
      .map((r) => columns.map((c) => escapeCsvCell(r[c])).join(","))
      .join("\n");
    const blob = new Blob([`${header}\n${body}`], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `querytrellis-results-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="qt-surface p-6 text-center text-xs text-[var(--text-secondary)]">
        Running query against active engine...
      </div>
    );
  }

  if (!result) {
    return (
      <div className="qt-surface p-6 text-center text-xs text-[var(--text-muted)]">
        Run a query to inspect result rows, column types, and export options.
      </div>
    );
  }

  if (!result.success) {
    return (
      <div className="rounded-lg border border-[var(--status-error-border)] bg-[var(--status-error-bg)] p-4 text-xs">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-2.5 text-[var(--status-error-text)]">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
              <div className="text-[13px] font-semibold">
                {result.requires_write_confirmation
                  ? "Write confirmation required"
                  : "Query execution error"}
              </div>
              <p className="mt-1 font-mono text-[12px] whitespace-pre-wrap">
                {result.error_message}
              </p>
              {(result.error_line || result.error_column) && (
                <div className="mt-1 font-mono text-[11px] opacity-85">
                  Line {result.error_line ?? "?"}, Column {result.error_column ?? "?"}
                </div>
              )}
            </div>
          </div>
          {onSendToDebug && (
            <button
              type="button"
              onClick={onSendToDebug}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--status-error-border)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--status-error-text)] hover:bg-[#FAF0F0]"
            >
              <Wrench className="h-3.5 w-3.5" />
              Diagnose in Debugger
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="qt-surface overflow-hidden text-xs">
      {/* Results Summary Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2.5 text-[12px] text-[var(--text-secondary)]">
          <span className="inline-flex items-center gap-1.5 font-medium text-[var(--status-success-text)]">
            <span className="h-2 w-2 rounded-full bg-[var(--accent-primary)]" />
            {result.rows_returned} row{result.rows_returned === 1 ? "" : "s"}
            {result.rows_affected !== null && result.rows_affected >= 0
              ? ` (${result.rows_affected} affected)`
              : ""}
          </span>
          <span className="text-[var(--border-strong)]">·</span>
          <span className="font-mono text-[11.5px] text-[var(--text-primary)]">
            {result.duration_ms} ms
          </span>
          <span className="text-[var(--border-strong)]">·</span>
          <span>{result.executed_dialect}</span>
          {result.was_truncated && (
            <span className="rounded border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] px-2 py-0.5 text-[11px] text-[var(--status-warning-text)]">
              Limited to {result.max_rows_applied} rows
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {columns.length > 0 && (
            <>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
                <input
                  type="text"
                  value={filterText}
                  onChange={(e) => {
                    setFilterText(e.target.value);
                    setPage(1);
                  }}
                  placeholder="Filter rows..."
                  className="w-40 rounded-md border border-[var(--border-subtle)] bg-white py-1 pl-7 pr-2.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:outline-none"
                />
              </div>
              <button
                type="button"
                onClick={() => setShowColInspector((v) => !v)}
                className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
                  showColInspector
                    ? "border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] text-[var(--accent-primary)]"
                    : "border-[var(--border-subtle)] bg-white text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                <Columns3 className="h-3.5 w-3.5" />
                Columns ({columns.length})
              </button>
              <button
                type="button"
                onClick={() => void handleCopy("tsv")}
                className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
              >
                {copiedMode === "tsv" ? (
                  <Check className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                TSV
              </button>
              <button
                type="button"
                onClick={() => void handleCopy("json")}
                className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
              >
                {copiedMode === "json" ? (
                  <Check className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                JSON
              </button>
              <button
                type="button"
                onClick={handleDownloadCsv}
                className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
              >
                <Download className="h-3.5 w-3.5" />
                CSV
              </button>
            </>
          )}
        </div>
      </div>

      {result.notes && result.notes.length > 0 && (
        <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 py-2 text-xs text-[var(--text-secondary)]">
          {result.notes.join(" · ")}
        </div>
      )}

      {/* Column Stats Inspector */}
      {showColInspector && columns.length > 0 && (
        <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-4">
          <div className="mb-2.5 text-xs font-medium text-[var(--text-primary)]">
            Column summary (computed from returned rows)
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {columnStats.map((st) => (
              <div
                key={st.name}
                className="rounded-md border border-[var(--border-subtle)] bg-white p-2.5"
              >
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate font-mono font-medium text-[var(--text-primary)]">
                    {st.name}
                  </span>
                  <span className="font-mono text-[10.5px] text-[var(--accent-primary)]">
                    {st.type}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-[var(--text-secondary)]">
                  <span>{st.nonNull} non-null</span>
                  <span>{st.distinctCount} distinct</span>
                  {st.minNum !== null && (
                    <span>
                      {st.minNum}–{st.maxNum}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Data Grid */}
      {columns.length === 0 ? (
        <div className="p-5 text-xs text-[var(--text-secondary)]">
          Statement completed ({result.statement_type}) in {result.duration_ms} ms with 0 result
          columns.
        </div>
      ) : rawRows.length === 0 ? (
        <div className="p-6 text-center text-xs text-[var(--text-secondary)]">
          Query returned <strong className="font-mono text-[var(--text-primary)]">0 rows</strong> in{" "}
          {result.duration_ms} ms. Columns:{" "}
          <span className="font-mono text-[var(--text-primary)]">{columns.join(", ")}</span>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto bg-white">
            <table className="w-full border-collapse text-left text-[12.5px]">
              <thead>
                <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)]">
                  <th className="w-11 border-r border-[var(--border-subtle)] px-3 py-2 font-mono text-[11px] font-medium text-[var(--text-muted)]">
                    #
                  </th>
                  {columns.map((col, idx) => (
                    <th
                      key={col}
                      className="border-r border-[var(--border-subtle)] last:border-r-0 px-3 py-2 font-medium text-[var(--text-primary)]"
                    >
                      <button
                        type="button"
                        onClick={() => toggleSort(col)}
                        className="flex w-full items-center justify-between gap-2 text-left hover:text-[var(--accent-primary)]"
                      >
                        <div>
                          <div className="font-mono text-xs">{col}</div>
                          <div className="text-[10.5px] font-normal text-[var(--text-muted)]">
                            {columnTypes[idx] || ""}
                          </div>
                        </div>
                        {sortCol === col ? (
                          sortDir === "asc" ? (
                            <ArrowUp className="h-3.5 w-3.5 shrink-0 text-[var(--accent-primary)]" />
                          ) : (
                            <ArrowDown className="h-3.5 w-3.5 shrink-0 text-[var(--accent-primary)]" />
                          )
                        ) : (
                          <ArrowUpDown className="h-3 w-3 shrink-0 text-[var(--text-muted)]/60" />
                        )}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {pagedRows.map((row, rowIdx) => (
                  <tr
                    key={rowIdx}
                    className="hover:bg-[var(--bg-subtle)] transition-colors"
                  >
                    <td className="border-r border-[var(--border-subtle)] px-3 py-2 font-mono text-[11px] text-[var(--text-muted)]">
                      {(safePage - 1) * pageSize + rowIdx + 1}
                    </td>
                    {columns.map((col) => {
                      const val = row[col];
                      const isNum = typeof val === "number";
                      return (
                        <td
                          key={col}
                          className={`max-w-[280px] truncate border-r border-[var(--border-subtle)]/70 last:border-r-0 px-3 py-2 ${
                            isNum
                              ? "text-right font-mono text-xs text-[var(--text-primary)]"
                              : "text-left text-[var(--text-primary)]"
                          }`}
                          title={val === null || val === undefined ? "NULL" : String(val)}
                        >
                          {val === null || val === undefined ? (
                            <span className="font-mono text-[11px] italic text-[var(--text-muted)]">
                              null
                            </span>
                          ) : (
                            String(val)
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 py-2 text-xs text-[var(--text-secondary)]">
            <div className="font-mono text-[11.5px]">
              Showing {(safePage - 1) * pageSize + 1}–
              {Math.min(safePage * pageSize, filteredAndSortedRows.length)} of{" "}
              {filteredAndSortedRows.length}
            </div>
            <div className="flex items-center gap-2">
              <select
                aria-label="Rows per page"
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                className="rounded-md border border-[var(--border-subtle)] bg-white px-2 py-1 text-xs"
              >
                {[25, 50, 100].map((n) => (
                  <option key={n} value={n}>
                    {n} rows / page
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={safePage <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1 hover:bg-[var(--bg-hover)] disabled:opacity-40"
              >
                Previous
              </button>
              <span className="font-mono text-[11.5px]">
                {safePage} / {totalPages}
              </span>
              <button
                type="button"
                disabled={safePage >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1 hover:bg-[var(--bg-hover)] disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
