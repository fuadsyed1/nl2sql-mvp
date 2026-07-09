#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 34
TIMEOUT_SECONDS = 180
OUTPUT_FILE = "retail_support_100_generated_sql_db34.sql"

QUESTIONS: List[str] = [
    "List customers who have at least one unpaid order and at least one unresolved high priority support ticket.",
    "Find customers whose latest order was cancelled but who have a later support ticket about payment.",
    "List products from preferred suppliers that were returned in at least one order item and are not discontinued.",
    "Find categories where every non-discontinued product has been ordered at least once.",
    "List suppliers whose products were shipped by every carrier service level represented in shipments.",
    "Find orders that have a delivered shipment but contain at least one returned item.",
    "List customers whose shipping city is different from the region of the department handling their assigned support ticket.",
    "Find employees who manage another employee and are assigned to unresolved urgent support tickets.",
    "List products whose total returned quantity is greater than their total non-returned quantity.",
    "Find customers who ordered products from all top-level categories.",
    "List orders where the shipment was delayed and the payment status is paid.",
    "Find departments where every active employee has been assigned at least one support ticket.",
    "List customers whose total spending is above the average total spending of customers in the same loyalty tier.",
    "Find products whose unit price is higher than the average unit price of products in their category.",
    "List support tickets for orders that contain discontinued products.",
    "Find customers who have orders shipped to a work address but have no billing address.",
    "List categories whose child categories contain products from more distinct suppliers than the parent category.",
    "Find orders where every item was returned.",
    "List suppliers whose products appear in orders from customers in every state represented in addresses.",
    "Find employees whose manager is inactive but who are assigned to unresolved tickets.",
    "List customers whose first order was unpaid and whose latest support ticket is unresolved.",
    "Find products that have never been returned but appear in delayed shipments.",
    "List carriers that delivered orders for every loyalty tier represented in customers.",
    "Find orders with no support ticket but at least one returned item.",
    "List customers with unresolved shipping tickets for orders that have not been delivered.",
    "Find products where the ordered unit price is lower than the product catalog unit price.",
    "List customers whose total number of returned items is greater than their total number of resolved tickets.",
    "Find employees who are assigned to tickets for customers outside the employee department region.",
    "List categories where all products are supplied by preferred suppliers.",
    "Find customers who have bought products from both preferred and non-preferred suppliers.",
    "List support tickets assigned to employees whose department has no active manager.",
    "Find orders whose latest shipment status is delayed.",
    "List products that are in categories with a parent category and have been ordered by platinum customers.",
    "Find customers who placed orders in at least three different shipping cities.",
    "List departments whose employees handled tickets for every issue type.",
    "Find products that were ordered in unpaid orders but never in paid orders.",
    "List customers whose orders include products from more categories than the average customer.",
    "Find suppliers whose discontinued products have never been ordered.",
    "List orders where total item value exceeds the average order value for the same customer.",
    "Find employees who have more unresolved tickets than their manager.",
    "List customers who have support tickets on orders shipped by international carriers.",
    "Find categories where the highest priced product has never been ordered but a cheaper product was ordered.",
    "List customers who ordered all products from at least one supplier.",
    "Find shipments that were delivered before a support ticket was opened for the same order.",
    "List products that appear in orders from customers in every loyalty tier.",
    "Find employees whose assigned tickets are all resolved.",
    "List orders where payment is refunded but no item was returned.",
    "Find customers who have no support tickets but have at least one delayed shipment.",
    "List suppliers whose products have total sales above the average total sales per supplier.",
    "Find categories whose products have been shipped by more distinct carriers than the category average.",
    "List customers with both cancelled and delivered orders.",
    "Find orders whose shipping address belongs to a different customer than the order customer.",
    "List employees who are managers and whose team members have unresolved urgent tickets.",
    "Find products ordered by customers whose signup date is before the order placed date and shipment is delayed.",
    "List support tickets for customers who have never placed a paid order.",
    "Find carriers whose delivered shipments have higher average order value than their delayed shipments.",
    "List categories where every child category has at least one active product.",
    "Find customers whose latest order contains a returned item.",
    "List products with returned quantity greater than 5 and supplied by non-preferred suppliers.",
    "Find departments where the number of unresolved tickets assigned to employees is above the department average.",
    "List orders with all shipments delivered and no unresolved support ticket.",
    "Find customers who have ordered from every preferred supplier.",
    "List employees whose assigned tickets involve orders containing products from the employee manager's customers.",
    "Find products whose total quantity ordered by gold customers exceeds total quantity ordered by bronze customers.",
    "List customers whose unpaid order total is greater than their paid order total.",
    "Find categories where at least one product has never appeared in order_items.",
    "List support tickets opened after the order was shipped but before it was delivered.",
    "Find orders with more distinct products than the average order.",
    "List suppliers that provide products in every category used by order_items.",
    "Find customers whose home address state differs from their work address state.",
    "List employees who are assigned tickets for orders shipped by all carriers.",
    "Find products that are both discontinued and still appear in new orders.",
    "List customers whose orders contain returned items from more than one category.",
    "Find departments whose employees have no unresolved urgent tickets.",
    "List orders whose total returned value is greater than total kept value.",
    "Find customers with tickets assigned to employees in more than one department.",
    "List categories whose average product unit price is above the average unit price of their parent category.",
    "Find carriers with no delayed shipments but at least one in-transit shipment.",
    "List products ordered by customers who have unresolved account tickets.",
    "Find suppliers whose products are only ordered by platinum or gold customers.",
    "List employees with no assigned tickets but whose direct reports have assigned tickets.",
    "Find customers whose latest support ticket is resolved but latest order is unpaid.",
    "List orders where a support ticket was opened before any shipment record exists.",
    "Find products whose highest sold unit price is lower than catalog unit price.",
    "List categories with products ordered in every address state.",
    "Find customers whose total order quantity is above average for their loyalty tier.",
    "List support tickets for orders containing products from a parent category's child category.",
    "Find employees whose unresolved ticket count is higher than the average unresolved ticket count in their department.",
    "List suppliers with preferred status whose products were never returned.",
    "Find orders that contain products from at least three different categories.",
    "List customers who have delayed shipments but no unresolved support tickets.",
    "Find products whose returned order count is above the average returned order count in their category.",
    "List departments whose active employees collectively handled every ticket priority.",
    "Find customers whose first support ticket was opened before their first order.",
    "List carriers that shipped orders containing discontinued products but had no delayed shipment for those orders.",
    "Find categories where the total sales value is above the total sales value of sibling categories.",
    "List employees who are assigned to tickets for customers with more than five orders.",
    "Find orders where the shipment carrier service level is express and every item was not returned.",
    "List customers whose orders include both Electronics and Home category products.",
    "Find customers with no billing address but at least one paid delivered order."
]


def post_query(question: str) -> Dict[str, Any]:
    payload = json.dumps({"question": question}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/database/{DATABASE_ID}/execute_sql",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_sql(response: Dict[str, Any]) -> str:
    generated = response.get("generated_sql")
    if isinstance(generated, dict):
        sql = generated.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    sql = response.get("sql")
    if isinstance(sql, str) and sql.strip():
        return sql.strip()
    return "-- NO SQL GENERATED"


def normalize_sql(sql: str) -> str:
    sql = sql.strip()
    if not sql:
        return "-- NO SQL GENERATED;"
    if sql.startswith("--"):
        return sql
    return sql if sql.endswith(";") else sql + ";"


def main() -> None:
    output_path = Path(OUTPUT_FILE)
    with output_path.open("w", encoding="utf-8") as out:
        for question in QUESTIONS:
            try:
                sql = normalize_sql(extract_sql(post_query(question)))
            except Exception as exc:
                sql = f"-- ERROR: {type(exc).__name__}: {exc}"
            print(sql)
            print()
            out.write(sql + "\n\n")


if __name__ == "__main__":
    main()
