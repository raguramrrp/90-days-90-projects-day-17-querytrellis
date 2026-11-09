"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Pause, Play, RotateCcw, SkipBack, SkipForward } from "lucide-react";
import type { TraceStage } from "@/lib/types";

interface StageTraceViewerProps {
  stages: TraceStage[];
  title?: string;
}

const STATUS_STYLE: Record<string, { badge: string; row: string; label: string }> = {
  kept: {
    badge:
      "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]",
    row: "bg-white text-[var(--text-primary)]",
    label: "kept",
  },
  excluded: {
    badge:
      "border-[var(--status-error-border)] bg-[var(--status-error-bg)] text-[var(--status-error-text)]",
    row: "bg-[#FDF6F6] text-[var(--text-muted)] line-through decoration-[#B85A60]/60",
    label: "excluded",
  },
  padded_null: {
    badge:
      "border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] text-[var(--status-warning-text)]",
    row: "bg-[#FCF9F1] text-[var(--text-primary)]",
    label: "null-padded",
  },
  added: {
    badge:
      "border-[var(--status-success-border)] bg-[var(--status-success-bg)] text-[var(--status-success-text)]",
    row: "bg-[#F4FAF6] text-[var(--text-primary)]",
    label: "inserted",
  },
  modified: {
    badge: "border-[#B8C7D9] bg-[#F2F6FA] text-[#2A4C6E]",
    row: "bg-[#F6F9FC] text-[var(--text-primary)]",
    label: "updated",
  },
};

