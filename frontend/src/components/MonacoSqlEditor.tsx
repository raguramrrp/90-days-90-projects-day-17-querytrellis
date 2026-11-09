"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Editor, { loader } from "@monaco-editor/react";
import type * as MonacoTypes from "monaco-editor";
import { Maximize2, Minimize2, Sparkles } from "lucide-react";
import type { SqlDialect, TableSchema } from "@/lib/types";

export interface EditorDiagnosticMarker {
  line?: number | null;
  column?: number | null;
  severity: string;
  message: string;
}

interface MonacoSqlEditorProps {
  value: string;
  onChange?: (next: string) => void;
  dialect?: SqlDialect;
  readOnly?: boolean;
  height?: string;
  schemaTables?: TableSchema[];
  diagnostics?: EditorDiagnosticMarker[];
  onExecuteShortcut?: () => void;
  onFormat?: () => void;
  expandable?: boolean;
  label?: string;
}

let monacoConfigured = false;

export function registerCharcoalMonacoTheme(monaco: typeof MonacoTypes) {
  monaco.editor.defineTheme("qt-charcoal", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "7CC4AA", fontStyle: "bold" },
      { token: "keyword.sql", foreground: "7CC4AA", fontStyle: "bold" },
      { token: "predefined.sql", foreground: "9CB9D9" },
      { token: "operator.sql", foreground: "9CA6A0" },
      { token: "string", foreground: "B3DFBE" },
      { token: "string.sql", foreground: "B3DFBE" },
      { token: "number", foreground: "E6C182" },
      { token: "comment", foreground: "6D7772", fontStyle: "italic" },
      { token: "identifier", foreground: "ECEFEB" },
    ],
    colors: {
      "editor.background": "#171B1A",
      "editor.foreground": "#ECEFEB",
      "editor.lineHighlightBackground": "#1F2422",
      "editor.lineHighlightBorder": "#252B29",
      "editorLineNumber.foreground": "#5F6964",
      "editorLineNumber.activeForeground": "#B9C9C0",
      "editorCursor.foreground": "#7CC4AA",
      "editor.selectionBackground": "#26745B4D",
      "editorWidget.background": "#1F2422",
      "editorWidget.border": "#313936",
      "editorSuggestWidget.background": "#1F2422",
      "editorSuggestWidget.border": "#313936",
      "editorSuggestWidget.selectedBackground": "#26745B44",
      "editorGutter.background": "#171B1A",
    },
  });
}

function mapMonacoLang(dialect?: SqlDialect): string {
  if (dialect === "mysql") return "mysql";
  if (dialect === "postgresql") return "pgsql";
  return "sql";
}

function formatDialectLabel(dialect: SqlDialect): string {
  if (dialect === "postgresql") return "PostgreSQL";
  if (dialect === "mysql") return "MySQL";
  if (dialect === "sqlite") return "SQLite";
  return "SQL Server";
}

