"""Schema-grounded ambiguity & missing-entity detector for natural-language SQL requests."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.context.models import DatabaseContextSnapshot


@dataclass(slots=True)
class AmbiguityAssessment:
    """Result of inspecting a user request against the active database schema."""

    status: str  # clear | clarification_required | missing_schema
    question: str = ""
    interpretations: list[dict[str, str]] = field(default_factory=list)
    missing_entities: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "question": self.question,
            "interpretations": self.interpretations,
            "missing_entities": self.missing_entities,
            "notes": self.notes,
        }


_STOP_WORDS = frozenset(
    {
        "show", "me", "the", "top", "best", "worst", "all", "list", "find", "get",
        "calculate", "compute", "count", "sum", "average", "avg", "total", "monthly",
        "yearly", "daily", "weekly", "for", "each", "by", "per", "with", "whose",
        "who", "where", "than", "more", "less", "above", "below", "between", "from",
        "in", "on", "of", "and", "or", "to", "a", "an", "is", "are", "this", "last",
        "previous", "current", "month", "year", "quarter", "day", "performing",
        "performance", "declining", "growing", "increasing", "running", "duplicate",
        "records", "rows", "times", "compare", "vs", "versus", "identify", "using",
        "group", "order", "sort", "limit", "filter", "metric", "revenue", "sales",
        "profit", "target", "achievement", "percentage", "rate", "number", "amount",
        "give", "return", "fetch", "select", "query", "records", "entries", "having",
    }
)


def _schema_vocabulary(context: DatabaseContextSnapshot) -> set[str]:
    vocab: set[str] = set()
    for tbl in context.tables:
        t_parts = tbl.name.lower().split("_")
        vocab.add(tbl.name.lower())
        vocab.update(t_parts)
        for p in t_parts:
            if p.endswith("s") and len(p) > 3:
                vocab.add(p[:-1])
            else:
                vocab.add(p + "s")
        for col in tbl.columns:
            c_parts = col.name.lower().split("_")
            vocab.add(col.name.lower())
            vocab.update(c_parts)
    return vocab


def assess_request_clarity(
    user_request: str,
    context: DatabaseContextSnapshot,
    clarification_answer: str | None = None,
) -> AmbiguityAssessment:
    """Detect missing schema objects or genuine analytical ambiguity before generating SQL."""
    req = (user_request or "").strip()
    low = req.lower()
    vocab = _schema_vocabulary(context)

    if not context.tables:
        return AmbiguityAssessment(
            status="missing_schema",
            question="The active database context contains no tables. Upload a schema/dataset or connect a database in Database Manager.",
            missing_entities=["tables"],
        )

    # 1. Check domain entities clearly outside the active schema (e.g., flights, patients, stocks)
    known_domain_nouns = {
        "flight", "flights", "airport", "airline", "patient", "patients", "diagnosis",
        "hospital", "doctor", "doctors", "student", "students", "course", "courses",
        "hotel", "bookings", "room", "rooms", "vehicle", "vehicles", "sensor", "sensors",
        "shipment", "shipments", "employee", "employees", "department", "departments",
        "customer", "customers", "product", "products", "order", "orders", "region",
        "regions", "payment", "payments", "review", "reviews", "invoice", "invoices",
        "deal", "deals", "target", "targets",
    }
    words = [w for w in re.findall(r"[a-zA-Z_]+", low) if len(w) > 2]
    missing: list[str] = []
    for w in words:
        if w in known_domain_nouns and w not in vocab and (w.rstrip("s") not in vocab):
            missing.append(w)

    if missing:
        unique_missing = list(dict.fromkeys(missing))
        avail = ", ".join(context.all_table_names())
        return AmbiguityAssessment(
            status="missing_schema",
            question=(
                f"Your active database schema does not contain table(s) or columns for "
                f"{', '.join(unique_missing)}. Available tables in active schema: {avail}."
            ),
            missing_entities=unique_missing,
            notes=["Schema verification prevented fabricating nonexistent tables or columns."],
        )

    # If user already provided a clarification answer, proceed cleanly
    if clarification_answer and clarification_answer.strip():
        return AmbiguityAssessment(status="clear")

    # 2. Ambiguity: "performing" / "best" / "top performing" without explicit metric
    if any(k in low for k in ("performing", "performance", "best employee", "top employee", "top product")):
        has_metric_explicit = any(
            k in low
            for k in (
                "revenue generated",
                "total revenue",
                "number of sales",
                "order count",
                "profit generated",
                "profit",
                "target achievement",
                "quota",
                "salary",
            )
        )
        if not has_metric_explicit:
            interpretations: list[dict[str, str]] = []
            has_orders = context.find_table("orders") is not None or context.find_table("quarterly_deals") is not None
            emp_tbl = context.find_table("employees")
            prod_tbl = context.find_table("products")
            items_tbl = context.find_table("order_items")

            if has_orders:
                interpretations.append(
                    {
                        "id": "total_revenue",
                        "label": "Total revenue generated",
                        "detail": "Sum of completed/valid order totals (`SUM(total_amount)`)",
                    }
                )
                interpretations.append(
                    {
                        "id": "order_count",
                        "label": "Number of sales / orders",
                        "detail": "Count of orders closed (`COUNT(order_id)`)",
                    }
                )
            if has_orders and prod_tbl and prod_tbl.get_column("unit_cost") and items_tbl:
                interpretations.append(
                    {
                        "id": "profit_generated",
                        "label": "Profit generated",
                        "detail": "Gross profit (`SUM(line_total - quantity * products.unit_cost)`)",
                    }
                )
            if emp_tbl and emp_tbl.get_column("sales_target") and has_orders:
                interpretations.append(
                    {
                        "id": "target_achievement",
                        "label": "Target achievement percentage",
                        "detail": "Percentage of quota reached (`SUM(total_amount) * 100.0 / sales_target`)",
                    }
                )
            if not interpretations and emp_tbl and emp_tbl.get_column("base_salary"):
                interpretations.append(
                    {
                        "id": "base_salary",
                        "label": "Highest base compensation",
                        "detail": "Sorted by `base_salary DESC`",
                    }
                )

            if len(interpretations) >= 2:
                return AmbiguityAssessment(
                    status="clarification_required",
                    question="Which performance metric should I use?",
                    interpretations=interpretations,
                    notes=["All candidate interpretations are derived strictly from existing schema columns."],
                )

    # 3. Ambiguity: "declining sales" without comparison window
    if "declining" in low and not any(k in low for k in ("month over month", "previous month", "quarter", "2 month", "two month", "consecutive")):
        return AmbiguityAssessment(
            status="clarification_required",
            question="How should I define declining product sales?",
            interpretations=[
                {
                    "id": "latest_vs_prev_month",
                    "label": "Latest month dropped compared to previous month",
                    "detail": "Compares each product's latest full month revenue against the immediately preceding month using LAG()",
                },
                {
                    "id": "consecutive_decline",
                    "label": "Two consecutive months of declining revenue",
                    "detail": "Flags products where both of the latest 2 transitions had lower month-over-month revenue",
                },
                {
                    "id": "first_half_vs_second_half",
                    "label": "Second half of dataset period vs first half",
                    "detail": "Compares average monthly revenue between earlier and later months in the dataset",
                },
            ],
        )

    # 4. Ambiguity: "this month" when historical data might not match system wall-clock date
    if ("this month" in low or "current month" in low) and "latest month" not in low:
        return AmbiguityAssessment(
            status="clarification_required",
            question="Which reference period represents 'this month' for this database?",
            interpretations=[
                {
                    "id": "latest_dataset_month",
                    "label": "Latest month present in the database (recommended for historical/demo datasets)",
                    "detail": "Anchors comparison to MAX(DATE_TRUNC('month', order_date)) vs the preceding month",
                },
                {
                    "id": "calendar_current_month",
                    "label": "Current wall-clock calendar month (CURRENT_DATE)",
                    "detail": "Compares DATE_TRUNC('month', CURRENT_DATE) against previous calendar month",
                },
            ],
        )

    # 5. Ambiguity: "duplicate customer records"
    if "duplicate" in low and "customer" in low and not any(k in low for k in ("email", "name", "phone", "id")):
        return AmbiguityAssessment(
            status="clarification_required",
            question="Which attribute(s) define a duplicate customer record?",
            interpretations=[
                {
                    "id": "duplicate_email",
                    "label": "Duplicate email address",
                    "detail": "Groups by normalized LOWER(email) where COUNT(*) > 1",
                },
                {
                    "id": "duplicate_name_country",
                    "label": "Duplicate customer name & country",
                    "detail": "Groups by (customer_name, country) where COUNT(*) > 1",
                },
            ],
        )

    return AmbiguityAssessment(status="clear")
