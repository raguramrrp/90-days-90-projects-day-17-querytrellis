"use client";

import React, { useState } from "react";
import { AlertTriangle, ShieldAlert, X } from "lucide-react";
import type { WriteConfirmationChallenge } from "@/lib/types";

interface WriteConfirmDialogProps {
  challenge: WriteConfirmationChallenge | null;
  sqlPreview: string;
  onCancel: () => void;
  onConfirm: (token: string) => Promise<void> | void;
  busy?: boolean;
}

export function WriteConfirmDialog({
  challenge,
  sqlPreview,
  onCancel,
  onConfirm,
  busy = false,
}: WriteConfirmDialogProps) {
  const [checked, setChecked] = useState(false);

  if (!challenge) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="write-confirm-title"
    >
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] shadow-xl">
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--status-warning-bg)] px-5 py-3.5">
          <div className="flex items-center gap-2 text-[var(--status-warning-text)]">
            <ShieldAlert className="h-4 w-4 shrink-0" />
            <h3 id="write-confirm-title" className="text-sm font-semibold">
              Confirm database modification
            </h3>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close confirmation dialog"
            className="rounded-md p-1 text-[var(--text-secondary)] hover:bg-black/5 hover:text-[var(--text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-5 text-[13px] text-[var(--text-secondary)]">
          <div className="grid grid-cols-2 gap-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3.5 text-xs">
            <div>
              <span className="block text-[11px] font-medium text-[var(--text-muted)]">
                Operation
              </span>
              <span className="mt-0.5 block font-mono font-semibold text-[var(--status-warning-text)]">
                {challenge.operation_type}
              </span>
            </div>
            <div>
              <span className="block text-[11px] font-medium text-[var(--text-muted)]">
                Target database
              </span>
              <span className="mt-0.5 block font-mono font-medium text-[var(--text-primary)]">
                {challenge.target_database}
              </span>
            </div>
          </div>

          <div>
            <span className="mb-1.5 block text-xs font-medium text-[var(--text-primary)]">
              Affected tables
            </span>
            <div className="flex flex-wrap gap-1.5">
              {challenge.affected_tables.length > 0 ? (
                challenge.affected_tables.map((t) => (
                  <span
                    key={t}
                    className="rounded border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 font-mono text-xs text-[var(--text-primary)]"
                  >
                    {t}
                  </span>
                ))
              ) : (
                <span className="text-xs text-[var(--text-muted)]">Target catalog / schema</span>
              )}
            </div>
          </div>

          <div>
            <span className="mb-1.5 block text-xs font-medium text-[var(--text-primary)]">
              Impact &amp; rollback guidance
            </span>
            <ul className="list-disc space-y-1 pl-4 text-xs text-[var(--text-secondary)]">
              {challenge.consequences.map((c, idx) => (
                <li key={idx}>{c}</li>
              ))}
            </ul>
            <p className="mt-2.5 flex items-start gap-2 rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-2.5 text-xs text-[var(--status-warning-text)]">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{challenge.rollback_note}</span>
            </p>
          </div>

          <div>
            <span className="mb-1.5 block text-xs font-medium text-[var(--text-primary)]">
              Statement
            </span>
            <pre className="max-h-28 overflow-auto rounded-md bg-[#171B1A] p-3 font-mono text-xs text-[#ECEFEB]">
              {sqlPreview}
            </pre>
          </div>

          <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-3 text-xs text-[var(--text-primary)]">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-[#26745B]"
            />
            <span>
              I confirm this statement modifies state in{" "}
              <strong className="font-mono">{challenge.target_database}</strong> and authorize its
              signed one-time execution.
            </span>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2.5 border-t border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-5 py-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3.5 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!checked || busy}
            onClick={() => void onConfirm(challenge.token)}
            className="rounded-md bg-[#9E3F13] px-4 py-1.5 text-xs font-medium text-white hover:bg-[#82330E] disabled:cursor-not-allowed disabled:opacity-45"
          >
            {busy ? "Executing..." : "Confirm & Execute"}
          </button>
        </div>
      </div>
    </div>
  );
}