export function MonacoSqlEditor({
  value,
  onChange,
  dialect = "postgresql",
  readOnly = false,
  height = "280px",
  schemaTables = [],
  diagnostics = [],
  onExecuteShortcut,
  onFormat,
  expandable = true,
  label,
}: MonacoSqlEditorProps) {
  const [ready, setReady] = useState(monacoConfigured);
  const [expanded, setExpanded] = useState(false);
  const monacoRef = useRef<typeof MonacoTypes | null>(null);
  const editorRef = useRef<MonacoTypes.editor.IStandaloneCodeEditor | null>(null);
  const completionDisposableRef = useRef<MonacoTypes.IDisposable | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function initMonaco() {
      if (typeof window === "undefined") return;
      if (!(window as unknown as { MonacoEnvironment?: unknown }).MonacoEnvironment) {
        (window as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
          getWorker() {
            const blob = new Blob(["self.onmessage = function () {};"], {
              type: "application/javascript",
            });
            return new Worker(URL.createObjectURL(blob));
          },
        };
      }
      const monaco = await import("monaco-editor");
      if (cancelled) return;
      monacoRef.current = monaco;
      registerCharcoalMonacoTheme(monaco);
      if (!monacoConfigured) {
        loader.config({ monaco });
        monacoConfigured = true;
      }
      setReady(true);
    }
    void initMonaco();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const monaco = monacoRef.current;
    if (!ready || !monaco) return;

    completionDisposableRef.current?.dispose();
    const lang = mapMonacoLang(dialect);

    completionDisposableRef.current = monaco.languages.registerCompletionItemProvider(lang, {
      triggerCharacters: [".", " "],
      provideCompletionItems(model, position) {
        const word = model.getWordUntilPosition(position);
        const range: MonacoTypes.IRange = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        };
        const suggestions: MonacoTypes.languages.CompletionItem[] = [];
        for (const t of schemaTables) {
          suggestions.push({
            label: t.name,
            kind: monaco.languages.CompletionItemKind.Struct,
            insertText: t.name,
            detail: `Table (${t.columns.length} cols)`,
            range,
          });
          for (const col of t.columns) {
            suggestions.push({
              label: col.name,
              kind: monaco.languages.CompletionItemKind.Field,
              insertText: col.name,
              detail: `${t.name}.${col.name} (${col.data_type})`,
              range,
            });
            suggestions.push({
              label: `${t.name}.${col.name}`,
              kind: monaco.languages.CompletionItemKind.Property,
              insertText: `${t.name}.${col.name}`,
              detail: col.data_type,
              range,
            });
          }
        }
        return { suggestions };
      },
    });

    return () => {
      completionDisposableRef.current?.dispose();
    };
  }, [ready, dialect, schemaTables]);

  useEffect(() => {
    const monaco = monacoRef.current;
    const ed = editorRef.current;
    if (!ready || !monaco || !ed) return;
    const model = ed.getModel();
    if (!model) return;

    const markers: MonacoTypes.editor.IMarkerData[] = diagnostics
      .filter((d) => d.message)
      .map((d) => {
        const line = Math.max(1, Math.min(d.line || 1, model.getLineCount()));
        const maxCol = model.getLineMaxColumn(line);
        const startCol = Math.max(1, Math.min(d.column || 1, maxCol));
        const sev =
          d.severity === "error"
            ? monaco.MarkerSeverity.Error
            : d.severity === "warning"
            ? monaco.MarkerSeverity.Warning
            : monaco.MarkerSeverity.Info;
        return {
          startLineNumber: line,
          endLineNumber: line,
          startColumn: startCol,
          endColumn: maxCol,
          message: d.message,
          severity: sev,
        };
      });

    monaco.editor.setModelMarkers(model, "querytrellis", markers);
  }, [ready, diagnostics, value]);

  const monacoLanguage = useMemo(() => mapMonacoLang(dialect), [dialect]);
  const editorHeight = expanded ? "76vh" : height;

  return (
    <div
      className={
        expanded
          ? "fixed inset-5 z-50 flex flex-col overflow-hidden rounded-lg border border-[#323A36] bg-[#171B1A] shadow-2xl"
          : "flex flex-col overflow-hidden rounded-lg border border-[#2C3330] bg-[#171B1A]"
      }
    >
      <div className="flex items-center justify-between border-b border-[#282F2C] bg-[#1E2321] px-3.5 py-2 text-xs">
        <div className="flex items-center gap-2.5 text-[#C8CFCB]">
          <span className="font-medium text-[#ECEFEB]">{label || "SQL Editor"}</span>
          <span className="rounded border border-[#343C39] bg-[#171B1A] px-2 py-0.5 text-[11px] text-[#9EB2A8]">
            {formatDialectLabel(dialect)}
          </span>
          {readOnly && (
            <span className="rounded border border-[#343C39] bg-[#171B1A] px-2 py-0.5 text-[11px] text-[#8E9691]">
              Read-only
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {onFormat && !readOnly && (
            <button
              type="button"
              onClick={onFormat}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11.5px] font-medium text-[#B8C2BD] hover:bg-[#2A312E] hover:text-[#ECEFEB] transition-colors"
            >
              <Sparkles className="h-3 w-3" />
              Format
            </button>
          )}
          {expandable && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              title={expanded ? "Restore size" : "Expand editor"}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11.5px] font-medium text-[#B8C2BD] hover:bg-[#2A312E] hover:text-[#ECEFEB] transition-colors"
            >
              {expanded ? (
                <>
                  <Minimize2 className="h-3 w-3" /> Collapse
                </>
              ) : (
                <>
                  <Maximize2 className="h-3 w-3" /> Expand
                </>
              )}
            </button>
          )}
        </div>
      </div>

      <div style={{ height: editorHeight }} className="w-full min-h-[140px]">
        {ready ? (
          <Editor
            height="100%"
            language={monacoLanguage}
            theme="qt-charcoal"
            value={value}
            onChange={(v) => onChange?.(v ?? "")}
            onMount={(ed, monaco) => {
              editorRef.current = ed;
              monacoRef.current = monaco as unknown as typeof MonacoTypes;
              registerCharcoalMonacoTheme(monaco as unknown as typeof MonacoTypes);
              monaco.editor.setTheme("qt-charcoal");
              if (onExecuteShortcut) {
                ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
                  onExecuteShortcut();
                });
              }
            }}
            options={{
              readOnly,
              minimap: { enabled: false },
              fontSize: 13,
              lineHeight: 22,
              fontFamily: "JetBrains Mono, Cascadia Mono, Consolas, monospace",
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              automaticLayout: true,
              wordWrap: "on",
              tabSize: 2,
              padding: { top: 12, bottom: 12 },
              renderLineHighlight: "line",
              quickSuggestions: !readOnly,
            }}
          />
        ) : (
          <textarea
            value={value}
            readOnly={readOnly}
            onChange={(e) => onChange?.(e.target.value)}
            className="h-full w-full resize-none border-0 bg-[#171B1A] p-3.5 font-mono text-[13px] leading-relaxed text-[#ECEFEB] focus:outline-none"
          />
        )}
      </div>
    </div>
  );
}
