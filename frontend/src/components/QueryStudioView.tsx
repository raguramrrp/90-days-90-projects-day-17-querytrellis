"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  BookOpenCheck,
  Bug,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Code2,
  Copy,
  Download,
  Gauge,
  HelpCircle,
  Play,
  Sparkles,
  TableProperties,
  Workflow,
} from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/context";
import type { ExecutionResponse, NLGenerateResponse } from "@/lib/types";
import { DialectSelect } from "./DialectSelect";
import { MonacoSqlEditor } from "./MonacoSqlEditor";
import { ResultsExplorer } from "./ResultsExplorer";

const SAMPLE_NL_PROMPTS = [
  "Show the top 10 performing employees.",
  "Calculate monthly revenue for each region.",
  "Find customers who purchased more than three times.",
  "Compare this month's sales with the previous month.",
  "Identify products with declining sales.",
  "Find employees whose performance is above the department average.",
  "Calculate a running total of monthly revenue.",
  "Find duplicate customer records.",
];

export function QueryStudioView() {
  const router = useRouter();
  const { context, setDialect, setActiveSql, setVisualizeSql } = useWorkspace();

  const [prompt, setPrompt] = useState("Calculate monthly revenue for each region.");
  const [generating, setGenerating] = useState(false);
  const [nlResult, setNlResult] = useState<NLGenerateResponse | null>(null);
  const [selectedClarification, setSelectedClarification] = useState<string>("");
  const [customClarification, setCustomClarification] = useState<string>("");
  const [editedSql, setEditedSql] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [expandedSchemaTable, setExpandedSchemaTable] = useState<string | null>(null);

  const [sampleExecLoading, setSampleExecLoading] = useState(false);
  const [sampleExecResult, setSampleExecResult] = useState<ExecutionResponse | null>(null);

  const [deepExplainOpen, setDeepExplainOpen] = useState(false);
  const [deepExplainData, setDeepExplainData] = useState<{
    summary: string;
    steps: { clause: string; detail: string }[];
  } | null>(null);

  const activeDialect = context?.dialect || "postgresql";
  const tables = context?.tables || [];

  const runGenerate = async (
    clarificationAnswer?: string | null,
    forceProvider?: string | null
  ) => {
    if (!prompt.trim()) return;
    setGenerating(true);
    setSampleExecResult(null);
    setDeepExplainOpen(false);
    try {
      const res = await api.generateNl2Sql({
        request: prompt.trim(),
        dialect: activeDialect,
        clarification_answer: clarificationAnswer ?? null,
        force_provider: forceProvider ?? null,
      });
      setNlResult(res);
      if (res.status === "generated" && res.sql) {
        setEditedSql(res.sql);
        setActiveSql(res.sql);
      }
      if (res.status === "clarification_required" && res.interpretations?.length) {
        setSelectedClarification(res.interpretations[0].label);
      }
    } catch (err) {
      setNlResult({
        status: "provider_error",
        dialect: activeDialect,
        error_message: err instanceof Error ? err.message : "Failed to synthesize SQL.",
        offer_external_fallback: true,
      });
    } finally {
      setGenerating(false);
    }
  };

  const handleCopySql = async () => {
    if (!editedSql) return;
    await navigator.clipboard.writeText(editedSql);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleShowSampleOutput = async () => {
    if (!editedSql.trim()) return;
    setSampleExecLoading(true);
    try {
      const execRes = await api.executeSql({
        sql: editedSql,
        dialect: activeDialect,
        max_rows: 25,
      });
      setSampleExecResult(execRes);
    } finally {
      setSampleExecLoading(false);
    }
  };

  const handleDeepExplain = async () => {
    if (!editedSql.trim()) return;
    const res = await api.explainSqlText(editedSql, activeDialect);
    setDeepExplainData({ summary: res.summary, steps: res.steps });
    setDeepExplainOpen(true);
  };

  const handleExportBundle = () => {
    if (!editedSql) return;
    const content = [
      `-- QueryTrellis Export`,
      `-- Request: ${prompt}`,
      `-- Dialect: ${activeDialect}`,
      `-- Database Context: ${context?.label || "active"}`,
      ``,
      editedSql,
      ``,
      `/* Explanation`,
      `${nlResult?.explanation || ""}`,
      ...(nlResult?.assumptions?.length
        ? [`\nAssumptions:\n- ${nlResult.assumptions.join("\n- ")}`]
        : []),
      ...(nlResult?.limitations?.length
        ? [`\nLimitations:\n- ${nlResult.limitations.join("\n- ")}`]
        : []),
      `*/`,
    ].join("\n");
    const blob = new Blob([content], { type: "text/sql;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `querytrellis-${activeDialect}-${Date.now()}.sql`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const inspectedTable = tables.find((t) => t.name === expandedSchemaTable) || null;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Natural Language to Schema-Verified SQL
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
            Translate plain-English analytical requests against inspected catalog tables without
            invented identifiers.
          </p>
        </div>
        <DialectSelect
          label="Target dialect"
          value={activeDialect}
          onChange={(d) => void setDialect(d)}
        />
      </div>

      {/* Main Split Workspace */}
      <div className="grid gap-6 lg:grid-cols-12 items-start">
        {/* Left: Intent Composer, Schema Reference & Prompts */}
        <section className="qt-surface lg:col-span-5 divide-y divide-[var(--border-subtle)] overflow-hidden">
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <label
                htmlFor="nl-prompt-input"
                className="text-[13px] font-semibold text-[var(--text-primary)]"
              >
                Describe what you want to query
              </label>
              <span className="font-mono text-[11px] text-[var(--text-muted)]">
                {tables.length} tables active
              </span>
            </div>

            <textarea
              id="nl-prompt-input"
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Show the top 10 performing employees, or calculate monthly revenue for each region..."
              className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2.5 text-[13px] leading-relaxed text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:outline-none"
            />

            <div className="flex items-center justify-between gap-2 pt-0.5">
              <span className="text-[11.5px] text-[var(--text-muted)]">
                Scoped to{" "}
                <strong className="font-medium text-[var(--text-secondary)]">
                  {context?.label || "active database"}
                </strong>
              </span>
              <button
                type="button"
                disabled={generating || !prompt.trim()}
                onClick={() => void runGenerate(null, null)}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-4 py-2 text-[12.5px] font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45 transition-colors"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {generating ? "Generating..." : "Generate SQL"}
              </button>
            </div>
          </div>

          {/* Interactive Schema Reference */}
          <div className="bg-[var(--bg-subtle)]/55 px-4 py-3 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-[var(--text-secondary)]">
                Available catalog tables
              </span>
              <span className="text-[11px] text-[var(--text-muted)]">Click to inspect columns</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {tables.map((t) => {
                const open = expandedSchemaTable === t.name;
                return (
                  <button
                    key={t.name}
                    type="button"
                    onClick={() => setExpandedSchemaTable(open ? null : t.name)}
                    className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[11px] transition-colors ${
                      open
                        ? "border-[var(--accent-primary)]/45 bg-[var(--accent-tint)] font-medium text-[var(--accent-primary)]"
                        : "border-[var(--border-subtle)] bg-white text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    {open ? (
                      <ChevronDown className="h-3 w-3" />
                    ) : (
                      <ChevronRight className="h-3 w-3 text-[var(--text-muted)]" />
                    )}
                    <span>{t.name}</span>
                  </button>
                );
              })}
            </div>

            {inspectedTable && (
              <div className="mt-2 rounded-md border border-[var(--border-subtle)] bg-white p-2.5 text-xs">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="font-mono font-medium text-[var(--text-primary)]">
                    {inspectedTable.name}
                  </span>
                  <span className="font-mono text-[11px] text-[var(--text-muted)]">
                    {inspectedTable.columns.length} columns
                    {inspectedTable.row_count !== null
                      ? ` · ${inspectedTable.row_count} rows`
                      : ""}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {inspectedTable.columns.map((c) => (
                    <span
                      key={c.name}
                      className="rounded border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-primary)]"
                    >
                      {c.name}{" "}
                      <span className="text-[10px] text-[var(--text-muted)]">{c.data_type}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Reference Prompts */}
          <div className="py-2">
            <div className="px-4 py-1.5 text-[11.5px] font-medium text-[var(--text-secondary)]">
              Example analytical questions
            </div>
            <div className="divide-y divide-[var(--border-subtle)]/60">
              {SAMPLE_NL_PROMPTS.map((example, idx) => {
                const selected = prompt === example;
                return (
                  <button
                    key={example}
                    type="button"
                    onClick={() => setPrompt(example)}
                    className={`flex w-full items-center gap-3 px-4 py-2 text-left text-[12.5px] transition-colors ${
                      selected
                        ? "bg-[var(--accent-tint)] font-medium text-[var(--text-primary)]"
                        : "text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="w-5 shrink-0 font-mono text-[11px] text-[var(--text-muted)]">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <span className="truncate">{example}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        {/* Right: Synthesis Output / Clarification / Error / Empty */}
        <section className="lg:col-span-7 space-y-4">
          {!nlResult && (
            <div className="qt-surface flex min-h-[380px] flex-col items-center justify-center p-10 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-[var(--accent-primary)]">
                <Sparkles className="h-5 w-5" />
              </div>
              <h2 className="mt-3.5 text-sm font-semibold text-[var(--text-primary)]">
                Ready to synthesize a schema-verified query
              </h2>
              <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-[var(--text-secondary)]">
                Enter an analytical prompt on the left or pick an example question, then click{" "}
                <strong className="font-medium text-[var(--text-primary)]">Generate SQL</strong>.
                Ambiguous metrics pause for clarification, and missing catalog objects are blocked
                automatically.
              </p>
            </div>
          )}

          {/* Clarification Required */}
          {nlResult?.status === "clarification_required" && (
            <div className="qt-surface overflow-hidden text-xs">
              <div className="flex items-start gap-2.5 border-b border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] px-5 py-3.5">
                <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--status-warning-text)]" />
                <div>
                  <h2 className="text-[13px] font-semibold text-[var(--status-warning-text)]">
                    Clarification needed before generating final SQL
                  </h2>
                  <p className="mt-1 text-[13px] text-[var(--text-primary)]">
                    {nlResult.question}
                  </p>
                </div>
              </div>

              <div className="p-5 space-y-4">
                <div className="grid gap-2.5 sm:grid-cols-2">
                  {(nlResult.interpretations || []).map((interp) => {
                    const active =
                      selectedClarification === interp.label && !customClarification.trim();
                    return (
                      <button
                        key={interp.id}
                        type="button"
                        onClick={() => {
                          setSelectedClarification(interp.label);
                          setCustomClarification("");
                        }}
                        className={`rounded-md border p-3.5 text-left transition-colors ${
                          active
                            ? "border-[var(--accent-primary)] bg-[var(--accent-tint)]"
                            : "border-[var(--border-subtle)] bg-white hover:border-[var(--border-strong)]"
                        }`}
                      >
                        <div className="text-[13px] font-medium text-[var(--text-primary)]">
                          {interp.label}
                        </div>
                        <div className="mt-1 text-xs leading-snug text-[var(--text-secondary)]">
                          {interp.detail}
                        </div>
                      </button>
                    );
                  })}
                </div>

                <div className="flex flex-wrap items-center gap-2.5 pt-1">
                  <input
                    type="text"
                    value={customClarification}
                    onChange={(e) => setCustomClarification(e.target.value)}
                    placeholder="Or enter a custom metric or timeframe definition..."
                    className="min-w-[240px] flex-1 rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:outline-none"
                  />
                  <button
                    type="button"
                    disabled={generating || (!selectedClarification && !customClarification.trim())}
                    onClick={() =>
                      void runGenerate(customClarification.trim() || selectedClarification, null)
                    }
                    className="rounded-md bg-[var(--accent-primary)] px-4 py-2 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
                  >
                    Generate With Selection
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Missing Schema Guard */}
          {nlResult?.status === "missing_schema" && (
            <div className="rounded-lg border border-[var(--status-error-border)] bg-[var(--status-error-bg)] p-4 text-[13px] space-y-2">
              <div className="flex items-center gap-2 font-semibold text-[var(--status-error-text)]">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Requested entity not found in active schema</span>
              </div>
              <p className="text-xs leading-relaxed text-[var(--text-primary)]">
                QueryTrellis refused to fabricate SQL identifiers because these entities are absent
                from <strong>{context?.label}</strong>:{" "}
                <span className="font-mono font-medium text-[var(--status-error-text)]">
                  {(nlResult.missing_entities || []).join(", ")}
                </span>
              </p>
              {nlResult.notes && nlResult.notes.length > 0 && (
                <ul className="list-disc pl-4 space-y-0.5 text-xs text-[var(--text-secondary)]">
                  {nlResult.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Provider Error Fallback */}
          {nlResult?.status === "provider_error" && (
            <div className="rounded-lg border border-[var(--status-error-border)] bg-[var(--status-error-bg)] p-4 text-xs space-y-3">
              <div className="text-[13px] font-semibold text-[var(--status-error-text)]">
                External synthesis provider request failed
              </div>
              <p className="font-mono text-xs text-[var(--text-primary)]">
                {nlResult.error_message}
              </p>
              {nlResult.offer_external_fallback && (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void runGenerate(null, "deterministic")}
                    className="rounded-md bg-[var(--accent-primary)] px-3.5 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)]"
                  >
                    Run Built-In Schema AST Engine
                  </button>
                  <button
                    type="button"
                    onClick={() => router.push("/ai-settings")}
                    className="rounded-md border border-[var(--border-strong)] bg-white px-3.5 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
                  >
                    Open Engine API Settings
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Generated SQL Result Surface */}
          {nlResult?.status === "generated" && (
            <div className="qt-surface p-4 space-y-3.5">
              {nlResult.provider_warning && (
                <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] px-3 py-2 text-xs text-[var(--status-warning-text)]">
                  {nlResult.provider_warning}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--status-success-border)] bg-[var(--status-success-bg)] px-2.5 py-0.5 font-medium text-[var(--status-success-text)]">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {nlResult.schema_verified ? "Schema verified" : "Generated SQL"}
                  </span>
                  <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 font-mono text-[11px] text-[var(--text-primary)]">
                    {nlResult.dialect}
                  </span>
                  {nlResult.provider_used && (
                    <span className="text-[11.5px] text-[var(--text-muted)]">
                      {nlResult.model_used || nlResult.provider_used}
                    </span>
                  )}
                </div>

                {nlResult.tables_used && nlResult.tables_used.length > 0 && (
                  <div className="font-mono text-[11px] text-[var(--text-secondary)]">
                    Tables:{" "}
                    <span className="text-[var(--text-primary)]">
                      {nlResult.tables_used.join(", ")}
                    </span>
                  </div>
                )}
              </div>

              <MonacoSqlEditor
                label="Generated SQL"
                value={editedSql}
                onChange={(v) => {
                  setEditedSql(v);
                  setActiveSql(v);
                }}
                dialect={activeDialect}
                height="255px"
                schemaTables={tables}
              />

              {/* Action Toolbar */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={sampleExecLoading}
                    onClick={() => void handleShowSampleOutput()}
                    className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-3.5 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
                  >
                    <Play className="h-3.5 w-3.5" />
                    {sampleExecLoading ? "Executing..." : "Show Sample Output"}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setActiveSql(editedSql);
                      router.push("/sql-editor");
                    }}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] px-3 py-1.5 text-xs font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-soft)]"
                  >
                    <Code2 className="h-3.5 w-3.5" />
                    Open in SQL Editor
                  </button>

                  <button
                    type="button"
                    onClick={() => void handleCopySql()}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
                  >
                    {copied ? (
                      <Check className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
                    ) : (
                      <Copy className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                    )}
                    {copied ? "Copied" : "Copy SQL"}
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => void handleDeepExplain()}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                  >
                    <BookOpenCheck className="h-3.5 w-3.5" />
                    Explain Query
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setVisualizeSql(editedSql);
                      router.push("/academy");
                    }}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                  >
                    <Workflow className="h-3.5 w-3.5" />
                    Visualize Execution
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setActiveSql(editedSql);
                      router.push("/debugging");
                    }}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                  >
                    <Bug className="h-3.5 w-3.5" />
                    Debug Query
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setActiveSql(editedSql);
                      router.push("/optimizer");
                    }}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                  >
                    <Gauge className="h-3.5 w-3.5" />
                    Optimize Query
                  </button>

                  <button
                    type="button"
                    onClick={handleExportBundle}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Export SQL &amp; Explanation
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* Lower Execution Results & Logic Documentation */}
      {nlResult?.status === "generated" && (
        <div className="space-y-5">
          {(sampleExecResult || sampleExecLoading) && (
            <section className="space-y-2">
              <div className="text-[13px] font-semibold text-[var(--text-primary)]">
                Executed sample output
              </div>
              <ResultsExplorer
                result={sampleExecResult}
                loading={sampleExecLoading}
                onSendToDebug={() => {
                  setActiveSql(editedSql);
                  router.push("/debugging");
                }}
              />
            </section>
          )}

          {deepExplainOpen && deepExplainData && (
            <section className="qt-surface p-4 space-y-3 text-xs">
              <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-2.5">
                <span className="text-[13px] font-semibold text-[var(--text-primary)]">
                  Clause-by-clause AST breakdown
                </span>
                <span className="text-[11px] text-[var(--text-muted)]">SQLGlot parse inspect</span>
              </div>
              <p className="text-[13px] text-[var(--text-secondary)]">{deepExplainData.summary}</p>
              <div className="grid gap-2 md:grid-cols-2">
                {deepExplainData.steps.map((s, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3 py-2"
                  >
                    <span className="w-24 shrink-0 font-mono font-medium text-[var(--accent-primary)]">
                      {s.clause}
                    </span>
                    <span className="text-[var(--text-secondary)]">{s.detail}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <div className="grid gap-6 lg:grid-cols-12 items-start">
            <section className="qt-surface lg:col-span-7 divide-y divide-[var(--border-subtle)] text-xs">
              <div className="p-4 space-y-2">
                <h2 className="text-[13px] font-semibold text-[var(--text-primary)]">
                  Query logic explanation
                </h2>
                <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
                  {nlResult.explanation}
                </p>
              </div>

              {nlResult.clause_breakdown && nlResult.clause_breakdown.length > 0 && (
                <div className="p-4 space-y-2">
                  <div className="text-xs font-medium text-[var(--text-primary)]">
                    Clause breakdown
                  </div>
                  <div className="divide-y divide-[var(--border-subtle)] rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/50">
                    {nlResult.clause_breakdown.map((step, i) => (
                      <div key={i} className="flex gap-3 px-3 py-2 text-xs">
                        <span className="w-24 shrink-0 font-mono font-medium text-[var(--accent-primary)]">
                          {step.clause}
                        </span>
                        <span className="text-[var(--text-secondary)]">{step.detail}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {nlResult.assumptions && nlResult.assumptions.length > 0 && (
                <div className="p-4 space-y-1.5">
                  <div className="text-xs font-medium text-[var(--text-primary)]">Assumptions</div>
                  <ul className="list-disc pl-4 space-y-1 text-[var(--text-secondary)]">
                    {nlResult.assumptions.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </div>
              )}

              {nlResult.limitations && nlResult.limitations.length > 0 && (
                <div className="bg-[var(--status-warning-bg)]/60 p-4 space-y-1.5">
                  <div className="text-xs font-medium text-[var(--status-warning-text)]">
                    Dialect notices &amp; limitations
                  </div>
                  <ul className="list-disc pl-4 space-y-1 text-[var(--status-warning-text)]">
                    {nlResult.limitations.map((l, i) => (
                      <li key={i}>{l}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            <section className="lg:col-span-5 space-y-4">
              {nlResult.illustrative_structure && (
                <div className="qt-surface p-4 text-xs space-y-2.5">
                  <div className="flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2.5">
                    <div className="flex items-center gap-1.5 text-[13px] font-semibold text-[var(--text-primary)]">
                      <TableProperties className="h-4 w-4 text-[var(--accent-primary)]" />
                      <span>Expected output columns</span>
                    </div>
                    <span className="rounded border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
                      Illustrative only
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)]">
                    {nlResult.illustrative_structure.notice}
                  </p>
                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {nlResult.illustrative_structure.columns.map((col, idx) => (
                      <span
                        key={idx}
                        className="rounded border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-1 font-mono text-[11px] text-[var(--text-primary)]"
                      >
                        {col.name}{" "}
                        <span className="text-[10.5px] text-[var(--accent-primary)]">
                          ({col.type})
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {nlResult.alternatives && nlResult.alternatives.length > 0 && (
                <div className="qt-surface divide-y divide-[var(--border-subtle)] text-xs">
                  <div className="px-4 py-3 text-[13px] font-semibold text-[var(--text-primary)]">
                    Alternative SQL formulations
                  </div>
                  {nlResult.alternatives.map((alt, i) => (
                    <div key={i} className="p-4 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-[var(--text-primary)]">{alt.title}</span>
                        <button
                          type="button"
                          onClick={() => {
                            setEditedSql(alt.sql);
                            setActiveSql(alt.sql);
                          }}
                          className="rounded-md border border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] px-2.5 py-1 text-[11px] font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-soft)]"
                        >
                          Use This SQL
                        </button>
                      </div>
                      <p className="text-xs text-[var(--text-secondary)]">{alt.reason}</p>
                      <pre className="overflow-x-auto rounded-md bg-[#171B1A] p-3 font-mono text-[11.5px] text-[#ECEFEB]">
                        {alt.sql}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
