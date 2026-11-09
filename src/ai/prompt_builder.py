"""Schema-grounded prompt construction and external transmission privacy disclosures."""
from __future__ import annotations

import json
from typing import Any

from src.context.models import DatabaseContextSnapshot


def build_transmission_disclosure(
    context: DatabaseContextSnapshot,
    include_sample_rows: bool = False,
) -> dict[str, Any]:
    """Explain transparently what data would leave the local machine for external AI."""
    return {
        "will_send": [
            f"Target SQL dialect ({context.dialect})",
            f"Table & column schema names for {len(context.tables)} table(s)",
            f"{len(context.relationships)} declared foreign-key relationships",
            "Your natural-language request / SQL snippet under inspection",
        ]
        + (["Up to 2 sanitized sample rows per table"] if include_sample_rows else []),
        "never_sent": [
            "Database passwords or connection strings",
            "API keys or local user credentials",
            "Full table row datasets" if not include_sample_rows else "Bulk table rows beyond the 2-row sample preview",
        ],
    }


def build_nl2sql_messages(
    user_request: str,
    context: DatabaseContextSnapshot,
    clarification_answer: str | None = None,
    include_sample_rows: bool = False,
) -> list[dict[str, str]]:
    """Build strictly schema-grounded messages for external AI model APIs."""
    schema_text = context.schema_prompt_summary(include_samples=include_sample_rows)
    clarify_line = f"\nUser Clarification Selection: {clarification_answer}" if clarification_answer else ""

    system_prompt = (
        "You are a senior SQL database engineer. Generate valid, read-only SQL strictly using ONLY tables, "
        "columns, data types, and relationships defined in the provided schema.\n"
        "RULES:\n"
        "1. NEVER invent table names, column names, or foreign keys not listed in the schema.\n"
        "2. Use exact syntax for the requested Target SQL Dialect.\n"
        "3. If the user's request is ambiguous (e.g. 'performing', 'best', 'recent') and no clarification was provided, "
        "return status='clarification_required' with a short question and up to 4 schema-grounded choices.\n"
        "4. Return STRICT JSON only matching:\n"
        + json.dumps(
            {
                "status": "generated | clarification_required",
                "clarification_question": "optional string",
                "interpretations": ["optional list of strings"],
                "sql": "string",
                "explanation": "string",
                "assumptions": ["string"],
                "limitations": ["string"],
                "alternatives": [{"title": "string", "sql": "string", "reason": "string"}],
            }
        )
    )

    user_prompt = (
        f"{schema_text}\n\n"
        f"User Request: {user_request}{clarify_line}\n"
        "Respond strictly with valid JSON."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
