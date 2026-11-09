"""Visual SQL Learning Academy: 21 interactive lessons, DuckDB stage tracer, and exercise checker."""

from src.academy.curriculum import ACADEMY_LESSONS, get_lesson_by_id, list_lessons_summary
from src.academy.exercise_evaluator import evaluate_academy_exercise
from src.academy.stage_tracer import trace_custom_select_query, trace_lesson_execution

__all__ = [
    "ACADEMY_LESSONS",
    "evaluate_academy_exercise",
    "get_lesson_by_id",
    "list_lessons_summary",
    "trace_custom_select_query",
    "trace_lesson_execution",
]
