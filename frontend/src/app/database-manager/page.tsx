"use client";

import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  KeyRound,
  Plug,
  RotateCcw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/context";
import type { ImportPreviewResponse, SqlDialect } from "@/lib/types";
import { DialectSelect } from "@/components/DialectSelect";
import { SchemaExplorerTree } from "@/components/SchemaExplorerTree";

const ENGINE_DEFAULTS: Record<string, { port: number; label: string }> = {
  postgresql: { port: 5432, label: "PostgreSQL" },
  mysql: { port: 3306, label: "MySQL / MariaDB" },
  sqlserver: { port: 1433, label: "Microsoft SQL Server" },
  sqlite: { port: 0, label: "SQLite Local File" },
};

export default function DatabaseManagerPage() {
  const { context, setContext } = useWorkspace();

  const [tab, setTab] = useState<"upload" | "live" | "schema">("upload");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadDialect, setUploadDialect] = useState<SqlDialect>("postgresql");
  const [samples, setSamples] = useState<{ key: string; file_name: string; size_bytes: number }[]>(
    []
  );
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [acceptBusy, setAcceptBusy] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [engine, setEngine] = useState<"postgresql" | "mysql" | "sqlite" | "sqlserver">(
    "postgresql"
  );
  const [host, setHost] = useState("localhost");
  const [port, setPort] = useState(5432);
  const [database, setDatabase] = useState("querytrellis_sample");
  const [username, setUsername] = useState("postgres");
  const [password, setPassword] = useState("");
  const [sqlitePath, setSqlitePath] = useState("");
  const [sslMode, setSslMode] = useState("prefer");
  const [allowWriteOptIn, setAllowWriteOptIn] = useState(false);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    void api
      .listSampleFiles()
      .then((res) => setSamples(res.samples || []))
      .catch(() => {});
  }, []);

  const handlePreviewUpload = async () => {
    if (!selectedFile) return;
    setPreviewBusy(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const res = await api.previewUpload(selectedFile, uploadDialect);
      setPreview(res);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to inspect uploaded file.");
    } finally {
      setPreviewBusy(false);
    }
  };

  const handlePreviewSample = async (key: string) => {
    setPreviewBusy(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const res = await api.previewSampleFile(key);
      setPreview(res);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to inspect sample dataset.");
    } finally {
      setPreviewBusy(false);
    }
  };

  const handleAcceptPreview = async () => {
    if (!preview) return;
    setAcceptBusy(true);
    setErrorMessage(null);
    try {
      const snap = await api.acceptUpload(preview.preview_id);
      setContext(snap);
      setStatusMessage(
        `Loaded "${snap.label}" (${snap.tables.length} tables) into isolated local DuckDB sandbox.`
      );
      setPreview(null);
      setTab("schema");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to load dataset into sandbox.");
    } finally {
      setAcceptBusy(false);
    }
  };

  const handleConnectLive = async (e: React.FormEvent) => {
    e.preventDefault();
    setConnecting(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const snap = await api.connectLive({
        engine,
        host,
        port,
        database,
        username,
        password,
        sqlite_path: sqlitePath,
        ssl_mode: sslMode,
        allow_write_opt_in: allowWriteOptIn,
      });
      setContext(snap);
      setPassword("");
      setStatusMessage(
        `Connected to ${snap.label} (${snap.tables.length} tables discovered) and synchronized schema.`
      );
      setTab("schema");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Connection failed.");
    } finally {
      setConnecting(false);
    }
  };

  const handleResetDemo = async () => {
    setErrorMessage(null);
    const snap = await api.activateDemo(context?.dialect);
    setContext(snap);
    setStatusMessage("Restored curated Enterprise HR & Sales Demo Database (DuckDB sandbox).");
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Database Manager &amp; Safe Schema Importer
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
            Upload <code className="font-mono text-xs">.sql</code>,{" "}
            <code className="font-mono text-xs">.csv</code>,{" "}
            <code className="font-mono text-xs">.xlsx</code>, or{" "}
            <code className="font-mono text-xs">.json</code> files with inspect-before-accept
            previews, or attach a live database engine.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void handleResetDemo()}
          className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
        >
          <RotateCcw className="h-3.5 w-3.5 text-[var(--text-secondary)]" /> Activate Demo Database
        </button>
      </div>

      {/* Hairline Tabs */}
      <div className="flex flex-wrap border-b border-[var(--border-subtle)] text-xs">
        {[
          { key: "upload" as const, label: "Upload Schema / Dataset" },
          { key: "live" as const, label: "Live Database Connection" },
          {
            key: "schema" as const,
            label: `Active Schema & Relationships (${context?.tables.length || 0})`,
          },
        ].map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`border-b-2 px-4 py-2 text-[13px] font-medium transition-colors ${
              tab === t.key
                ? "border-[var(--accent-primary)] text-[var(--text-primary)]"
                : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {statusMessage && (
        <div className="flex items-center gap-2 rounded-lg border border-[var(--status-success-border)] bg-[var(--status-success-bg)] px-4 py-3 text-xs text-[var(--status-success-text)]">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{statusMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div className="flex items-start gap-2 rounded-lg border border-[var(--status-error-border)] bg-[var(--status-error-bg)] px-4 py-3 text-xs text-[var(--status-error-text)]">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="font-mono text-xs">{errorMessage}</span>
        </div>
      )}

      {/* TAB 1: UPLOAD DATASET & PREVIEW */}
      {tab === "upload" && (
        <div className="space-y-5">
          <div className="grid gap-6 lg:grid-cols-12 items-start">
            <section className="qt-surface lg:col-span-7 p-5 text-xs space-y-3.5">
              <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] pb-2.5 text-[13px] font-semibold text-[var(--text-primary)]">
                <Upload className="h-4 w-4 text-[var(--accent-primary)]" />
                <span>Inspect file before loading into sandbox</span>
              </div>
              <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
                Supports <code className="font-mono text-xs">.sql</code>,{" "}
                <code className="font-mono text-xs">.dump</code>,{" "}
                <code className="font-mono text-xs">.csv</code>,{" "}
                <code className="font-mono text-xs">.xlsx</code>, and{" "}
                <code className="font-mono text-xs">.json</code> (max 15 MB). Dump shell commands are
                stripped safely before inspecting schemas inside isolated DuckDB sandboxes.
              </p>

              <div className="flex flex-wrap items-center gap-3 rounded-md border border-dashed border-[var(--border-strong)] bg-[var(--bg-subtle)] p-3.5">
                <input
                  type="file"
                  accept=".sql,.dump,.csv,.xlsx,.xls,.json,.ndjson"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  className="block flex-1 text-xs text-[var(--text-secondary)] file:mr-3 file:rounded-md file:border file:border-[var(--border-strong)] file:bg-white file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-[var(--text-primary)] hover:file:bg-[var(--bg-hover)]"
                />
                <DialectSelect
                  label="SQL hint"
                  value={uploadDialect}
                  compact
                  onChange={setUploadDialect}
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={!selectedFile || previewBusy}
                  onClick={() => void handlePreviewUpload()}
                  className="rounded-md bg-[var(--accent-primary)] px-4 py-2 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
                >
                  {previewBusy ? "Inspecting..." : "Inspect & Preview Dataset"}
                </button>
              </div>
            </section>

            {/* Bundled Sample Files */}
            <section className="qt-surface lg:col-span-5 p-5 text-xs space-y-3">
              <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] pb-2.5 text-[13px] font-semibold text-[var(--text-primary)]">
                <FileSpreadsheet className="h-4 w-4 text-[var(--accent-primary)]" />
                <span>Bundled sample datasets</span>
              </div>
              <p className="text-[13px] text-[var(--text-secondary)]">
                Inspect and sandbox-load ready-to-test sample files across formats.
              </p>
              <div className="divide-y divide-[var(--border-subtle)] rounded-md border border-[var(--border-subtle)] bg-white">
                {samples.map((smp) => (
                  <div
                    key={smp.key}
                    className="flex items-center justify-between px-3.5 py-2.5"
                  >
                    <div>
                      <div className="font-mono font-medium text-[var(--text-primary)]">
                        {smp.file_name}
                      </div>
                      <div className="font-mono text-[11px] text-[var(--text-muted)]">
                        {(smp.size_bytes / 1024).toFixed(1)} KB
                      </div>
                    </div>
                    <button
                      type="button"
                      disabled={previewBusy}
                      onClick={() => void handlePreviewSample(smp.key)}
                      className="rounded-md border border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] px-3 py-1 text-xs font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-soft)]"
                    >
                      Preview
                    </button>
                  </div>
                ))}
              </div>
            </section>
          </div>

          {preview && (
            <section className="qt-surface p-5 text-xs space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-3">
                <div>
                  <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                    Import inspection preview —{" "}
                    <span className="font-mono text-[var(--accent-primary)]">
                      {preview.file_name}
                    </span>
                  </h2>
                  <p className="mt-0.5 font-mono text-[11px] text-[var(--text-secondary)]">
                    Format: {preview.file_kind} · Dialect: {preview.detected_dialect} ·{" "}
                    {preview.tables.length} table(s)
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPreview(null)}
                    className="rounded-md border border-[var(--border-strong)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                  >
                    Discard Preview
                  </button>
                  <button
                    type="button"
                    disabled={acceptBusy}
                    onClick={() => void handleAcceptPreview()}
                    className="rounded-md bg-[var(--accent-primary)] px-4 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
                  >
                    {acceptBusy ? "Loading sandbox..." : "Accept & Activate Dataset"}
                  </button>
                </div>
              </div>

              {preview.warnings.length > 0 && (
                <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3 text-[var(--status-warning-text)] space-y-1">
                  <div className="font-semibold">Schema inspection warnings</div>
                  <ul className="list-disc pl-4">
                    {preview.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {preview.ambiguous_or_unsupported.length > 0 && (
                <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3 text-[var(--text-secondary)] space-y-1">
                  <div className="font-medium text-[var(--text-primary)]">
                    Ignored / unsupported dump statements
                  </div>
                  <ul className="list-disc pl-4">
                    {preview.ambiguous_or_unsupported.map((u, i) => (
                      <li key={i} className="font-mono text-[11px]">
                        {u}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid gap-3 md:grid-cols-2">
                {preview.tables.map((t) => (
                  <div
                    key={t.name}
                    className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3.5 space-y-2"
                  >
                    <div className="flex items-center justify-between font-mono font-semibold text-[var(--text-primary)]">
                      <span>{t.name}</span>
                      <span className="text-[11px] font-normal text-[var(--text-secondary)]">
                        {t.columns.length} cols · {t.row_count ?? 0} rows
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {t.columns.map((c) => (
                        <span
                          key={c.name}
                          className="rounded border border-[var(--border-subtle)] bg-white px-2 py-0.5 font-mono text-[11px]"
                        >
                          {c.is_primary_key ? "PK " : ""}
                          {c.name}:{" "}
                          <span className="text-[var(--text-muted)]">{c.data_type}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* TAB 2: LIVE DATABASE CONNECTION */}
      {tab === "live" && (
        <div className="grid gap-6 lg:grid-cols-12 items-start">
          <form
            onSubmit={handleConnectLive}
            className="qt-surface lg:col-span-7 p-5 text-xs space-y-4"
          >
            <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] pb-2.5 text-[13px] font-semibold text-[var(--text-primary)]">
              <Plug className="h-4 w-4 text-[var(--accent-primary)]" />
              <span>Connect to live database engine</span>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1">
                <span className="block text-xs font-medium text-[var(--text-secondary)]">
                  Engine
                </span>
                <select
                  value={engine}
                  onChange={(e) => {
                    const next = e.target.value as typeof engine;
                    setEngine(next);
                    if (ENGINE_DEFAULTS[next]) setPort(ENGINE_DEFAULTS[next].port);
                  }}
                  className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 text-xs text-[var(--text-primary)]"
                >
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mysql">MySQL / MariaDB</option>
                  <option value="sqlserver">Microsoft SQL Server</option>
                  <option value="sqlite">SQLite Local File</option>
                </select>
              </label>

              {engine === "sqlite" ? (
                <label className="space-y-1">
                  <span className="block text-xs font-medium text-[var(--text-secondary)]">
                    SQLite file path
                  </span>
                  <input
                    type="text"
                    required
                    value={sqlitePath}
                    onChange={(e) => setSqlitePath(e.target.value)}
                    placeholder="D:\data\my_database.db"
                    className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                  />
                </label>
              ) : (
                <>
                  <label className="space-y-1">
                    <span className="block text-xs font-medium text-[var(--text-secondary)]">
                      Host
                    </span>
                    <input
                      type="text"
                      required
                      value={host}
                      onChange={(e) => setHost(e.target.value)}
                      className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="block text-xs font-medium text-[var(--text-secondary)]">
                      Port
                    </span>
                    <input
                      type="number"
                      required
                      value={port}
                      onChange={(e) => setPort(Number(e.target.value))}
                      className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="block text-xs font-medium text-[var(--text-secondary)]">
                      Database name
                    </span>
                    <input
                      type="text"
                      required
                      value={database}
                      onChange={(e) => setDatabase(e.target.value)}
                      className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="block text-xs font-medium text-[var(--text-secondary)]">
                      Username
                    </span>
                    <input
                      type="text"
                      required
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="block text-xs font-medium text-[var(--text-secondary)]">
                      Password (memory only)
                    </span>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="block text-xs font-medium text-[var(--text-secondary)]">
                      SSL mode
                    </span>
                    <select
                      value={sslMode}
                      onChange={(e) => setSslMode(e.target.value)}
                      className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                    >
                      <option value="prefer">prefer</option>
                      <option value="require">require</option>
                      <option value="disable">disable</option>
                    </select>
                  </label>
                </>
              )}
            </div>

            <label className="flex items-start gap-2.5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3 text-xs text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={allowWriteOptIn}
                onChange={(e) => setAllowWriteOptIn(e.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 accent-[#26745B]"
              />
              <span>
                Allow Opt-In Write Mode on this session (even when enabled, every INSERT / UPDATE /
                DELETE / DDL requires explicit HMAC confirmation).
              </span>
            </label>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={connecting}
                className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-4 py-2 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
              >
                <Database className="h-3.5 w-3.5" />
                {connecting ? "Connecting & inspecting..." : "Test Connection & Load Schema"}
              </button>
            </div>
          </form>

          <aside className="qt-surface lg:col-span-5 p-5 text-xs space-y-3.5">
            <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] pb-2.5 text-[13px] font-semibold text-[var(--text-primary)]">
              <ShieldCheck className="h-4 w-4 text-[var(--accent-primary)]" />
              <span>Connection security &amp; least-privilege hygiene</span>
            </div>
            <ul className="list-disc space-y-2 pl-4 text-[13px] text-[var(--text-secondary)]">
              <li>
                <strong className="text-[var(--text-primary)]">Read-only account advisory:</strong>{" "}
                Use a dedicated <code className="font-mono text-xs">SELECT</code>-only user when
                inspecting staging or production databases.
              </li>
              <li>
                <strong className="text-[var(--text-primary)]">Zero disk secrets:</strong> Passwords
                stay strictly in process memory and are scrubbed from error traces.
              </li>
              <li>
                <strong className="text-[var(--text-primary)]">SQLite read-only URI:</strong> When
                write opt-in is unchecked, local SQLite opens via immutable read-only safeguards.
              </li>
            </ul>
            <pre className="overflow-x-auto rounded-md bg-[#171B1A] p-3 font-mono text-[11.5px] text-[#7CC4AA]">
              <KeyRound className="mr-1.5 inline h-3.5 w-3.5" />
              GRANT SELECT ON ALL TABLES IN SCHEMA public TO querytrellis_ro;
            </pre>
          </aside>
        </div>
      )}

      {/* TAB 3: ACTIVE SCHEMA & RELATIONSHIPS */}
      {tab === "schema" && (
        <div className="grid gap-6 lg:grid-cols-12 items-start">
          <div className="qt-surface lg:col-span-5 p-5 text-xs space-y-3.5">
            <div className="border-b border-[var(--border-subtle)] pb-2.5 text-[13px] font-semibold text-[var(--text-primary)]">
              Active database metadata
            </div>
            {context && (
              <dl className="grid grid-cols-2 gap-3.5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3.5">
                <div>
                  <dt className="text-[11px] font-medium text-[var(--text-muted)]">Label</dt>
                  <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                    {context.label}
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] font-medium text-[var(--text-muted)]">Engine / Kind</dt>
                  <dd className="mt-0.5 font-mono text-[var(--accent-primary)]">
                    {context.engine} ({context.source_kind})
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] font-medium text-[var(--text-muted)]">EXPLAIN</dt>
                  <dd className="mt-0.5">{context.supports_explain ? "Supported" : "Unavailable"}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-medium text-[var(--text-muted)]">
                    EXPLAIN ANALYZE
                  </dt>
                  <dd className="mt-0.5">
                    {context.supports_explain_analyze ? "Opt-in supported" : "Estimated / timed"}
                  </dd>
                </div>
              </dl>
            )}
            {context?.restricted_account_advisory && (
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3 text-xs text-[var(--text-secondary)]">
                {context.restricted_account_advisory}
              </div>
            )}
            {context?.warnings && context.warnings.length > 0 && (
              <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3 text-[var(--status-warning-text)]">
                <ul className="list-disc pl-4 space-y-0.5">
                  {context.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="qt-surface lg:col-span-7 max-h-[620px] overflow-hidden">
            <SchemaExplorerTree context={context} />
          </div>
        </div>
      )}
    </div>
  );
}
