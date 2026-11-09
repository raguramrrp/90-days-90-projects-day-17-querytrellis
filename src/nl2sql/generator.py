"""Orchestrates Schema-Grounded NL-to-SQL generation, clarification, dialect transpilation, and verification."""
from __future__ import annotations

from typing import Any

from src.ai.external_client import generate_with_external_ai
from src.ai.prompt_builder import build_nl2sql_messages
from src.ai.provider_base import AIProviderConfig
from src.context.models import DatabaseContextSnapshot
from src.dialects.sqlglot_engine import convert_sql_dialect, normalize_dialect
from src.nl2sql.ambiguity import assess_request_clarity
from src.nl2sql.deterministic_planner import generate_deterministic_sql
from src.nl2sql.explainer import explain_sql_query, verify_sql_against_schema


def generate_sql_from_nl(
    user_request: str,
    context: DatabaseContextSnapshot,
    ai_config: AIProviderConfig,
    *,
    dialect: str | None = None,
    clarification_answer: str | None = None,
    force_provider: str | None = None,
) -> dict[str, Any]:
    """Generate schema-verified SQL in requested dialect or ask clarifying questions first."""
    target_dialect = normalize_dialect(dialect or context.dialect)
    clarity = assess_request_clarity(user_request, context, clarification_answer=clarification_answer)

    if clarity.status in {"clarification_required", "missing_schema"}:
        return {
            "status": clarity.status,
            "dialect": target_dialect,
            "question": clarity.question,
            "interpretations": clarity.interpretations,
            "missing_entities": clarity.missing_entities,
            "notes": clarity.notes,
            "provider_used": "schema_inspector",
        }

    provider_choice = (force_provider or ai_config.active_provider or "deterministic").lower()
    ai_used = "deterministic_schema_engine"
    ai_model = "Schema-Grounded AST Compiler"
    ai_error = ""
    offer_external = False
    raw_sql = ""
    explanation = ""
    assumptions: list[str] = []
    limitations: list[str] = []
    alternatives: list[dict[str, str]] = []

    if provider_choice == "external":
        msgs = build_nl2sql_messages(
            user_request,
            context,
            clarification_answer=clarification_answer,
            include_sample_rows=ai_config.include_sample_rows_in_external,
        )
        ai_res = generate_with_external_ai(msgs, ai_config)
        if ai_res.success and ai_res.parsed_json:
            p = ai_res.parsed_json
            if p.get("status") == "clarification_required" and p.get("clarification_question"):
                return {
                    "status": "clarification_required",
                    "dialect": target_dialect,
                    "question": str(p["clarification_question"]),
                    "interpretations": [
                        {"id": f"opt_{i}", "label": str(opt), "detail": ""}
                        for i, opt in enumerate(p.get("interpretations") or [])
                    ],
                    "provider_used": f"external:{ai_config.external_provider}",
                }
            candidate_sql = str(p.get("sql") or "").strip()
            ver = verify_sql_against_schema(candidate_sql, context, target_dialect)
            if candidate_sql and ver.is_valid_syntax and ver.schema_verified:
                raw_sql = candidate_sql
                ai_used = f"external:{ai_config.external_provider}"
                ai_model = ai_res.model_used
                explanation = str(p.get("explanation") or "")
                assumptions = [str(a) for a in (p.get("assumptions") or [])]
                limitations = [str(l) for l in (p.get("limitations") or [])]
                alternatives = list(p.get("alternatives") or [])
            else:
                ai_error = (
                    f"External model response failed strict schema/syntax verification "
                    f"({ver.error_message or ', '.join(ver.unknown_tables + ver.unknown_columns)})."
                )
        else:
            ai_error = ai_res.error_message
            if not ai_config.deterministic_fallback_enabled:
                return {
                    "status": "provider_error",
                    "dialect": target_dialect,
                    "error_message": ai_error,
                    "provider_used": f"external:{ai_config.external_provider}",
                    "offer_external_fallback": True,
                }

    # Primary Deterministic Schema AST Compiler (or resilient fallback on external API error)
    if not raw_sql:
        planned = generate_deterministic_sql(user_request, context, clarification_answer=clarification_answer)
        conv = convert_sql_dialect(planned.postgres_sql, "postgresql", target_dialect, pretty=True)
        raw_sql = conv.converted_sql if conv.success else planned.postgres_sql
        explanation = planned.explanation
        assumptions = planned.assumptions
        limitations = planned.limitations + conv.warnings + conv.limitations
        alternatives = []
        for alt in planned.alternatives:
            alt_conv = convert_sql_dialect(alt["sql"], "postgresql", target_dialect, pretty=True)
            alternatives.append(
                {
                    "title": alt["title"],
                    "sql": alt_conv.converted_sql if alt_conv.success else alt["sql"],
                    "reason": alt["reason"],
                }
            )
        if ai_error:
            assumptions.insert(0, f"Fallback notice: {ai_error}")

    expl_meta = explain_sql_query(raw_sql, context=context, dialect=target_dialect)
    return {
        "status": "generated",
        "dialect": target_dialect,
        "sql": raw_sql,
        "explanation": explanation or expl_meta["summary"],
        "clause_breakdown": expl_meta["steps"],
        "tables_used": expl_meta["tables_used"],
        "columns_used": expl_meta["columns_used"],
        "schema_verified": expl_meta["schema_verified"],
        "assumptions": assumptions,
        "limitations": limitations,
        "alternatives": alternatives,
        "illustrative_structure": expl_meta["illustrative_structure"],
        "provider_used": ai_used,
        "model_used": ai_model,
        "provider_warning": ai_error,
        "offer_external_fallback": offer_external,
    }
