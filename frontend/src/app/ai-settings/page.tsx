"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, Cpu, Globe, Lock, Save, ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/context";
import type { AIConfigSafe } from "@/lib/types";

export default function AiSettingsPage() {
  const { setAiConfig } = useWorkspace();

  const [config, setConfig] = useState<AIConfigSafe | null>(null);
  const [disclosure, setDisclosure] = useState<{
    will_send: string[];
    never_sent: string[];
  } | null>(null);

  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const [externalStatus, setExternalStatus] = useState<{
    reachable: boolean;
    provider: string;
    model?: string;
    error_message?: string;
  } | null>(null);
  const [testingExternal, setTestingExternal] = useState(false);

  useEffect(() => {
    void api.getAiSettings().then((res) => {
      setConfig(res.config);
      setDisclosure(res.external_disclosure);
    });
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setSavedMsg(null);
    try {
      const payload: Record<string, unknown> = {
        active_provider: config.active_provider,
        external_provider: config.external_provider,
        external_base_url: config.external_base_url,
        external_model: config.external_model,
        external_data_consent: config.external_data_consent,
        include_sample_rows_in_external: config.include_sample_rows_in_external,
        deterministic_fallback_enabled: config.deterministic_fallback_enabled,
      };
      if (apiKeyInput.trim()) {
        payload.external_api_key = apiKeyInput.trim();
      }
      const res = await api.updateAiSettings(payload);
      setConfig(res.config);
      setAiConfig(res.config);
      setDisclosure(res.external_disclosure);
      setApiKeyInput("");
      setSavedMsg("Engine and API gateway settings synchronized for active session.");
    } finally {
      setSaving(false);
    }
  };

  const handleClearKey = async () => {
    const res = await api.updateAiSettings({ clear_external_api_key: true });
    setConfig(res.config);
    setAiConfig(res.config);
    setSavedMsg("Cleared session API key from server memory.");
  };

  const handleTestExternal = async () => {
    await handleSave();
    setTestingExternal(true);
    try {
      const res = await api.testExternalAi();
      setExternalStatus(res);
    } finally {
      setTestingExternal(false);
    }
  };

  if (!config) {
    return (
      <div className="p-6 text-xs text-[var(--text-secondary)]">
        Loading engine gateway configuration...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-col gap-3 border-b border-[var(--border-subtle)] pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 flex-1">
          <h1 className="text-[20px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Engine Configuration &amp; Privacy Controls
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
            Runs offline by default via the built-in Schema AST Compiler, or optionally routes NL
            synthesis to an opt-in cloud API gateway.
          </p>
        </div>

        <button
          type="button"
          disabled={saving}
          onClick={() => void handleSave()}
          className="inline-flex shrink-0 items-center gap-1.5 self-start sm:self-end rounded-md bg-[var(--accent-primary)] px-4 py-2 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
        >
          <Save className="h-3.5 w-3.5" />
          {saving ? "Saving..." : "Save Configuration"}
        </button>
      </div>

      {savedMsg && (
        <div className="flex items-center gap-2 rounded-lg border border-[var(--status-success-border)] bg-[var(--status-success-bg)] px-4 py-3 text-xs text-[var(--status-success-text)]">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{savedMsg}</span>
        </div>
      )}

      {/* Mode Selection */}
      <section className="grid gap-4 md:grid-cols-2 text-xs">
        {[
          {
            id: "deterministic" as const,
            badge: "Default · Offline",
            title: "Deterministic Schema AST Engine",
            desc: "In-process SQLGlot AST compiler & schema-graph planner. Executes locally with zero external dependencies, zero background model servers, and strict catalog verification.",
            icon: Cpu,
          },
          {
            id: "external" as const,
            badge: "Opt-in gateway",
            title: "External Cloud API Gateway",
            desc: "Routes natural-language synthesis to OpenAI, OpenAI-compatible endpoints, Anthropic Claude, or Google Gemini with schema verification and session-only API key memory.",
            icon: Globe,
          },
        ].map((card) => {
          const Icon = card.icon;
          const active = config.active_provider === card.id;
          return (
            <button
              key={card.id}
              type="button"
              onClick={() => setConfig({ ...config, active_provider: card.id })}
              className={`rounded-lg border p-4 text-left transition-colors ${
                active
                  ? "border-[var(--accent-primary)] bg-[var(--accent-tint)]"
                  : "border-[var(--border-subtle)] bg-white hover:border-[var(--border-strong)]"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[11.5px] font-medium text-[var(--accent-primary)]">
                  {card.badge}
                </span>
                {active && (
                  <span className="rounded bg-[var(--accent-primary)] px-2 py-0.5 text-[11px] font-medium text-white">
                    Active
                  </span>
                )}
              </div>
              <div className="mt-2 flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <Icon className="h-4 w-4 text-[var(--accent-primary)]" />
                <span>{card.title}</span>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                {card.desc}
              </p>
            </button>
          );
        })}
      </section>

      {/* Main Clean Settings Sheet */}
      <div className="qt-surface divide-y divide-[var(--border-subtle)] text-xs">
        {/* Compiler Guarantees & Fallback */}
        <section className="p-5 space-y-3.5">
          <div className="flex items-center justify-between">
            <h2 className="text-[13.5px] font-semibold text-[var(--text-primary)]">
              Compiler guarantees &amp; fallback
            </h2>
            <ShieldCheck className="h-4 w-4 text-[var(--accent-primary)]" />
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3.5 space-y-1">
              <div className="font-medium text-[var(--text-primary)]">Zero local agent daemons</div>
              <p className="text-[var(--text-secondary)]">
                No local LLM model downloads, background inference servers, or host port probing.
              </p>
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3.5 space-y-1">
              <div className="font-medium text-[var(--text-primary)]">Strict catalog verification</div>
              <p className="text-[var(--text-secondary)]">
                Every generated query passes{" "}
                <code className="font-mono text-[11.5px]">verify_sql_against_schema</code> and
                SQLGlot dialect transpilation.
              </p>
            </div>
          </div>

          <label className="flex items-start gap-2.5 rounded-md border border-[var(--border-subtle)] bg-white p-3 text-xs text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={config.deterministic_fallback_enabled}
              onChange={(e) =>
                setConfig({ ...config, deterministic_fallback_enabled: e.target.checked })
              }
              className="mt-0.5 h-3.5 w-3.5 accent-[#26745B]"
            />
            <span>
              Automatically fall back to the Deterministic Schema AST Engine if an external API
              endpoint is unreachable or emits unverified identifiers.
            </span>
          </label>
        </section>

        {/* External Gateway Configuration */}
        <section className="p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[13.5px] font-semibold text-[var(--text-primary)]">
              External cloud API gateway (opt-in)
            </h2>
            <button
              type="button"
              disabled={testingExternal}
              onClick={() => void handleTestExternal()}
              className="rounded-md border border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] px-3 py-1.5 text-xs font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-soft)]"
            >
              {testingExternal ? "Testing..." : "Test Connection"}
            </button>
          </div>

          <div className="grid gap-3.5 sm:grid-cols-2">
            <label className="space-y-1">
              <span className="block text-xs font-medium text-[var(--text-secondary)]">
                Provider type
              </span>
              <select
                value={config.external_provider}
                onChange={(e) => setConfig({ ...config, external_provider: e.target.value })}
                className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 text-xs text-[var(--text-primary)]"
              >
                <option value="openai">OpenAI</option>
                <option value="openai_compatible">OpenAI-Compatible Endpoint</option>
                <option value="anthropic">Anthropic Claude</option>
                <option value="gemini">Google Gemini</option>
              </select>
            </label>

            <label className="space-y-1">
              <span className="block text-xs font-medium text-[var(--text-secondary)]">
                Model identifier
              </span>
              <input
                type="text"
                value={config.external_model}
                onChange={(e) => setConfig({ ...config, external_model: e.target.value })}
                className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
              />
            </label>

            <label className="space-y-1 sm:col-span-2">
              <span className="block text-xs font-medium text-[var(--text-secondary)]">
                API base URL
              </span>
              <input
                type="text"
                value={config.external_base_url}
                onChange={(e) => setConfig({ ...config, external_base_url: e.target.value })}
                placeholder="https://api.openai.com/v1"
                className="w-full rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
              />
            </label>

            <div className="space-y-1.5 sm:col-span-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--text-secondary)]">
                  Session API key (memory-only — never written to disk)
                </span>
                {config.external_api_key_configured && (
                  <button
                    type="button"
                    onClick={() => void handleClearKey()}
                    className="text-xs font-medium text-[var(--status-error-text)] hover:underline"
                  >
                    Clear Key
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="password"
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  placeholder={
                    config.external_api_key_configured
                      ? "Key active in session memory (enter replacement key)"
                      : "Enter API key for current session..."
                  }
                  className="flex-1 rounded-md border border-[var(--border-strong)] bg-white px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                />
                <span
                  className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-2 text-xs font-medium ${
                    config.external_api_key_configured
                      ? "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]"
                      : "border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-[var(--text-muted)]"
                  }`}
                >
                  <Lock className="h-3.5 w-3.5" />
                  {config.external_api_key_configured ? "Key Set" : "Not Set"}
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-4 space-y-2.5 text-[var(--status-warning-text)]">
            <div className="flex items-center gap-1.5 text-xs font-semibold">
              <ShieldAlert className="h-4 w-4 shrink-0" />
              <span>External data transmission disclosure &amp; consent</span>
            </div>

            {disclosure && (
              <div className="grid gap-3 sm:grid-cols-2 text-xs">
                <div>
                  <div className="font-semibold">Transmitted when consented:</div>
                  <ul className="mt-1 list-disc pl-4 space-y-0.5">
                    {disclosure.will_send.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="font-semibold">Never transmitted:</div>
                  <ul className="mt-1 list-disc pl-4 space-y-0.5">
                    {disclosure.never_sent.map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            <label className="flex items-start gap-2.5 pt-1 text-xs font-medium">
              <input
                type="checkbox"
                checked={config.external_data_consent}
                onChange={(e) =>
                  setConfig({ ...config, external_data_consent: e.target.checked })
                }
                className="mt-0.5 h-3.5 w-3.5 accent-[#26745B]"
              />
              <span>
                I explicitly consent to sending my natural-language query and inspected schema
                metadata to the configured external API provider.
              </span>
            </label>
          </div>

          {externalStatus && (
            <div
              className={`rounded-md border p-3 text-xs ${
                externalStatus.reachable
                  ? "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]"
                  : "border-[var(--status-error-border)] bg-[var(--status-error-bg)] text-[var(--status-error-text)]"
              }`}
            >
              {externalStatus.reachable
                ? `External provider (${externalStatus.provider} / ${externalStatus.model}) connected cleanly.`
                : `External test failed: ${externalStatus.error_message}`}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
