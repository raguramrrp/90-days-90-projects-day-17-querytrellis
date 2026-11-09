"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  CheckCircle2,
  Code2,
  DatabaseZap,
  Gauge,
  Layers,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/context";
import type { OptimizeAnalyzeResponse } from "@/lib/types";
import { MonacoSqlEditor } from "@/components/MonacoSqlEditor";

const OPTIMIZER_PRESETS = [
  {
    label: "SELECT * + Leading Wildcard LIKE",
    sql: "SELECT *\nFROM customers\nWHERE email LIKE '%@acme.com'\nORDER BY signup_date DESC;",
  },
  {
    label: "Date Function Filter on Indexed Column",
    sql: "SELECT order_id, customer_id, total_amount\nFROM orders\nWHERE EXTRACT(YEAR FROM order_date) = 2026\nORDER BY order_date DESC;",
  },
  {
    label: "Unindexed Status Filter + OFFSET Pagination",
    sql: "SELECT order_id, employee_id, total_amount\nFROM orders\nWHERE status = 'completed' OR status = 'shipped'\nORDER BY order_id DESC\nLIMIT 25 OFFSET 50;",
  },
];

export default function OptimizerPage() {
  const router = useRouter();
  const { context, activeSql, setActiveSql } = useWorkspace();

  const [allowExplainAnalyze, setAllowExplainAnalyze] = useState(false);
  const [selectedCandidateSql, setSelectedCandidateSql] = useState<string>("");
  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState<OptimizeAnalyzeResponse | null>(null);

  const activeDialect = context?.dialect || "postgresql";

  const runOptimize = async (
    sqlOverride?: string,
    optInAnalyze?: boolean,
    candidateOverride?: string
  ) => {
    const sqlToAnalyze = sqlOverride ?? activeSql;
    if (!sqlToAnalyze.trim()) return;
    const useAnalyze = optInAnalyze ?? allowExplainAnalyze;
    const candidate = candidateOverride !== undefined ? candidateOverride : selectedCandidateSql;
    setAnalyzing(true);
    try {
      const res = await api.optimizeSql({
        sql: sqlToAnalyze,
        dialect: activeDialect,
        include_estimated_plan: true,
        allow_explain_analyze: useAnalyze,
        benchmark_candidate_sql: useAnalyze && candidate.trim() ? candidate : null,
      });
      setReport(res);
      if (!candidate && res.static_suggestions?.rewrite_alternatives?.length) {
        setSelectedCandidateSql(res.static_suggestions.rewrite_alternatives[0].rewritten_sql);
      }
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Query Optimizer &amp; Execution Plan Analysis
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
            Separates static AST recommendations, estimated planner output (EXPLAIN), and opt-in
            A/B execution timing (EXPLAIN ANALYZE).
          </p>
        </div>
        <button
          type="button"
          onClick={() => router.push("/sql-editor")}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
        >
          <Code2 className="h-3.5 w-3.5 text-[var(--accent-primary)]" /> Open in SQL IDE
        </button>
      </div>

      {/* Unified 3-Tier Inspection Bar */}
      <div className="qt-surface grid divide-y divide-[var(--border-subtle)] sm:grid-cols-3 sm:divide-x sm:divide-y-0 text-xs">
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <div className="font-medium text-[var(--text-primary)]">Tier 1 · Static AST</div>
            <div className="mt-0.5 text-[var(--text-secondary)]">Anti-patterns &amp; index DDL</div>
          </div>
          <span className="rounded border border-[var(--status-success-border)] bg-[var(--status-success-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--status-success-text)]">
            Zero execution
          </span>
        </div>

        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <div className="font-medium text-[var(--text-primary)]">Tier 2 · Planner estimate</div>
            <div className="mt-0.5 text-[var(--text-secondary)]">EXPLAIN operator tree</div>
          </div>
          <span className="rounded border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
            Estimate only
          </span>
        </div>

        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <div className="font-medium text-[var(--text-primary)]">Tier 3 · Measured timing</div>
            <div className="mt-0.5 text-[var(--text-secondary)]">Opt-in A/B benchmark</div>
          </div>
          <span
            className={`rounded border px-2 py-0.5 text-[11px] font-medium ${
              allowExplainAnalyze
                ? "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]"
                : "border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-[var(--status-warning-text)]"
            }`}
          >
            {allowExplainAnalyze ? "Unlocked" : "Consent lock"}
          </span>
        </div>
      </div>

      {/* Target Input & Presets */}
      <section className="qt-surface p-4 space-y-3.5 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[13px] font-semibold text-[var(--text-primary)]">
            Target query for analysis
          </span>
          <div className="flex flex-wrap gap-1.5">
            {OPTIMIZER_PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => {
                  setActiveSql(p.sql);
                  setSelectedCandidateSql("");
                  void runOptimize(p.sql, false, "");
                }}
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:border-[var(--accent-primary)]/50 hover:text-[var(--accent-primary)] transition-colors"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <MonacoSqlEditor
          label="Query To Analyze"
          value={activeSql}
          onChange={setActiveSql}
          dialect={activeDialect}
          height="195px"
          schemaTables={context?.tables || []}
        />

        <div className="flex flex-wrap items-center justify-between gap-3 pt-0.5">
          <label className="flex cursor-pointer items-center gap-2 rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] px-3 py-1.5 text-xs text-[var(--status-warning-text)]">
            <input
              type="checkbox"
              checked={allowExplainAnalyze}
              onChange={(e) => setAllowExplainAnalyze(e.target.checked)}
              className="h-3.5 w-3.5 accent-[#26745B]"
            />
            <span>
              <strong>Opt-in timing:</strong> run{" "}
              <code className="font-mono font-semibold">EXPLAIN ANALYZE</code> benchmark (never
              executes unless checked)
            </span>
          </label>

          <button
            type="button"
            disabled={analyzing || !activeSql.trim()}
            onClick={() => void runOptimize()}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-4 py-2 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
          >
            <Gauge className="h-3.5 w-3.5" />
            {analyzing ? "Analyzing..." : "Run Optimization Analysis"}
          </button>
        </div>
      </section>

      {report && !report.success && (
        <div className="rounded-lg border border-[var(--status-error-border)] bg-[var(--status-error-bg)] p-4 text-xs text-[var(--status-error-text)]">
          {report.error_message || "Could not parse SQL statement for optimization analysis."}
        </div>
      )}

      {report?.success && (
        <div className="space-y-5">
          {/* TIER 1 */}
          <section className="qt-surface divide-y divide-[var(--border-subtle)] text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3.5">
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <Layers className="h-4 w-4 text-[var(--accent-primary)]" />
                <span>Tier 1: Static SQL optimization suggestions</span>
              </div>
              <span className="text-[11.5px] text-[var(--text-muted)]">
                Static AST analysis · Zero DB execution
              </span>
            </div>

            <div className="p-5 space-y-2.5">
              <div className="text-xs font-semibold text-[var(--text-primary)]">
                Detected anti-patterns ({report.static_suggestions?.antipatterns.length || 0})
              </div>
              {(report.static_suggestions?.antipatterns.length || 0) === 0 ? (
                <div className="rounded-md border border-[var(--status-success-border)] bg-[var(--status-success-bg)] p-3 text-[var(--status-success-text)]">
                  No structural anti-patterns flagged by static AST rules.
                </div>
              ) : (
                <div className="grid gap-3 md:grid-cols-2">
                  {report.static_suggestions?.antipatterns.map((ap, i) => (
                    <div
                      key={`${ap.rule_id}-${i}`}
                      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3.5 space-y-1.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-[var(--text-primary)]">
                          {ap.issue_name}
                        </span>
                        <span
                          className={`rounded border px-1.5 py-0.5 text-[10.5px] font-medium ${
                            ap.severity === "high"
                              ? "border-[var(--status-error-border)] bg-[var(--status-error-bg)] text-[var(--status-error-text)]"
                              : ap.severity === "medium"
                              ? "border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-[var(--status-warning-text)]"
                              : "border-[var(--border-subtle)] bg-white text-[var(--text-secondary)]"
                          }`}
                        >
                          {ap.severity}
                        </span>
                      </div>
                      <p className="text-[var(--text-secondary)] leading-snug">{ap.explanation}</p>
                      <p className="font-medium text-[var(--accent-primary)]">
                        Recommendation: {ap.suggested_improvement}
                      </p>
                      <p className="text-[11px] text-[var(--text-muted)]">
                        When acceptable: {ap.when_acceptable}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="p-5 space-y-2.5">
              <div className="text-xs font-semibold text-[var(--text-primary)]">
                Index recommendations ({report.static_suggestions?.index_recommendations.length || 0})
              </div>
              {(report.static_suggestions?.index_recommendations.length || 0) === 0 ? (
                <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3 text-[var(--text-muted)]">
                  No missing index opportunities detected for current predicates/joins.
                </div>
              ) : (
                <div className="space-y-3">
                  {report.static_suggestions?.index_recommendations.map((rec) => (
                    <div
                      key={rec.rec_id}
                      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3.5 space-y-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono font-semibold text-[var(--text-primary)]">
                          {rec.table_name} ({rec.columns.join(", ")}) · {rec.index_type}
                        </span>
                        <span className="rounded border border-[var(--border-subtle)] bg-white px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
                          {rec.existing_index_status}
                        </span>
                      </div>
                      <pre className="overflow-x-auto rounded-md bg-[#171B1A] p-3 font-mono text-xs text-[#7CC4AA]">
                        {rec.suggested_sql}
                      </pre>
                      <p className="text-[var(--text-secondary)]">{rec.why_it_helps}</p>
                      <div className="flex flex-wrap gap-4 text-[11px] text-[var(--text-muted)]">
                        <span>Trade-off: {rec.write_and_storage_overhead}</span>
                        <span>Dialect note: {rec.dialect_note}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {(report.static_suggestions?.rewrite_alternatives.length || 0) > 0 && (
              <div className="p-5 space-y-2.5">
                <div className="text-xs font-semibold text-[var(--text-primary)]">
                  Rewrite alternatives
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {report.static_suggestions?.rewrite_alternatives.map((rw, idx) => (
                    <div
                      key={idx}
                      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3.5 space-y-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold text-[var(--text-primary)]">{rw.title}</span>
                        <div className="flex gap-1.5">
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedCandidateSql(rw.rewritten_sql);
                              if (allowExplainAnalyze) {
                                void runOptimize(activeSql, true, rw.rewritten_sql);
                              }
                            }}
                            className="rounded border border-[var(--border-strong)] bg-white px-2.5 py-1 text-[11px] font-medium text-[var(--text-primary)] hover:border-[var(--accent-primary)]"
                          >
                            Select A/B
                          </button>
                          <button
                            type="button"
                            onClick={() => setActiveSql(rw.rewritten_sql)}
                            className="rounded bg-[var(--accent-primary)] px-2.5 py-1 text-[11px] font-medium text-white hover:bg-[var(--accent-hover)]"
                          >
                            Load Rewrite
                          </button>
                        </div>
                      </div>
                      <p className="text-[var(--text-secondary)]">{rw.rationale}</p>
                      <pre className="overflow-x-auto rounded-md bg-[#171B1A] p-3 font-mono text-[11.5px] text-[#ECEFEB]">
                        {rw.rewritten_sql}
                      </pre>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* TIER 2 */}
          <section className="qt-surface p-5 space-y-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2.5">
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <DatabaseZap className="h-4 w-4 text-[var(--accent-primary)]" />
                <span>Tier 2: Estimated execution plan (EXPLAIN)</span>
              </div>
              <span className="rounded border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
                Planner estimate only · Query not executed
              </span>
            </div>

            {report.estimated_plan?.success ? (
              <>
                {report.estimated_plan.notes && report.estimated_plan.notes.length > 0 && (
                  <div className="text-xs text-[var(--text-muted)]">
                    {report.estimated_plan.notes.join(" · ")}
                  </div>
                )}
                <pre className="max-h-72 overflow-auto rounded-md bg-[#171B1A] p-3.5 font-mono text-xs text-[#ECEFEB]">
                  {report.estimated_plan.text_tree}
                </pre>
              </>
            ) : (
              <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3 text-[var(--status-warning-text)]">
                Estimated plan unavailable:{" "}
                {report.estimated_plan?.error_message || "Target dialect/connection unsupported."}
              </div>
            )}
          </section>

          {/* TIER 3 */}
          <section className="qt-surface p-5 space-y-3.5 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2.5">
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <Activity className="h-4 w-4 text-[var(--accent-primary)]" />
                <span>Tier 3: Measured execution performance (EXPLAIN ANALYZE)</span>
              </div>
              <span
                className={`rounded border px-2 py-0.5 text-[11px] font-medium ${
                  report.measured_performance?.executed
                    ? "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]"
                    : "border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]"
                }`}
              >
                {report.measured_performance?.executed ? "Measured on engine" : "Not executed"}
              </span>
            </div>

            {!report.measured_performance?.executed ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3.5 text-[var(--status-warning-text)]">
                <div className="flex items-center gap-2.5">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  <span>{report.measured_performance?.notice}</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setAllowExplainAnalyze(true);
                    void runOptimize(activeSql, true, selectedCandidateSql);
                  }}
                  className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-3.5 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)]"
                >
                  <Sparkles className="h-3.5 w-3.5" /> Consent &amp; Measure Now
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-4 space-y-1">
                    <div className="text-xs font-medium text-[var(--text-secondary)]">
                      Original query timing
                    </div>
                    <div className="flex items-baseline gap-4 font-mono">
                      <span className="text-lg font-semibold text-[var(--text-primary)]">
                        {report.measured_performance.original?.duration_ms} ms
                      </span>
                      <span className="text-xs text-[var(--text-secondary)]">
                        {report.measured_performance.original?.rows_returned} rows
                      </span>
                    </div>
                  </div>

                  {report.measured_performance.candidate && (
                    <div className="rounded-md border border-[var(--status-success-border)] bg-[var(--accent-tint)] p-4 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-[var(--accent-primary)]">
                          Rewrite candidate timing
                        </span>
                        <span className="inline-flex items-center gap-1 rounded border border-[var(--status-success-border)] bg-white px-2 py-0.5 font-mono text-[11px] text-[var(--status-success-text)]">
                          <CheckCircle2 className="h-3 w-3" />
                          Row match:{" "}
                          {report.measured_performance.candidate.row_count_matches ? "YES" : "NO"}
                        </span>
                      </div>
                      <div className="flex items-baseline gap-4 font-mono">
                        <span className="text-lg font-semibold text-[var(--accent-primary)]">
                          {report.measured_performance.candidate.duration_ms} ms
                        </span>
                        <span className="text-xs text-[var(--text-secondary)]">
                          Delta: {report.measured_performance.candidate.duration_delta_ms} ms
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                <div className="space-y-1.5">
                  <label
                    htmlFor="ab-candidate-sql"
                    className="block text-xs font-medium text-[var(--text-secondary)]"
                  >
                    Candidate rewrite SQL for A/B timing (optional)
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <textarea
                      id="ab-candidate-sql"
                      rows={3}
                      value={selectedCandidateSql}
                      onChange={(e) => setSelectedCandidateSql(e.target.value)}
                      placeholder="Select or edit candidate rewrite query..."
                      className="flex-1 min-w-[260px] rounded-md border border-[var(--border-strong)] bg-white p-2.5 font-mono text-xs text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
                    />
                    <button
                      type="button"
                      disabled={analyzing}
                      onClick={() => void runOptimize(activeSql, true, selectedCandidateSql)}
                      className="self-end rounded-md bg-[var(--accent-primary)] px-4 py-2 text-xs font-medium text-white hover:bg-[var(--accent-hover)]"
                    >
                      Re-Run Timed A/B Benchmark
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
