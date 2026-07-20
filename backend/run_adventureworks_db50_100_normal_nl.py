#!/usr/bin/env python3
"""
Run 100 normal natural-language queries against AdventureWorks CTU database #50.

Run this file from:
    C:\\Projects\\nl2sql-mvp\\backend

Command:
    python run_adventureworks_db50_100_normal_nl.py

Terminal:
    Prints PASS when a query generates SQL and executes successfully.
    Prints FAIL when the request, SQL generation, or execution fails.

Output:
    Creates only one text file in the current backend folder:
    adventureworks_db50_100_normal_sql.txt

The text file contains only each natural-language query followed by its
generated SQL. There is no hard-coded SQL answer matching.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 50
TIMEOUT_SECONDS = 420
OUTPUT_FILE = Path("adventureworks_db50_100_normal_sql.txt")


TESTS: list[tuple[str, str]] = [
    # 1-5: Projection and filtering
    ("projection_filter", "Show every product's ID, name, product number, color, standard cost, and list price, but include only products that are currently for sale."),
    ("projection_filter", "List employees with their full names, job titles, hire dates, vacation hours, and current employment status."),
    ("projection_filter", "Show sales orders placed after 2012 with the order number, customer, order date, ship date, subtotal, tax, freight, and total due."),
    ("projection_filter", "List active vendors with their account numbers, credit ratings, preferred-vendor status, and purchasing web-service URLs."),
    ("projection_filter", "Show work orders that scrapped at least one unit, including the product, ordered quantity, stocked quantity, scrapped quantity, dates, and scrap reason."),

    # 6-10: Comparisons and ranges
    ("comparison_range", "Find products whose list price is at least 500 but less than 2000, and show their names, colors, standard costs, and list prices."),
    ("comparison_range", "Show sales orders with total due between 10000 and 50000 that were placed from 2012 through 2013."),
    ("comparison_range", "List employees hired between 2006 and 2010 who have more than 40 vacation hours."),
    ("comparison_range", "Find purchase orders with total due between 5000 and 25000 and rejected quantity greater than zero on at least one order line."),
    ("comparison_range", "Show product inventory records with quantity between 100 and 500, including product name, location name, shelf, and bin."),

    # 11-15: Text matching and null handling
    ("text_null", "Find people whose last name begins with S and whose first name contains the letter a, showing their full names and person types."),
    ("text_null", "Show products whose names contain Mountain or Road and whose color is recorded."),
    ("text_null", "List vendors whose names contain Bike and whose purchasing web-service URL is missing."),
    ("text_null", "Find addresses in cities beginning with San, including state or province and country."),
    ("text_null", "Show sales orders that have no salesperson assigned or have not yet been shipped."),

    # 16-20: Two-table joins
    ("join", "Show each product with its product subcategory name, including products that do not have a subcategory."),
    ("join", "List sales orders with the customer's account number and sales territory name."),
    ("join", "Show employees with their first name, last name, job title, department, and shift for current department assignments."),
    ("join", "List purchase orders with vendor name, order date, ship date, subtotal, freight, and total due."),
    ("join", "Show addresses with their state or province name, country name, postal code, and sales territory."),

    # 21-25: Multi-table joins
    ("multi_join", "List sales order lines with customer account number, product name, category, order date, quantity, unit price, discount, and line total."),
    ("multi_join", "Show current employees with full names, departments, shifts, job titles, hire dates, and current pay rates."),
    ("multi_join", "List products with their subcategory, category, product model, list price, standard cost, and current inventory quantity."),
    ("multi_join", "Show purchase order lines with vendor name, product name, order date, quantity ordered, quantity received, rejected quantity, unit price, and line total."),
    ("multi_join", "List stores with the customer record linked to the store, the assigned salesperson's full name, and the salesperson's territory."),

    # 26-30: Basic aggregation
    ("aggregation", "Show the total number of products, the average list price, the minimum list price, and the maximum list price."),
    ("aggregation", "Calculate the total subtotal, tax, freight, and total due across all sales orders."),
    ("aggregation", "Show the number of employees, their average vacation hours, and their average sick-leave hours."),
    ("aggregation", "Calculate the total ordered quantity, received quantity, rejected quantity, and line value across all purchase order lines."),
    ("aggregation", "Show the total ordered quantity, total sales amount, average unit price, and average discount across all sales order lines."),

    # 31-35: GROUP BY
    ("group_by", "For each customer, show the number of sales orders, total subtotal, total tax, total freight, and total amount due."),
    ("group_by", "For each sales territory, show the territory name, order count, total sales due, and average order value."),
    ("group_by", "For each product category and subcategory, count products and show average list price and average standard cost."),
    ("group_by", "For each current department, count employees and show average vacation hours and average sick-leave hours."),
    ("group_by", "For each vendor, show purchase order count, total ordered value, average order value, and latest purchase order date."),

    # 36-40: HAVING
    ("having", "Find customers who placed more than 10 sales orders and spent more than 100000 in total."),
    ("having", "Show product subcategories containing more than 10 products with an average list price above 500."),
    ("having", "Find sales territories with more than 1000 orders and total sales due above 1000000."),
    ("having", "Show vendors that received more than 20 purchase orders with total order value above 500000."),
    ("having", "Find departments with more than 10 current employees and average vacation hours above 30."),

    # 41-45: DISTINCT and COUNT DISTINCT
    ("distinct", "List every distinct product color and product class combination, excluding rows where both values are missing."),
    ("distinct", "Show all distinct employee job titles and organization levels."),
    ("distinct", "Count how many different customers have placed sales orders in each sales territory."),
    ("distinct", "Count how many distinct products each vendor supplies."),
    ("distinct", "For each year, count distinct customers, distinct products sold, and distinct salespeople appearing in sales orders."),

    # 46-50: Ordering and top-k
    ("order_topk", "Show the 20 most expensive products, breaking ties by product name."),
    ("order_topk", "List the 25 sales orders with the highest total due, including customer, order date, subtotal, tax, freight, and total due."),
    ("order_topk", "Show the 15 customers with the highest lifetime sales total and include their order counts."),
    ("order_topk", "List the 15 vendors with the greatest total purchase order value and include order count and average order value."),
    ("order_topk", "Show the 20 products with the highest total quantity sold, including sales revenue and number of order lines."),

    # 51-55: Scalar and grouped subqueries
    ("subquery", "Find products priced above the average list price for products in the same subcategory."),
    ("subquery", "Show sales orders whose total due is above the average total due for orders placed in the same year."),
    ("subquery", "List employees whose vacation hours are above the average vacation hours of employees in their current department."),
    ("subquery", "Find customers whose lifetime sales total is above the average lifetime sales total across all customers."),
    ("subquery", "Show vendors whose total purchase order value is above the average total purchase value across vendors."),

    # 56-60: EXISTS and NOT EXISTS
    ("exists", "List customers who have at least one sales order worth more than 20000."),
    ("exists", "Find products that have never appeared on any sales order line."),
    ("exists", "Show vendors that have at least one purchase order containing a rejected item quantity."),
    ("exists", "Find employees who do not have a current department assignment."),
    ("exists", "List products that have inventory in more than three different locations."),

    # 61-65: Set operations
    ("set_operation", "List product IDs that appear in both sales order details and purchase order details."),
    ("set_operation", "Find customer IDs that placed an order in 2012 and also placed an order in 2013."),
    ("set_operation", "Combine employee business entity IDs and vendor business entity IDs into one list without duplicates."),
    ("set_operation", "Find products that have been sold to customers but have never been ordered from a vendor."),
    ("set_operation", "List people who are employees or salespeople, showing each business entity ID only once."),

    # 66-70: CASE expressions
    ("case_expression", "Label every product as budget, midrange, or premium based on list price, and show product name, price, and label."),
    ("case_expression", "Classify sales orders as small, medium, or large based on total due, and show the order number, total due, and classification."),
    ("case_expression", "Label inventory records as out of stock, low stock, normal stock, or high stock based on quantity."),
    ("case_expression", "Group employees into short, medium, or long tenure based on years since hire, and show their names, hire dates, and tenure group."),
    ("case_expression", "Classify vendors as preferred-low-risk, active-standard, inactive, or other based on preferred status, active flag, and credit rating."),

    # 71-75: Derived metrics
    ("derived_metric", "For each sales order line, calculate gross line value, discount amount, and net line revenue."),
    ("derived_metric", "For each product, calculate margin amount and margin percentage from list price and standard cost."),
    ("derived_metric", "For each sales order, calculate the number of lines, total quantity, total line value, and average line value."),
    ("derived_metric", "For each work order, calculate the scrap rate as scrapped quantity divided by ordered quantity."),
    ("derived_metric", "For each salesperson with a quota, calculate quota attainment, year-over-year sales change, and commission amount."),

    # 76-80: Date and time analysis
    ("date_time", "Show monthly sales totals for each year, including order count, subtotal, tax, freight, and total due."),
    ("date_time", "For each employee hire year, count employees and show average vacation and sick-leave hours."),
    ("date_time", "For each purchase order year and month, show order count, total due, and average days from order date to ship date."),
    ("date_time", "List products whose sell start date was earlier than the average sell start date of products in the same subcategory."),
    ("date_time", "Show sales orders shipped more than seven days after the order date, including the number of days taken to ship."),

    # 81-85: Self-joins and hierarchy
    ("self_join", "Show employees together with their direct managers using the employee organization hierarchy."),
    ("self_join", "List product assemblies and their component products from the bill of materials, including quantity required and component level."),
    ("self_join", "Find pairs of products in the same subcategory that have different list prices, showing the higher-priced and lower-priced product."),
    ("self_join", "Show pairs of vendors with the same credit rating where the first vendor name comes alphabetically before the second."),
    ("self_join", "Find customers in the same territory whose lifetime sales totals differ by more than 100000."),

    # 86-90: Conditional aggregation
    ("conditional_aggregation", "For each product category, count red products, black products, blue products, and products with no color."),
    ("conditional_aggregation", "For each sales territory, show counts of online orders, non-online orders, shipped orders, and unshipped orders."),
    ("conditional_aggregation", "For each department, count salaried employees, hourly employees, male employees, and female employees."),
    ("conditional_aggregation", "For each vendor, count open purchase orders, completed purchase orders, and rejected order lines."),
    ("conditional_aggregation", "For each customer, show total orders, orders above 10000, orders above 20000, and total lifetime sales."),

    # 91-95: CTE-style analytical queries
    ("cte", "Calculate lifetime sales for every customer, then list customers whose lifetime sales are in the top ten percent."),
    ("cte", "Calculate total sales revenue for every product, then show products whose revenue is above the average product revenue."),
    ("cte", "Calculate purchase totals for every vendor, then show each vendor's share of total purchasing value."),
    ("cte", "Calculate current employee counts by department, then show departments whose headcount is above the average department headcount."),
    ("cte", "Calculate yearly sales by territory, then show each territory's best sales year."),

    # 96-100: Window functions
    ("window", "Rank products by total sales revenue within each product category."),
    ("window", "Show a running total of daily sales order value ordered by date."),
    ("window", "Return the most recent sales order for each customer."),
    ("window", "Rank salespeople by year-to-date sales within each territory and return the top salesperson in every territory."),
    ("window", "Show yearly sales for each territory together with the previous year's sales and the year-over-year change."),
]


def request_query(question: str) -> dict[str, Any]:
    """Send one natural-language question to SpiderSQL."""
    endpoint = f"{BASE_URL}/database/{DATABASE_ID}/execute_sql"
    payload = json.dumps({"question": question}).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
            result = json.loads(raw) if raw.strip() else {}
            if not isinstance(result, dict):
                return {"success": False, "error": "Backend returned a non-object response."}
            return result
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "error": f"HTTP {exc.code}: {body[:300]}",
        }
    except Exception as exc:  # Keep the remaining tests running.
        return {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def extract_sql(response: dict[str, Any]) -> str:
    """Extract generated SQL from common SpiderSQL response shapes."""
    generated_sql = response.get("generated_sql")

    candidates: list[Any] = [
        generated_sql.get("sql") if isinstance(generated_sql, dict) else None,
        generated_sql if isinstance(generated_sql, str) else None,
        response.get("sql"),
        response.get("selected_sql"),
        response.get("query"),
    ]

    result = response.get("result")
    if isinstance(result, dict):
        candidates.extend([result.get("sql"), result.get("generated_sql")])

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().rstrip(";")

    return ""


def execution_succeeded(response: dict[str, Any], sql: str) -> tuple[bool, str]:
    """PASS means generation and execution succeeded; no SQL answer matching."""
    if response.get("success") is not True:
        reason = (
            response.get("error")
            or response.get("message")
            or response.get("detail")
            or "Backend returned success=false."
        )
        return False, str(reason)

    if not sql:
        return False, "No SQL was generated."

    execution = response.get("execution")
    if isinstance(execution, dict):
        if execution.get("success") is False:
            return False, str(
                execution.get("error")
                or execution.get("message")
                or "SQL execution failed."
            )
        if execution.get("error"):
            return False, str(execution["error"])

    return True, "Generated and executed successfully."


def write_query_and_sql(
    handle: Any,
    number: int,
    question: str,
    sql: str,
) -> None:
    """Write only the query followed by its generated SQL."""
    handle.write(f"{number}. Query:\n{question}\n\n")
    handle.write("SQL:\n")
    handle.write(sql + ";\n" if sql else "(no SQL generated)\n")
    handle.write("\n" + "-" * 100 + "\n\n")
    handle.flush()


def main() -> int:
    if len(TESTS) != 100:
        raise RuntimeError(f"Expected exactly 100 tests, found {len(TESTS)}.")

    passed = 0
    failed = 0

    print("=" * 110)
    print("AdventureWorks CTU #50 — 100 Normal Natural-Language Queries")
    print(f"Endpoint: {BASE_URL}/database/{DATABASE_ID}/execute_sql")
    print(f"Output:   {OUTPUT_FILE.resolve()}")
    print("PASS means the query generated SQL and executed without a reported error.")
    print("=" * 110)

    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for number, (category, question) in enumerate(TESTS, start=1):
            started = time.perf_counter()
            response = request_query(question)
            sql = extract_sql(response)
            success, reason = execution_succeeded(response, sql)
            elapsed = time.perf_counter() - started

            write_query_and_sql(output, number, question, sql)

            if success:
                passed += 1
                print(
                    f"[{number:03d}/100] PASS  [{category}]  "
                    f"{elapsed:7.2f}s",
                    flush=True,
                )
            else:
                failed += 1
                print(
                    f"[{number:03d}/100] FAIL  [{category}]  "
                    f"{elapsed:7.2f}s  {reason}",
                    flush=True,
                )

    print("=" * 110)
    print(f"Finished: PASS {passed}/100 | FAIL {failed}/100")
    print(f"Generated SQL saved to: {OUTPUT_FILE.resolve()}")
    print("=" * 110)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
