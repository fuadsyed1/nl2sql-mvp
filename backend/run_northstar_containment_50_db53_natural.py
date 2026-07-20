#!/usr/bin/env python3
"""
SpiderSQL DB53: 50 realistic natural-language containment cases.

Design:
- 50 cases, 4 natural-language queries per case (200 total queries).
- Queries inside a case target the same result entity/grain, but are not simple
  copies with different threshold values.
- Containment must be inferred from different conditions, joins, existence
  requirements, grouping, set logic, or subqueries.
- Every multi-table query follows a confirmed DB53 relationship path.

Run while the backend is already running with full tracing enabled:

    python run_northstar_containment_50_db53_natural.py

Outputs:
    benchmarks/results/northstar_containment_50_db53_natural_<timestamp>.txt

The backend should separately write:
    benchmarks/results/
    northstar_containment_50_db53_natural_<timestamp>_full_trace_db53_<timestamp>.txt
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


TEST_CASES: list[dict[str, Any]] = [
    # =========================================================================
    # CUSTOMER SETS
    # =========================================================================
    {
        "id": 1,
        "category": "customer_sets",
        "difficulty": "hard",
        "name": "Gold customers with delivered online activity",
        "queries": [
            "Which active Gold customers placed a delivered online order in 2025?",
            "Which Gold customers placed a delivered order in 2025?",
            "Which active customers placed an online order in 2025?",
            "Which customers had a failed payment and no delivered orders?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not implied by Q1, Q2, or Q3.",
        ],
    },
    {
        "id": 2,
        "category": "customer_sets",
        "difficulty": "hard",
        "name": "Enterprise customers and settled card payments",
        "queries": [
            "Which enterprise customers have made a settled credit-card payment?",
            "Which customers have made at least one settled payment?",
            "Which enterprise customers have ever paid by credit card?",
            "Which customers have payments but have never had one settle successfully?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different customer set.",
        ],
    },
    {
        "id": 3,
        "category": "customer_sets",
        "difficulty": "hard",
        "name": "Residential Washington deliveries",
        "queries": [
            "Which active customers received a delivered order at a residential address in Washington?",
            "Which customers received a delivered order in Washington?",
            "Which active customers have used a residential shipping address?",
            "Which customers used different states for billing and shipping on an order?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is generally incomparable with the first three.",
        ],
    },
    {
        "id": 4,
        "category": "customer_sets",
        "difficulty": "hard",
        "name": "Customers across product categories",
        "queries": [
            "Which customers bought both Electronics and Outdoors products but never bought Apparel?",
            "Which customers have bought an Electronics product?",
            "Which customers have bought an Outdoors product?",
            "Which customers bought Apparel but have never bought Electronics?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q1 and Q4 should be disjoint.",
        ],
    },
    {
        "id": 5,
        "category": "customer_sets",
        "difficulty": "hard",
        "name": "Refunded Gold-customer orders",
        "queries": [
            "Which Gold customers received a refund on an order that was eventually delivered?",
            "Which customers have received any refund?",
            "Which Gold customers have had a delivered order?",
            "Which customers have settled payments but no refunded payments?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not a superset of Q1.",
        ],
    },

    # =========================================================================
    # SALES-ORDER SETS
    # =========================================================================
    {
        "id": 6,
        "category": "sales_order_sets",
        "difficulty": "hard",
        "name": "Platinum high-priority online orders",
        "queries": [
            "Which high-priority online orders from Platinum customers were delivered?",
            "Which online orders were delivered?",
            "Which high-priority orders were placed by Platinum customers?",
            "Which store orders were cancelled?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different order population.",
        ],
    },
    {
        "id": 7,
        "category": "sales_order_sets",
        "difficulty": "hard",
        "name": "Orders containing high-risk Electronics products",
        "queries": [
            "Which orders included an Electronics product supplied by a high-risk supplier?",
            "Which orders included at least one Electronics product?",
            "Which orders included a product from a high-risk supplier?",
            "Which orders contained Apparel products from low-risk suppliers?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is generally incomparable.",
        ],
    },
    {
        "id": 8,
        "category": "sales_order_sets",
        "difficulty": "hard",
        "name": "Late signature-required deliveries",
        "queries": [
            "Which orders had a delivered shipment that arrived late and required a signature?",
            "Which orders had a shipment delivered after its estimated delivery date?",
            "Which orders had a shipment that required a signature?",
            "Which orders still have no shipment?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should be disjoint from Q1, Q2, and Q3.",
        ],
    },
    {
        "id": 9,
        "category": "sales_order_sets",
        "difficulty": "hard",
        "name": "Settled card payments with refunds",
        "queries": [
            "Which orders have a settled credit-card payment with a positive refunded amount?",
            "Which orders have at least one settled payment?",
            "Which orders have a credit-card payment that was partly or fully refunded?",
            "Which orders have failed payments and no successful payment?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different order set.",
        ],
    },
    {
        "id": 10,
        "category": "sales_order_sets",
        "difficulty": "hard",
        "name": "Temperature-controlled Washington shipments",
        "queries": [
            "Which orders were shipped from a temperature-controlled Northwest warehouse to a residential address in Washington?",
            "Which orders were shipped from a temperature-controlled warehouse?",
            "Which orders were sent to a residential address in Washington?",
            "Which orders have never been shipped?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should be disjoint from Q1.",
        ],
    },

    # =========================================================================
    # PRODUCT SETS
    # =========================================================================
    {
        "id": 11,
        "category": "product_sets",
        "difficulty": "hard",
        "name": "Discontinued products still being sold",
        "queries": [
            "Which discontinued products still have available inventory and were sold during 2025?",
            "Which discontinued products still have available inventory?",
            "Which products were sold during 2025?",
            "Which products have never been ordered and have no inventory?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is disjoint from Q1.",
        ],
    },
    {
        "id": 12,
        "category": "product_sets",
        "difficulty": "hard",
        "name": "Electronics from high-risk suppliers",
        "queries": [
            "Which Electronics products from high-risk suppliers are stocked in temperature-controlled warehouses?",
            "Which Electronics products come from high-risk suppliers?",
            "Which products are stocked in temperature-controlled warehouses?",
            "Which Apparel products come from low-risk suppliers?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is generally incomparable.",
        ],
    },
    {
        "id": 13,
        "category": "product_sets",
        "difficulty": "hard",
        "name": "Products sold across channels",
        "queries": [
            "Which products were sold through both online and store orders but never through partner orders?",
            "Which products were sold through online orders?",
            "Which products were sold through store orders?",
            "Which products were sold through partner orders but never online?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q1 and Q4 should be disjoint.",
        ],
    },
    {
        "id": 14,
        "category": "product_sets",
        "difficulty": "hard",
        "name": "Ordered products with inadequate stock",
        "queries": [
            "Which low-stock products have total ordered quantity greater than their current available inventory?",
            "Which products have been ordered in a quantity greater than their available inventory?",
            "Which products are currently low in stock?",
            "Which products have never appeared on an order?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should not contain Q1.",
        ],
    },
    {
        "id": 15,
        "category": "product_sets",
        "difficulty": "hard",
        "name": "Products above category benchmarks",
        "queries": [
            "Which products are priced above their category average and also have a gross margin above their category average?",
            "Which products are priced above the average sale price for their category?",
            "Which products have a gross margin percentage above their category average?",
            "Which products are priced below the overall average sale price?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not implied by the first three.",
        ],
    },

    # =========================================================================
    # SUPPLIER SETS
    # =========================================================================
    {
        "id": 16,
        "category": "supplier_sets",
        "difficulty": "hard",
        "name": "High-risk suppliers with active sales",
        "queries": [
            "Which active high-risk suppliers have low-stock products that appeared on delivered orders?",
            "Which high-risk suppliers provide at least one low-stock product?",
            "Which active suppliers had a product appear on a delivered order?",
            "Which inactive suppliers have no products on any order?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different supplier set.",
        ],
    },
    {
        "id": 17,
        "category": "supplier_sets",
        "difficulty": "hard",
        "name": "Widely stocked suppliers selling to Gold customers",
        "queries": [
            "Which suppliers have products stored in at least three warehouses and sold to Gold customers?",
            "Which suppliers have products stored in at least three different warehouses?",
            "Which suppliers have sold a product to a Gold customer?",
            "Which suppliers have products with no inventory records?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not a superset of Q1.",
        ],
    },
    {
        "id": 18,
        "category": "supplier_sets",
        "difficulty": "hard",
        "name": "Suppliers spanning product categories",
        "queries": [
            "Which suppliers provide both Electronics and Apparel products but no Automotive products?",
            "Which suppliers provide Electronics products?",
            "Which suppliers provide Apparel products?",
            "Which suppliers provide Automotive products and no Electronics products?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q1 and Q4 should be disjoint.",
        ],
    },
    {
        "id": 19,
        "category": "supplier_sets",
        "difficulty": "hard",
        "name": "Manufacturer pricing and rating",
        "queries": [
            "Which manufacturer suppliers with rating 1 provide a product priced above 500 dollars?",
            "Which manufacturer suppliers have rating 1?",
            "Which suppliers provide at least one product priced above 500 dollars?",
            "Which inactive distributor suppliers provide no products above 500 dollars?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different supplier population.",
        ],
    },
    {
        "id": 20,
        "category": "supplier_sets",
        "difficulty": "hard",
        "name": "Suppliers above revenue and price benchmarks",
        "queries": [
            "Which suppliers have above-average product revenue and an average product sale price above the overall product average?",
            "Which suppliers have product revenue above the average supplier revenue?",
            "Which suppliers have an average product sale price above the overall product average?",
            "Which suppliers have products that have never been ordered?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not implied by the first three.",
        ],
    },

    # =========================================================================
    # EMPLOYEE SETS
    # =========================================================================
    {
        "id": 21,
        "category": "employee_sets",
        "difficulty": "hard",
        "name": "Highly paid employees in compliant departments",
        "queries": [
            "Which active full-time employees earn more than 100,000 dollars in departments with high compliance?",
            "Which active full-time employees work in high-compliance departments?",
            "Which employees in high-compliance departments earn more than 100,000 dollars?",
            "Which contractors work in departments with low compliance?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is generally incomparable.",
        ],
    },
    {
        "id": 22,
        "category": "employee_sets",
        "difficulty": "hard",
        "name": "Warehouse managers who also sell",
        "queries": [
            "Which employees both manage a warehouse and have handled at least one sales order?",
            "Which employees manage a warehouse?",
            "Which employees have handled a sales order?",
            "Which employees neither manage a warehouse nor appear as a sales representative?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should be disjoint from Q1.",
        ],
    },
    {
        "id": 23,
        "category": "employee_sets",
        "difficulty": "hard",
        "name": "Managers serving Platinum customers",
        "queries": [
            "Which employees manage a temperature-controlled warehouse and handled a delivered order for a Platinum customer?",
            "Which employees handled a delivered order for a Platinum customer?",
            "Which employees manage a temperature-controlled warehouse?",
            "Which employees handled cancelled Bronze-customer orders but manage no warehouse?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different employee set.",
        ],
    },
    {
        "id": 24,
        "category": "employee_sets",
        "difficulty": "hard",
        "name": "Employees above department benchmarks",
        "queries": [
            "Which employees earn more than their department average and have a performance rating above 4?",
            "Which employees earn more than the average salary in their department?",
            "Which employees have a performance rating above 4?",
            "Which employees earn below the company average and have a performance rating no higher than 3?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not implied by the first three.",
        ],
    },
    {
        "id": 25,
        "category": "employee_sets",
        "difficulty": "hard",
        "name": "Employees separated from their managers",
        "queries": [
            "Which active employees work in a different state from their manager and belong to the Corporate division?",
            "Which active employees work in a different state from their manager?",
            "Which employees belong to a department in the Corporate division?",
            "Which employees have no manager assigned?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different employee set.",
        ],
    },

    # =========================================================================
    # WAREHOUSE SETS
    # =========================================================================
    {
        "id": 26,
        "category": "warehouse_sets",
        "difficulty": "hard",
        "name": "Northwest warehouses with low-stock Electronics",
        "queries": [
            "Which open temperature-controlled warehouses in the Northwest region hold low-stock Electronics products?",
            "Which open temperature-controlled warehouses are in the Northwest region?",
            "Which warehouses hold at least one low-stock Electronics product?",
            "Which closed warehouses have no inventory records?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different warehouse population.",
        ],
    },
    {
        "id": 27,
        "category": "warehouse_sets",
        "difficulty": "hard",
        "name": "Warehouses serving Washington with risky stock",
        "queries": [
            "Which warehouses delivered shipments to Washington and hold products from high-risk suppliers?",
            "Which warehouses have delivered at least one shipment to Washington?",
            "Which warehouses hold products from high-risk suppliers?",
            "Which warehouses have inventory but have never originated a shipment?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is generally incomparable.",
        ],
    },
    {
        "id": 28,
        "category": "warehouse_sets",
        "difficulty": "hard",
        "name": "Warehouses supporting multiple sales channels",
        "queries": [
            "Which warehouses stocked products sold through both online and partner orders but never through store orders?",
            "Which warehouses stocked products sold online?",
            "Which warehouses stocked products sold through the partner channel?",
            "Which warehouses stocked products sold through store orders but never online?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q1 and Q4 should be disjoint.",
        ],
    },
    {
        "id": 29,
        "category": "warehouse_sets",
        "difficulty": "hard",
        "name": "Warehouses under inventory pressure",
        "queries": [
            "Which warehouses have shipped more units than their current available inventory and are over 80 percent utilized?",
            "Which warehouses have shipped more units than they currently have available?",
            "Which warehouses are more than 80 percent utilized?",
            "Which warehouses have never shipped an order item and are below 50 percent utilization?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not implied by the first three.",
        ],
    },
    {
        "id": 30,
        "category": "warehouse_sets",
        "difficulty": "hard",
        "name": "Regions handling selected categories",
        "queries": [
            "Which warehouse regions handled both Electronics and Apparel items but no Automotive items?",
            "Which warehouse regions handled Electronics items?",
            "Which warehouse regions handled Apparel items?",
            "Which warehouse regions handled Automotive items but no Electronics items?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q1 and Q4 should be disjoint.",
        ],
    },

    # =========================================================================
    # SHIPMENT SETS
    # =========================================================================
    {
        "id": 31,
        "category": "shipment_sets",
        "difficulty": "moderate",
        "name": "Late signed deliveries",
        "queries": [
            "Which delivered shipments arrived late and required a signature?",
            "Which delivered shipments arrived after their estimated delivery date?",
            "Which shipments required a signature?",
            "Which shipments have not been delivered?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q1 and Q4 should be disjoint.",
        ],
    },
    {
        "id": 32,
        "category": "shipment_sets",
        "difficulty": "moderate",
        "name": "FedEx overnight deliveries to Washington",
        "queries": [
            "Which FedEx shipments used overnight service and went to Washington?",
            "Which FedEx shipments went to Washington?",
            "Which overnight shipments went to Washington?",
            "Which UPS freight shipments went to Idaho?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different shipment set.",
        ],
    },
    {
        "id": 33,
        "category": "shipment_sets",
        "difficulty": "hard",
        "name": "Shipments for Gold online Electronics orders",
        "queries": [
            "Which shipments belong to online orders from Gold customers that contained Electronics products?",
            "Which shipments belong to online orders from Gold customers?",
            "Which shipments belong to orders containing Electronics products?",
            "Which shipments belong to store orders from Bronze customers with no Electronics items?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different shipment set.",
        ],
    },
    {
        "id": 34,
        "category": "shipment_sets",
        "difficulty": "hard",
        "name": "Temperature-control agreement",
        "queries": [
            "Which temperature-controlled shipments originated from temperature-controlled warehouses?",
            "Which shipments were marked as temperature controlled?",
            "Which shipments originated from temperature-controlled warehouses?",
            "Which hazmat shipments were not temperature controlled and came from a non-temperature-controlled warehouse?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different shipment set.",
        ],
    },
    {
        "id": 35,
        "category": "shipment_sets",
        "difficulty": "hard",
        "name": "Shipments above carrier benchmarks",
        "queries": [
            "Which shipments cost more than their carrier average and also weigh more than the average shipment for that carrier?",
            "Which shipments cost more than the average shipping cost for the same carrier?",
            "Which shipments weigh more than the average shipment weight for the same carrier?",
            "Which shipments are below both carrier averages for cost and weight?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not implied by the first three.",
        ],
    },

    # =========================================================================
    # PAYMENT SETS
    # =========================================================================
    {
        "id": 36,
        "category": "payment_sets",
        "difficulty": "hard",
        "name": "Enterprise card payments in 2025",
        "queries": [
            "Which settled credit-card payments came from enterprise customers during 2025?",
            "Which settled payments came from enterprise customers during 2025?",
            "Which credit-card payments came from enterprise customers during 2025?",
            "Which failed ACH payments came from individual customers?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different payment set.",
        ],
    },
    {
        "id": 37,
        "category": "payment_sets",
        "difficulty": "hard",
        "name": "Refunds tied to delivered online orders",
        "queries": [
            "Which refunded payments belong to delivered online orders?",
            "Which payments have a positive refunded amount?",
            "Which payments belong to delivered online orders?",
            "Which settled payments belong to cancelled orders and have no refund?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different payment set.",
        ],
    },
    {
        "id": 38,
        "category": "payment_sets",
        "difficulty": "moderate",
        "name": "High-fraud payments with fees",
        "queries": [
            "Which payments have a fraud score above 80 and a positive processing fee?",
            "Which payments have a fraud score above 80?",
            "Which payments were charged a processing fee?",
            "Which payments have no fee and a fraud score below 20?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is not implied by the first three.",
        ],
    },
    {
        "id": 39,
        "category": "payment_sets",
        "difficulty": "hard",
        "name": "Gold-customer payments above method averages",
        "queries": [
            "Which payments from Gold customers are larger than the average payment for the same payment method?",
            "Which payments are larger than the average for their payment method?",
            "Which payments were made by Gold customers?",
            "Which payments from Bronze customers are below their payment-method average?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is a different payment set.",
        ],
    },
    {
        "id": 40,
        "category": "payment_sets",
        "difficulty": "hard",
        "name": "Payment providers with volume and low refunds",
        "queries": [
            "Which payment providers settled more than 50,000 dollars and kept their refund rate below 5 percent?",
            "Which payment providers settled more than 50,000 dollars?",
            "Which payment providers have a refund rate below 5 percent?",
            "Which payment providers processed more failed money than settled money?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is generally incomparable.",
        ],
    },

    # =========================================================================
    # GROUPED / AGGREGATED ENTITY SETS
    # =========================================================================
    {
        "id": 41,
        "category": "aggregate_sets",
        "difficulty": "hard",
        "name": "Customer segments with revenue and low refunds",
        "queries": [
            "Which customer segments generated more than 50,000 dollars in delivered-order revenue and kept their refund rate below 5 percent?",
            "Which customer segments generated more than 50,000 dollars in delivered-order revenue?",
            "Which customer segments have a refund rate below 5 percent?",
            "Which customer segments generated no delivered-order revenue?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should not contain Q1.",
        ],
    },
    {
        "id": 42,
        "category": "aggregate_sets",
        "difficulty": "hard",
        "name": "Categories with margin and channel reach",
        "queries": [
            "Which product categories have gross margin above 40 percent and were sold through both online and partner orders?",
            "Which product categories have gross margin above 40 percent?",
            "Which product categories were sold through both online and partner orders?",
            "Which product categories have never been sold online?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should not contain Q1.",
        ],
    },
    {
        "id": 43,
        "category": "aggregate_sets",
        "difficulty": "hard",
        "name": "Departments above salary and payroll benchmarks",
        "queries": [
            "Which departments have an average employee salary above the company average and active payroll above 500,000 dollars?",
            "Which departments have an average employee salary above the company-wide average?",
            "Which departments have active employee payroll above 500,000 dollars?",
            "Which departments have no active employees?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should not contain Q1.",
        ],
    },
    {
        "id": 44,
        "category": "aggregate_sets",
        "difficulty": "hard",
        "name": "Efficient carriers",
        "queries": [
            "Which carriers have an on-time delivery rate above 90 percent and average shipping cost below the overall average?",
            "Which carriers have an on-time delivery rate above 90 percent?",
            "Which carriers have average shipping cost below the overall shipment average?",
            "Which carriers have no delivered shipments?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should not contain Q1.",
        ],
    },
    {
        "id": 45,
        "category": "aggregate_sets",
        "difficulty": "hard",
        "name": "Suppliers with revenue and broad stocking",
        "queries": [
            "Which suppliers generated more than 20,000 dollars in delivered-order revenue and have products stored in at least three warehouses?",
            "Which suppliers generated more than 20,000 dollars in delivered-order revenue?",
            "Which suppliers have products stored in at least three warehouses?",
            "Which suppliers have products that have never appeared on an order?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 is generally incomparable.",
        ],
    },

    # =========================================================================
    # SET, DIFFERENCE, EXISTENCE, AND SUBQUERY SETS
    # =========================================================================
    {
        "id": 46,
        "category": "set_subquery_sets",
        "difficulty": "hard",
        "name": "Customers active across years",
        "queries": [
            "Which customers had delivered orders in both 2024 and 2025 but none in 2026?",
            "Which customers had delivered orders in both 2024 and 2025?",
            "Which customers had no delivered orders in 2026?",
            "Which customers had delivered orders only in 2026?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q1 and Q4 should be disjoint.",
        ],
    },
    {
        "id": 47,
        "category": "set_subquery_sets",
        "difficulty": "hard",
        "name": "Products stocked everywhere and sold online",
        "queries": [
            "Which products are stocked in every open warehouse and have been sold online?",
            "Which products are stocked in every open warehouse?",
            "Which products have been sold through the online channel?",
            "Which products have no inventory records?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should be disjoint from Q1 and Q2.",
        ],
    },
    {
        "id": 48,
        "category": "set_subquery_sets",
        "difficulty": "moderate",
        "name": "Orders with payment and shipment differences",
        "queries": [
            "Which orders have a payment but no shipment?",
            "Which orders have at least one payment?",
            "Which orders have no shipment?",
            "Which orders have a shipment but no payment?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q1 and Q4 should be disjoint.",
        ],
    },
    {
        "id": 49,
        "category": "set_subquery_sets",
        "difficulty": "hard",
        "name": "Employees occupying both operational roles",
        "queries": [
            "Which active employees are both warehouse managers and sales representatives on orders?",
            "Which employees manage at least one warehouse?",
            "Which employees have served as a sales representative on an order?",
            "Which employees have done neither of those jobs?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should be disjoint from Q1.",
        ],
    },
    {
        "id": 50,
        "category": "set_subquery_sets",
        "difficulty": "hard",
        "name": "Customers with recent success and high lifetime value",
        "queries": [
            "Which customers have a delivered most-recent order and total order value above the average customer total?",
            "Which customers have a delivered order as their most recent order?",
            "Which customers have total order value above the average customer total order value?",
            "Which customers have never placed an order?",
        ],
        "expected": [
            "Q1 is contained in Q2.",
            "Q1 is contained in Q3.",
            "Q4 should be disjoint from Q1, Q2, and Q3.",
        ],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 50 realistic natural-language containment cases on SpiderSQL DB53."
    )
    parser.add_argument("--database-id", type=int, default=53)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int, default=50)
    parser.add_argument("--only-category", default="")
    parser.add_argument(
        "--output",
        default="",
        help="Optional result TXT path. A timestamped path is used when omitted.",
    )
    parser.add_argument(
        "--trace-run",
        default="",
        help="Optional full-trace run ID. A timestamped ID is used when omitted.",
    )
    return parser.parse_args()


def post_batch(
    base_url: str,
    database_id: int,
    queries: list[str],
    timeout: int,
    *,
    test_id: int,
    category: str,
    difficulty: str,
    trace_run: str,
) -> tuple[int, dict[str, Any], float]:
    url = f"{base_url.rstrip('/')}/database/{database_id}/check_containment_batch"
    body = json.dumps({"queries": queries}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-SpiderSQL-Test-ID": str(test_id),
        "X-SpiderSQL-Test-Category": category,
        "X-SpiderSQL-Test-Difficulty": difficulty,
        "X-SpiderSQL-Trace-Run": trace_run,
    }

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    started = time.time()

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, {"success": False, "_client_error": str(exc)}, time.time() - started

    elapsed = time.time() - started
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"success": False, "_raw_response": raw}

    if not isinstance(payload, dict):
        payload = {"success": False, "_raw_response": payload}

    return status, payload, elapsed


def extract_sql(result: dict[str, Any]) -> str:
    for key in ("sql", "final_sql", "query_sql"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    generated = result.get("generated_sql")
    if isinstance(generated, str) and generated.strip():
        return generated.strip()
    if isinstance(generated, dict):
        for key in ("sql", "query", "generated_sql"):
            value = generated.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return "<NO SQL GENERATED>"


def query_label(index: Any) -> str:
    try:
        return f"Q{int(index) + 1}"
    except (TypeError, ValueError):
        return str(index)


def format_case(
    case: dict[str, Any],
    status_code: int,
    payload: dict[str, Any],
    elapsed: float,
) -> str:
    lines: list[str] = []
    lines.append("=" * 120)
    lines.append(
        f"TEST {case['id']:02d} | {case['category']} | "
        f"{case['difficulty']} | {case['name']}"
    )
    lines.append("=" * 120)
    lines.append(f"HTTP STATUS: {status_code}")
    lines.append(f"ENDPOINT SUCCESS: {payload.get('success')}")
    lines.append(f"ELAPSED SECONDS: {elapsed:.2f}")
    lines.append("")

    lines.append("NATURAL-LANGUAGE QUERIES")
    for idx, query in enumerate(case["queries"], start=1):
        lines.append(f"Q{idx}: {query}")

    lines.append("")
    lines.append("EXPECTED LOGICAL RELATIONSHIPS")
    for note in case["expected"]:
        lines.append(f"- {note}")

    lines.append("")
    lines.append("GENERATED SQL")
    query_results = payload.get("query_results") or []
    if query_results:
        for idx, result in enumerate(query_results, start=1):
            result_label = query_label(result.get("query_id", idx - 1))
            lines.append(
                f"{result_label}: success={result.get('success')} "
                f"safe={result.get('safe')} rows={result.get('row_count')} "
                f"source={result.get('selected_candidate_source')} "
                f"score={result.get('selected_candidate_score')}"
            )
            lines.append(extract_sql(result))
            if result.get("warnings"):
                lines.append(f"WARNINGS: {result.get('warnings')}")
    else:
        lines.append("<NO QUERY RESULTS RETURNED>")

    lines.append("")
    lines.append("CONTAINMENT SUMMARY")
    summaries = payload.get("query_summaries") or []
    if summaries:
        for summary in summaries:
            lines.append(
                f"{query_label(summary.get('query_index'))}: "
                f"status={summary.get('status')} | "
                f"contained_in={summary.get('contained_in') or '-'} | "
                f"contains={summary.get('contains') or '-'} | "
                f"equivalent_to={summary.get('equivalent_to') or '-'} | "
                f"incomparable_with={summary.get('incomparable_with') or '-'} | "
                f"unknown_with={summary.get('unknown_with') or '-'}"
            )
    else:
        lines.append("<NO QUERY SUMMARIES RETURNED>")

    lines.append("")
    lines.append("PAIRWISE RESULTS")
    pairs = payload.get("pairwise_relationships") or []
    if pairs:
        for pair in pairs:
            a = query_label(pair.get("query_a_index"))
            b = query_label(pair.get("query_b_index"))
            lines.append(f"{a} vs {b}: {pair.get('relationship')}")
            if pair.get("explanation"):
                lines.append(f"  {pair.get('explanation')}")
            if pair.get("a_minus_b_rows"):
                lines.append(f"  {a} minus {b}: {pair.get('a_minus_b_rows')[:5]}")
            if pair.get("b_minus_a_rows"):
                lines.append(f"  {b} minus {a}: {pair.get('b_minus_a_rows')[:5]}")
    else:
        lines.append("<NO PAIRWISE RESULTS RETURNED>")

    lines.append("")
    lines.append("RAW RESPONSE JSON")
    lines.append(json.dumps(payload, indent=2, ensure_ascii=False))
    lines.append("")
    return "\n".join(lines)


def discover_trace(output_dir: Path, trace_run: str, database_id: int) -> Path | None:
    pattern = f"{trace_run}_full_trace_db{database_id}_*.txt"
    deadline = time.time() + 4.0
    while time.time() <= deadline:
        matches = sorted(output_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
        if matches:
            return matches[-1]
        time.sleep(0.25)
    return None


def main() -> int:
    args = parse_args()

    if args.start_index < 1 or args.end_index > 50 or args.start_index > args.end_index:
        print("Use 1 <= start-index <= end-index <= 50.", file=sys.stderr)
        return 2

    selected = [
        case
        for case in TEST_CASES
        if args.start_index <= case["id"] <= args.end_index
        and (not args.only_category or case["category"] == args.only_category)
    ]
    if not selected:
        print("No matching cases selected.", file=sys.stderr)
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_run = args.trace_run or f"northstar_containment_50_db53_natural_{timestamp}"

    output_dir = Path("benchmarks") / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (
        Path(args.output)
        if args.output
        else output_dir / f"{trace_run}.txt"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    category_stats: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    total_success = 0
    total_failure = 0

    print("=" * 110)
    print("SpiderSQL DB53 - 50 Realistic Natural-Language Containment Cases")
    print(f"Database: {args.database_id}")
    print(f"Cases selected: {len(selected)}")
    print(f"Result file: {output_path}")
    print(f"Trace run ID: {trace_run}")
    print("=" * 110)

    with output_path.open("w", encoding="utf-8") as report:
        report.write("SpiderSQL DB53 Realistic Natural-Language Containment Benchmark\n")
        report.write(f"Started: {datetime.now().isoformat(timespec='seconds')}\n")
        report.write(f"Database ID: {args.database_id}\n")
        report.write(f"Trace run ID: {trace_run}\n")
        report.write(f"Selected cases: {len(selected)}\n\n")
        report.write(
            "Important: endpoint success only means the request executed. "
            "The generated SQL and containment relationships still require semantic review.\n\n"
        )

        for position, case in enumerate(selected, start=1):
            print()
            print("-" * 110)
            print(
                f"[{position:02d}/{len(selected):02d}] TEST {case['id']:02d}: "
                f"{case['name']} [{case['category']} / {case['difficulty']}]"
            )
            for idx, query in enumerate(case["queries"], start=1):
                print(f"  Q{idx}: {query}")

            status, payload, elapsed = post_batch(
                args.base_url,
                args.database_id,
                case["queries"],
                args.timeout,
                test_id=case["id"],
                category=case["category"],
                difficulty=case["difficulty"],
                trace_run=trace_run,
            )

            success = payload.get("success") is True and 200 <= status < 300
            if success:
                total_success += 1
                category_stats[case["category"]]["success"] += 1
            else:
                total_failure += 1
                category_stats[case["category"]]["failure"] += 1

            pair_count = len(payload.get("pairwise_relationships") or [])
            query_count = len(payload.get("query_results") or [])
            category_stats[case["category"]]["queries_returned"] += query_count
            category_stats[case["category"]]["pairs_returned"] += pair_count

            for pair in payload.get("pairwise_relationships") or []:
                relation = str(pair.get("relationship") or "missing")
                category_stats[case["category"]][f"relation:{relation}"] += 1

            print(f"success:         {success}")
            print(f"http_status:     {status}")
            print(f"elapsed_seconds: {elapsed:.2f}")
            print(f"query_results:   {query_count} | pairwise: {pair_count}")

            report.write(format_case(case, status, payload, elapsed))
            report.flush()
            time.sleep(args.sleep)

        report.write("\n" + "=" * 120 + "\n")
        report.write("FINAL EXECUTION SUMMARY\n")
        report.write("=" * 120 + "\n")
        report.write(f"Cases executed: {len(selected)}\n")
        report.write(f"Successful endpoint responses: {total_success}\n")
        report.write(f"Failed endpoint responses: {total_failure}\n")

        for category in sorted(category_stats):
            report.write(f"\n{category}\n")
            stats = category_stats[category]
            for key, value in sorted(stats.items()):
                report.write(f"  {key}: {value}\n")

    trace_path = discover_trace(output_dir, trace_run, args.database_id)

    print()
    print("=" * 110)
    print("DONE")
    print(f"Successful responses: {total_success}/{len(selected)}")
    print(f"Failed responses:     {total_failure}/{len(selected)}")
    print(f"Final result:         {output_path.resolve()}")
    if trace_path:
        print(f"Full backend trace:   {trace_path.resolve()}")
    else:
        print("Full backend trace:   NOT FOUND YET")
        print(f"Expected pattern:     {trace_run}_full_trace_db{args.database_id}_*.txt")
    print("=" * 110)

    return 0 if total_failure == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
