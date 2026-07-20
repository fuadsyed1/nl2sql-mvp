#!/usr/bin/env python3
"""
Run 50 natural-language containment benchmark cases against SpiderSQL database 53.

Run from the backend folder while FastAPI is running:

    python run_northstar_containment_50_db53.py

The backend must be started with full tracing enabled BEFORE this runner starts.
PowerShell example:

    $env:SPIDERSQL_FULL_TRACE="true"
    python -m uvicorn app:app --reload

Primary output:
    benchmarks/results/northstar_containment_50_db53_<timestamp>.txt

Expected backend trace:
    benchmarks/results/northstar_containment_50_db53_<timestamp>_full_trace_db53_<timestamp>.txt

Optional examples:

    python run_northstar_containment_50_db53.py --start 1 --end 5
    python run_northstar_containment_50_db53.py --only-category join_containment
    python run_northstar_containment_50_db53.py --timeout 600
"""

from __future__ import annotations

import argparse
import collections
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


TEST_CASES: list[dict[str, Any]] = [
    {
        "id": 1,
        "category": "single_table_threshold",
        "difficulty": "easy",
        "name": "Customer risk-score threshold chain",
        "queries": [
            "List customers whose risk score is greater than 80. Show customer ID, full name, and risk score.",
            "List customers whose risk score is greater than 60. Show customer ID, full name, and risk score.",
            "List customers whose risk score is greater than 40. Show customer ID, full name, and risk score.",
            "List customers whose risk score is greater than 90. Show customer ID, full name, and risk score.",
        ],
        "expected_note": "Risk>90 should be contained in Risk>80, which should be contained in Risk>60, then Risk>40.",
    },
    {
        "id": 2,
        "category": "single_table_threshold",
        "difficulty": "easy",
        "name": "Product list-price threshold chain",
        "queries": [
            "List products with a list price greater than 500. Show product ID, product name, and list price.",
            "List products with a list price greater than 250. Show product ID, product name, and list price.",
            "List products with a list price greater than 100. Show product ID, product name, and list price.",
            "List products with a list price greater than 750. Show product ID, product name, and list price.",
        ],
        "expected_note": "Price>750 is narrowest; Price>100 is broadest.",
    },
    {
        "id": 3,
        "category": "single_table_threshold",
        "difficulty": "easy",
        "name": "Employee salary threshold chain",
        "queries": [
            "List employees whose salary is greater than 120000. Show employee ID, full name, and salary.",
            "List employees whose salary is greater than 100000. Show employee ID, full name, and salary.",
            "List employees whose salary is greater than 80000. Show employee ID, full name, and salary.",
            "List employees whose salary is greater than 150000. Show employee ID, full name, and salary.",
        ],
        "expected_note": "Salary>150000 should be contained in >120000, >100000, and >80000.",
    },
    {
        "id": 4,
        "category": "single_table_threshold",
        "difficulty": "easy",
        "name": "Warehouse utilization threshold chain",
        "queries": [
            "List warehouses whose current utilization percentage is greater than 85. Show warehouse ID, warehouse name, and utilization percentage.",
            "List warehouses whose current utilization percentage is greater than 70. Show warehouse ID, warehouse name, and utilization percentage.",
            "List warehouses whose current utilization percentage is greater than 50. Show warehouse ID, warehouse name, and utilization percentage.",
            "List warehouses whose current utilization percentage is greater than 95. Show warehouse ID, warehouse name, and utilization percentage.",
        ],
        "expected_note": "Utilization>95 is narrowest; >50 is broadest.",
    },
    {
        "id": 5,
        "category": "single_table_threshold",
        "difficulty": "easy",
        "name": "Inventory available-quantity threshold chain",
        "queries": [
            "List inventory records with quantity available greater than 200. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records with quantity available greater than 100. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records with quantity available greater than 50. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records with quantity available greater than 300. Show inventory ID, product ID, warehouse ID, and quantity available.",
        ],
        "expected_note": "Available>300 should be contained in >200, >100, and >50.",
    },
    {
        "id": 6,
        "category": "conjunctive_filters",
        "difficulty": "easy",
        "name": "Active enterprise customer narrowing",
        "queries": [
            "List active enterprise customers whose current balance is greater than 10000. Show customer ID, full name, account status, customer segment, and current balance.",
            "List active enterprise customers. Show customer ID, full name, account status, customer segment, and current balance.",
            "List enterprise customers whose current balance is greater than 10000. Show customer ID, full name, account status, customer segment, and current balance.",
            "List active enterprise customers whose current balance is greater than 5000. Show customer ID, full name, account status, customer segment, and current balance.",
        ],
        "expected_note": "Q1 should be contained in Q2, Q3, and the weaker-balance Q4.",
    },
    {
        "id": 7,
        "category": "conjunctive_filters",
        "difficulty": "easy",
        "name": "Electronics product price narrowing",
        "queries": [
            "List Electronics products with a sale price greater than 300. Show product ID, product name, category, and sale price.",
            "List Electronics products. Show product ID, product name, category, and sale price.",
            "List products with a sale price greater than 300. Show product ID, product name, category, and sale price.",
            "List Electronics products with a sale price greater than 150. Show product ID, product name, category, and sale price.",
        ],
        "expected_note": "Electronics+Price>300 should be contained in each single condition and Electronics+Price>150.",
    },
    {
        "id": 8,
        "category": "conjunctive_filters",
        "difficulty": "easy",
        "name": "Active full-time employee narrowing",
        "queries": [
            "List active full-time employees whose salary is greater than 100000. Show employee ID, full name, employment status, employment type, and salary.",
            "List active full-time employees. Show employee ID, full name, employment status, employment type, and salary.",
            "List full-time employees whose salary is greater than 100000. Show employee ID, full name, employment status, employment type, and salary.",
            "List active full-time employees whose salary is greater than 80000. Show employee ID, full name, employment status, employment type, and salary.",
        ],
        "expected_note": "Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 9,
        "category": "conjunctive_filters",
        "difficulty": "easy",
        "name": "Active temperature-controlled warehouse narrowing",
        "queries": [
            "List active temperature-controlled warehouses with utilization greater than 80 percent. Show warehouse ID, warehouse name, operating status, temperature-controlled flag, and utilization percentage.",
            "List active temperature-controlled warehouses. Show warehouse ID, warehouse name, operating status, temperature-controlled flag, and utilization percentage.",
            "List temperature-controlled warehouses with utilization greater than 80 percent. Show warehouse ID, warehouse name, operating status, temperature-controlled flag, and utilization percentage.",
            "List active temperature-controlled warehouses with utilization greater than 60 percent. Show warehouse ID, warehouse name, operating status, temperature-controlled flag, and utilization percentage.",
        ],
        "expected_note": "Q1 should be contained in Q2, Q3, and the weaker-utilization Q4.",
    },
    {
        "id": 10,
        "category": "conjunctive_filters",
        "difficulty": "easy",
        "name": "Active manufacturer supplier narrowing",
        "queries": [
            "List active manufacturer suppliers with a rating of at least 4. Show supplier ID, supplier name, supplier type, active flag, and rating.",
            "List active manufacturer suppliers. Show supplier ID, supplier name, supplier type, active flag, and rating.",
            "List manufacturer suppliers with a rating of at least 4. Show supplier ID, supplier name, supplier type, active flag, and rating.",
            "List active manufacturer suppliers with a rating of at least 3. Show supplier ID, supplier name, supplier type, active flag, and rating.",
        ],
        "expected_note": "Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 11,
        "category": "date_status",
        "difficulty": "moderate",
        "name": "Customer signup-date and active-status containment",
        "queries": [
            "List active customers who signed up on or after January 1, 2024. Show customer ID, full name, signup date, and account status.",
            "List active customers. Show customer ID, full name, signup date, and account status.",
            "List customers who signed up on or after January 1, 2024. Show customer ID, full name, signup date, and account status.",
            "List active customers who signed up on or after January 1, 2022. Show customer ID, full name, signup date, and account status.",
        ],
        "expected_note": "Active+signup>=2024 should be contained in active, signup>=2024, and active+signup>=2022.",
    },
    {
        "id": 12,
        "category": "date_status",
        "difficulty": "moderate",
        "name": "Product launch-date and category containment",
        "queries": [
            "List Electronics products launched on or after January 1, 2024. Show product ID, product name, category, and launch date.",
            "List Electronics products. Show product ID, product name, category, and launch date.",
            "List products launched on or after January 1, 2024. Show product ID, product name, category, and launch date.",
            "List Electronics products launched on or after January 1, 2022. Show product ID, product name, category, and launch date.",
        ],
        "expected_note": "Electronics+launch>=2024 should be contained in each broader condition.",
    },
    {
        "id": 13,
        "category": "date_status",
        "difficulty": "moderate",
        "name": "Employee hire-date and active-status containment",
        "queries": [
            "List active employees hired on or after January 1, 2022. Show employee ID, full name, hire date, and employment status.",
            "List active employees. Show employee ID, full name, hire date, and employment status.",
            "List employees hired on or after January 1, 2022. Show employee ID, full name, hire date, and employment status.",
            "List active employees hired on or after January 1, 2020. Show employee ID, full name, hire date, and employment status.",
        ],
        "expected_note": "Active+hire>=2022 should be contained in active, hire>=2022, and active+hire>=2020.",
    },
    {
        "id": 14,
        "category": "date_status",
        "difficulty": "moderate",
        "name": "Delivered-order date containment",
        "queries": [
            "List delivered sales orders placed on or after January 1, 2025. Show order ID, order number, order date, order status, and grand total.",
            "List delivered sales orders. Show order ID, order number, order date, order status, and grand total.",
            "List sales orders placed on or after January 1, 2025. Show order ID, order number, order date, order status, and grand total.",
            "List delivered sales orders placed on or after January 1, 2024. Show order ID, order number, order date, order status, and grand total.",
        ],
        "expected_note": "Delivered+date>=2025 should be contained in the three broader result sets.",
    },
    {
        "id": 15,
        "category": "date_status",
        "difficulty": "moderate",
        "name": "Delivered-shipment date containment",
        "queries": [
            "List delivered shipments sent on or after January 1, 2025. Show shipment ID, shipment number, ship date, shipment status, and shipping cost.",
            "List delivered shipments. Show shipment ID, shipment number, ship date, shipment status, and shipping cost.",
            "List shipments sent on or after January 1, 2025. Show shipment ID, shipment number, ship date, shipment status, and shipping cost.",
            "List delivered shipments sent on or after January 1, 2024. Show shipment ID, shipment number, ship date, shipment status, and shipping cost.",
        ],
        "expected_note": "Delivered+ship-date>=2025 should be contained in all three broader queries.",
    },
    {
        "id": 16,
        "category": "join_containment",
        "difficulty": "moderate",
        "name": "Products joined to manufacturer suppliers",
        "queries": [
            "List distinct Electronics products supplied by manufacturer suppliers with a sale price greater than 300. Show product ID, product name, category, and sale price.",
            "List distinct Electronics products supplied by manufacturer suppliers. Show product ID, product name, category, and sale price.",
            "List distinct products supplied by manufacturer suppliers with a sale price greater than 300. Show product ID, product name, category, and sale price.",
            "List distinct Electronics products supplied by manufacturer suppliers with a sale price greater than 150. Show product ID, product name, category, and sale price.",
        ],
        "expected_note": "Uses products.supplier_id -> suppliers.supplier_id. Q1 is narrower than Q2, Q3, and Q4.",
    },
    {
        "id": 17,
        "category": "join_containment",
        "difficulty": "moderate",
        "name": "Employees joined to departments",
        "queries": [
            "List active employees in the Information Technology department whose salary is greater than 100000. Show employee ID, full name, salary, and department name.",
            "List active employees in the Information Technology department. Show employee ID, full name, salary, and department name.",
            "List employees in the Information Technology department whose salary is greater than 100000. Show employee ID, full name, salary, and department name.",
            "List active employees in the Information Technology department whose salary is greater than 80000. Show employee ID, full name, salary, and department name.",
        ],
        "expected_note": "Uses employees.department_id -> departments.department_id. Q1 is contained in Q2, Q3, and Q4.",
    },
    {
        "id": 18,
        "category": "join_containment",
        "difficulty": "moderate",
        "name": "Inventory joined to Spokane warehouses",
        "queries": [
            "List inventory records in Spokane warehouses with quantity available below 50. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records in Spokane warehouses. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records with quantity available below 50. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records in Spokane warehouses with quantity available below 100. Show inventory ID, product ID, warehouse ID, and quantity available.",
        ],
        "expected_note": "Uses inventory.warehouse_id -> warehouses.warehouse_id. Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 19,
        "category": "join_containment",
        "difficulty": "moderate",
        "name": "Orders joined to Gold customers",
        "queries": [
            "List delivered sales orders placed by Gold loyalty customers with a grand total greater than 1000. Show order ID, order number, order status, and grand total.",
            "List delivered sales orders placed by Gold loyalty customers. Show order ID, order number, order status, and grand total.",
            "List sales orders placed by Gold loyalty customers with a grand total greater than 1000. Show order ID, order number, order status, and grand total.",
            "List delivered sales orders placed by Gold loyalty customers with a grand total greater than 500. Show order ID, order number, order status, and grand total.",
        ],
        "expected_note": "Uses sales_orders.customer_id -> customers.customer_id. Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 20,
        "category": "join_containment",
        "difficulty": "moderate",
        "name": "Payments joined to enterprise customers",
        "queries": [
            "List settled payments from enterprise customers with an amount greater than 500. Show payment ID, payment number, amount, and payment status.",
            "List settled payments from enterprise customers. Show payment ID, payment number, amount, and payment status.",
            "List payments from enterprise customers with an amount greater than 500. Show payment ID, payment number, amount, and payment status.",
            "List settled payments from enterprise customers with an amount greater than 250. Show payment ID, payment number, amount, and payment status.",
        ],
        "expected_note": "Uses payments.customer_id -> customers.customer_id. Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 21,
        "category": "multijoin_containment",
        "difficulty": "hard",
        "name": "Delivered-order items for Electronics products",
        "queries": [
            "List order items for Electronics products on delivered sales orders where the line total is greater than 500. Show order item ID, order ID, product ID, and line total.",
            "List order items for Electronics products on delivered sales orders. Show order item ID, order ID, product ID, and line total.",
            "List order items for Electronics products where the line total is greater than 500. Show order item ID, order ID, product ID, and line total.",
            "List order items for Electronics products on delivered sales orders where the line total is greater than 250. Show order item ID, order ID, product ID, and line total.",
        ],
        "expected_note": "Uses sales_order_items -> products and sales_order_items -> sales_orders. Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 22,
        "category": "multijoin_containment",
        "difficulty": "hard",
        "name": "Shipments for Gold-customer orders",
        "queries": [
            "List delivered shipments for sales orders placed by Gold loyalty customers with shipping cost greater than 50. Show shipment ID, order ID, shipment status, and shipping cost.",
            "List delivered shipments for sales orders placed by Gold loyalty customers. Show shipment ID, order ID, shipment status, and shipping cost.",
            "List shipments for sales orders placed by Gold loyalty customers with shipping cost greater than 50. Show shipment ID, order ID, shipment status, and shipping cost.",
            "List delivered shipments for sales orders placed by Gold loyalty customers with shipping cost greater than 25. Show shipment ID, order ID, shipment status, and shipping cost.",
        ],
        "expected_note": "Uses shipments.order_id -> sales_orders.order_id -> customers.customer_id. Q1 is narrower than Q2, Q3, and Q4.",
    },
    {
        "id": 23,
        "category": "multijoin_containment",
        "difficulty": "hard",
        "name": "Products stocked in temperature-controlled warehouses",
        "queries": [
            "List distinct Electronics products stored in temperature-controlled warehouses where quantity available is below 50. Show product ID, product name, and category.",
            "List distinct Electronics products stored in temperature-controlled warehouses. Show product ID, product name, and category.",
            "List distinct products stored in temperature-controlled warehouses where quantity available is below 50. Show product ID, product name, and category.",
            "List distinct Electronics products stored in temperature-controlled warehouses where quantity available is below 100. Show product ID, product name, and category.",
        ],
        "expected_note": "Uses products <- inventory -> warehouses. Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 24,
        "category": "multijoin_containment",
        "difficulty": "hard",
        "name": "Orders handled by Sales-department representatives",
        "queries": [
            "List delivered high-priority sales orders handled by employees in the Sales department. Show order ID, order number, order status, priority, and grand total.",
            "List delivered sales orders handled by employees in the Sales department. Show order ID, order number, order status, priority, and grand total.",
            "List high-priority sales orders handled by employees in the Sales department. Show order ID, order number, order status, priority, and grand total.",
            "List delivered high-priority sales orders. Show order ID, order number, order status, priority, and grand total.",
        ],
        "expected_note": "Uses sales_orders.sales_rep_id -> employees.employee_id -> departments.department_id. Q1 is contained in Q2, Q3, and Q4.",
    },
    {
        "id": 25,
        "category": "multijoin_containment",
        "difficulty": "hard",
        "name": "Products from high-risk suppliers in Northwest warehouses",
        "queries": [
            "List distinct Electronics products from high-risk suppliers that are stored in Northwest-region warehouses. Show product ID, product name, and category.",
            "List distinct products from high-risk suppliers that are stored in Northwest-region warehouses. Show product ID, product name, and category.",
            "List distinct Electronics products from high-risk suppliers. Show product ID, product name, and category.",
            "List distinct Electronics products stored in Northwest-region warehouses. Show product ID, product name, and category.",
        ],
        "expected_note": "Uses products -> suppliers and products <- inventory -> warehouses. Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 26,
        "category": "range_containment",
        "difficulty": "moderate",
        "name": "Sales-order grand-total ranges",
        "queries": [
            "List sales orders with grand total between 500 and 1000. Show order ID, order number, and grand total.",
            "List sales orders with grand total between 300 and 1500. Show order ID, order number, and grand total.",
            "List sales orders with grand total greater than or equal to 500. Show order ID, order number, and grand total.",
            "List sales orders with grand total less than or equal to 1000. Show order ID, order number, and grand total.",
        ],
        "expected_note": "The 500-1000 range should be contained in the broader 300-1500 range and in each one-sided bound.",
    },
    {
        "id": 27,
        "category": "range_containment",
        "difficulty": "moderate",
        "name": "Payment amount ranges",
        "queries": [
            "List payments with amount between 100 and 500. Show payment ID, payment number, and amount.",
            "List payments with amount between 50 and 1000. Show payment ID, payment number, and amount.",
            "List payments with amount greater than or equal to 100. Show payment ID, payment number, and amount.",
            "List payments with amount less than or equal to 500. Show payment ID, payment number, and amount.",
        ],
        "expected_note": "The 100-500 payment range should be contained in the other three.",
    },
    {
        "id": 28,
        "category": "range_containment",
        "difficulty": "moderate",
        "name": "Product sale-price ranges",
        "queries": [
            "List products with sale price between 50 and 200. Show product ID, product name, and sale price.",
            "List products with sale price between 25 and 300. Show product ID, product name, and sale price.",
            "List products with sale price greater than or equal to 50. Show product ID, product name, and sale price.",
            "List products with sale price less than or equal to 200. Show product ID, product name, and sale price.",
        ],
        "expected_note": "The 50-200 product range should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 29,
        "category": "range_containment",
        "difficulty": "moderate",
        "name": "Employee salary ranges",
        "queries": [
            "List employees with salary between 60000 and 90000. Show employee ID, full name, and salary.",
            "List employees with salary between 40000 and 120000. Show employee ID, full name, and salary.",
            "List employees with salary greater than or equal to 60000. Show employee ID, full name, and salary.",
            "List employees with salary less than or equal to 90000. Show employee ID, full name, and salary.",
        ],
        "expected_note": "The 60000-90000 salary range should be contained in the other three.",
    },
    {
        "id": 30,
        "category": "range_containment",
        "difficulty": "moderate",
        "name": "Inventory quantity ranges",
        "queries": [
            "List inventory records with quantity available between 20 and 100. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records with quantity available between 0 and 200. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records with quantity available greater than or equal to 20. Show inventory ID, product ID, warehouse ID, and quantity available.",
            "List inventory records with quantity available less than or equal to 100. Show inventory ID, product ID, warehouse ID, and quantity available.",
        ],
        "expected_note": "The 20-100 range should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 31,
        "category": "set_membership",
        "difficulty": "moderate",
        "name": "Customer loyalty-tier unions",
        "queries": [
            "List customers whose loyalty tier is Gold or Platinum. Show customer ID, full name, and loyalty tier.",
            "List Gold loyalty customers. Show customer ID, full name, and loyalty tier.",
            "List Platinum loyalty customers. Show customer ID, full name, and loyalty tier.",
            "List customers whose loyalty tier is Gold, Platinum, or Silver. Show customer ID, full name, and loyalty tier.",
        ],
        "expected_note": "Gold and Platinum are each contained in Gold-or-Platinum; Gold-or-Platinum is contained in Gold-or-Platinum-or-Silver.",
    },
    {
        "id": 32,
        "category": "set_membership",
        "difficulty": "moderate",
        "name": "Product-category unions",
        "queries": [
            "List products in the Electronics or Apparel category. Show product ID, product name, and category.",
            "List Electronics products. Show product ID, product name, and category.",
            "List Apparel products. Show product ID, product name, and category.",
            "List products in the Electronics, Apparel, or Office Supplies category. Show product ID, product name, and category.",
        ],
        "expected_note": "Electronics and Apparel are subsets of their union, which is a subset of the three-category union.",
    },
    {
        "id": 33,
        "category": "set_membership",
        "difficulty": "moderate",
        "name": "Sales-channel unions",
        "queries": [
            "List sales orders from the online or partner sales channel. Show order ID, order number, and sales channel.",
            "List online sales orders. Show order ID, order number, and sales channel.",
            "List partner-channel sales orders. Show order ID, order number, and sales channel.",
            "List sales orders from the online, partner, or retail sales channel. Show order ID, order number, and sales channel.",
        ],
        "expected_note": "Online and partner are each subsets of their union; the two-channel union is contained in the three-channel union.",
    },
    {
        "id": 34,
        "category": "set_membership",
        "difficulty": "moderate",
        "name": "Payment-status unions",
        "queries": [
            "List payments whose status is settled or failed. Show payment ID, payment number, and payment status.",
            "List settled payments. Show payment ID, payment number, and payment status.",
            "List failed payments. Show payment ID, payment number, and payment status.",
            "List all payments. Show payment ID, payment number, and payment status.",
        ],
        "expected_note": "Settled and failed are subsets of their union; the union is contained in all payments.",
    },
    {
        "id": 35,
        "category": "set_membership",
        "difficulty": "moderate",
        "name": "Shipment service-level unions",
        "queries": [
            "List shipments using overnight or freight service. Show shipment ID, shipment number, and service level.",
            "List shipments using overnight service. Show shipment ID, shipment number, and service level.",
            "List shipments using freight service. Show shipment ID, shipment number, and service level.",
            "List all shipments. Show shipment ID, shipment number, and service level.",
        ],
        "expected_note": "Overnight and freight are subsets of their union; the union is contained in all shipments.",
    },
    {
        "id": 36,
        "category": "group_having",
        "difficulty": "hard",
        "name": "Customers by order-count thresholds",
        "queries": [
            "List customers with more than 10 sales orders. Show customer ID, full name, and order count.",
            "List customers with more than 5 sales orders. Show customer ID, full name, and order count.",
            "List customers with more than 2 sales orders. Show customer ID, full name, and order count.",
            "List customers with more than 15 sales orders. Show customer ID, full name, and order count.",
        ],
        "expected_note": "OrderCount>15 is contained in >10, which is contained in >5, then >2.",
    },
    {
        "id": 37,
        "category": "group_having",
        "difficulty": "hard",
        "name": "Products by total quantity ordered",
        "queries": [
            "List products whose total quantity ordered is greater than 1000. Show product ID, product name, and total quantity ordered.",
            "List products whose total quantity ordered is greater than 500. Show product ID, product name, and total quantity ordered.",
            "List products whose total quantity ordered is greater than 100. Show product ID, product name, and total quantity ordered.",
            "List products whose total quantity ordered is greater than 2000. Show product ID, product name, and total quantity ordered.",
        ],
        "expected_note": "TotalQty>2000 is narrowest; >100 is broadest.",
    },
    {
        "id": 38,
        "category": "group_having",
        "difficulty": "hard",
        "name": "Warehouses by total inventory value",
        "queries": [
            "List warehouses whose total inventory value is greater than 1000000. Show warehouse ID, warehouse name, and total inventory value.",
            "List warehouses whose total inventory value is greater than 500000. Show warehouse ID, warehouse name, and total inventory value.",
            "List warehouses whose total inventory value is greater than 100000. Show warehouse ID, warehouse name, and total inventory value.",
            "List warehouses whose total inventory value is greater than 2000000. Show warehouse ID, warehouse name, and total inventory value.",
        ],
        "expected_note": "InventoryValue>2000000 is narrowest; >100000 is broadest.",
    },
    {
        "id": 39,
        "category": "group_having",
        "difficulty": "hard",
        "name": "Departments by average employee salary",
        "queries": [
            "List departments whose average employee salary is greater than 100000. Show department ID, department name, and average salary.",
            "List departments whose average employee salary is greater than 80000. Show department ID, department name, and average salary.",
            "List departments whose average employee salary is greater than 60000. Show department ID, department name, and average salary.",
            "List departments whose average employee salary is greater than 120000. Show department ID, department name, and average salary.",
        ],
        "expected_note": "AverageSalary>120000 is narrowest; >60000 is broadest.",
    },
    {
        "id": 40,
        "category": "group_having",
        "difficulty": "hard",
        "name": "Suppliers by product-count thresholds",
        "queries": [
            "List suppliers that provide more than 20 products. Show supplier ID, supplier name, and product count.",
            "List suppliers that provide more than 10 products. Show supplier ID, supplier name, and product count.",
            "List suppliers that provide more than 5 products. Show supplier ID, supplier name, and product count.",
            "List suppliers that provide more than 30 products. Show supplier ID, supplier name, and product count.",
        ],
        "expected_note": "ProductCount>30 is narrowest; >5 is broadest.",
    },
    {
        "id": 41,
        "category": "existence_containment",
        "difficulty": "hard",
        "name": "Customers with delivered orders",
        "queries": [
            "List distinct customers who have at least one delivered online sales order. Show customer ID and full name.",
            "List distinct customers who have at least one delivered sales order. Show customer ID and full name.",
            "List distinct customers who have at least one online sales order. Show customer ID and full name.",
            "List distinct customers who have at least one sales order. Show customer ID and full name.",
        ],
        "expected_note": "Delivered+online customers should be contained in delivered-order customers, online-order customers, and any-order customers.",
    },
    {
        "id": 42,
        "category": "existence_containment",
        "difficulty": "hard",
        "name": "Products with inventory in special warehouses",
        "queries": [
            "List distinct products that have inventory in temperature-controlled Northwest-region warehouses. Show product ID and product name.",
            "List distinct products that have inventory in temperature-controlled warehouses. Show product ID and product name.",
            "List distinct products that have inventory in Northwest-region warehouses. Show product ID and product name.",
            "List distinct products that have any inventory record. Show product ID and product name.",
        ],
        "expected_note": "Temperature-controlled+Northwest inventory products should be contained in each single condition and in all inventoried products.",
    },
    {
        "id": 43,
        "category": "existence_containment",
        "difficulty": "hard",
        "name": "Employees who manage warehouses",
        "queries": [
            "List distinct active employees who manage temperature-controlled warehouses. Show employee ID and full name.",
            "List distinct employees who manage temperature-controlled warehouses. Show employee ID and full name.",
            "List distinct active employees who manage any warehouse. Show employee ID and full name.",
            "List distinct employees who manage any warehouse. Show employee ID and full name.",
        ],
        "expected_note": "Active managers of temperature-controlled warehouses should be contained in the other three manager sets.",
    },
    {
        "id": 44,
        "category": "existence_containment",
        "difficulty": "hard",
        "name": "Suppliers with products in multiple categories",
        "queries": [
            "List distinct suppliers that provide at least one Electronics product and at least one Apparel product. Show supplier ID and supplier name.",
            "List distinct suppliers that provide at least one Electronics product. Show supplier ID and supplier name.",
            "List distinct suppliers that provide at least one Apparel product. Show supplier ID and supplier name.",
            "List distinct suppliers that provide at least one product. Show supplier ID and supplier name.",
        ],
        "expected_note": "Suppliers with both categories should be contained in each single-category supplier set and in all product suppliers.",
    },
    {
        "id": 45,
        "category": "existence_containment",
        "difficulty": "hard",
        "name": "Customers with settled payments",
        "queries": [
            "List distinct customers who have at least one settled credit-card payment. Show customer ID and full name.",
            "List distinct customers who have at least one settled payment. Show customer ID and full name.",
            "List distinct customers who have at least one credit-card payment. Show customer ID and full name.",
            "List distinct customers who have at least one payment. Show customer ID and full name.",
        ],
        "expected_note": "Settled credit-card customers should be contained in settled-payment, credit-card-payment, and any-payment customer sets.",
    },
    {
        "id": 46,
        "category": "equivalence_hierarchy",
        "difficulty": "moderate",
        "name": "Equivalent active-customer paraphrases",
        "queries": [
            "List customers whose account status is active. Show customer ID and full name.",
            "Show all active customer accounts. Return customer ID and full name.",
            "List active enterprise customers. Show customer ID and full name.",
            "List all customers. Show customer ID and full name.",
        ],
        "expected_note": "Q1 and Q2 should be equivalent; active enterprise is contained in them; both are contained in all customers.",
    },
    {
        "id": 47,
        "category": "equivalence_hierarchy",
        "difficulty": "moderate",
        "name": "Equivalent delivered-shipment paraphrases",
        "queries": [
            "List shipments whose shipment status is delivered. Show shipment ID and shipment number.",
            "Show all shipments that have been delivered. Return shipment ID and shipment number.",
            "List delivered shipments that required a signature. Show shipment ID and shipment number.",
            "List all shipments. Show shipment ID and shipment number.",
        ],
        "expected_note": "Q1 and Q2 should be equivalent; delivered+signature is contained in them; delivered is contained in all shipments.",
    },
    {
        "id": 48,
        "category": "equivalence_hierarchy",
        "difficulty": "hard",
        "name": "Orders by shipping-address properties",
        "queries": [
            "List delivered sales orders whose shipping address is residential and in Washington state. Show order ID and order number.",
            "List delivered sales orders whose shipping address is in Washington state. Show order ID and order number.",
            "List sales orders whose shipping address is residential and in Washington state. Show order ID and order number.",
            "List delivered sales orders. Show order ID and order number.",
        ],
        "expected_note": "Uses sales_orders.shipping_address_id -> addresses.address_id. Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 49,
        "category": "equivalence_hierarchy",
        "difficulty": "hard",
        "name": "Payments tied to delivered orders",
        "queries": [
            "List settled credit-card payments for delivered sales orders. Show payment ID, payment number, and amount.",
            "List settled payments for delivered sales orders. Show payment ID, payment number, and amount.",
            "List credit-card payments for delivered sales orders. Show payment ID, payment number, and amount.",
            "List all payments for delivered sales orders. Show payment ID, payment number, and amount.",
        ],
        "expected_note": "Uses payments.order_id -> sales_orders.order_id. Q1 should be contained in Q2, Q3, and Q4.",
    },
    {
        "id": 50,
        "category": "equivalence_hierarchy",
        "difficulty": "hard",
        "name": "High-risk supplier and temperature-controlled inventory hierarchy",
        "queries": [
            "List distinct Electronics products from high-risk suppliers that have inventory below 50 units available in temperature-controlled warehouses. Show product ID and product name.",
            "List distinct products from high-risk suppliers that have inventory below 50 units available in temperature-controlled warehouses. Show product ID and product name.",
            "List distinct Electronics products from high-risk suppliers that have inventory in temperature-controlled warehouses. Show product ID and product name.",
            "List distinct Electronics products that have inventory below 50 units available in temperature-controlled warehouses. Show product ID and product name.",
        ],
        "expected_note": "Uses products -> suppliers and products <- inventory -> warehouses. Q1 should be contained in Q2, Q3, and Q4.",
    },
]


