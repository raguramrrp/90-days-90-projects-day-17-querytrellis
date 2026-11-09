"""Generate real HTML, JSON, and CSV optimization report examples in reports_examples/."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.benchmark.comparator import QuerySnapshot, compare_queries
from src.benchmark.runner import run_query_benchmark
from src.config.settings import load_settings
from src.db.connection_manager import ConnectionManager
from src.reporting.report_generator import (
    build_benchmark_csv,
    build_html_report,
    build_json_report,
    build_plan_nodes_csv,
)
from src.services.workbench_service import analyze_query_end_to_end
from src.sql_analysis.sample_queries import SAMPLE_QUERIES


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate QueryTrellis sample optimization reports.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--database", default=None)
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
        pair = SAMPLE_QUERIES[6]  # Correlated subquery vs CTE LEFT JOIN
        opt_sql = pair.suggested_optimization or pair.sql

        b_bundle = analyze_query_end_to_end(pair.sql, conn_manager=mgr, persist=False)
        b_bench = run_query_benchmark(
            mgr.get_connection(), pair.sql, label="Baseline (Correlated Subquery)", repeat_count=5, include_warmup=True
        )
        o_bundle = analyze_query_end_to_end(opt_sql, conn_manager=mgr, persist=False)
        o_bench = run_query_benchmark(
            mgr.get_connection(), opt_sql, label="Optimized (CTE LEFT JOIN)", repeat_count=5, include_warmup=True
        )
        cmp = compare_queries(
            QuerySnapshot("Baseline (Correlated Subquery)", pair.sql, plan=b_bundle.parsed_plan, benchmark=b_bench, antipatterns=b_bundle.antipatterns),
            QuerySnapshot("Optimized (CTE LEFT JOIN)", opt_sql, plan=o_bundle.parsed_plan, benchmark=o_bench, antipatterns=o_bundle.antipatterns),
        )

        out_dir = PROJECT_ROOT / "reports_examples"
        out_dir.mkdir(parents=True, exist_ok=True)

        html_out = build_html_report(
            title="Correlated Subquery vs. CTE LEFT JOIN — Sample Report",
            sql_text=pair.sql,
            formatted_sql=b_bundle.formatted_sql,
            connection_info=cfg,
            server_version=status.server_version,
            plan=b_bundle.parsed_plan,
            plan_insights=b_bundle.plan_insights,
            antipatterns=b_bundle.antipatterns,
            index_recommendations=b_bundle.index_recommendations,
            benchmark=b_bench,
            comparison=cmp,
            optimization_notes="Sample optimization report generated directly against querytrellis_sample.",
        )
        json_out = build_json_report(
            title="Correlated Subquery vs. CTE LEFT JOIN — Sample Report",
            sql_text=pair.sql,
            formatted_sql=b_bundle.formatted_sql,
            connection_info=cfg,
            server_version=status.server_version,
            plan=b_bundle.parsed_plan,
            plan_insights=b_bundle.plan_insights,
            antipatterns=b_bundle.antipatterns,
            index_recommendations=b_bundle.index_recommendations,
            benchmark=b_bench,
            comparison=cmp,
            optimization_notes="Sample optimization report generated directly against querytrellis_sample.",
        )

        (out_dir / "sample_optimization_report.html").write_text(html_out, encoding="utf-8")
        (out_dir / "sample_optimization_report.json").write_text(json_out, encoding="utf-8")
        (out_dir / "sample_benchmark_runs.csv").write_text(build_benchmark_csv(b_bench), encoding="utf-8")
        if b_bundle.parsed_plan:
            (out_dir / "sample_plan_nodes.csv").write_text(
                build_plan_nodes_csv(b_bundle.parsed_plan), encoding="utf-8"
            )
        print(f"[OK] Generated HTML, JSON, and CSV sample reports in {out_dir}")
        return 0
    finally:
        mgr.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
