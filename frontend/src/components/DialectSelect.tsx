"use client";

import React from "react";
import type { SqlDialect } from "@/lib/types";

interface DialectSelectProps {
  value: SqlDialect;
  onChange: (dialect: SqlDialect) => void;
  disabled?: boolean;
  compact?: boolean;
  label?: string;
}

const DIALECT_OPTIONS: { value: SqlDialect; label: string }[] = [
  { value: "postgresql", label: "PostgreSQL" },
  { value: "mysql", label: "MySQL" },
  { value: "sqlite", label: "SQLite" },
  { value: "sqlserver", label: "SQL Server" },
];

export function DialectSelect({
  value,
  onChange,
  disabled = false,
  compact = false,
  label,
}: DialectSelectProps) {
  return (
    <label className="inline-flex items-center gap-2 text-xs text-[var(--text-secondary)]">
      {label && <span className="font-medium text-[var(--text-secondary)]">{label}</span>}
      <select
        aria-label={label || "SQL Dialect"}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value as SqlDialect)}
        className={`rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] font-medium text-[var(--text-primary)] transition-colors hover:border-[#B6BCB4] focus:border-[var(--accent-primary)] focus:outline-none ${
          compact ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-[13px]"
        }`}
      >
        {DIALECT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
