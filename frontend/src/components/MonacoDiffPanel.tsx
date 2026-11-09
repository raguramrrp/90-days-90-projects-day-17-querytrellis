"use client";

import React, { useEffect, useState } from "react";
import { DiffEditor, loader } from "@monaco-editor/react";
import type * as MonacoTypes from "monaco-editor";
import type { SqlDialect } from "@/lib/types";
import { registerCharcoalMonacoTheme } from "./MonacoSqlEditor";

interface MonacoDiffPanelProps {
  originalSql: string;
  modifiedSql: string;
  dialect?: SqlDialect;
  height?: string;
}

function mapLang(d?: SqlDialect): string {
  if (d === "mysql") return "mysql";
  if (d === "postgresql") return "pgsql";
  return "sql";
}

export function MonacoDiffPanel({
  originalSql,
  modifiedSql,
  dialect = "postgresql",
  height = "260px",
}: MonacoDiffPanelProps) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function init() {
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
      registerCharcoalMonacoTheme(monaco);
      loader.config({ monaco });
      setReady(true);
    }
    void init();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="overflow-hidden rounded-lg border border-[#2C3330] bg-[#171B1A]">
      <div className="grid grid-cols-2 border-b border-[#282F2C] bg-[#1E2321] px-3.5 py-2 text-xs font-medium text-[#C8CFCB]">
        <div>Original query</div>
        <div>Proposed fix</div>
      </div>
      <div style={{ height }} className="w-full min-h-[160px]">
        {ready ? (
          <DiffEditor
            height="100%"
            language={mapLang(dialect)}
            theme="qt-charcoal"
            original={originalSql}
            modified={modifiedSql}
            onMount={(_ed, monaco) => {
              registerCharcoalMonacoTheme(monaco as unknown as typeof MonacoTypes);
              monaco.editor.setTheme("qt-charcoal");
            }}
            options={{
              readOnly: true,
              renderSideBySide: true,
              minimap: { enabled: false },
              fontSize: 12.5,
              lineHeight: 20,
              fontFamily: "JetBrains Mono, Cascadia Mono, Consolas, monospace",
              scrollBeyondLastLine: false,
              automaticLayout: true,
              wordWrap: "on",
            }}
          />
        ) : (
          <div className="grid h-full grid-cols-2 divide-x divide-[#282F2C]">
            <pre className="m-0 overflow-auto p-3 font-mono text-xs text-[#A5AEA9]">
              {originalSql}
            </pre>
            <pre className="m-0 overflow-auto p-3 font-mono text-xs text-[#ECEFEB]">
              {modifiedSql}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
