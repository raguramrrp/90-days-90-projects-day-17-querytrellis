"""Multi-dialect query optimizer combining static rewrites, index advice, and EXPLAIN verification."""

from src.optimizer.engine import optimize_sql_query

__all__ = ["optimize_sql_query"]
