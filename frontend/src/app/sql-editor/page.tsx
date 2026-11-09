"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRightLeft,
  BookOpenCheck,
  Bug,
  CheckCircle2,
  Gauge,
  PanelLeftClose,
  PanelLeftOpen,
  Play,
  ShieldAlert,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/context";
import type { ExecutionResponse, SqlDialect } from "@/lib/types";
import { DialectSelect } from "@/components/DialectSelect";
import { EditorDiagnosticMarker, MonacoSqlEditor } from "@/components/MonacoSqlEditor";
import { ResultsExplorer } from "@/components/ResultsExplorer";
import { SchemaExplorerTree } from "@/components/SchemaExplorerTree";
import { WriteConfirmDialog } from "@/components/WriteConfirmDialog";

export default function SqlEditorPage() {
  const router = useRouter();
  const { context, setContext, setDialect, activeSql, setActiveSql, setLastError, setVisualizeSql } =
    useWorkspace();

  const [schemaOpen, setSchemaOpen] = useState(true);
  const [running, setRunning] = useState(false);
  const [execResult, setExecResult] = useState<ExecutionResponse | null>(null);
  const [diagnostics, setDiagnostics] = useState<EditorDiagnosticMarker[]>([]);
  const [maxRows, setMaxRows] = useState(500);
  const [timeoutMs, setTimeoutMs] = useState(5000);

  const [bottomTab, setBottomTab] = useState<"results" | "explain" | "convert">("results");
  const [explainData, setExplainData] = useState<{
    valid: boolean;
    summary: string;
    steps: { clause: string; detail: string }[];
    schema_verified: boolean;
    unknown_tables: string[];
    unknown_columns: string[];
  } | null>(null);

  const [targetDialect, setTargetDialect] = useState<SqlDialect>("mysql");
  const [convertedPayload, setConvertedPayload] = useState<{
    converted_sql: string;
    success: boolean;
    warnings: string[];
    limitations: string[];
    error_message: string;
  } | null>(null);

  const [pendingChallenge, setPendingChallenge] = useState<
    ExecutionResponse["confirmation_challenge"]
  >(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  const activeDialect = context?.dialect || "postgresql";

  const handleRun = async (confirmedToken?: string) => {
    if (!activeSql.trim()) return;
    setRunning(true);
    setBottomTab("results");
    setDiagnostics([]);
    try {
      const res = await api.executeSql({
        sql: activeSql,
        dialect: activeDialect,
        max_rows: maxRows,
        timeout_ms: timeoutMs,
        allow_write_opt_in: context?.allow_write_opt_in ?? false,
        confirmed_write: Boolean(confirmedToken),
        confirmation_token: confirmedToken ?? null,
      });

      if (res.requires_write_confirmation && res.confirmation_challenge && !confirmedToken) {
        setPendingChallenge(res.confirmation_challenge);
      }

      setExecResult(res);
      if (!res.success && res.error_message) {
        setLastError(res.error_message);
        setDiagnostics([
          {
            line: res.error_line || 1,
            column: res.error_column || 1,
            severity: "error",
            message: res.error_message,
          },
        ]);
      } else {
        setLastError(null);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Query execution error";
      setLastError(msg);
      setDiagnostics([{ line: 1, column: 1, severity: "error", message: msg }]);
    } finally {
      setRunning(false);
    }
  };

  const handleValidate = async () => {
    const res = await api.validateSql(activeSql, activeDialect);
    if (res.is_valid) {
      setDiagnostics([
        {
          line: 1,
          column: 1,
          severity: "info",
          message: `AST valid (${res.statement_types.join(", ")}) for ${res.dialect}.`,
        },
      ]);
    } else {
      setDiagnostics([
        {
          line: res.error_line || 1,
          column: res.error_column || 1,
          severity: "error",
          message: res.error_message,
        },
      ]);
    }
  };

  const handleFormat = async () => {
    const res = await api.formatSql(activeSql, activeDialect);
    setActiveSql(res.formatted_sql);
  };

  const handleExplain = async () => {
    const res = await api.explainSqlText(activeSql, activeDialect);
    setExplainData(res);
    setBottomTab("explain");
  };

  const handleConvert = async () => {
    const res = await api.convertSql(activeSql, activeDialect, targetDialect);
    setConvertedPayload(res);
    setBottomTab("convert");
  };

  const toggleWriteMode = async () => {
    if (!context) return;
    const updated = await api.setWriteMode(!context.allow_write_opt_in);
    setContext(updated);
  };

  return (
    <div className="space-y-4">
      {/* Unified IDE Action Bar */}
      <div className="qt-surface flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setSchemaOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2.5 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
          >
            {schemaOpen ? (
              <>
                <PanelLeftClose className="h-3.5 w-3.5 text-[var(--accent-primary)]" /> Hide schema
              </>
            ) : (
              <>
                <PanelLeftOpen className="h-3.5 w-3.5 text-[var(--accent-primary)]" /> Show schema
              </>
            )}
          </button>

          <button
            type="button"
            disabled={running || !activeSql.trim()}
            onClick={() => void handleRun()}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-3.5 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
          >
            <Play className="h-3.5 w-3.5" />
            {running ? "Running..." : "Run Query (Ctrl+Enter)"}
          </button>

          <button
            type="button"
            onClick={() => void handleValidate()}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Validate
          </button>

          <button
            type="button"
            onClick={() => void handleExplain()}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <BookOpenCheck className="h-3.5 w-3.5" />
            Explain
          </button>

          <span className="mx-1 hidden h-4 w-px bg-[var(--border-subtle)] sm:inline-block" />

          <button
            type="button"
            onClick={() => router.push("/debugging")}
            className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <Bug className="h-3.5 w-3.5" />
            Debug
          </button>

          <button
            type="button"
            onClick={() => router.push("/optimizer")}
            className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <Gauge className="h-3.5 w-3.5" />
            Optimize
          </button>

          <button
            type="button"
            onClick={() => {
              setVisualizeSql(activeSql);
              router.push("/academy");
            }}
            className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <Workflow className="h-3.5 w-3.5" />
            Visualize
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]">
            <span>Rows</span>
            <select
              value={maxRows}
              onChange={(e) => setMaxRows(Number(e.target.value))}
              className="rounded-md border border-[var(--border-strong)] bg-white px-2 py-1 font-mono text-xs text-[var(--text-primary)]"
            >
              {[100, 500, 2000].map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>

          <label className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]">
            <span>Timeout</span>
            <select
              value={timeoutMs}
              onChange={(e) => setTimeoutMs(Number(e.target.value))}
              className="rounded-md border border-[var(--border-strong)] bg-white px-2 py-1 font-mono text-xs text-[var(--text-primary)]"
            >
              <option value={2000}>2s</option>
              <option value={5000}>5s</option>
              <option value={15000}>15s</option>
            </select>
          </label>

          <button
            type="button"
            onClick={() => void toggleWriteMode()}
            className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium ${
              context?.allow_write_opt_in
                ? "border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-[var(--status-warning-text)]"
                : "border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]"
            }`}
            title="Toggle opt-in write mode (every write still requires explicit HMAC confirmation)"
          >
            {context?.allow_write_opt_in ? (
              <>
                <ShieldAlert className="h-3.5 w-3.5" /> Write: Opt-In
              </>
            ) : (
              <>
                <ShieldCheck className="h-3.5 w-3.5 text-[var(--accent-primary)]" /> Read-Only Safe
              </>
            )}
          </button>
        </div>
      </div>

      {/* Main Split IDE */}
      <div className="grid gap-4 lg:grid-cols-12 items-start">
        {schemaOpen && (
          <div className="qt-surface lg:col-span-3 max-h-[760px] overflow-hidden">
            <SchemaExplorerTree
              context={context}
              onInsertIdentifier={(ident) =>
                setActiveSql(activeSql ? `${activeSql} ${ident}` : ident)
              }
            />
          </div>
        )}

        <div className={`${schemaOpen ? "lg:col-span-9" : "lg:col-span-12"} space-y-4`}>
          <MonacoSqlEditor
            label="Workspace SQL"
            value={activeSql}
            onChange={setActiveSql}
            dialect={activeDialect}
            height="340px"
            schemaTables={context?.tables || []}
            diagnostics={diagnostics}
            onExecuteShortcut={() => void handleRun()}
            onFormat={() => void handleFormat()}
          />

          {/* AST Dialect Transpiler Strip */}
          <div className="qt-surface flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-[var(--text-secondary)]">Convert dialect</span>
              <DialectSelect value={activeDialect} compact onChange={(d) => void setDialect(d)} />
              <ArrowRightLeft className="h-3.5 w-3.5 text-[var(--text-muted)]" />
              <DialectSelect value={targetDialect} compact onChange={setTargetDialect} />
              <button
                type="button"
                onClick={() => void handleConvert()}
                className="rounded-md border border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] px-3 py-1 text-xs font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-soft)]"
              >
                Convert Syntax
              </button>
            </div>
            <span className="text-[11.5px] text-[var(--text-muted)]">
              SQLGlot AST compiler across dialects
            </span>
          </div>

          {/* Output Tabs */}
          <div className="space-y-3">
            <div className="flex items-center border-b border-[var(--border-subtle)] text-xs">
              {[
                { key: "results" as const, label: "Execution results" },
                { key: "explain" as const, label: "Clause explanation" },
                { key: "convert" as const, label: "Dialect conversion" },
              ].map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setBottomTab(t.key)}
                  className={`border-b-2 px-4 py-2 text-[13px] font-medium transition-colors ${
                    bottomTab === t.key
                      ? "border-[var(--accent-primary)] text-[var(--text-primary)]"
                      : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {bottomTab === "results" && (
              <ResultsExplorer
                result={execResult}
                loading={running}
                onSendToDebug={() => router.push("/debugging")}
              />
            )}

            {bottomTab === "explain" && (
              <div className="qt-surface p-4 text-xs space-y-3">
                {!explainData ? (
                  <div className="text-[var(--text-muted)]">
                    Click <strong className="text-[var(--text-primary)]">Explain</strong> above to
                    inspect AST clauses and verified schema identifiers.
                  </div>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[13px] font-semibold text-[var(--text-primary)]">
                        Parsed query summary
                      </span>
                      <span
                        className={`rounded-md border px-2 py-0.5 text-[11px] font-medium ${
                          explainData.schema_verified
                            ? "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]"
                            : "border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-[var(--status-warning-text)]"
                        }`}
                      >
                        {explainData.schema_verified
                          ? "All schema entities verified"
                          : "Unverified identifiers flagged"}
                      </span>
                    </div>
                    <p className="text-[13px] text-[var(--text-secondary)]">{explainData.summary}</p>
                    {(explainData.unknown_tables.length > 0 ||
                      explainData.unknown_columns.length > 0) && (
                      <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3 font-mono text-xs text-[var(--status-warning-text)]">
                        Unknown tables: {explainData.unknown_tables.join(", ") || "none"} · Unknown
                        columns: {explainData.unknown_columns.join(", ") || "none"}
                      </div>
                    )}
                    <div className="divide-y divide-[var(--border-subtle)] rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)]/50">
                      {explainData.steps.map((s, i) => (
                        <div key={i} className="flex gap-3 px-3.5 py-2">
                          <span className="w-24 shrink-0 font-mono font-medium text-[var(--accent-primary)]">
                            {s.clause}
                          </span>
                          <span className="text-[var(--text-secondary)]">{s.detail}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

            {bottomTab === "convert" && (
              <div className="qt-surface p-4 text-xs space-y-3">
                {!convertedPayload ? (
                  <div className="text-[var(--text-muted)]">
                    Select a target dialect and click{" "}
                    <strong className="text-[var(--text-primary)]">Convert Syntax</strong> to view
                    AST transpilation output.
                  </div>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-[13px] font-semibold text-[var(--text-primary)]">
                        Converted output ({targetDialect})
                      </div>
                      {convertedPayload.success && (
                        <button
                          type="button"
                          onClick={async () => {
                            await setDialect(targetDialect);
                            setActiveSql(convertedPayload.converted_sql);
                          }}
                          className="rounded-md bg-[var(--accent-primary)] px-3 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)]"
                        >
                          Apply &amp; Switch Dialect
                        </button>
                      )}
                    </div>
                    {convertedPayload.error_message && (
                      <div className="rounded-md border border-[var(--status-error-border)] bg-[var(--status-error-bg)] p-3 font-mono text-xs text-[var(--status-error-text)]">
                        {convertedPayload.error_message}
                      </div>
                    )}
                    {convertedPayload.warnings.length > 0 && (
                      <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3 text-xs text-[var(--status-warning-text)]">
                        <strong>Notices:</strong> {convertedPayload.warnings.join(" · ")}
                      </div>
                    )}
                    {convertedPayload.limitations.length > 0 && (
                      <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3 text-xs text-[var(--status-warning-text)]">
                        <strong>Manual review required:</strong>{" "}
                        {convertedPayload.limitations.join(" · ")}
                      </div>
                    )}
                    <pre className="overflow-x-auto rounded-md bg-[#171B1A] p-3.5 font-mono text-xs text-[#ECEFEB]">
                      {convertedPayload.converted_sql}
                    </pre>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <WriteConfirmDialog
        challenge={pendingChallenge}
        sqlPreview={activeSql}
        busy={confirmBusy}
        onCancel={() => setPendingChallenge(null)}
        onConfirm={async (token) => {
          setConfirmBusy(true);
          try {
            await handleRun(token);
            setPendingChallenge(null);
          } finally {
            setConfirmBusy(false);
          }
        }}
      />
    </div>
  );
}
