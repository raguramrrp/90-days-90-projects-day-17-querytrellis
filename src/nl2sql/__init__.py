"""Schema-aware natural language to SQL generation, ambiguity detection, and query explanation."""

from src.nl2sql.ambiguity import AmbiguityAssessment, assess_request_clarity
from src.nl2sql.explainer import explain_sql_query, verify_sql_against_schema
from src.nl2sql.generator import generate_sql_from_nl

__all__ = [
    "AmbiguityAssessment",
    "assess_request_clarity",
    "explain_sql_query",
    "generate_sql_from_nl",
    "verify_sql_against_schema",
]
