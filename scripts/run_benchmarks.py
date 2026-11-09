"""CLI benchmark and before/after optimization demo runner for QueryTrellis."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.benchmark.comparator import QuerySnapshot, compare_queries
from src.benchmark.runner import run_query_benchmark
from src.config.settings import load_settings
from src.db.connection_manager import ConnectionManager
from src.services.workbench_service import analyze_query_end_to_end
from src.sql_analysis.sample_queries import SAMPLE_QUERIES


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QueryTrellis before/after SQL benchmark pairs.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    settings = load_settings()
    cfg = settings.connection
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port
    if args.user:
        cfg.username = args.user
    if args.password is not None:
        cfg.password = args.password
    if args.database:
        cfg.database = args.database

    mgr = ConnectionManager(cfg)
    status = mgr.connect(cfg)
    if not status.connected:
        print(f"[ERROR] {status.error_message}", file=sys.stderr)
        return 1

    try:
        pairs = [s for s in SAMPLE_QUERIES if s.suggested_optimization]
        results = []
        for pair in pairs:
            print(f"\n=== {pair.title} ===")
            b_bundle = analyze_query_end_to_end(pair.sql, conn_manager=mgr, persist=False)
            b_bench = run_query_benchmark(mgr.get_connection(), pair.sql, label="Baseline", repeat_count=args.repeats, include_warmup=True)

            o_sql = pair.suggested_optimization or pair.sql
            o_bundle = analyze_query_end_to_end(o_sql, conn_manager=mgr, persist=False)
            o_bench = run_query_benchmark(mgr.get_connection(), o_sql, label="Optimized", repeat_count=args.repeats, include_warmup=True)

            cmp = compare_queries(
                QuerySnapshot("Baseline", pair.sql, plan=b_bundle.parsed_plan, benchmark=b_bench, antipatterns=b_bundle.antipatterns),
                QuerySnapshot("Optimized", o_sql, plan=o_bundle.parsed_plan, benchmark=o_bench, antipatterns=o_bundle.antipatterns),
            )
            print(f"Verdict: {cmp.verdict} | {cmp.verdict_summary}")
            print(f"Baseline: {cmp.baseline_time_ms} ms (Cost {cmp.baseline_cost}) | Optimized: {cmp.optimized_time_ms} ms (Cost {cmp.optimized_cost})")
            print(f"Resolved Anti-patterns: {cmp.resolved_antipatterns}")
            results.append(cmp.to_dict())

        out_dir = PROJECT_ROOT / "reports_examples"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "benchmark_comparisons.json"
        out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n[OK] Saved benchmark comparison output to {out_file}")
        return 0
    finally:
        mgr.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
