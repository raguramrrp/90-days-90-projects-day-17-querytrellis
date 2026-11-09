"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Eye,
  GraduationCap,
  HelpCircle,
  Lightbulb,
  Play,
  Sparkles,
  Workflow,
} from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/context";
import type { LessonDetailResponse, LessonSummary, TraceStage } from "@/lib/types";
import { MonacoSqlEditor } from "@/components/MonacoSqlEditor";
import { StageTraceViewer } from "@/components/StageTraceViewer";

const TIER_ORDER = ["Beginner", "Intermediate", "Advanced", "Storage & DML"];

export default function AcademyPage() {
  const { visualizeSql, setVisualizeSql, activeSql } = useWorkspace();

  const [mode, setMode] = useState<"curriculum" | "custom">(visualizeSql ? "custom" : "curriculum");
  const [lessons, setLessons] = useState<LessonSummary[]>([]);
  const [selectedLessonId, setSelectedLessonId] = useState<string>("select");
  const [lessonDetail, setLessonDetail] = useState<LessonDetailResponse | null>(null);
  const [loadingLesson, setLoadingLesson] = useState(false);

  const [exerciseSql, setExerciseSql] = useState("");
  const [hintsShown, setHintsShown] = useState(0);
  const [showSolution, setShowSolution] = useState(false);
  const [checking, setChecking] = useState(false);
  const [completedMap, setCompletedMap] = useState<Record<string, boolean>>({});
  const [evalResult, setEvalResult] = useState<{
    success: boolean;
    passed: boolean;
    feedback: string;
    expected_columns: string[];
    expected_rows: Record<string, unknown>[];
    actual_columns: string[];
    actual_rows: Record<string, unknown>[];
  } | null>(null);

  const [customSqlInput, setCustomSqlInput] = useState(
    visualizeSql ||
      "SELECT e.first_name, e.department_id, e.base_salary\nFROM employees e\nWHERE e.base_salary >= 115000\nORDER BY e.base_salary DESC\nLIMIT 5;"
  );
  const [customStages, setCustomStages] = useState<TraceStage[]>([]);
  const [customError, setCustomError] = useState<string | null>(null);
  const [customNotes, setCustomNotes] = useState<string[]>([]);
  const [customLoading, setCustomLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function load() {
      const res = await api.listLessons();
      if (!mounted) return;
      setLessons(res.lessons);
      if (res.lessons.length > 0) {
        setSelectedLessonId(res.lessons[0].lesson_id);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedLessonId) return;
    let mounted = true;
    async function loadDetail() {
      setLoadingLesson(true);
      setHintsShown(0);
      setShowSolution(false);
      setEvalResult(null);
      try {
        const res = await api.getLessonDetail(selectedLessonId);
        if (!mounted) return;
        setLessonDetail(res);
        setExerciseSql(res.exercise.starter_sql);
      } finally {
        if (mounted) setLoadingLesson(false);
      }
    }
    void loadDetail();
    return () => {
      mounted = false;
    };
  }, [selectedLessonId]);

  useEffect(() => {
    if (visualizeSql) {
      setMode("custom");
      setCustomSqlInput(visualizeSql);
      void runCustomTrace(visualizeSql);
      setVisualizeSql(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visualizeSql]);

  const runCustomTrace = async (sqlToTrace: string) => {
    if (!sqlToTrace.trim()) return;
    setCustomLoading(true);
    setCustomError(null);
    try {
      const res = await api.visualizeCustomSql(sqlToTrace);
      setCustomStages(res.stages || []);
      setCustomNotes(res.notes || []);
      if (!res.success && res.error_message) {
        setCustomError(res.error_message);
      }
    } finally {
      setCustomLoading(false);
    }
  };

  const handleCheckExercise = async () => {
    if (!lessonDetail) return;
    setChecking(true);
    try {
      const res = await api.checkExercise(lessonDetail.lesson.lesson_id, exerciseSql);
      setEvalResult(res);
      if (res.passed) {
        setCompletedMap((prev) => ({ ...prev, [lessonDetail.lesson.lesson_id]: true }));
      }
    } finally {
      setChecking(false);
    }
  };

  const groupedLessons = useMemo(() => {
    return TIER_ORDER.map((tier) => ({
      tier,
      items: lessons.filter((l) => l.tier === tier),
    })).filter((g) => g.items.length > 0);
  }, [lessons]);

  const completedCount = Object.values(completedMap).filter(Boolean).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div>
          <h1 className="text-[20px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Visual SQL Learning Academy
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
            21 interactive lessons with live DuckDB step-by-step execution traces, kept/excluded row
            highlighting, and SQL exercises.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="font-mono text-xs text-[var(--text-secondary)]">
            Completed:{" "}
            <strong className="text-[var(--text-primary)]">
              {completedCount} / {lessons.length || 21}
            </strong>
          </span>

          <div className="inline-flex rounded-md border border-[var(--border-strong)] bg-[var(--bg-subtle)] p-0.5">
            <button
              type="button"
              onClick={() => setMode("curriculum")}
              className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                mode === "curriculum"
                  ? "bg-white text-[var(--text-primary)] shadow-xs"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <GraduationCap className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
              21 Lessons
            </button>
            <button
              type="button"
              onClick={() => setMode("custom")}
              className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                mode === "custom"
                  ? "bg-white text-[var(--text-primary)] shadow-xs"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <Workflow className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
              Custom Query Tracer
            </button>
          </div>
        </div>
      </div>

      {mode === "custom" ? (
        <div className="space-y-4">
          <section className="qt-surface p-4 space-y-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[13px] font-semibold text-[var(--text-primary)]">
                Trace any SELECT query step by step
              </span>
              <button
                type="button"
                onClick={() => {
                  setCustomSqlInput(activeSql);
                  void runCustomTrace(activeSql);
                }}
                className="rounded-md border border-[var(--border-strong)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
              >
                Load Active Workspace SQL
              </button>
            </div>
            <MonacoSqlEditor
              label="Query To Trace"
              value={customSqlInput}
              onChange={setCustomSqlInput}
              dialect="postgresql"
              height="170px"
            />
            {customError && (
              <div className="rounded-md border border-[var(--status-error-border)] bg-[var(--status-error-bg)] p-3 font-mono text-xs text-[var(--status-error-text)]">
                {customError}
              </div>
            )}
            {customNotes.length > 0 && (
              <div className="text-xs text-[var(--text-muted)]">{customNotes.join(" · ")}</div>
            )}
            <div className="flex justify-end">
              <button
                type="button"
                disabled={customLoading || !customSqlInput.trim()}
                onClick={() => void runCustomTrace(customSqlInput)}
                className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-4 py-2 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
              >
                <Play className="h-3.5 w-3.5" />
                {customLoading ? "Computing stages..." : "Compute & Visualize Stages"}
              </button>
            </div>
          </section>

          <StageTraceViewer stages={customStages} title="Custom Query Stage Execution" />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-12 items-start">
          {/* Left 21-Lesson Index */}
          <aside className="qt-surface lg:col-span-3 p-3 max-h-[82vh] overflow-y-auto space-y-4 text-xs">
            {groupedLessons.map((group) => (
              <div key={group.tier}>
                <div className="mb-1.5 px-2 text-[11.5px] font-semibold text-[var(--text-muted)]">
                  {group.tier}
                </div>
                <ul className="space-y-0.5">
                  {group.items.map((les) => {
                    const active = les.lesson_id === selectedLessonId;
                    const done = Boolean(completedMap[les.lesson_id]);
                    return (
                      <li key={les.lesson_id}>
                        <button
                          type="button"
                          onClick={() => setSelectedLessonId(les.lesson_id)}
                          className={`flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left transition-colors ${
                            active
                              ? "bg-[var(--accent-tint)] font-medium text-[var(--accent-primary)]"
                              : "text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]"
                          }`}
                        >
                          <span className="truncate">
                            <span className="mr-2 font-mono text-[11px] opacity-60">
                              {String(les.order).padStart(2, "0")}
                            </span>
                            {les.concept}
                          </span>
                          {done && (
                            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-[var(--accent-primary)]" />
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </aside>

          {/* Right Lesson Content, Execution Visualizer & Interactive Exercise */}
          <div className="lg:col-span-9 space-y-5">
            {loadingLesson || !lessonDetail ? (
              <div className="qt-surface p-10 text-center text-xs text-[var(--text-secondary)]">
                Computing interactive lesson stages in DuckDB sandbox...
              </div>
            ) : (
              <>
                <section className="qt-surface p-5 text-xs space-y-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-3">
                    <div className="flex items-center gap-2.5">
                      <span className="rounded border border-[var(--status-success-border)] bg-[var(--accent-tint)] px-2 py-0.5 font-mono text-[11px] font-medium text-[var(--accent-primary)]">
                        Module {String(lessonDetail.lesson.order).padStart(2, "0")}
                      </span>
                      <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
                        {lessonDetail.lesson.title}
                      </h2>
                    </div>
                    <span className="rounded border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">
                      {lessonDetail.lesson.tier}
                    </span>
                  </div>

                  <p className="text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
                    {lessonDetail.lesson.summary}
                  </p>

                  <div className="flex items-start gap-2.5 rounded-r-md border-l-2 border-[var(--accent-primary)] bg-[var(--accent-tint)] px-3.5 py-3 text-[13px] text-[var(--text-primary)]">
                    <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent-primary)]" />
                    <span>
                      <strong className="font-semibold text-[var(--accent-primary)]">
                        Mental model:
                      </strong>{" "}
                      {lessonDetail.lesson.key_rule}
                    </span>
                  </div>

                  <pre className="overflow-x-auto rounded-md bg-[#171B1A] p-3.5 font-mono text-xs text-[#ECEFEB]">
                    {lessonDetail.lesson.lesson_sql}
                  </pre>
                </section>

                <StageTraceViewer
                  stages={lessonDetail.stages}
                  title={`Execution sequence: ${lessonDetail.lesson.concept}`}
                />

                {/* Hands-On Interactive Exercise */}
                <section className="qt-surface p-5 text-xs space-y-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--border-subtle)] pb-3">
                    <div>
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                        Hands-on exercise
                      </h3>
                      <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
                        {lessonDetail.exercise.prompt}
                      </p>
                    </div>
                    <span className="shrink-0 rounded border border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                      {lessonDetail.exercise.is_dml
                        ? "Isolated DML sandbox"
                        : lessonDetail.exercise.order_sensitive
                        ? "Order-sensitive check"
                        : "Set equivalence check"}
                    </span>
                  </div>

                  <MonacoSqlEditor
                    label="Exercise Buffer (Sandbox Tables: staff, teams, deals, leads_archive)"
                    value={exerciseSql}
                    onChange={setExerciseSql}
                    dialect="sqlite"
                    height="160px"
                  />

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={checking || !exerciseSql.trim()}
                      onClick={() => void handleCheckExercise()}
                      className="inline-flex items-center gap-1.5 rounded-md bg-[var(--accent-primary)] px-4 py-1.5 text-xs font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-45"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      {checking ? "Evaluating..." : "Check Solution"}
                    </button>

                    <button
                      type="button"
                      disabled={hintsShown >= lessonDetail.exercise.hints.length}
                      onClick={() => setHintsShown((h) => h + 1)}
                      className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] disabled:opacity-40"
                    >
                      <HelpCircle className="h-3.5 w-3.5" />
                      Hint ({hintsShown}/{lessonDetail.exercise.hints.length})
                    </button>

                    <button
                      type="button"
                      onClick={() => setShowSolution((v) => !v)}
                      className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      {showSolution ? "Hide Solution" : "Step-by-Step Solution"}
                    </button>
                  </div>

                  {hintsShown > 0 && (
                    <div className="rounded-md border border-[var(--status-warning-border)] bg-[var(--status-warning-bg)] p-3.5 space-y-1.5 text-[var(--status-warning-text)]">
                      <div className="text-xs font-semibold">Progressive hints</div>
                      <ul className="list-disc pl-4 space-y-1">
                        {lessonDetail.exercise.hints.slice(0, hintsShown).map((hint, idx) => (
                          <li key={idx}>{hint}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {showSolution && (
                    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-subtle)] p-4 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-[var(--text-primary)]">
                          Step-by-step solution guide
                        </span>
                        <button
                          type="button"
                          onClick={() => setExerciseSql(lessonDetail.exercise.solution_sql)}
                          className="rounded-md border border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] hover:bg-[var(--accent-soft)]"
                        >
                          Load Solution Into Editor
                        </button>
                      </div>
                      <ul className="list-disc pl-4 space-y-1 text-[var(--text-secondary)]">
                        {lessonDetail.exercise.step_by_step_solution.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ul>
                      <pre className="overflow-x-auto rounded-md bg-[#171B1A] p-3 font-mono text-xs text-[#ECEFEB]">
                        {lessonDetail.exercise.solution_sql}
                      </pre>
                    </div>
                  )}

                  {evalResult && (
                    <div
                      className={`rounded-md border p-4 space-y-3 ${
                        evalResult.passed
                          ? "border-[var(--status-success-border)] bg-[var(--status-success-bg)]"
                          : "border-[var(--status-error-border)] bg-[var(--status-error-bg)]"
                      }`}
                    >
                      <div
                        className={`text-[13px] font-semibold ${
                          evalResult.passed
                            ? "text-[var(--status-success-text)]"
                            : "text-[var(--status-error-text)]"
                        }`}
                      >
                        {evalResult.passed
                          ? "Passed — matches expected output"
                          : "Output does not match expected result yet"}
                      </div>
                      <p className="text-xs text-[var(--text-primary)]">{evalResult.feedback}</p>

                      {!evalResult.passed && evalResult.expected_columns.length > 0 && (
                        <div className="grid gap-3 pt-1 md:grid-cols-2">
                          <div>
                            <div className="mb-1 text-[11.5px] font-medium text-[var(--text-secondary)]">
                              Expected preview ({evalResult.expected_rows.length} rows)
                            </div>
                            <div className="max-h-44 overflow-auto rounded-md border border-[var(--border-subtle)] bg-white">
                              <table className="w-full border-collapse font-mono text-[11px]">
                                <thead>
                                  <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)]">
                                    {evalResult.expected_columns.map((c) => (
                                      <th
                                        key={c}
                                        className="px-2.5 py-1.5 text-left font-medium text-[var(--accent-primary)]"
                                      >
                                        {c}
                                      </th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {evalResult.expected_rows.slice(0, 8).map((r, i) => (
                                    <tr
                                      key={i}
                                      className="border-b border-[var(--border-subtle)]/60 last:border-0"
                                    >
                                      {evalResult.expected_columns.map((c) => (
                                        <td
                                          key={c}
                                          className="px-2.5 py-1 text-[var(--text-primary)]"
                                        >
                                          {r[c] === null || r[c] === undefined
                                            ? "null"
                                            : String(r[c])}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>

                          <div>
                            <div className="mb-1 text-[11.5px] font-medium text-[var(--text-secondary)]">
                              Your output ({evalResult.actual_rows.length} rows)
                            </div>
                            <div className="max-h-44 overflow-auto rounded-md border border-[var(--border-subtle)] bg-white">
                              <table className="w-full border-collapse font-mono text-[11px]">
                                <thead>
                                  <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)]">
                                    {evalResult.actual_columns.map((c) => (
                                      <th
                                        key={c}
                                        className="px-2.5 py-1.5 text-left font-medium text-[var(--status-error-text)]"
                                      >
                                        {c}
                                      </th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {evalResult.actual_rows.slice(0, 8).map((r, i) => (
                                    <tr
                                      key={i}
                                      className="border-b border-[var(--border-subtle)]/60 last:border-0"
                                    >
                                      {evalResult.actual_columns.map((c) => (
                                        <td
                                          key={c}
                                          className="px-2.5 py-1 text-[var(--text-primary)]"
                                        >
                                          {r[c] === null || r[c] === undefined
                                            ? "null"
                                            : String(r[c])}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