export function StageTraceViewer({ stages, title }: StageTraceViewerProps) {
  const [stageIdx, setStageIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speedMs, setSpeedMs] = useState(1100);

  useEffect(() => {
    setStageIdx(0);
    setPlaying(false);
  }, [stages]);

  useEffect(() => {
    if (!playing || stages.length <= 1) return;
    const timer = setInterval(() => {
      setStageIdx((prev) => {
        if (prev + 1 >= stages.length) {
          setPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, speedMs);
    return () => clearInterval(timer);
  }, [playing, stages.length, speedMs]);

  const currentStage = stages[stageIdx] || null;

  const hasAnnotations = useMemo(() => {
    if (!currentStage) return false;
    return currentStage.row_meta.some(
      (m) => (m.status && m.status !== "kept") || Boolean(m.reason)
    );
  }, [currentStage]);

  if (!currentStage) {
    return (
      <div className="qt-surface p-6 text-center text-xs text-[var(--text-muted)]">
        Select a lesson from the curriculum or trace a custom SELECT query to step through execution stages.
      </div>
    );
  }

  return (
    <div className="qt-surface overflow-hidden text-xs">
      {/* Control Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="text-[13px] font-semibold text-[var(--text-primary)]">
            {title || "Execution Pipeline"}
          </span>
          <span className="font-mono text-[11.5px] text-[var(--text-secondary)]">
            Step {stageIdx + 1} of {stages.length}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => {
              setPlaying(false);
              setStageIdx(0);
            }}
            className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
          >
            <RotateCcw className="h-3 w-3" /> Reset
          </button>
          <button
            type="button"
            disabled={stageIdx === 0}
            onClick={() => {
              setPlaying(false);
              setStageIdx((i) => Math.max(0, i - 1));
            }}
            className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] disabled:opacity-40"
          >
            <SkipBack className="h-3 w-3" /> Back
          </button>
          <button
            type="button"
            disabled={stages.length <= 1}
            onClick={() => {
              if (!playing && stageIdx >= stages.length - 1) setStageIdx(0);
              setPlaying((p) => !p);
            }}
            className="inline-flex items-center gap-1 rounded-md bg-[var(--accent-primary)] px-3 py-1 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-40"
          >
            {playing ? (
              <>
                <Pause className="h-3 w-3" /> Pause
              </>
            ) : (
              <>
                <Play className="h-3 w-3" /> Play
              </>
            )}
          </button>
          <button
            type="button"
            disabled={stageIdx >= stages.length - 1}
            onClick={() => {
              setPlaying(false);
              setStageIdx((i) => Math.min(stages.length - 1, i + 1));
            }}
            className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] disabled:opacity-40"
          >
            Step <SkipForward className="h-3 w-3" />
          </button>
          <select
            aria-label="Animation Speed"
            value={speedMs}
            onChange={(e) => setSpeedMs(Number(e.target.value))}
            className="rounded-md border border-[var(--border-subtle)] bg-white px-2 py-1 text-xs text-[var(--text-secondary)]"
          >
            <option value={1700}>Slow (1.7s)</option>
            <option value={1100}>Normal (1.1s)</option>
            <option value={550}>Fast (0.55s)</option>
          </select>
        </div>
      </div>

      {/* Stage Timeline Sequence */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--border-subtle)] bg-white px-4 py-2.5">
        {stages.map((st, idx) => {
          const hasNumPrefix = /^\d+\./.test(st.title.trim());
          return (
            <button
              key={`${st.stage_key}-${idx}`}
              type="button"
              onClick={() => {
                setPlaying(false);
                setStageIdx(idx);
              }}
              className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors ${
                idx === stageIdx
                  ? "border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] font-medium text-[var(--accent-primary)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
              }`}
            >
              {!hasNumPrefix && (
                <span className="font-mono text-[11px] opacity-60">{idx + 1}.</span>
              )}
              <span>{st.title}</span>
              <span className="font-mono text-[11px] opacity-75">({st.row_count})</span>
            </button>
          );
        })}
      </div>

      {/* Active Stage Description & SQL Clause */}
      <div className="border-b border-[var(--border-subtle)] bg-white px-4 py-3.5 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold text-[var(--text-primary)]">{currentStage.title}</div>
          <span className="font-mono text-xs text-[var(--text-secondary)]">
            {currentStage.row_count} active row{currentStage.row_count === 1 ? "" : "s"}
          </span>
        </div>
        <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
          {currentStage.description}
        </p>
        {currentStage.sql_fragment && (
          <pre className="overflow-x-auto rounded-md bg-[#171B1A] px-3.5 py-2.5 font-mono text-xs text-[#A8D8B9]">
            {currentStage.sql_fragment}
          </pre>
        )}
      </div>

      {/* Stage Snapshot Data Grid */}
      <div className="overflow-x-auto bg-white">
        {currentStage.rows.length === 0 ? (
          <div className="p-6 text-center text-xs text-[var(--text-muted)]">
            No rows remain after this evaluation step.
          </div>
        ) : (
          <table className="w-full border-collapse text-left text-[12.5px]">
            <thead>
              <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)]">
                {hasAnnotations && (
                  <th className="border-r border-[var(--border-subtle)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
                    State
                  </th>
                )}
                {currentStage.columns.map((col) => (
                  <th
                    key={col}
                    className="border-r border-[var(--border-subtle)] last:border-r-0 px-3 py-2 font-mono text-xs font-medium text-[var(--text-primary)]"
                  >
                    {col}
                  </th>
                ))}
                {hasAnnotations && (
                  <th className="border-l border-[var(--border-subtle)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
                    Explanation
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-subtle)]">
              {currentStage.rows.map((row, idx) => {
                const meta = currentStage.row_meta[idx] || { status: "kept", reason: "" };
                const st = STATUS_STYLE[meta.status] || STATUS_STYLE.kept;
                return (
                  <tr key={idx} className={st.row}>
                    {hasAnnotations && (
                      <td className="border-r border-[var(--border-subtle)] px-3 py-2 no-underline">
                        <span
                          className={`inline-block rounded border px-1.5 py-0.5 text-[11px] font-medium ${st.badge}`}
                        >
                          {st.label}
                        </span>
                      </td>
                    )}
                    {currentStage.columns.map((col) => {
                      const val = row[col];
                      return (
                        <td
                          key={col}
                          className="max-w-[220px] truncate border-r border-[var(--border-subtle)]/70 last:border-r-0 px-3 py-2 font-mono text-xs"
                        >
                          {val === null || val === undefined ? (
                            <span className="italic text-[var(--text-muted)]">null</span>
                          ) : (
                            String(val)
                          )}
                        </td>
                      );
                    })}
                    {hasAnnotations && (
                      <td className="border-l border-[var(--border-subtle)] px-3 py-2 text-xs text-[var(--text-secondary)] no-underline">
                        {meta.reason}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
