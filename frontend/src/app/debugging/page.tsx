"use client";

import React, { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  Bug,
  Check,
  CheckCircle2,
  Code2,
  Play,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/context";
import type { DebugAnalyzeResponse, DebugFixCandidate, ExecutionResponse } from "@/lib/types";
import { EditorDiagnosticMarker, MonacoSqlEditor } from "@/components/MonacoSqlEditor";
import { MonacoDiffPanel } from "@/components/MonacoDiffPanel";
import { ResultsExplorer } from "@/components/ResultsExplorer";

const BUG_PRESETS = [
  {
    label: "Missing Column Typo",
    sql: "SELECT e.employee_id, e.first_nam, e.base_salary\nFROM employees e\nORDER BY e.base_salary DESC;",
  },
  {
    label: "Ambiguous Column & Missing JOIN ON",
    sql: "SELECT employee_id, first_name, total_amount\nFROM employees e\nJOIN orders o;",
  },
  {
    label: "NULL Equality Trap (= NULL)",
    sql: "SELECT employee_id, first_name, hire_date\nFROM employees\nWHERE hire_date = NULL;",
  },
  {
    label: "Unaggregated SELECT / Missing GROUP BY",
    sql: "SELECT department_id, COUNT(employee_id) AS headcount\nFROM employees;",
  },
];

export default function DebuggingPage() {
  const router = useRouter();
  const { context, activeSql, setActiveSql, lastError, setLastError } = useWorkspace();

  const [capturedError, setCapturedError] = useState(lastError || "");
  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState<DebugAnalyzeResponse | null>(null);
  const [selectedFixId, setSelectedFixId] = useState<string | null>(null);
  const [rejectedIds, setRejectedIds] = useState<Record<string, boolean>>({});
  const [appliedBanner, setAppliedBanner] = useState<string | null>(null);

  const [testingFix, setTestingFix] = useState(false);
  const [testedExecResult, setTestedExecResult] = useState<ExecutionResponse | null>(null);

  const activeDialect = context?.dialect || "postgresql";

  const handleAnalyze = async (sqlOverride?: string) => {
    const targetSql = sqlOverride ?? activeSql;
    if (!targetSql.trim()) return;
    setAnalyzing(true);
    setAppliedBanner(null);
    setTestedExecResult(null);
    setRejectedIds({});
    try {
      const res = await api.debugSql({
        sql: targetSql,
        dialect: activeDialect,
        captured_error: capturedError.trim() || null,
        test_fixes: true,
      });
      setReport(res);
      setSelectedFixId(res.fix_candidates[0]?.fix_id || null);
    } finally {
      setAnalyzing(false);
    }
  };

  const editorMarkers = useMemo<EditorDiagnosticMarker[]>(() => {
    if (!report) return [];
    return report.diagnostics.map((d) => ({
      line: d.line,
      column: d.column,
      severity: d.category === "confirmed_error" ? "error" : "warning",
      message: `${d.title}: ${d.message}`,
    }));
  }, [report]);

  const visibleCandidates = useMemo(() => {
    return (report?.fix_candidates || []).filter((c) => !rejectedIds[c.fix_id]);
  }, [report, rejectedIds]);

  const selectedFix: DebugFixCandidate | null =
    visibleCandidates.find((c) => c.fix_id === selectedFixId) || visibleCandidates[0] || null;

  const handleTestFix = async (candidate: DebugFixCandidate) => {
    setTestingFix(true);
    try {
      const res = await api.executeSql({
        sql: candidate.corrected_sql,
        dialect: activeDialect,
        max_rows: 50,
      });
      setTestedExecResult(res);
    } finally {
      setTestingFix(false);
    }
  };

  const handleApplyFix = (candidate: DebugFixCandidate) => {
    setActiveSql(candidate.corrected_sql);
    setLastError(null);
    setCapturedError("");
    setAppliedBanner(`Applied "${candidate.title}" to active SQL buffer.`);
  };

  const handleRejectFix = (fixId: string) => {
    setRejectedIds((prev) => ({ ...prev, [fixId]: true }));
    if (selectedFix?.fix_id === fixId) {
      setSelectedFixId(null);
      setTestedExecResult(null);
    }
  };

  const groupedDiagnostics = useMemo(() => {
    const diags = report?.diagnostics || [];
    return {
      confirmed: diags.filter((d) => d.category === "confirmed_error"),
      logical: diags.filter((d) => d.category === "logical_warning"),
      perf: diags.filter((d) => d.category === "performance_warning"),
    };
  }, [report]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Debugging &amp; AST Fix Verification
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
            Isolates syntax errors, unknown identifiers, missing joins, and NULL traps, then
            pre-verifies candidate fixes in a safe diff review.
          </p>
        </div>
        <button
          type="button"
          onClick={() => router.push("/sql-editor")}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
        >
          <Code2 className="h-3.5 w-3.5 text-[var(--accent-primary)]" /> Open Active SQL in IDE
        </button>
      </div>

      {/* Diagnostic Input & Presets */}
      <section className="qt-surface p-4 space-y-3.5 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[13px] font-semibold text-[var(--text-primary)]">
            Sample fault scenarios
          </span>
          <div className="flex flex-wrap gap-1.5">
            {BUG_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  setActiveSql(preset.sql);
                  setCapturedError("");
                  void handleAnalyze(preset.sql);
                }}
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:border-[var(--accent-primary)]/50 hover:text-[var(--accent-primary)] transition-colors"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        <MonacoSqlEditor
          label="SQL Under Diagnosis"
          value={activeSql}
          onChange={setActiveSql}
          dialect={activeDialect}
          height="210px"
          schemaTables={context?.tables || []}
          diagnostics={editorMarkers}
        />

        <div className="grid gap-3 md:grid-cols-12 items-end">
          <div className="md:col-span-9">
            <label
              htmlFor="captured-error-input"
              className="mb-1.5 block text-xs font-medium text-[var(--text-secondary)]"
            >
              Captured runtime error trace (optional — auto-populated from SQL IDE)
            </label>
            <input
              id="captured-error-input"
              type="text"
              value={capturedError}
              onChange={(e) => setCapturedError(e.target.value)}
              placeholder='e.g. Binder Error: Referenced column "first_nam" not found'
              className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:outline-none"
            />
          </div>
          <div className="md:col-span-3 flex justify-end">
            <button
              type="button"
              disabled={analyzing || !activeSql.trim()}
              onClick={() => void handleAnalyze()}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-4 py-2 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
            >
              <Bug className="h-3.5 w-3.5" />
              {analyzing ? "Inspecting..." : "Diagnose & Verify Fixes"}
            </button>
          </div>
        </div>
      </section>

      {appliedBanner && (
        <div className="flex items-center justify-between rounded-lg border border-[var(--status-success-border)] bg-[var(--status-success-bg)] px-4 py-3 text-xs text-[var(--status-success-text)]">
          <span className="font-medium">{appliedBanner}</span>
          <button
            type="button"
            onClick={() => router.push("/sql-editor")}
            className="font-medium underline hover:opacity-80"
          >
            Execute in SQL IDE →
          </button>
        </div>
      )}

      {report && (
        <div className="grid gap-6 lg:grid-cols-12 items-start">
          {/* Left Diagnostics Column */}
          <section className="qt-surface lg:col-span-5 p-4 text-xs space-y-3.5">
            <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-2.5">
              <h2 className="text-[13px] font-semibold text-[var(--text-primary)]">
                Diagnostics ({report.diagnostics.length})
              </h2>
              <span
                className={`rounded-md border px-2 py-0.5 text-[11px] font-medium ${
                  report.has_errors
                    ? "border-[var(--status-error-border)] bg-[var(--status-error-bg)] text-[var(--status-error-text)]"
                    : "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]"
                }`}
              >
                {report.has_errors ? "Faults detected" : "No errors"}
              </span>
            </div>

            {report.diagnostics.length === 0 && (
              <div className="rounded-md border border-[var(--status-success-border)] bg-[var(--status-success-bg)] p-3 text-[var(--status-success-text)]">
                No syntax, schema, ambiguity, or logic errors detected against{" "}
                <strong>{context?.label}</strong>.
              </div>
            )}

            {[
              {
                key: "confirmed",
                title: "Confirmed errors",
                items: groupedDiagnostics.confirmed,
                box: "border-[var(--status-error-border)] bg-[var(--status-error-bg)]",
                titleColor: "text-[var(--status-error-text)]",
                icon: AlertCircle,
              },
              {
                key: "logical",
                title: "Logical warnings",
                items: groupedDiagnostics.logical,
                box: "border-[var(--status-warning-border)] bg-[var(--status-warning-bg)]",
                titleColor: "text-[var(--status-warning-text)]",
                icon: AlertTriangle,
              },
              {
                key: "perf",
                title: "Structural warnings",
                items: groupedDiagnostics.perf,
                box: "border-[var(--border-subtle)] bg-[var(--bg-subtle)]",
                titleColor: "text-[var(--text-primary)]",
                icon: AlertTriangle,
              },
            ]
              .filter((g) => g.items.length > 0)
              .map((group) => {
                const Icon = group.icon;
                return (
                  <div key={group.key} className="space-y-2">
                    <div className="text-[11.5px] font-medium text-[var(--text-secondary)]">
                      {group.title} ({group.items.length})
                    </div>
                    {group.items.map((diag, idx) => (
                      <div
                        key={`${diag.code}-${idx}`}
                        className={`rounded-md border p-3 space-y-1.5 ${group.box}`}
                      >
                        <div className={`flex items-center justify-between gap-2 font-semibold ${group.titleColor}`}>
                          <span className="inline-flex items-center gap-1.5">
                            <Icon className="h-3.5 w-3.5 shrink-0" />
                            {diag.title}
                          </span>
                          {diag.line && (
                            <span className="font-mono text-[11px]">
                              L{diag.line}
                              {diag.column ? `:C${diag.column}` : ""}
                            </span>
                          )}
                        </div>
                        <p className="text-xs leading-snug text-[var(--text-primary)]">
                          {diag.message}
                        </p>
                        {diag.suggestion && (
                          <p className="text-[11.5px] text-[var(--text-secondary)]">
                            Suggested fix: {diag.suggestion}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}
          </section>

          {/* Right Candidate Fixes & Diff Column */}
          <section className="lg:col-span-7 space-y-4">
            <div className="qt-surface p-4 text-xs space-y-3.5">
              <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-2.5">
                <h2 className="text-[13px] font-semibold text-[var(--text-primary)]">
                  Verified fix candidates ({visibleCandidates.length})
                </h2>
                <span className="text-[11px] text-[var(--text-muted)]">
                  Diff preview before applying
                </span>
              </div>

              {visibleCandidates.length === 0 ? (
                <div className="rounded-md border border-dashed border-[var(--border-strong)] p-6 text-center text-xs text-[var(--text-muted)]">
                  No active fix candidates remaining. Review diagnostics on the left and edit SQL
                  above.
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {visibleCandidates.map((cand) => (
                      <button
                        key={cand.fix_id}
                        type="button"
                        onClick={() => {
                          setSelectedFixId(cand.fix_id);
                          setTestedExecResult(null);
                        }}
                        className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                          selectedFix?.fix_id === cand.fix_id
                            ? "border-[var(--accent-primary)]/50 bg-[var(--accent-tint)] text-[var(--accent-primary)]"
                            : "border-[var(--border-subtle)] bg-white text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                        }`}
                      >
                        {cand.test_passed === true && (
                          <CheckCircle2 className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
                        )}
                        <span>{cand.title}</span>
                      </button>
                    ))}
                  </div>

                  {selectedFix && (
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3.5 py-2.5">
                        <div>
                          <div className="font-semibold text-[var(--text-primary)]">
                            {selectedFix.title}
                          </div>
                          <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                            {selectedFix.explanation}
                          </div>
                        </div>
                        {selectedFix.tested && (
                          <span
                            className={`rounded-md border px-2 py-0.5 font-mono text-[11px] ${
                              selectedFix.test_passed
                                ? "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]"
                                : "border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-[var(--status-warning-text)]"
                            }`}
                          >
                            {selectedFix.test_passed
                              ? `Verified pass · ${selectedFix.test_rows ?? 0} rows · ${selectedFix.test_duration_ms ?? 0} ms`
                              : `Notice: ${selectedFix.test_error}`}
                          </span>
                        )}
                      </div>

                      <MonacoDiffPanel
                        originalSql={report.original_sql}
                        modifiedSql={selectedFix.corrected_sql}
                        dialect={activeDialect}
                        height="245px"
                      />

                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleApplyFix(selectedFix)}
                          className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-3.5 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)]"
                        >
                          <Check className="h-3.5 w-3.5" />
                          Apply Correction
                        </button>
                        <button
                          type="button"
                          disabled={testingFix}
                          onClick={() => void handleTestFix(selectedFix)}
                          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] px-3 py-1.5 text-xs font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-soft)]"
                        >
                          <Play className="h-3.5 w-3.5" />
                          {testingFix ? "Testing..." : "Test Correction"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRejectFix(selectedFix.fix_id)}
                          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:border-[var(--status-error-border)] hover:text-[var(--status-error-text)]"
                        >
                          <X className="h-3.5 w-3.5" />
                          Reject Correction
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {(testedExecResult || testingFix) && (
              <ResultsExplorer result={testedExecResult} loading={testingFix} />
            )}
          </section>
        </div>
      )}
    </div>
  );
}