def post_json(url: str, payload: dict[str, Any], *, timeout: int, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"success": False, "raw_text": raw}
            body["_http_status"] = response.status
            return body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"success": False, "raw_text": raw}
        body["_http_status"] = exc.code
        return body
    except Exception as exc:
        return {
            "success": False,
            "_http_status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def qlabel(index: Any) -> str:
    try:
        value = int(index)
        return f"Q{value + 1}" if value == 0 else f"Q{value}"
    except (TypeError, ValueError):
        return str(index)


def summarize_query_result(result: dict[str, Any], fallback_index: int) -> list[str]:
    question = result.get("question") or ""
    lines = [f"Q{fallback_index}. {question}"]
    lines.append(
        "   "
        f"success={result.get('success')} | safe={result.get('safe')} | "
        f"rows={result.get('row_count')} | empty={result.get('empty_result')} | "
        f"source={result.get('selected_candidate_source')} | "
        f"score={result.get('selected_candidate_score')}"
    )
    lines.append(f"   columns: {result.get('execution_columns')}")
    lines.append(f"   sql: {result.get('sql')}")
    if result.get("warnings"):
        lines.append(f"   warnings: {result.get('warnings')}")
    if result.get("safety_reason"):
        lines.append(f"   safety_reason: {result.get('safety_reason')}")
    return lines


def summarize_query_summary(summary: dict[str, Any]) -> str:
    return (
        f"Q{int(summary.get('query_index', 0)) + 1} | "
        f"status={summary.get('status')} | "
        f"empty={summary.get('empty_result')} | "
        f"contained_in={summary.get('contained_in') or '-'} | "
        f"contains={summary.get('contains') or '-'} | "
        f"equivalent_to={summary.get('equivalent_to') or '-'} | "
        f"incomparable_with={summary.get('incomparable_with') or '-'} | "
        f"unknown_with={summary.get('unknown_with') or '-'}"
    )


def summarize_pairwise(pair: dict[str, Any]) -> list[str]:
    a = int(pair.get("query_a_index", 0)) + 1
    b = int(pair.get("query_b_index", 0)) + 1
    lines = [f"Q{a} vs Q{b}: {pair.get('relationship')}"]
    if pair.get("explanation"):
        lines.append(f"   {pair.get('explanation')}")
    a_rows = pair.get("a_minus_b_rows") or []
    b_rows = pair.get("b_minus_a_rows") or []
    if a_rows:
        lines.append(f"   Q{a} minus Q{b} sample: {a_rows[:5]}")
    if b_rows:
        lines.append(f"   Q{b} minus Q{a} sample: {b_rows[:5]}")
    return lines


def write_case_report(handle: Any, case: dict[str, Any], response: dict[str, Any], elapsed: float) -> None:
    handle.write("\n" + "=" * 110 + "\n")
    handle.write(f"TEST {case['id']:02d}: {case['name']}\n")
    handle.write("=" * 110 + "\n")
    handle.write(f"Category: {case['category']}\n")
    handle.write(f"Difficulty: {case['difficulty']}\n")
    handle.write(f"Expected note: {case['expected_note']}\n")
    handle.write(f"HTTP status: {response.get('_http_status')}\n")
    handle.write(f"Endpoint success: {response.get('success')}\n")
    handle.write(f"Elapsed seconds: {elapsed:.2f}\n")
    handle.write(
        f"proof_type: {response.get('proof_type')} | "
        f"checked_on_current_database: {response.get('checked_on_current_database')}\n"
    )
    if response.get("limitations"):
        handle.write(f"limitations: {response.get('limitations')}\n")
    if response.get("warnings"):
        handle.write(f"top-level warnings: {response.get('warnings')}\n")

    handle.write("\nINPUT QUERIES\n")
    for index, query in enumerate(case["queries"], start=1):
        handle.write(f"  Q{index}: {query}\n")

    handle.write("\nGENERATED SQL / QUERY RESULTS\n")
    query_results = response.get("query_results") or []
    if query_results:
        for index, result in enumerate(query_results, start=1):
            for line in summarize_query_result(result, index):
                handle.write(line + "\n")
    else:
        handle.write("  No query_results returned.\n")

    handle.write("\nRELATIONSHIP SUMMARY\n")
    summaries = response.get("query_summaries") or []
    if summaries:
        for summary in summaries:
            handle.write("  " + summarize_query_summary(summary) + "\n")
    else:
        handle.write("  No query_summaries returned.\n")

    handle.write("\nPAIRWISE RELATIONSHIPS\n")
    pairs = response.get("pairwise_relationships") or []
    if pairs:
        for pair in pairs:
            for line in summarize_pairwise(pair):
                handle.write("  " + line + "\n")
    else:
        handle.write("  No pairwise_relationships returned.\n")

    handle.write("\nRAW RESPONSE JSON\n")
    handle.write(json.dumps(response, indent=2, ensure_ascii=False))
    handle.write("\n")


def filtered_cases(only_category: str | None, start: int | None, end: int | None) -> list[dict[str, Any]]:
    cases = list(TEST_CASES)
    if only_category:
        cases = [case for case in cases if case["category"] == only_category]
    if start is not None:
        cases = [case for case in cases if case["id"] >= start]
    if end is not None:
        cases = [case for case in cases if case["id"] <= end]
    return cases


def discover_trace(output_dir: Path, run_id: str, database_id: int, wait_seconds: float = 3.0) -> Path | None:
    deadline = time.time() + wait_seconds
    pattern = f"{run_id}_full_trace_db{database_id}_*.txt"
    while time.time() <= deadline:
        matches = sorted(output_dir.glob(pattern), key=lambda path: path.stat().st_mtime)
        if matches:
            return matches[-1]
        time.sleep(0.25)
    return None


def main() -> int:
    categories = sorted({case["category"] for case in TEST_CASES})
    parser = argparse.ArgumentParser(description="Run 50 natural-language containment cases against Northstar DB53.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--db-id", type=int, default=53)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--only-category", choices=categories, default=None)
    parser.add_argument("--allow-missing-trace", action="store_true")
    args = parser.parse_args()

    cases = filtered_cases(args.only_category, args.start, args.end)
    if not cases:
        print("No test cases selected.")
        return 2

    actual_ids = [case["id"] for case in TEST_CASES]
    if actual_ids != list(range(1, 51)):
        raise RuntimeError("TEST_CASES must contain exactly IDs 1 through 50 in order.")

    base_url = args.base_url.rstrip("/")
    endpoint = f"{base_url}/database/{args.db_id}/check_containment_batch"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"northstar_containment_50_db{args.db_id}_{timestamp}"
    output_dir = Path("benchmarks") / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f"{run_id}.txt"

    category_counts = collections.Counter(case["category"] for case in cases)
    category_stats: dict[str, dict[str, Any]] = {
        category: {
            "cases": 0,
            "endpoint_success": 0,
            "endpoint_failure": 0,
            "query_success": 0,
            "query_failure": 0,
            "safe_queries": 0,
            "unsafe_queries": 0,
            "pair_relationships": collections.Counter(),
        }
        for category in category_counts
    }

    successful_cases = 0
    failed_cases = 0
    request_failures = 0
    all_pair_relationships: collections.Counter[str] = collections.Counter()

    print("=" * 110)
    print("SpiderSQL Northstar Natural-Language Containment Benchmark")
    print(f"Database ID: {args.db_id}")
    print(f"Endpoint:    {endpoint}")
    print(f"Trace run:   {run_id}")
    print(f"Selected:    {len(cases)} case(s)")
    print(f"Timeout:     {args.timeout}s per case")
    print("=" * 110)

    with result_path.open("w", encoding="utf-8") as report:
        report.write("SpiderSQL Northstar Containment Benchmark - 50 Natural-Language Cases\n")
        report.write(f"Started: {datetime.now().isoformat(timespec='seconds')}\n")
        report.write(f"Database ID: {args.db_id}\n")
        report.write(f"Endpoint: {endpoint}\n")
        report.write(f"Trace run ID: {run_id}\n")
        report.write(f"Selected case count: {len(cases)}\n")
        report.write("\nManual correctness note:\n")
        report.write("Endpoint success is not semantic correctness. Inspect generated SQL, relationships, hierarchy, and counterexamples.\n")
        report.write("Contained/equivalent results are current-database evidence, not universal symbolic proofs.\n")
        report.write("\nSelected category counts:\n")
        for category, count in sorted(category_counts.items()):
            report.write(f"  {category}: {count}\n")

        for case in cases:
            print()
            print("-" * 110)
            print(f"TEST {case['id']:02d}: {case['name']} [{case['category']} / {case['difficulty']}]")
            for index, query in enumerate(case["queries"], start=1):
                print(f"  Q{index}: {query}")

            headers = {
                "X-SpiderSQL-Test-ID": str(case["id"]),
                "X-SpiderSQL-Category": case["category"],
                "X-SpiderSQL-Difficulty": case["difficulty"],
                "X-SpiderSQL-Trace-Run": run_id,
            }
            started = time.time()
            response = post_json(endpoint, {"queries": case["queries"]}, timeout=args.timeout, headers=headers)
            elapsed = time.time() - started

            stats = category_stats[case["category"]]
            stats["cases"] += 1
            endpoint_success = response.get("success") is True
            if endpoint_success:
                successful_cases += 1
                stats["endpoint_success"] += 1
            else:
                failed_cases += 1
                stats["endpoint_failure"] += 1
            if response.get("_http_status") is None and not endpoint_success:
                request_failures += 1

            for query_result in response.get("query_results") or []:
                stats["query_success" if query_result.get("success") is True else "query_failure"] += 1
                stats["safe_queries" if query_result.get("safe") is True else "unsafe_queries"] += 1
            for pair in response.get("pairwise_relationships") or []:
                relationship = str(pair.get("relationship") or "missing")
                stats["pair_relationships"][relationship] += 1
                all_pair_relationships[relationship] += 1

            print(f"success:         {response.get('success')}")
            print(f"http_status:     {response.get('_http_status')}")
            print(f"elapsed_seconds: {elapsed:.2f}")
            print(f"query_results:   {len(response.get('query_results') or [])} | pairwise: {len(response.get('pairwise_relationships') or [])}")
            write_case_report(report, case, response, elapsed)
            report.flush()
            time.sleep(args.sleep)

        report.write("\n" + "=" * 110 + "\n")
        report.write("FINAL RESULT SUMMARY\n")
        report.write("=" * 110 + "\n")
        report.write(f"Selected cases: {len(cases)}\n")
        report.write(f"Successful endpoint responses: {successful_cases}\n")
        report.write(f"Failed endpoint responses: {failed_cases}\n")
        report.write(f"Timeout/request failures: {request_failures}\n")
        report.write("\nCATEGORY SUMMARY\n")
        for category in sorted(category_stats):
            stats = category_stats[category]
            report.write(f"\n{category}\n")
            for key in ["cases", "endpoint_success", "endpoint_failure", "query_success", "query_failure", "safe_queries", "unsafe_queries"]:
                report.write(f"  {key}: {stats[key]}\n")
            report.write("  pair_relationships:\n")
            if stats["pair_relationships"]:
                for relationship, count in sorted(stats["pair_relationships"].items()):
                    report.write(f"    {relationship}: {count}\n")
            else:
                report.write("    none\n")
        report.write("\nALL PAIRWISE RELATIONSHIP COUNTS\n")
        if all_pair_relationships:
            for relationship, count in sorted(all_pair_relationships.items()):
                report.write(f"  {relationship}: {count}\n")
        else:
            report.write("  none\n")

    trace_path = discover_trace(output_dir, run_id, args.db_id)
    print()
    print("=" * 110)
    print("DONE")
    print(f"Successful endpoint responses: {successful_cases}/{len(cases)}")
    print(f"Failed endpoint responses:     {failed_cases}/{len(cases)}")
    print(f"Timeout/request failures:      {request_failures}/{len(cases)}")
    print(f"Final result saved to:         {result_path}")
    if trace_path is not None:
        print(f"Full backend trace saved to:   {trace_path}")
    else:
        print("Full backend trace:            NOT FOUND")
        print("Start the backend with SPIDERSQL_FULL_TRACE=true before running this file.")
        print(f"Expected filename pattern:     {run_id}_full_trace_db{args.db_id}_*.txt")
    print("=" * 110)

    if failed_cases:
        return 1
    if trace_path is None and not args.allow_missing_trace:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
