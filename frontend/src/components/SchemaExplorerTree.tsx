"use client";

import React, { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Database,
  Eye,
  GitBranch,
  KeyRound,
  Link2,
  Search,
  Table2,
} from "lucide-react";
import type { DatabaseContextSnapshot, TableSchema } from "@/lib/types";

interface SchemaExplorerTreeProps {
  context: DatabaseContextSnapshot | null;
  onInsertIdentifier?: (text: string) => void;
}

export function SchemaExplorerTree({ context, onInsertIdentifier }: SchemaExplorerTreeProps) {
  const [search, setSearch] = useState("");
  const [expandedTables, setExpandedTables] = useState<Record<string, boolean>>({});
  const [sampleTable, setSampleTable] = useState<string | null>(null);

  const tables = context?.tables || [];
  const relationships = context?.relationships || [];

  const filteredTables = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return tables;
    return tables.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.columns.some((c) => c.name.toLowerCase().includes(q))
    );
  }, [tables, search]);

  const isExpanded = (t: TableSchema, idx: number) => {
    if (expandedTables[t.name] !== undefined) return expandedTables[t.name];
    return idx < 2 || Boolean(search.trim());
  };

  if (!context) {
    return (
      <div className="p-4 text-xs text-[var(--text-muted)]">
        Inspecting active database schema...
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-white text-xs">
      <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-subtle)] px-3.5 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0 flex-1 flex items-center gap-1.5 font-semibold text-[var(--text-primary)]">
            <Database className="h-3.5 w-3.5 shrink-0 text-[var(--accent-primary)]" />
            <span className="truncate">{context.label}</span>
          </div>
          <span className="shrink-0 font-mono text-[11px] text-[var(--text-muted)]">
            {tables.length} tables
          </span>
        </div>
        <div className="relative mt-2.5">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter tables or columns..."
            className="w-full rounded-md border border-[var(--border-subtle)] bg-white py-1.5 pl-8 pr-2.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)] focus:outline-none"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto divide-y divide-[var(--border-subtle)]">
        {filteredTables.length === 0 ? (
          <div className="p-4 text-center text-xs text-[var(--text-muted)]">
            No tables match &ldquo;{search}&rdquo;.
          </div>
        ) : (
          filteredTables.map((tbl, idx) => {
            const open = isExpanded(tbl, idx);
            const showSample = sampleTable === tbl.name;
            return (
              <div key={tbl.name} className="bg-white">
                <div className="flex items-center justify-between gap-1 px-3 py-2 hover:bg-[var(--bg-subtle)]">
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedTables((prev) => ({ ...prev, [tbl.name]: !open }))
                    }
                    className="flex min-w-0 flex-1 items-center gap-1.5 text-left font-medium text-[var(--text-primary)] hover:text-[var(--accent-primary)] transition-colors"
                  >
                    {open ? (
                      <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
                    )}
                    <Table2 className="h-3.5 w-3.5 shrink-0 text-[var(--accent-primary)]" />
                    <span className="truncate font-mono text-[12px]">{tbl.name}</span>
                  </button>
                  <div className="flex shrink-0 items-center gap-1">
                    {tbl.row_count !== null && (
                      <span
                        title={
                          tbl.row_count_is_estimated
                            ? "Estimated table row count"
                            : "Exact row count"
                        }
                        className="font-mono text-[10.5px] text-[var(--text-muted)]"
                      >
                        {tbl.row_count_is_estimated ? "~" : ""}
                        {tbl.row_count}
                      </span>
                    )}
                    {onInsertIdentifier && (
                      <button
                        type="button"
                        onClick={() => onInsertIdentifier(tbl.name)}
                        title={`Insert ${tbl.name}`}
                        className="rounded border border-[var(--border-subtle)] bg-white px-1.5 py-0.5 font-mono text-[10.5px] text-[var(--text-secondary)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)]"
                      >
                        +
                      </button>
                    )}
                    {tbl.sample_rows.length > 0 && (
                      <button
                        type="button"
                        onClick={() =>
                          setSampleTable((prev) => (prev === tbl.name ? null : tbl.name))
                        }
                        title="Preview sample rows"
                        className={`rounded border p-1 transition-colors ${
                          showSample
                            ? "border-[var(--accent-primary)]/40 bg-[var(--accent-tint)] text-[var(--accent-primary)]"
                            : "border-transparent text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]"
                        }`}
                      >
                        <Eye className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                </div>

                {open && (
                  <div className="bg-[var(--bg-subtle)]/60 px-3 py-1.5 space-y-0.5 border-t border-[var(--border-subtle)]/70">
                    {tbl.columns.map((col) => (
                      <div
                        key={col.name}
                        className="flex items-center justify-between gap-2 rounded px-1.5 py-0.5 hover:bg-[var(--bg-hover)]"
                      >
                        <button
                          type="button"
                          onClick={() => onInsertIdentifier?.(`${tbl.name}.${col.name}`)}
                          disabled={!onInsertIdentifier}
                          className="flex min-w-0 items-center gap-1.5 text-left font-mono text-[11.5px] text-[var(--text-primary)] hover:text-[var(--accent-primary)] disabled:cursor-default"
                        >
                          {col.is_primary_key && (
                            <span title="Primary key">
                              <KeyRound className="h-3 w-3 shrink-0 text-[#9B6B16]" />
                            </span>
                          )}
                          {col.is_foreign_key && !col.is_primary_key && (
                            <span title="Foreign key">
                              <Link2 className="h-3 w-3 shrink-0 text-[var(--accent-primary)]" />
                            </span>
                          )}
                          <span className="truncate">{col.name}</span>
                        </button>
                        <div className="flex shrink-0 items-center gap-1.5 font-mono text-[10.5px] text-[var(--text-muted)]">
                          <span>{col.data_type}</span>
                          {!col.nullable && <span className="text-[10px]">not null</span>}
                        </div>
                      </div>
                    ))}

                    {showSample && tbl.sample_rows.length > 0 && (
                      <div className="my-1.5 rounded-md border border-[var(--border-subtle)] bg-white p-2">
                        <div className="mb-1 text-[11px] font-medium text-[var(--text-secondary)]">
                          Sample rows
                        </div>
                        <div className="max-h-32 overflow-auto">
                          <table className="w-full border-collapse font-mono text-[10.5px]">
                            <thead>
                              <tr className="border-b border-[var(--border-subtle)] text-left text-[var(--text-secondary)]">
                                {Object.keys(tbl.sample_rows[0] || {}).map((k) => (
                                  <th key={k} className="pr-2.5 pb-1 font-medium">
                                    {k}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {tbl.sample_rows.map((row, rIdx) => (
                                <tr
                                  key={rIdx}
                                  className="border-b border-[var(--border-subtle)]/50 last:border-0"
                                >
                                  {Object.keys(tbl.sample_rows[0] || {}).map((k) => (
                                    <td
                                      key={k}
                                      className="max-w-[115px] truncate pr-2.5 py-0.5 text-[var(--text-primary)]"
                                    >
                                      {row[k] === null || row[k] === undefined ? (
                                        <span className="italic text-[var(--text-muted)]">null</span>
                                      ) : (
                                        String(row[k])
                                      )}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}

        {relationships.length > 0 && (
          <div className="bg-[var(--bg-subtle)]/40 p-3 space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11.5px] font-semibold text-[var(--text-primary)]">
              <GitBranch className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
              <span>Foreign key relationships ({relationships.length})</span>
            </div>
            <div className="space-y-1">
              {relationships.map((rel, i) => (
                <div
                  key={`${rel.constraint_name}-${i}`}
                  className="font-mono text-[10.5px] text-[var(--text-secondary)] leading-snug"
                >
                  <span className="font-medium text-[var(--text-primary)]">
                    {rel.source_table}
                  </span>
                  .({rel.source_columns.join(", ")}) →{" "}
                  <span className="font-medium text-[var(--accent-primary)]">
                    {rel.target_table}
                  </span>
                  .({rel.target_columns.join(", ")})
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
