#!/usr/bin/env python3
"""
SpiderSQL AdventureWorks CTU 100-question debug runner.

Database:
- AdventureWorks CTU: database_id 50

Run from the backend folder while FastAPI backend is running:
    cd C:\\Projects\\nl2sql-mvp\\backend
    python run_adventureworks_100_sql_debug_db50.py

It sends 100 normal natural-language questions to:
    POST /database/50/execute_sql

It saves the same detailed information that the original debug runner printed,
but saves it to one TXT file instead.

Terminal output:
- One PASS/FAIL progress line per question.

Saved output:
- One TXT file containing question, status, metadata, warnings, errors,
  generated SQL, and the final summary.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 50
DATABASE_NAME = "AdventureWorks CTU"
TIMEOUT_SECONDS = 120

QUESTIONS: List[str] = ['Find products that are still being sold, have a recorded color, and cost more than the average product in the same subcategory.', 'Find employees who were hired after 2008 and have more vacation hours than the average employee in their current department.', 'Find sales orders placed in 2013 whose total due is higher than the average total due for the same customer.', 'Find active preferred vendors whose credit rating is better than the average rating of all active vendors.', 'Find work orders whose scrap rate is higher than the average scrap rate for work orders involving the same product.', 'Find products whose list price is at least twice their standard cost and is also above the average list price for their category.', 'Find customers who placed orders in more than one sales territory and whose total spending is above the average customer total.', 'Find vendors whose purchase orders include at least one rejected item and whose total purchase value is above the vendor average.', 'Find employees whose latest pay rate is above both their previous pay rate and the average latest pay rate in their department.', 'Find stores whose assigned salesperson has year-to-date sales above the average for salespeople in the same territory.', 'Find products that have inventory in more than three locations but have never been sold to a customer.', 'Find customers who bought products from at least three different categories and spent more than 100000 dollars in total.', 'Find salespeople who manage more stores than the average salesperson and whose year-to-date sales exceed their quota.', 'Find vendors that supply more distinct products than the average vendor and have received more than twenty purchase orders.', 'Find departments whose current employee count is above the average department headcount and whose average pay rate is above the company average.', 'Find products that generated more revenue than the average product in the same category and were purchased by more than one hundred distinct customers.', 'Find customers whose largest order is more than twice their average order value.', 'Find vendors whose average purchase order value is higher than the average for vendors with the same credit rating.', 'Find employees whose vacation hours are above the average for employees hired in the same year.', 'Find sales territories whose total sales and average order value are both above the averages across all territories.', 'Find products whose current inventory is below the average inventory for products in the same category but whose sales revenue is above the category average.', 'Find customers whose lifetime spending is higher than the average spending of customers in the same territory.', 'Find vendors whose total purchase order value is higher than the average vendor total and whose latest purchase order was placed after 2012.', 'Find products that were sold in 2012 and 2013 but were not sold in 2011.', 'Find employees who are currently assigned to a department but have no pay-rate change recorded after 2010.', 'Find customers who have at least one order worth more than 20000 dollars but have never placed an order below 100 dollars.', 'Find vendors that have purchase orders but have never had any rejected quantity on their order lines.', 'Find products that are registered with a vendor but have never appeared on a purchase order.', 'Find salespeople who have assigned stores but have never been assigned to a sales order.', 'Find departments that currently have employees but have not hired anyone since 2010.', 'Find the ten customers with the highest lifetime spending and show their order count, average order value, and most recent order date.', 'Find the five highest-revenue products within each product category.', 'Find the three vendors with the greatest purchase order value within each credit rating.', "Find the highest-paid current employee in each department using each employee's latest pay rate.", 'Find the most recent sales order for every customer who has placed more than one order.', 'Find the most expensive product in each product subcategory.', 'Find the salesperson with the highest year-to-date sales in each territory.', 'Find the product with the largest total inventory quantity in each category.', 'Find the three customers with the highest lifetime spending in each sales territory.', 'Find the month with the highest total sales in each year.', 'Find products whose list price is higher than the average price of other products in the same subcategory.', 'Find sales orders whose total due is higher than the average order total for the same customer.', 'Find employees whose vacation hours are higher than the average vacation hours in their current department.', 'Find work orders whose scrap percentage is higher than the average scrap percentage for the same product.', 'Find purchase orders whose total due is higher than the average purchase order total for the same vendor.', 'Find salespeople whose year-to-date sales are above both their quota and the average sales of other salespeople in the same territory.', 'Find products whose total sales revenue is higher than the average revenue of products in the same category.', 'Find stores whose assigned salesperson has higher year-to-date sales than the average salesperson in that territory.', 'Find customers whose total spending increased from 2012 to 2013.', 'Find vendors whose total purchase order value decreased from 2012 to 2013.', 'Find products that have appeared in both customer sales and vendor purchase orders.', 'Find customers who placed orders in both 2012 and 2013.', 'Find people who are employees, salespeople, or both, showing each person only once.', 'Find products that were sold to customers but were never included in a purchase order.', 'Find vendors whose business entity IDs also appear as employee business entity IDs.', 'Find customers who placed an order in 2013 but did not place any order in 2012.', 'Find products that have inventory in both location 1 and location 6.', 'Find sales territories that have both customers and salespeople assigned to them.', 'Find people who have both an email address and a phone number.', 'Find product categories that contain products sold to customers and products ordered from vendors.', 'Classify products as budget, midrange, or premium based on list price, then show the average profit margin in each class.', 'Classify sales orders as small, medium, or large based on total due, then show the number of orders and total revenue in each class.', 'Classify inventory records as out of stock, low stock, normal stock, or high stock and count how many products fall into each class by location.', 'Classify employees as recently hired, experienced, or long-tenured and show the average latest pay rate for each group.', 'Classify vendors by active status, preferred status, and credit risk, then show total purchase value for each class.', 'Find sales order lines whose net revenue after discount is above the average net revenue for the same product.', 'Find products whose markup percentage is above the average markup percentage for their category.', 'Find work orders whose scrap rate is above the average scrap rate for their product and whose scrapped quantity is greater than ten.', 'Find salespeople whose quota attainment is above 100 percent and whose year-to-date sales improved over last year.', 'Find purchase order lines whose rejection percentage is worse than the average rejection percentage for the same vendor.', "Show monthly sales totals together with the previous month's total and the change from the previous month.", "Show yearly sales totals for each territory together with the previous year's total and percentage change.", 'Show a running total of daily sales order value ordered by date.', 'Show a running total of purchase order spending for each vendor over time.', 'Find the year in which each product category generated its highest sales revenue.', 'Find customers whose spending increased for at least two consecutive years.', "Find salespeople whose year-to-date sales are higher than last year's sales and also higher than their territory average.", 'Find products whose total quantity sold increased from 2012 to 2013.', 'Find vendors whose total purchase value declined from one year to the next.', 'Find the first and last sales order date for every customer and calculate the number of days between them.', "Find employees together with their direct managers and show employees whose pay rate is higher than their manager's pay rate.", 'Find product assemblies that contain more components than the average assembly.', 'Find pairs of products in the same subcategory where one product costs at least twice as much as the other.', 'Find pairs of vendors with the same credit rating whose total purchase order values differ by more than 500000 dollars.', 'Find pairs of customers in the same territory whose lifetime spending differs by more than 100000 dollars.', 'Find employees whose manager was hired after they were hired.', 'Find components that are used in more than one product assembly and have an average required quantity above the overall component average.', "Find stores assigned to the same salesperson where one store's customer spending is at least twice the other's.", 'Find products in the same category that have the same color but different list prices.', 'Find salespeople who have worked in more than one territory and whose current sales are above their historical territory average.', 'Find customers who have purchased at least one product from every product category.', 'Find vendors that supply products from every product category represented in the product table.', 'Find departments where every current employee has at least one pay-history record.', 'Find products that have been sold in every sales territory.', 'Find salespeople whose assigned stores have customers in every territory where the salesperson has sales orders.', 'Find vendors where every supplied product has appeared on at least one purchase order.', 'Find customers who have placed at least one order in every year represented in the sales order table.', 'Find product categories where every product has at least one inventory record.', 'Find departments where every current employee has vacation hours above the company average.', 'Find customers who bought products from a different sales territory and whose average order total is higher than the average order total for customers in the same home territory.']

try:
    from benchmarks.run_meta import (
        candidate_meta,
        format_candidates,
        repair_meta,
        format_repair,
    )
except Exception:
    def candidate_meta(response: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "selected_candidate_source": response.get("selected_candidate_source"),
            "selection_reason": response.get("selection_reason"),
            "candidate_count": response.get("candidate_count"),
            "warnings": response.get("warnings") or [],
            "candidates": [],
        }

    def format_candidates(meta: Dict[str, Any]) -> List[str]:
        return [
            f"SELECTED: {meta.get('selected_candidate_source')} "
            f"(reason={meta.get('selection_reason')})"
        ]

    def repair_meta(response: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "repair_attempted": bool(response.get("repair_attempted")),
            "repair_selected": bool(response.get("repair_selected")),
        }

    def format_repair(meta: Dict[str, Any]) -> str:
        if not meta.get("repair_attempted"):
            return "REPAIR: not attempted"
        return (
            "REPAIR: attempted | "
            f"selected={meta.get('repair_selected')}"
        )


def post_query(question: str) -> Dict[str, Any]:
    url = f"{BASE_URL}/database/{DATABASE_ID}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()

    try:
        with urllib.request.urlopen(
            request,
            timeout=TIMEOUT_SECONDS,
        ) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)
            data["_http_status"] = response.status
            data["_elapsed_seconds"] = round(
                time.time() - start,
                3,
            )
            return data
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )
        return {
            "success": False,
            "_http_status": exc.code,
            "_elapsed_seconds": round(
                time.time() - start,
                3,
            ),
            "_http_error": exc.reason,
            "_error_body": error_body,
        }
    except Exception as exc:
        return {
            "success": False,
            "_http_status": None,
            "_elapsed_seconds": round(
                time.time() - start,
                3,
            ),
            "_exception": repr(exc),
        }


def get_nested(
    data: Dict[str, Any],
    path: List[str],
    default: Any = None,
) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def sql_flags(sql: str) -> Dict[str, bool]:
    value = (sql or "").upper()
    return {
        "has_with_cte": "WITH " in value,
        "has_not_exists": "NOT EXISTS" in value,
        "has_left_join": "LEFT JOIN" in value,
        "has_inner_join": (
            "INNER JOIN" in value or " JOIN " in value
        ),
        "has_count_distinct": "COUNT(DISTINCT" in value,
        "has_group_by": "GROUP BY" in value,
        "has_having": "HAVING" in value,
        "has_window": (
            "ROW_NUMBER()" in value
            or "RANK()" in value
            or "DENSE_RANK()" in value
            or " OVER " in value
        ),
        "has_null_filter": (
            " IS NULL" in value
            or " IS NOT NULL" in value
        ),
        "has_self_alias_hint": (
            " P1" in value
            or " P2" in value
            or " F1" in value
            or " F2" in value
            or "__G" in value
        ),
    }


def summarize_response(
    index: int,
    question: str,
    response: Dict[str, Any],
) -> Dict[str, Any]:
    sql = get_nested(
        response,
        ["generated_sql", "sql"],
        "",
    ) or ""

    execution = (
        response.get("execution")
        if isinstance(response.get("execution"), dict)
        else {}
    )

    error = (
        response.get("error")
        or response.get("detail")
        or response.get("_http_error")
        or response.get("_exception")
    )

    if not error and not response.get("success", False):
        error = (
            get_nested(response, ["execution", "error"])
            or get_nested(
                response,
                ["generated_sql", "error"],
            )
            or response.get("_error_body")
            or "success=false but no explicit error field found"
        )

    status = (
        "EXEC_OK"
        if response.get("success")
        else "EXEC_FAIL"
    )

    if (
        response.get("_http_status")
        and response.get("_http_status") >= 400
    ):
        status = (
            f"HTTP_ERROR_{response.get('_http_status')}"
        )

    return {
        "database_name": DATABASE_NAME,
        "database_id": DATABASE_ID,
        "query_number": index,
        "question": question,
        "status": status,
        "success": bool(response.get("success")),
        "row_count": execution.get("row_count"),
        "elapsed_seconds": response.get(
            "_elapsed_seconds"
        ),
        "extraction_source": response.get(
            "extraction_source"
        ),
        "selected_candidate_source": response.get(
            "selected_candidate_source"
        ),
        "selection_reason": response.get(
            "selection_reason"
        ),
        "query_family": response.get("query_family"),
        "query_family_confidence": response.get(
            "query_family_confidence"
        ),
        "query_family_reason": response.get(
            "query_family_reason"
        ),
        "family_guard_valid": response.get(
            "family_guard_valid"
        ),
        "family_guard_reasons": response.get(
            "family_guard_reasons"
        ),
        "repair": repair_meta(response),
        "candidates": candidate_meta(response),
        "warnings": response.get("warnings") or [],
        "sql": sql,
        "params": get_nested(
            response,
            ["generated_sql", "params"],
            [],
        ) or [],
        "flags": sql_flags(sql),
        "error": error,
    }


def format_result(item: Dict[str, Any]) -> str:
    lines: List[str] = []

    lines.append("=" * 100)
    lines.append(
        f"{item['database_name']} | "
        f"DB {item['database_id']} | "
        f"Q{item['query_number']:03d}"
    )
    lines.append(
        f"QUESTION: {item['question']}"
    )
    lines.append(
        (
            "STATUS: {status} | rows={rows} | "
            "source={source} | selected={selected} | "
            "family={family} | conf={confidence} | "
            "time={elapsed}s"
        ).format(
            status=item["status"],
            rows=item["row_count"],
            source=item["extraction_source"],
            selected=item[
                "selected_candidate_source"
            ],
            family=item["query_family"],
            confidence=item[
                "query_family_confidence"
            ],
            elapsed=item["elapsed_seconds"],
        )
    )
    lines.append(
        f"REASON: {item.get('query_family_reason')}"
    )

    if item.get("family_guard_reasons"):
        lines.append(
            "GUARD_REASONS: "
            + json.dumps(
                item["family_guard_reasons"],
                ensure_ascii=False,
            )
        )

    lines.append(
        "FLAGS: "
        + json.dumps(
            item["flags"],
            sort_keys=True,
        )
    )

    for line in format_candidates(
        item.get("candidates") or {}
    ):
        lines.append(line)

    lines.append(
        format_repair(item.get("repair") or {})
    )

    for warning in item.get("warnings") or []:
        lines.append(f"WARNING: {warning}")

    if item.get("error"):
        lines.append(f"ERROR: {item['error']}")

    lines.append("SQL:")
    lines.append(
        item["sql"] or "-- NO SQL GENERATED"
    )
    lines.append("")

    return "\n".join(lines)


def build_summary(
    results: List[Dict[str, Any]],
    timestamp: str,
) -> Dict[str, Any]:
    selected_sources = Counter(
        (
            item.get("selected_candidate_source")
            or item.get("extraction_source")
        )
        for item in results
    )

    family_count = sum(
        1
        for item in results
        if item.get("selected_candidate_source")
        == "query_family"
    )

    repair_attempted = [
        item
        for item in results
        if (
            item.get("repair") or {}
        ).get("repair_attempted")
    ]

    repair_selected = [
        item
        for item in results
        if (
            item.get("repair") or {}
        ).get("repair_selected")
    ]

    return {
        "database_name": DATABASE_NAME,
        "database_id": DATABASE_ID,
        "total": len(results),
        "exec_ok_count": sum(
            1
            for item in results
            if item["status"] == "EXEC_OK"
        ),
        "exec_fail_count": sum(
            1
            for item in results
            if item["status"] != "EXEC_OK"
        ),
        "query_family_count": family_count,
        "llm_count": len(results) - family_count,
        "no_sql_count": sum(
            1
            for item in results
            if not item.get("sql")
        ),
        "repair_attempted_count": len(
            repair_attempted
        ),
        "repair_selected_count": len(
            repair_selected
        ),
        "repair_selected_queries": [
            item["query_number"]
            for item in repair_selected
        ],
        "selected_source_breakdown": dict(
            selected_sources
        ),
        "generated_at": timestamp,
    }


def main() -> None:
    if len(QUESTIONS) != 100:
        raise RuntimeError(
            f"Expected 100 questions, "
            f"found {len(QUESTIONS)}."
        )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    txt_path = Path(
        f"adventureworks_100_sql_debug_db50_"
        f"{timestamp}.txt"
    )

    results: List[Dict[str, Any]] = []

    with txt_path.open(
        "w",
        encoding="utf-8",
    ) as output:
        output.write(
            "SpiderSQL AdventureWorks CTU "
            "100-Question Debug Results\n"
        )
        output.write(
            f"Database: {DATABASE_NAME} "
            f"#{DATABASE_ID}\n"
        )
        output.write(
            f"Generated: {timestamp}\n\n"
        )
        output.flush()

        for index, question in enumerate(
            QUESTIONS,
            start=1,
        ):
            response = post_query(question)
            item = summarize_response(
                index,
                question,
                response,
            )
            results.append(item)

            output.write(format_result(item))
            output.write("\n")
            output.flush()

            terminal_status = (
                "PASS"
                if item["status"] == "EXEC_OK"
                else "FAIL"
            )

            print(
                f"[{index:03d}/100] "
                f"{terminal_status} "
                f"{item['elapsed_seconds']}s",
                flush=True,
            )

        summary = build_summary(
            results,
            timestamp,
        )

        output.write("\n" + "=" * 100 + "\n")
        output.write("SUMMARY\n")
        output.write(
            json.dumps(
                summary,
                indent=2,
                ensure_ascii=False,
            )
        )
        output.write("\n")

    print(
        f"Saved detailed results to: {txt_path}"
    )


if __name__ == "__main__":
    main()
