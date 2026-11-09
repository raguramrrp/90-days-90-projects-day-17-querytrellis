# Project Overview — QueryTrellis

## Problem Statement

Developers and data analysts frequently write SQL queries that appear syntactically valid and fast on small development tables, yet degrade sharply in production due to missing foreign-key indexes, non-sargable predicates (functions on filtered columns), correlated subqueries, leading-wildcard `LIKE` patterns, disk-spilling sorts, or large `OFFSET` pagination. Reading raw PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` text output is steep for early-career engineers, while generic AI SQL assistants often fabricate timing guesses without inspecting real execution plans or `pg_catalog` index metadata.

## Project Goals

**QueryTrellis** is a local, zero-paid-API **PostgreSQL Query Performance & Optimization Workbench** designed to:

1. Provide a safe, AST-validated read-only PostgreSQL query workspace (`SET TRANSACTION READ ONLY`, `statement_timeout`, row caps).
2. Inspect and visualize real PostgreSQL `EXPLAIN` and `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` execution trees.
3. Detect common SQL anti-patterns with nuanced explanations (explicitly describing when a pattern is acceptable vs. harmful).
4. Recommend non-redundant B-tree, composite (ESR), covering (`INCLUDE`), and partial indexes backed by `pg_catalog` metadata and execution plan evidence — without ever automatically creating indexes.
5. Benchmark query performance across repeatable runs while separating client-observed duration from PostgreSQL planning/execution timing.
6. Support evidence-based before-and-after query comparisons and export sanitized HTML, JSON, and CSV optimization reports.

## Intended Users

- Backend & data engineers tuning PostgreSQL queries locally
- Computer science / AI & Data Science students learning query optimization and indexing
- QA and database reviewers auditing SQL regressions prior to deployment

## MVP Boundaries & Design Discipline

- **Read-Only Analysis Scope:** Default execution strictly allows single read-only `SELECT` (including CTEs and set operations). Write/DDL/DCL statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`) and locking clauses (`FOR UPDATE`) are blocked at both the AST layer and PostgreSQL transaction layer.
- **No Auto-DDL Execution:** Suggested `CREATE INDEX` statements are strictly advisory and copyable.
- **No Fabricated Telemetry:** Overview stats, plan timings, and comparisons display only verified PostgreSQL or SQLite-recorded values (marking unmeasured fields `Unavailable`).
- **100% Local & Open Source:** Zero external LLM APIs, cloud dependencies, or paid services.
