"""Curriculum definitions for all 21 Visual SQL Academy lessons & interactive exercises."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AcademyExercise:
    """Hands-on SQL challenge bundled with progressive hints & verified solution."""

    exercise_id: str
    prompt: str
    starter_sql: str
    solution_sql: str
    order_sensitive: bool
    is_dml: bool = False
    target_verify_table: str | None = None
    hints: tuple[str, ...] = ()
    step_by_step_solution: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcademyLesson:
    """Single interactive SQL concept lesson in progression order."""

    lesson_id: str
    order: int
    title: str
    concept: str
    tier: str  # Beginner | Intermediate | Advanced | Storage & DML
    summary: str
    key_rule: str
    lesson_sql: str
    exercise: AcademyExercise
    secondary_sql: str | None = None


ACADEMY_LESSONS: tuple[AcademyLesson, ...] = (
    AcademyLesson(
        lesson_id="select",
        order=1,
        title="SELECT — Column Projection & Expressions",
        concept="SELECT",
        tier="Beginner",
        summary="SELECT picks which columns or calculated expressions appear in your final output table without altering stored data.",
        key_rule="List explicit columns instead of SELECT * to keep projections lean and clear.",
        lesson_sql="SELECT emp_name, role, salary, ROUND(salary * 1.10, 2) AS projected_salary\nFROM staff;",
        exercise=AcademyExercise(
            exercise_id="ex_select",
            prompt="Select `emp_name`, `role`, and `salary` from `staff`.",
            starter_sql="SELECT emp_name, role\nFROM staff;",
            solution_sql="SELECT emp_name, role, salary FROM staff;",
            order_sensitive=False,
            hints=("Include `salary` as the third projected column after `role`.",),
            step_by_step_solution=(
                "1. Start with `SELECT emp_name, role, salary`.",
                "2. Read rows with `FROM staff;`.",
            ),
        ),
    ),
    AcademyLesson(
        lesson_id="from",
        order=2,
        title="FROM — Choosing the Base Table",
        concept="FROM",
        tier="Beginner",
        summary="SQL engines logically start execution at FROM to load candidate rows before any filtering or projection happens.",
        key_rule="FROM defines the initial row stream and table aliases.",
        lesson_sql="SELECT dept_id, dept_name, office\nFROM teams;",
        exercise=AcademyExercise(
            exercise_id="ex_from",
            prompt="Retrieve all columns (`dept_id`, `dept_name`, `office`) from the `teams` table.",
            starter_sql="SELECT dept_id, dept_name, office\nFROM ;",
            solution_sql="SELECT dept_id, dept_name, office FROM teams;",
            order_sensitive=False,
            hints=("Specify `teams` after `FROM`.",),
            step_by_step_solution=("1. Load rows from `teams` using `FROM teams`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="where",
        order=3,
        title="WHERE — Filtering Individual Rows",
        concept="WHERE",
        tier="Beginner",
        summary="WHERE evaluates each row independently and keeps only rows where the boolean predicate evaluates to TRUE (discarding FALSE and NULL).",
        key_rule="WHERE runs BEFORE grouping, aggregation, and SELECT aliases.",
        lesson_sql="SELECT emp_name, dept_id, salary\nFROM staff\nWHERE salary >= 80000;",
        exercise=AcademyExercise(
            exercise_id="ex_where",
            prompt="Return `emp_name` and `salary` for `staff` members earning strictly more than `75000`.",
            starter_sql="SELECT emp_name, salary\nFROM staff\nWHERE salary > 0;",
            solution_sql="SELECT emp_name, salary FROM staff WHERE salary > 75000;",
            order_sensitive=False,
            hints=("Replace `0` with `75000` in the `WHERE` predicate.",),
            step_by_step_solution=(
                "1. Read rows from `staff`.",
                "2. Keep only rows matching `WHERE salary > 75000`.",
            ),
        ),
    ),
    AcademyLesson(
        lesson_id="order_by",
        order=4,
        title="ORDER BY — Sorting Query Results",
        concept="ORDER BY",
        tier="Beginner",
        summary="ORDER BY sorts rows after projections are formed. Without ORDER BY, table row order is never guaranteed.",
        key_rule="Combine primary DESC/ASC keys with a tie-breaker column for deterministic sorting.",
        lesson_sql="SELECT emp_name, role, salary\nFROM staff\nORDER BY salary DESC, emp_name ASC;",
        exercise=AcademyExercise(
            exercise_id="ex_order_by",
            prompt="List `emp_name` and `salary` from `staff` sorted from highest salary to lowest salary.",
            starter_sql="SELECT emp_name, salary\nFROM staff\nORDER BY salary ASC;",
            solution_sql="SELECT emp_name, salary FROM staff ORDER BY salary DESC;",
            order_sensitive=True,
            hints=("Use `DESC` after `ORDER BY salary`.",),
            step_by_step_solution=("1. Project `emp_name, salary` and append `ORDER BY salary DESC`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="limit",
        order=5,
        title="LIMIT — Returning Top-N Rows",
        concept="LIMIT",
        tier="Beginner",
        summary="LIMIT slices the final ordered stream to at most N rows.",
        key_rule="Always pair LIMIT with ORDER BY when asking for 'top' or 'first' records.",
        lesson_sql="SELECT emp_name, role, salary\nFROM staff\nORDER BY salary DESC\nLIMIT 3;",
        exercise=AcademyExercise(
            exercise_id="ex_limit",
            prompt="Find the top 2 highest-paid staff members (`emp_name`, `salary`).",
            starter_sql="SELECT emp_name, salary\nFROM staff\nORDER BY salary DESC\nLIMIT 5;",
            solution_sql="SELECT emp_name, salary FROM staff ORDER BY salary DESC LIMIT 2;",
            order_sensitive=True,
            hints=("Sort descending by `salary` and set `LIMIT 2`.",),
            step_by_step_solution=("1. `ORDER BY salary DESC`.", "2. Truncate to `LIMIT 2`."),
        ),
    ),
    AcademyLesson(
        lesson_id="distinct",
        order=6,
        title="DISTINCT — Removing Duplicate Values",
        concept="DISTINCT",
        tier="Beginner",
        summary="DISTINCT collapses identical projected row combinations into unique tuples.",
        key_rule="Applies across the entire projected column tuple, not just the first column.",
        lesson_sql="SELECT DISTINCT role\nFROM staff\nORDER BY role;",
        exercise=AcademyExercise(
            exercise_id="ex_distinct",
            prompt="List each unique `region` appearing in `deals`, sorted alphabetically.",
            starter_sql="SELECT region\nFROM deals\nORDER BY region;",
            solution_sql="SELECT DISTINCT region FROM deals ORDER BY region;",
            order_sensitive=True,
            hints=("Insert `DISTINCT` right after `SELECT`.",),
            step_by_step_solution=("1. Use `SELECT DISTINCT region FROM deals ORDER BY region`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="aggregates",
        order=7,
        title="Aggregate Functions — Collapsing Rows Into Metrics",
        concept="Aggregate Functions",
        tier="Beginner",
        summary="COUNT, SUM, AVG, MIN, and MAX summarize multiple input rows. COUNT(*) counts rows while COUNT(col) skips NULLs.",
        key_rule="Notice `bonus` contains NULLs — `COUNT(*)` differs from `COUNT(bonus)`!",
        lesson_sql="SELECT COUNT(*) AS total_staff, COUNT(bonus) AS with_bonus, ROUND(AVG(salary), 2) AS avg_salary, SUM(salary) AS payroll\nFROM staff;",
        exercise=AcademyExercise(
            exercise_id="ex_aggregates",
            prompt="Calculate total deal value as `total_amount` and count of deals as `deal_count` across `deals`.",
            starter_sql="SELECT SUM(amount) AS total_amount\nFROM deals;",
            solution_sql="SELECT SUM(amount) AS total_amount, COUNT(*) AS deal_count FROM deals;",
            order_sensitive=False,
            hints=("Add `COUNT(*) AS deal_count` alongside `SUM(amount)`.",),
            step_by_step_solution=("1. Aggregate `deals` with `SUM(amount)` and `COUNT(*)`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="group_by",
        order=8,
        title="GROUP BY — Partitioning Rows Into Buckets",
        concept="GROUP BY",
        tier="Intermediate",
        summary="GROUP BY assigns every surviving row into a bucket matching its grouping key(s), then evaluates aggregates per bucket.",
        key_rule="Every unaggregated column in SELECT must appear in GROUP BY.",
        lesson_sql="SELECT role, COUNT(*) AS staff_count, ROUND(AVG(salary), 2) AS avg_salary\nFROM staff\nGROUP BY role\nORDER BY avg_salary DESC;",
        exercise=AcademyExercise(
            exercise_id="ex_group_by",
            prompt="Calculate total `amount` per `region` from `deals` aliased as `region_sales`, ordered highest first.",
            starter_sql="SELECT region, SUM(amount) AS region_sales\nFROM deals;",
            solution_sql="SELECT region, SUM(amount) AS region_sales FROM deals GROUP BY region ORDER BY region_sales DESC;",
            order_sensitive=True,
            hints=("Add `GROUP BY region` and `ORDER BY region_sales DESC`.",),
            step_by_step_solution=(
                "1. Group `deals` rows by `region`.",
                "2. Compute `SUM(amount)` per region and sort descending.",
            ),
        ),
    ),
    AcademyLesson(
        lesson_id="having",
        order=9,
        title="HAVING — Filtering Aggregated Groups",
        concept="HAVING",
        tier="Intermediate",
        summary="WHERE filters rows BEFORE grouping; HAVING filters entire buckets AFTER GROUP BY and aggregate computation.",
        key_rule="Use WHERE for row-level predicates and HAVING for aggregate conditions like SUM(amount) > 50000.",
        lesson_sql="SELECT region, COUNT(*) AS deal_count, SUM(amount) AS region_revenue\nFROM deals\nGROUP BY region\nHAVING SUM(amount) >= 50000\nORDER BY region_revenue DESC;",
        exercise=AcademyExercise(
            exercise_id="ex_having",
            prompt="Find `emp_id` values in `deals` that closed more than 1 deal (`COUNT(*) > 1`), returning `emp_id` and `deal_count`.",
            starter_sql="SELECT emp_id, COUNT(*) AS deal_count\nFROM deals\nGROUP BY emp_id;",
            solution_sql="SELECT emp_id, COUNT(*) AS deal_count FROM deals GROUP BY emp_id HAVING COUNT(*) > 1;",
            order_sensitive=False,
            hints=("Add `HAVING COUNT(*) > 1` after `GROUP BY emp_id`.",),
            step_by_step_solution=(
                "1. Group `deals` by `emp_id`.",
                "2. Filter groups with `HAVING COUNT(*) > 1`.",
            ),
        ),
    ),
    AcademyLesson(
        lesson_id="inner_join",
        order=10,
        title="INNER JOIN — Matching Related Rows",
        concept="INNER JOIN",
        tier="Intermediate",
        summary="INNER JOIN compares pairs across left and right tables and keeps ONLY combinations matching the ON condition.",
        key_rule="Unmatched rows from either table (such as staff with NULL dept_id or empty Legal team) are dropped.",
        lesson_sql="SELECT s.emp_name, s.role, t.dept_name\nFROM staff s\nINNER JOIN teams t ON t.dept_id = s.dept_id\nORDER BY s.emp_id;",
        exercise=AcademyExercise(
            exercise_id="ex_inner_join",
            prompt="Join `deals` (`d`) with `staff` (`s`) on `emp_id` to show `d.deal_id`, `s.emp_name`, and `d.amount`.",
            starter_sql="SELECT d.deal_id, s.emp_name, d.amount\nFROM deals d\nINNER JOIN staff s ON ;",
            solution_sql="SELECT d.deal_id, s.emp_name, d.amount FROM deals d INNER JOIN staff s ON s.emp_id = d.emp_id;",
            order_sensitive=False,
            hints=("Match on `s.emp_id = d.emp_id`.",),
            step_by_step_solution=("1. Connect `deals d` to `staff s` via `ON s.emp_id = d.emp_id`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="left_join",
        order=11,
        title="LEFT JOIN — Preserving All Left Rows",
        concept="LEFT JOIN",
        tier="Intermediate",
        summary="LEFT JOIN keeps every row from the left table; when the right table has no match, right columns become NULL.",
        key_rule="Putting right-table filters in WHERE turns a LEFT JOIN back into an INNER JOIN — filter right-table rules in ON when keeping unmatched rows.",
        lesson_sql="SELECT s.emp_name, s.dept_id, t.dept_name\nFROM staff s\nLEFT JOIN teams t ON t.dept_id = s.dept_id\nORDER BY s.emp_id;",
        exercise=AcademyExercise(
            exercise_id="ex_left_join",
            prompt="Show ALL `teams` (`dept_name`) and total `staff` count as `member_count`, including empty teams (`0`).",
            starter_sql="SELECT t.dept_name, COUNT(s.emp_id) AS member_count\nFROM teams t;",
            solution_sql="SELECT t.dept_name, COUNT(s.emp_id) AS member_count FROM teams t LEFT JOIN staff s ON s.dept_id = t.dept_id GROUP BY t.dept_name;",
            order_sensitive=False,
            hints=("Use `LEFT JOIN staff s ON s.dept_id = t.dept_id` and count `s.emp_id` (not `*`, because NULL doesn't increment COUNT(col)!)."),
            step_by_step_solution=(
                "1. Start from `teams t` and `LEFT JOIN staff s ON s.dept_id = t.dept_id`.",
                "2. `COUNT(s.emp_id)` gives 0 for unmatched teams like `Legal`.",
            ),
        ),
    ),
    AcademyLesson(
        lesson_id="right_join",
        order=12,
        title="RIGHT JOIN — Preserving All Right Rows",
        concept="RIGHT JOIN",
        tier="Intermediate",
        summary="RIGHT JOIN mirrors LEFT JOIN by keeping all rows from the right table and padding missing left columns with NULL.",
        key_rule="Any team with zero members (`Legal`) stays visible on the right side with NULL `emp_name`.",
        lesson_sql="SELECT s.emp_name, t.dept_id, t.dept_name\nFROM staff s\nRIGHT JOIN teams t ON t.dept_id = s.dept_id\nORDER BY t.dept_id, s.emp_id;",
        exercise=AcademyExercise(
            exercise_id="ex_right_join",
            prompt="Using `RIGHT JOIN`, list `s.emp_name` and `t.dept_name` from `staff s RIGHT JOIN teams t` so empty teams appear.",
            starter_sql="SELECT s.emp_name, t.dept_name\nFROM staff s;",
            solution_sql="SELECT s.emp_name, t.dept_name FROM staff s RIGHT JOIN teams t ON t.dept_id = s.dept_id;",
            order_sensitive=False,
            hints=("Append `RIGHT JOIN teams t ON t.dept_id = s.dept_id`.",),
            step_by_step_solution=("1. Keep all right-side rows via `RIGHT JOIN teams t ON t.dept_id = s.dept_id`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="subqueries",
        order=13,
        title="Subqueries — Nested Query Evaluation",
        concept="Subqueries",
        tier="Intermediate",
        summary="A subquery executes an inner SELECT inside WHERE, FROM, or SELECT, feeding scalar values or lists into the outer query.",
        key_rule="Prefer uncorrelated scalar/set subqueries or CTEs over correlated per-row lookups on large tables.",
        lesson_sql="SELECT emp_name, role, salary\nFROM staff\nWHERE salary > (SELECT AVG(salary) FROM staff)\nORDER BY salary DESC;",
        exercise=AcademyExercise(
            exercise_id="ex_subqueries",
            prompt="Return `emp_name` from `staff` whose `emp_id` appears in `deals` with `amount >= 40000` using an `IN (SELECT ...)` subquery.",
            starter_sql="SELECT emp_name\nFROM staff\nWHERE emp_id IN ();",
            solution_sql="SELECT emp_name FROM staff WHERE emp_id IN (SELECT emp_id FROM deals WHERE amount >= 40000);",
            order_sensitive=False,
            hints=("Inside `IN (...)`, select `emp_id FROM deals WHERE amount >= 40000`.",),
            step_by_step_solution=("1. Inner query: `SELECT emp_id FROM deals WHERE amount >= 40000`.", "2. Filter `staff` with `WHERE emp_id IN (...)`."),
        ),
    ),
    AcademyLesson(
        lesson_id="cte",
        order=14,
        title="CTEs — Named Readable Query Steps (WITH)",
        concept="Common Table Expressions",
        tier="Intermediate",
        summary="WITH defines clean named temporary relations executed before the main query, eliminating deeply nested subqueries.",
        key_rule="Pre-aggregate heavy fact tables in a CTE before joining summary dimensions.",
        lesson_sql="WITH emp_deals AS (\n    SELECT emp_id, COUNT(*) AS deal_count, SUM(amount) AS total_sales\n    FROM deals\n    GROUP BY emp_id\n)\nSELECT s.emp_name, COALESCE(ed.deal_count, 0) AS deal_count, COALESCE(ed.total_sales, 0) AS total_sales\nFROM staff s\nLEFT JOIN emp_deals ed ON ed.emp_id = s.emp_id\nORDER BY total_sales DESC;",
        exercise=AcademyExercise(
            exercise_id="ex_cte",
            prompt="Write a CTE `regional_totals` with `(region, rev)` from `deals`, then select regions with `rev >= 50000`.",
            starter_sql="WITH regional_totals AS (\n    SELECT region, SUM(amount) AS rev\n    FROM deals\n    GROUP BY region\n)\nSELECT region, rev\nFROM regional_totals;",
            solution_sql="WITH regional_totals AS (SELECT region, SUM(amount) AS rev FROM deals GROUP BY region) SELECT region, rev FROM regional_totals WHERE rev >= 50000;",
            order_sensitive=False,
            hints=("Filter the CTE in the outer SELECT with `WHERE rev >= 50000`.",),
            step_by_step_solution=("1. Aggregate per `region` inside `regional_totals`.", "2. Apply `WHERE rev >= 50000` cleanly in outer `SELECT`."),
        ),
    ),
    AcademyLesson(
        lesson_id="case",
        order=15,
        title="CASE — Conditional Buckets & Logic",
        concept="CASE",
        tier="Intermediate",
        summary="CASE WHEN evaluates conditions sequentially from top to bottom and returns the matching expression value per row.",
        key_rule="Always include an ELSE fallback so non-matching rows don't silently become NULL.",
        lesson_sql="SELECT emp_name, salary,\n    CASE\n        WHEN salary >= 90000 THEN 'Senior Band'\n        WHEN salary >= 75000 THEN 'Mid Band'\n        ELSE 'Associate Band'\n    END AS salary_band\nFROM staff\nORDER BY salary DESC;",
        exercise=AcademyExercise(
            exercise_id="ex_case",
            prompt="Select `deal_id`, `amount`, and `deal_tier` (`'Large'` when `amount >= 40000` else `'Standard'`) from `deals`.",
            starter_sql="SELECT deal_id, amount,\n    CASE WHEN amount >= 40000 THEN 'Large' ELSE 'Standard' END AS deal_tier\nFROM deals;",
            solution_sql="SELECT deal_id, amount, CASE WHEN amount >= 40000 THEN 'Large' ELSE 'Standard' END AS deal_tier FROM deals;",
            order_sensitive=False,
            hints=("Ensure column alias matches `deal_tier`.",),
            step_by_step_solution=("1. Classify each deal row inline using `CASE WHEN ... THEN ... ELSE ... END AS deal_tier`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="window_functions",
        order=16,
        title="Window Functions — Ranking & Running Totals Without Collapsing Rows",
        concept="Window Functions",
        tier="Advanced",
        summary="Unlike GROUP BY, window functions (`OVER (PARTITION BY ... ORDER BY ...)`) compute rankings or totals across peer rows while preserving every input row.",
        key_rule="DENSE_RANK() assigns identical ranks to ties without skipping numbers; AVG() OVER compares each row against its partition average.",
        lesson_sql="SELECT emp_name, dept_id, salary,\n    ROUND(AVG(salary) OVER (PARTITION BY dept_id), 2) AS dept_avg_salary,\n    DENSE_RANK() OVER (PARTITION BY dept_id ORDER BY salary DESC) AS dept_rank\nFROM staff\nWHERE dept_id IS NOT NULL\nORDER BY dept_id, dept_rank;",
        exercise=AcademyExercise(
            exercise_id="ex_window",
            prompt="Return `emp_name`, `salary`, and overall `RANK() OVER (ORDER BY salary DESC) AS salary_rank` from `staff`.",
            starter_sql="SELECT emp_name, salary,\n    RANK() OVER (ORDER BY salary DESC) AS salary_rank\nFROM staff;",
            solution_sql="SELECT emp_name, salary, RANK() OVER (ORDER BY salary DESC) AS salary_rank FROM staff;",
            order_sensitive=False,
            hints=("Use `RANK() OVER (ORDER BY salary DESC) AS salary_rank`.",),
            step_by_step_solution=("1. Compute `RANK()` across all `staff` ordered by `salary DESC` without `GROUP BY`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="union",
        order=17,
        title="UNION vs UNION ALL — Combining Result Sets",
        concept="UNION",
        tier="Intermediate",
        summary="UNION stacks rows vertically and removes duplicates; UNION ALL retains all rows without paying a deduplication sort/hash cost.",
        key_rule="Prefer UNION ALL whenever sets are known to be disjoint or duplicates should remain.",
        lesson_sql="SELECT emp_name AS contact_name, 'Staff' AS source_list FROM staff WHERE dept_id = 1\nUNION\nSELECT lead_name AS contact_name, 'Archive' AS source_list FROM leads_archive;",
        secondary_sql="SELECT emp_name AS contact_name FROM staff WHERE dept_id = 1\nUNION\nSELECT lead_name AS contact_name FROM leads_archive;",
        exercise=AcademyExercise(
            exercise_id="ex_union",
            prompt="Combine unique `region` names from `deals` and `leads_archive` using `UNION` ordered alphabetically.",
            starter_sql="SELECT region FROM deals\nUNION\nSELECT region FROM leads_archive\nORDER BY region;",
            solution_sql="SELECT region FROM deals UNION SELECT region FROM leads_archive ORDER BY region;",
            order_sensitive=True,
            hints=("Stack both `SELECT region` queries with `UNION` and sort at the end with `ORDER BY region`.",),
            step_by_step_solution=("1. `UNION` merges both region lists and removes duplicates cleanly.",),
        ),
    ),
    AcademyLesson(
        lesson_id="insert",
        order=18,
        title="INSERT — Adding Rows Safely",
        concept="INSERT",
        tier="Storage & DML",
        summary="INSERT adds explicit column-mapped tuples into a table inside an isolated sandbox state.",
        key_rule="Always specify explicit column names inside `INSERT INTO tbl (col1, col2)` so schema changes never misalign columns.",
        lesson_sql="INSERT INTO teams (dept_id, dept_name, office) VALUES (5, 'Customer Success', 'Bengaluru');",
        exercise=AcademyExercise(
            exercise_id="ex_insert",
            prompt="Insert a new team `(5, 'Security', 'Austin')` into `teams`.",
            starter_sql="INSERT INTO teams (dept_id, dept_name, office)\nVALUES (5, 'Security', 'Austin');",
            solution_sql="INSERT INTO teams (dept_id, dept_name, office) VALUES (5, 'Security', 'Austin');",
            order_sensitive=False,
            is_dml=True,
            target_verify_table="teams",
            hints=("Map `(dept_id, dept_name, office)` to `(5, 'Security', 'Austin')`.",),
            step_by_step_solution=("1. Run `INSERT INTO teams (dept_id, dept_name, office) VALUES (5, 'Security', 'Austin');` inside the isolated sandbox.",),
        ),
    ),
    AcademyLesson(
        lesson_id="update",
        order=19,
        title="UPDATE — Modifying Matched Rows",
        concept="UPDATE",
        tier="Storage & DML",
        summary="UPDATE locates rows matching WHERE and rewrites only target columns. Omitting WHERE mutates every row!",
        key_rule="Preview the exact WHERE filter as a SELECT first before executing an UPDATE in production.",
        lesson_sql="UPDATE staff\nSET bonus = 5000\nWHERE dept_id = 1;",
        exercise=AcademyExercise(
            exercise_id="ex_update",
            prompt="Update `staff` to set `salary = 95000` ONLY where `emp_id = 2`.",
            starter_sql="UPDATE staff\nSET salary = 95000\nWHERE emp_id = 2;",
            solution_sql="UPDATE staff SET salary = 95000 WHERE emp_id = 2;",
            order_sensitive=False,
            is_dml=True,
            target_verify_table="staff",
            hints=("Include `WHERE emp_id = 2` so only one row changes.",),
            step_by_step_solution=("1. Filter precisely with `WHERE emp_id = 2` and update `salary = 95000`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="delete",
        order=20,
        title="DELETE — Removing Specific Rows",
        concept="DELETE",
        tier="Storage & DML",
        summary="DELETE removes rows matching WHERE from the table. Missing WHERE deletes all rows in the table!",
        key_rule="Inspect dependent foreign-key references before deleting parent records.",
        lesson_sql="DELETE FROM leads_archive\nWHERE region = 'Europe West';",
        exercise=AcademyExercise(
            exercise_id="ex_delete",
            prompt="Delete only the row in `teams` where `dept_id = 4`.",
            starter_sql="DELETE FROM teams\nWHERE dept_id = 4;",
            solution_sql="DELETE FROM teams WHERE dept_id = 4;",
            order_sensitive=False,
            is_dml=True,
            target_verify_table="teams",
            hints=("Specify `WHERE dept_id = 4` cleanly.",),
            step_by_step_solution=("1. Verify `dept_id = 4` has no child rows and execute `DELETE FROM teams WHERE dept_id = 4;`.",),
        ),
    ),
    AcademyLesson(
        lesson_id="index_fundamentals",
        order=21,
        title="Index Fundamentals — Sequential Scan vs B-Tree Seek",
        concept="Index Fundamentals",
        tier="Storage & DML",
        summary="Without an index, finding `emp_id = 7` scans rows sequentially (O(N)); a B-tree index navigates sorted keys in logarithmic hops (O(log N)).",
        key_rule="B-trees accelerate selective sargable filters (`=`, `>`, `<`, `BETWEEN`, `LIKE 'abc%'`), while non-sargable wrappers like `LOWER(col)` defeat B-tree seeks.",
        lesson_sql="SELECT emp_id, emp_name, role, salary\nFROM staff\nWHERE emp_id = 7;",
        exercise=AcademyExercise(
            exercise_id="ex_index",
            prompt="Write a sargable equality query selecting `emp_name, salary` from `staff` where `emp_id = 5` (no functions around `emp_id`).",
            starter_sql="SELECT emp_name, salary\nFROM staff\nWHERE emp_id = 5;",
            solution_sql="SELECT emp_name, salary FROM staff WHERE emp_id = 5;",
            order_sensitive=False,
            hints=("Filter directly with `WHERE emp_id = 5` rather than `WHERE emp_id + 0 = 5`.",),
            step_by_step_solution=("1. Keep the indexed column bare on one side: `WHERE emp_id = 5`.",),
        ),
    ),
)


def list_lessons_summary() -> list[dict[str, Any]]:
    return [
        {
            "lesson_id": l.lesson_id,
            "order": l.order,
            "title": l.title,
            "concept": l.concept,
            "tier": l.tier,
            "summary": l.summary,
            "key_rule": l.key_rule,
        }
        for l in ACADEMY_LESSONS
    ]


def get_lesson_by_id(lesson_id: str) -> AcademyLesson | None:
    target = (lesson_id or "").strip().lower()
    for l in ACADEMY_LESSONS:
        if l.lesson_id.lower() == target:
            return l
    return None
