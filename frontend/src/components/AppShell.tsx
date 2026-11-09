"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Bug,
  Code2,
  Database,
  Gauge,
  Lock,
  Menu,
  MessageSquare,
  RotateCcw,
  ShieldAlert,
  Sliders,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/context";
import { DialectSelect } from "./DialectSelect";

const WORKSPACE_TABS = [
  { label: "Query Studio", href: "/query-studio", icon: MessageSquare },
  { label: "SQL IDE", href: "/sql-editor", icon: Code2 },
  { label: "Debugger", href: "/debugging", icon: Bug },
  { label: "Optimizer", href: "/optimizer", icon: Gauge },
  { label: "SQL Academy", href: "/academy", icon: BookOpen },
];

const SYSTEM_TABS = [
  { label: "Databases", href: "/database-manager", icon: Database },
  { label: "Engine API", href: "/ai-settings", icon: Sliders },
];

function QueryTrellisMark() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      className="shrink-0"
    >
      <rect
        x="1.75"
        y="1.75"
        width="20.5"
        height="20.5"
        rx="4"
        fill="#FFFFFF"
        stroke="#D0D4CE"
        strokeWidth="1.25"
      />
      <path
        d="M8 6.5V17.5M16 6.5V17.5M6.5 9.5H17.5M6.5 14.5H17.5"
        stroke="#26745B"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <circle cx="8" cy="9.5" r="1.6" fill="#202321" />
      <circle cx="16" cy="14.5" r="1.6" fill="#202321" />
    </svg>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { context, aiConfig, setDialect, setContext, contextError, refreshContext } =
    useWorkspace();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);

  const isNavActive = (href: string) => {
    if (href === "/query-studio" && pathname === "/") return true;
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  const handleResetDemo = async () => {
    setResetBusy(true);
    try {
      const snap = await api.activateDemo(context?.dialect);
      setContext(snap);
    } finally {
      setResetBusy(false);
    }
  };

  const engineLabel =
    aiConfig?.active_provider === "external"
      ? `External API (${aiConfig.external_model})`
      : "Schema AST Engine";

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Editorial Top Workbench Masthead */}
      <header className="sticky top-0 z-30 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]">
        {/* Row 1: Brand Identity, Connected Source Context & Global Guards */}
        <div className="mx-auto flex h-12 max-w-[1380px] items-center justify-between gap-4 border-b border-[var(--border-subtle)]/75 px-4 lg:px-8">
          <div className="flex min-w-0 items-center gap-3 text-xs">
            <button
              type="button"
              onClick={() => setMobileNavOpen((v) => !v)}
              className="rounded-md border border-[var(--border-subtle)] bg-white p-1.5 text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] md:hidden"
              aria-label="Toggle workspace navigation"
            >
              {mobileNavOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>

            <Link href="/query-studio" className="flex shrink-0 items-center gap-2">
              <QueryTrellisMark />
              <span className="text-[14.5px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
                QueryTrellis
              </span>
            </Link>

            <span className="hidden text-[var(--border-strong)] sm:inline">/</span>

            <Link
              href="/database-manager"
              className="hidden min-w-0 items-center gap-1.5 truncate rounded-md px-2 py-1 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] sm:inline-flex"
              title={context?.label || "Inspect active database"}
            >
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)]" />
              <span className="truncate font-medium text-[var(--text-primary)]">
                {context ? context.label : "Connecting..."}
              </span>
              {context && (
                <span className="shrink-0 font-mono text-[11px] text-[var(--text-muted)]">
                  · {context.tables.length} tables · {context.engine}
                </span>
              )}
            </Link>
          </div>

          <div className="flex shrink-0 items-center gap-2 text-xs">
            <Link
              href="/ai-settings"
              className="hidden rounded-md px-2 py-1 text-[11.5px] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)] lg:inline-block"
              title="Configure SQL synthesis engine"
            >
              {engineLabel}
            </Link>

            <DialectSelect
              value={context?.dialect || "postgresql"}
              compact
              onChange={(d) => void setDialect(d)}
            />

            <span
              className={`hidden sm:inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11.5px] font-medium ${
                context?.allow_write_opt_in
                  ? "border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-[var(--status-warning-text)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]"
              }`}
              title="Database execution protection mode"
            >
              {context?.allow_write_opt_in ? (
                <>
                  <ShieldAlert className="h-3.5 w-3.5" />
                  Write opt-in
                </>
              ) : (
                <>
                  <Lock className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
                  Read-only
                </>
              )}
            </span>

            {context && !context.source_kind.startsWith("demo") && (
              <button
                type="button"
                disabled={resetBusy}
                onClick={() => void handleResetDemo()}
                className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-strong)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
              >
                <RotateCcw className="h-3.5 w-3.5 text-[var(--text-secondary)]" />
                {resetBusy ? "Resetting..." : "Reset Demo"}
              </button>
            )}
          </div>
        </div>

        {/* Row 2: Clean Desktop Horizontal Workspace Navigation (Left: Workflows, Right: Infrastructure) */}
        <nav
          aria-label="Primary Workspaces"
          className="hidden bg-[var(--bg-subtle)]/55 md:block"
        >
          <div className="mx-auto flex h-10 max-w-[1380px] items-stretch justify-between gap-6 px-4 lg:px-8">
            <div className="flex items-stretch gap-5 overflow-x-auto">
              {WORKSPACE_TABS.map((item) => {
                const active = isNavActive(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`relative inline-flex shrink-0 items-center gap-2 border-b-2 px-0.5 text-[13px] transition-colors ${
                      active
                        ? "border-[var(--accent-primary)] font-medium text-[var(--text-primary)]"
                        : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <Icon
                      className={`h-3.5 w-3.5 shrink-0 ${
                        active ? "text-[var(--accent-primary)]" : "text-[var(--text-muted)]"
                      }`}
                    />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>

            <div className="flex shrink-0 items-stretch gap-5 border-l border-[var(--border-subtle)] pl-5">
              {SYSTEM_TABS.map((item) => {
                const active = isNavActive(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`relative inline-flex shrink-0 items-center gap-2 border-b-2 px-0.5 text-[13px] transition-colors ${
                      active
                        ? "border-[var(--accent-primary)] font-medium text-[var(--text-primary)]"
                        : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <Icon
                      className={`h-3.5 w-3.5 shrink-0 ${
                        active ? "text-[var(--accent-primary)]" : "text-[var(--text-muted)]"
                      }`}
                    />
                    <span>{item.label}</span>
                    {item.href === "/database-manager" && context && (
                      <span className="font-mono text-[11px] text-[var(--text-muted)]">
                        {context.tables.length}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        </nav>

        {/* Mobile Expandable Menu */}
        {mobileNavOpen && (
          <nav
            aria-label="Mobile Navigation"
            className="border-t border-[var(--border-subtle)] bg-white px-4 py-3 md:hidden space-y-1"
          >
            {[...WORKSPACE_TABS, ...SYSTEM_TABS].map((item) => {
              const active = isNavActive(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileNavOpen(false)}
                  className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] ${
                    active
                      ? "bg-[var(--accent-tint)] font-medium text-[var(--accent-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        )}
      </header>

      {contextError && (
        <div className="border-b border-[var(--status-error-border)] bg-[var(--status-error-bg)] px-4 py-2 text-xs text-[var(--status-error-text)] lg:px-8">
          <div className="mx-auto flex max-w-[1380px] items-center justify-between gap-3">
            <span>
              Unable to reach QueryTrellis backend API:{" "}
              <strong className="font-mono">{contextError}</strong>. Ensure the API server is
              running on port 8000.
            </span>
            <button
              type="button"
              onClick={() => void refreshContext()}
              className="rounded-md border border-[var(--status-error-border)] bg-white px-2.5 py-1 font-medium text-[var(--status-error-text)] hover:bg-[#FAF0F0]"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Full-Width Centered Canvas */}
      <main className="mx-auto w-full max-w-[1380px] flex-1 px-4 py-6 lg:px-8 lg:py-7">
        {children}
      </main>
    </div>
  );
}
