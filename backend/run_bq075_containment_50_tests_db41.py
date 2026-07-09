"""
Run 50 natural-language containment benchmark tests against SpiderSQL bq075 database.

Usage from backend folder while FastAPI is running:
    python run_bq075_containment_50_tests_db41.py

Optional environment variables:
    set CONTAINMENT_DB_ID=41
    set SPIDERSQL_BASE_URL=http://localhost:8000
    set CONTAINMENT_TIMEOUT=360

Output:
    benchmarks/results/containment_batch_50_results_db<id>_<timestamp>.txt

This script calls:
    POST /database/{database_id}/check_containment_batch

Each test contains 2+ natural-language queries. The backend should generate SQL
for all queries and compare every safe pair using live-database EXCEPT logic.

Manual scoring note:
    These tests are for manual review. A response can execute but still be
    semantically wrong if SQL generation selected the wrong table, column,
    quarter, year, aggregate, or output grain.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


BASE_URL = os.environ.get("SPIDERSQL_BASE_URL", "http://localhost:8000").rstrip("/")
DATABASE_ID = int(os.environ.get("CONTAINMENT_DB_ID", "41"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("CONTAINMENT_TIMEOUT", "360"))

INDUSTRY = "agriculture, forestry, fishing, and hunting"

TEST_CASES: List[Dict[str, Any]] = [
    {
        "id": 1,
        "category": "numeric_threshold_chain",
        "name": "1991 Q1 weekly wage threshold chain",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages above 700 in the first quarter of 1991?",
            f"Which areas had {INDUSTRY} weekly wages above 600 in the first quarter of 1991?",
            f"Which areas had {INDUSTRY} weekly wages above 500 in the first quarter of 1991?",
            f"Which areas had {INDUSTRY} weekly wages above 1000 in the first quarter of 1991?",
        ],
        "expected_note": "Higher wage thresholds should be contained in lower wage thresholds. Very high threshold may be empty.",
    },
    {
        "id": 2,
        "category": "numeric_threshold_chain",
        "name": "1994 Q4 weekly wage threshold chain",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages above 800 in the fourth quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages above 600 in the fourth quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages above 400 in the fourth quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages above 1200 in the fourth quarter of 1994?",
        ],
        "expected_note": "Wage >800 should be contained in >600 and >400. Wage >1200 may be empty or narrower.",
    },
    {
        "id": 3,
        "category": "numeric_threshold_chain",
        "name": "1993 Q2 establishment threshold chain",
        "queries": [
            f"Which areas had at least 20 {INDUSTRY} establishments in the second quarter of 1993?",
            f"Which areas had at least 10 {INDUSTRY} establishments in the second quarter of 1993?",
            f"Which areas had at least 5 {INDUSTRY} establishments in the second quarter of 1993?",
            f"Which areas had at least 50 {INDUSTRY} establishments in the second quarter of 1993?",
        ],
        "expected_note": "Higher establishment thresholds should be contained in lower establishment thresholds. >=50 may be empty.",
    },
    {
        "id": 4,
        "category": "numeric_threshold_chain",
        "name": "1990 Q3 establishment threshold chain",
        "queries": [
            f"Which areas had more than 25 {INDUSTRY} establishments in the third quarter of 1990?",
            f"Which areas had more than 15 {INDUSTRY} establishments in the third quarter of 1990?",
            f"Which areas had more than 5 {INDUSTRY} establishments in the third quarter of 1990?",
            f"Which areas had more than 60 {INDUSTRY} establishments in the third quarter of 1990?",
        ],
        "expected_note": "Establishment count >25 should be contained in >15 and >5. >60 may be empty.",
    },
    {
        "id": 5,
        "category": "compound_filter_single_quarter",
        "name": "1993 Q4 wage and establishment conjunction",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages above 500 and at least 10 establishments in the fourth quarter of 1993?",
            f"Which areas had {INDUSTRY} weekly wages above 500 in the fourth quarter of 1993?",
            f"Which areas had at least 10 {INDUSTRY} establishments in the fourth quarter of 1993?",
            f"Which areas had {INDUSTRY} weekly wages above 300 and at least 5 establishments in the fourth quarter of 1993?",
        ],
        "expected_note": "The conjunction should be contained in each single condition and in the weaker conjunction.",
    },
    {
        "id": 6,
        "category": "compound_filter_single_quarter",
        "name": "1992 Q2 below/above average style conjunction",
        "queries": [
            f"Which areas had below-average {INDUSTRY} weekly wages but above-average establishment counts in the second quarter of 1992?",
            f"Which areas had below-average {INDUSTRY} weekly wages in the second quarter of 1992?",
            f"Which areas had above-average {INDUSTRY} establishment counts in the second quarter of 1992?",
            f"Which areas had above-average {INDUSTRY} weekly wages in the second quarter of 1992?",
        ],
        "expected_note": "The first query should be contained in the below-wage query and the above-establishment query; it may be incomparable with above-wage.",
    },
    {
        "id": 7,
        "category": "compound_filter_single_quarter",
        "name": "1994 Q1 strong vs weak wage/establishment conjunctions",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages above 600 and at least 20 establishments in the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages above 500 and at least 10 establishments in the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages above 500 in the first quarter of 1994?",
            f"Which areas had at least 10 {INDUSTRY} establishments in the first quarter of 1994?",
        ],
        "expected_note": "The stronger conjunction should be contained in the weaker conjunction and both single-condition broader queries.",
    },
    {
        "id": 8,
        "category": "time_scope_containment",
        "name": "1994 any-quarter vs every-quarter wage threshold",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages above 500 in every quarter of 1994?",
            f"Which areas had at least one quarter in 1994 with {INDUSTRY} weekly wages above 500?",
            f"Which areas had {INDUSTRY} weekly wages above 500 in the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages above 500 in the fourth quarter of 1994?",
        ],
        "expected_note": "Every-quarter should be contained in at-least-one-quarter and in each named quarter if SQL output grain is areas.",
    },
    {
        "id": 9,
        "category": "time_scope_containment",
        "name": "1994 any-quarter vs every-quarter establishment threshold",
        "queries": [
            f"Which areas had {INDUSTRY} establishment counts above 10 in every quarter of 1994?",
            f"Which areas had at least one quarter in 1994 with {INDUSTRY} establishment counts above 10?",
            f"Which areas had {INDUSTRY} establishment counts above 10 in the first quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts above 10 in the third quarter of 1994?",
        ],
        "expected_note": "Every-quarter threshold is narrower than at-least-one and each specific quarter result.",
    },
    {
        "id": 10,
        "category": "time_scope_containment",
        "name": "First-quarter multi-year rising wages",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages rise every first quarter from 1990 through 1994?",
            f"Which areas had higher {INDUSTRY} weekly wages in the first quarter of 1994 than in the first quarter of 1990?",
            f"Which areas had {INDUSTRY} weekly wages increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages decrease from the first quarter of 1990 to the first quarter of 1994?",
        ],
        "expected_note": "Rising every first quarter should be contained in overall 1990-to-1994 increase; decrease should usually be incomparable/disjoint.",
    },
    {
        "id": 11,
        "category": "time_scope_containment",
        "name": "First-quarter multi-year rising establishments",
        "queries": [
            f"Which areas had {INDUSTRY} establishment counts rise every first quarter from 1990 through 1994?",
            f"Which areas had higher {INDUSTRY} establishment counts in the first quarter of 1994 than in the first quarter of 1990?",
            f"Which areas had {INDUSTRY} establishment counts increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts decrease from the first quarter of 1990 to the first quarter of 1994?",
        ],
        "expected_note": "Monotonic rise should be contained in simple start-to-end increase; decrease query should be incomparable or disjoint.",
    },
    {
        "id": 12,
        "category": "comparison_delta",
        "name": "Wage growth percent and absolute increase",
        "queries": [
            f"Which areas had at least 25 percent growth in {INDUSTRY} weekly wages from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages increase by at least 100 from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages decrease from the first quarter of 1990 to the first quarter of 1994?",
        ],
        "expected_note": "Growth by >=25% and increase by >=100 should both be contained in simple increase when generated correctly.",
    },
    {
        "id": 13,
        "category": "comparison_delta",
        "name": "Establishment growth percent and absolute increase",
        "queries": [
            f"Which areas had at least 25 percent growth in {INDUSTRY} establishment counts from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts increase by at least 5 from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts decrease from the first quarter of 1990 to the first quarter of 1994?",
        ],
        "expected_note": "Specific growth conditions should be contained in simple increase; decrease should be incomparable/disjoint.",
    },
    {
        "id": 14,
        "category": "comparison_delta",
        "name": "Wage up and establishment down decomposition",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages increase while establishment counts decreased from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts decrease from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had both {INDUSTRY} weekly wages and establishment counts increase from the first quarter of 1990 to the first quarter of 1994?",
        ],
        "expected_note": "Wage-up+est-down should be contained in each single condition and incomparable with wage-up+est-up.",
    },
    {
        "id": 15,
        "category": "comparison_delta",
        "name": "Establishment up and wage down decomposition",
        "queries": [
            f"Which areas had {INDUSTRY} establishment counts increase while weekly wages decreased from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages decrease from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had both {INDUSTRY} weekly wages and establishment counts decrease from the first quarter of 1990 to the first quarter of 1994?",
        ],
        "expected_note": "Est-up+wage-down should be contained in each single condition and generally incomparable with both-decrease.",
    },
    {
        "id": 16,
        "category": "same_vs_changed",
        "name": "Same establishment count but changed wages",
        "queries": [
            f"Which areas had the same {INDUSTRY} establishment count in the first quarter of 1990 and the first quarter of 1994, but different weekly wages?",
            f"Which areas had the same {INDUSTRY} establishment count in the first quarter of 1990 and the first quarter of 1994?",
            f"Which areas had different {INDUSTRY} weekly wages between the first quarter of 1990 and the first quarter of 1994?",
            f"Which areas had unchanged {INDUSTRY} weekly wages and unchanged establishment counts between the first quarter of 1990 and the first quarter of 1994?",
        ],
        "expected_note": "Same-count+different-wage should be contained in same-count and different-wage; unchanged-both should be incomparable/disjoint.",
    },
    {
        "id": 17,
        "category": "same_vs_changed",
        "name": "Same weekly wage but changed establishments",
        "queries": [
            f"Which areas had the same {INDUSTRY} weekly wage in the first quarter of 1990 and the first quarter of 1994, but different establishment counts?",
            f"Which areas had the same {INDUSTRY} weekly wage in the first quarter of 1990 and the first quarter of 1994?",
            f"Which areas had different {INDUSTRY} establishment counts between the first quarter of 1990 and the first quarter of 1994?",
            f"Which areas had unchanged {INDUSTRY} weekly wages and unchanged establishment counts between the first quarter of 1990 and the first quarter of 1994?",
        ],
        "expected_note": "Same-wage+different-count should be contained in same-wage and different-count; unchanged-both should be incomparable/disjoint.",
    },
    {
        "id": 18,
        "category": "average_threshold",
        "name": "Above average wages across Q1 1990 and Q1 1994",
        "queries": [
            f"Which areas had above-average {INDUSTRY} weekly wages in both the first quarter of 1990 and the first quarter of 1994?",
            f"Which areas had above-average {INDUSTRY} weekly wages in the first quarter of 1990?",
            f"Which areas had above-average {INDUSTRY} weekly wages in the first quarter of 1994?",
            f"Which areas moved from below-average {INDUSTRY} weekly wages in the first quarter of 1990 to above-average wages in the first quarter of 1994?",
        ],
        "expected_note": "Above-average in both quarters should be contained in each single above-average quarter; moved-below-to-above is likely incomparable with above-both.",
    },
    {
        "id": 19,
        "category": "average_threshold",
        "name": "Above/below average establishments across Q1 1990 and Q1 1994",
        "queries": [
            f"Which areas moved from above-average {INDUSTRY} establishment counts in the first quarter of 1990 to below-average counts in the first quarter of 1994?",
            f"Which areas had above-average {INDUSTRY} establishment counts in the first quarter of 1990?",
            f"Which areas had below-average {INDUSTRY} establishment counts in the first quarter of 1994?",
            f"Which areas had above-average {INDUSTRY} establishment counts in both the first quarter of 1990 and the first quarter of 1994?",
        ],
        "expected_note": "Above-to-below should be contained in Q1-1990 above and Q1-1994 below; above-both should be incomparable/disjoint with above-to-below.",
    },
    {
        "id": 20,
        "category": "average_threshold",
        "name": "1994 Q4 wage high and establishment low",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages in 1994 Q4 above the 1994 Q4 average and establishment counts below the 1994 Q4 average?",
            f"Which areas had {INDUSTRY} weekly wages in 1994 Q4 above the 1994 Q4 average?",
            f"Which areas had {INDUSTRY} establishment counts in 1994 Q4 below the 1994 Q4 average?",
            f"Which areas had {INDUSTRY} establishment counts in 1994 Q4 above the 1994 Q4 average and weekly wages below the 1994 Q4 average?",
        ],
        "expected_note": "High-wage+low-count should be contained in each component and generally incomparable with high-count+low-wage.",
    },
    {
        "id": 21,
        "category": "highest_lowest_year_quarter",
        "name": "Highest wage in a named quarter of 1990",
        "queries": [
            f"Which areas had their highest {INDUSTRY} weekly wage in the fourth quarter of 1990 compared with the other quarters of 1990?",
            f"Which areas had {INDUSTRY} weekly wages in the fourth quarter of 1990 above their own 1990 average weekly wage?",
            f"Which areas had {INDUSTRY} weekly wages in the fourth quarter of 1990 above 500?",
            f"Which areas had their highest {INDUSTRY} weekly wage in the second quarter of 1990 compared with the other quarters of 1990?",
        ],
        "expected_note": "Highest-in-Q4 may be contained in Q4-above-own-average but not necessarily in Q4>500; Q4 highest and Q2 highest may be incomparable.",
    },
    {
        "id": 22,
        "category": "highest_lowest_year_quarter",
        "name": "Lowest establishment count in a named quarter of 1992",
        "queries": [
            f"Which areas had their lowest {INDUSTRY} establishment count in the first quarter of 1992 compared with the other quarters of 1992?",
            f"Which areas had {INDUSTRY} establishment counts in the first quarter of 1992 below their own 1992 average establishment count?",
            f"Which areas had {INDUSTRY} establishment counts in the first quarter of 1992 below 10?",
            f"Which areas had their lowest {INDUSTRY} establishment count in the third quarter of 1992 compared with the other quarters of 1992?",
        ],
        "expected_note": "Lowest-in-Q1 may be contained in below-own-average; Q1-lowest and Q3-lowest may be incomparable.",
    },
    {
        "id": 23,
        "category": "half_year_comparison",
        "name": "1993 first-half vs second-half establishments",
        "queries": [
            f"Which areas had more {INDUSTRY} establishments in the first half of 1993 than in the second half of 1993?",
            f"Which areas had higher total {INDUSTRY} establishments in the first half of 1993 than in the second half of 1993?",
            f"Which areas had more {INDUSTRY} establishments in the second half of 1993 than in the first half of 1993?",
            f"Which areas had above-average {INDUSTRY} establishment counts in the first quarter of 1993?",
        ],
        "expected_note": "The first two should be equivalent or near-equivalent. First-half-more and second-half-more should be incomparable/disjoint.",
    },
    {
        "id": 24,
        "category": "half_year_comparison",
        "name": "1993 wage average first-half vs second-half",
        "queries": [
            f"Which areas had higher average {INDUSTRY} weekly wages in the second half of 1993 than in the first half of 1993?",
            f"Which areas had higher {INDUSTRY} weekly wages in the second half of 1993 than in the first half of 1993 on average?",
            f"Which areas had higher average {INDUSTRY} weekly wages in the first half of 1993 than in the second half of 1993?",
            f"Which areas had above-average {INDUSTRY} weekly wages in the fourth quarter of 1993?",
        ],
        "expected_note": "The first two should be equivalent or similar; opposite direction should be incomparable/disjoint.",
    },
    {
        "id": 25,
        "category": "year_total_comparison",
        "name": "1994 vs 1990 total establishments and average wages",
        "queries": [
            f"Which areas had a higher total {INDUSTRY} establishment count in 1994 than in 1990?",
            f"Which areas had a higher average {INDUSTRY} weekly wage in 1994 than in 1990?",
            f"Which areas had both a higher total {INDUSTRY} establishment count and a higher average weekly wage in 1994 than in 1990?",
            f"Which areas had either a higher total {INDUSTRY} establishment count or a higher average weekly wage in 1994 than in 1990?",
        ],
        "expected_note": "The both-higher query should be contained in each single condition and in the either-higher query.",
    },
    {
        "id": 26,
        "category": "year_total_comparison",
        "name": "1992 totals compared with 1991 and 1993",
        "queries": [
            f"Which areas had more total {INDUSTRY} establishments in 1992 than in both 1991 and 1993?",
            f"Which areas had more total {INDUSTRY} establishments in 1992 than in 1991?",
            f"Which areas had more total {INDUSTRY} establishments in 1992 than in 1993?",
            f"Which areas had lower average {INDUSTRY} weekly wages in 1992 than in both 1991 and 1993?",
        ],
        "expected_note": "More-than-both should be contained in each single more-than comparison; wage-low-both may be incomparable.",
    },
    {
        "id": 27,
        "category": "year_total_comparison",
        "name": "1992 wage averages compared with 1991 and 1993",
        "queries": [
            f"Which areas had lower average {INDUSTRY} weekly wages in 1992 than in both 1991 and 1993?",
            f"Which areas had lower average {INDUSTRY} weekly wages in 1992 than in 1991?",
            f"Which areas had lower average {INDUSTRY} weekly wages in 1992 than in 1993?",
            f"Which areas had more total {INDUSTRY} establishments in 1992 than in both 1991 and 1993?",
        ],
        "expected_note": "Lower-than-both should be contained in each single lower-than comparison; establishment query may be incomparable.",
    },
    {
        "id": 28,
        "category": "quarter_peak_across_years",
        "name": "Highest fourth-quarter wages in 1994",
        "queries": [
            f"Which areas had their highest fourth-quarter {INDUSTRY} weekly wage in 1994 compared with the fourth quarters from 1990 through 1993?",
            f"Which areas had fourth-quarter {INDUSTRY} weekly wages in 1994 higher than in fourth quarter 1990?",
            f"Which areas had fourth-quarter {INDUSTRY} weekly wages in 1994 higher than in fourth quarter 1991?",
            f"Which areas had fourth-quarter {INDUSTRY} weekly wages in 1994 lower than in fourth quarter 1990?",
        ],
        "expected_note": "Highest-1994 should be contained in higher-than-1990 and higher-than-1991; lower-than-1990 should be incomparable/disjoint.",
    },
    {
        "id": 29,
        "category": "quarter_peak_across_years",
        "name": "Lowest first-quarter establishments in 1990",
        "queries": [
            f"Which areas had their lowest first-quarter {INDUSTRY} establishment count in 1990 compared with the first quarters from 1991 through 1994?",
            f"Which areas had first-quarter {INDUSTRY} establishment counts in 1990 lower than in first quarter 1991?",
            f"Which areas had first-quarter {INDUSTRY} establishment counts in 1990 lower than in first quarter 1994?",
            f"Which areas had first-quarter {INDUSTRY} establishment counts in 1990 higher than in first quarter 1994?",
        ],
        "expected_note": "Lowest-1990 should be contained in lower-than-1991 and lower-than-1994; higher-than-1994 should be incomparable/disjoint.",
    },
    {
        "id": 30,
        "category": "between_neighbor_years",
        "name": "1992 Q2 wage local peak",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages in the second quarter of 1992 that were higher than both the second quarter of 1991 and the second quarter of 1993?",
            f"Which areas had {INDUSTRY} weekly wages in the second quarter of 1992 higher than the second quarter of 1991?",
            f"Which areas had {INDUSTRY} weekly wages in the second quarter of 1992 higher than the second quarter of 1993?",
            f"Which areas had {INDUSTRY} weekly wages in the second quarter of 1992 lower than both the second quarter of 1991 and the second quarter of 1993?",
        ],
        "expected_note": "Higher-than-both should be contained in each single higher-than condition; lower-than-both should be incomparable/disjoint.",
    },
    {
        "id": 31,
        "category": "between_neighbor_years",
        "name": "1992 Q4 wage dip",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages dip in the fourth quarter of 1992 compared with both the fourth quarter of 1991 and the fourth quarter of 1993?",
            f"Which areas had {INDUSTRY} weekly wages in the fourth quarter of 1992 lower than in the fourth quarter of 1991?",
            f"Which areas had {INDUSTRY} weekly wages in the fourth quarter of 1992 lower than in the fourth quarter of 1993?",
            f"Which areas had {INDUSTRY} weekly wages in the fourth quarter of 1992 higher than both the fourth quarter of 1991 and the fourth quarter of 1993?",
        ],
        "expected_note": "Dip-below-both should be contained in each single lower-than condition; peak-above-both should be incomparable/disjoint.",
    },
    {
        "id": 32,
        "category": "threshold_with_year_scope",
        "name": "1994 yearly wage threshold all/any",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages in every quarter of 1994 above 500?",
            f"Which areas had at least one quarter in 1994 with {INDUSTRY} weekly wages above 500?",
            f"Which areas had {INDUSTRY} weekly wages in the first quarter of 1994 above 500?",
            f"Which areas had {INDUSTRY} weekly wages in every quarter of 1994 above 800?",
        ],
        "expected_note": "Every quarter >800 should be contained in every quarter >500; every quarter >500 should be contained in at-least-one >500.",
    },
    {
        "id": 33,
        "category": "threshold_with_year_scope",
        "name": "1994 yearly establishment threshold all/any",
        "queries": [
            f"Which areas had {INDUSTRY} establishment counts in every quarter of 1994 above 10?",
            f"Which areas had at least one quarter in 1994 with {INDUSTRY} establishment counts above 10?",
            f"Which areas had {INDUSTRY} establishment counts in the first quarter of 1994 above 10?",
            f"Which areas had {INDUSTRY} establishment counts in every quarter of 1994 above 20?",
        ],
        "expected_note": "Every quarter >20 should be contained in every quarter >10; every quarter >10 should be contained in at-least-one >10.",
    },
    {
        "id": 34,
        "category": "range_within_tolerance",
        "name": "1993 Q2 wage within range around 1990 Q2",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages in the second quarter of 1993 within 50 of their second-quarter 1990 wages?",
            f"Which areas had {INDUSTRY} weekly wages in the second quarter of 1993 within 100 of their second-quarter 1990 wages?",
            f"Which areas had {INDUSTRY} weekly wages in the second quarter of 1993 higher than their second-quarter 1990 wages?",
            f"Which areas had {INDUSTRY} weekly wages in the second quarter of 1993 lower than their second-quarter 1990 wages?",
        ],
        "expected_note": "Within-50 should be contained in within-100; higher/lower comparisons may overlap or be incomparable with tolerance ranges.",
    },
    {
        "id": 35,
        "category": "spread_extreme",
        "name": "Wage spread extremes in 1990",
        "queries": [
            f"Which areas had the largest spread between their highest and lowest {INDUSTRY} weekly wage in 1990?",
            f"Which areas had the top 10 largest spreads between their highest and lowest {INDUSTRY} weekly wage in 1990?",
            f"Which areas had the smallest spread between their highest and lowest {INDUSTRY} weekly wage in 1990?",
            f"Which areas had a spread greater than 100 between their highest and lowest {INDUSTRY} weekly wage in 1990?",
        ],
        "expected_note": "Top/largest queries may involve LIMIT and may be unsupported/unknown. This tests safe abstention for top-k containment.",
    },
    {
        "id": 36,
        "category": "spread_extreme",
        "name": "Establishment spread extremes in 1994",
        "queries": [
            f"Which areas had the largest spread between their highest and lowest {INDUSTRY} establishment count in 1994?",
            f"Which areas had the top 10 largest spreads between their highest and lowest {INDUSTRY} establishment count in 1994?",
            f"Which areas had the smallest spread between their highest and lowest {INDUSTRY} establishment count in 1994?",
            f"Which areas had a spread greater than 5 between their highest and lowest {INDUSTRY} establishment count in 1994?",
        ],
        "expected_note": "Largest/top-k and smallest spread are difficult; system should either compare safely or return unknown.",
    },
    {
        "id": 37,
        "category": "top_k_unsupported",
        "name": "Top 10 wage increases vs positive wage increases",
        "queries": [
            f"Which areas had the top 10 {INDUSTRY} wage increases from 1990 Q1 to 1994 Q1?",
            f"Which areas had a positive {INDUSTRY} wage increase from 1990 Q1 to 1994 Q1?",
            f"Which areas had {INDUSTRY} weekly wages increase from 1990 Q1 to 1994 Q1?",
            f"Which areas had the top 10 {INDUSTRY} wage decreases from 1990 Q1 to 1994 Q1?",
        ],
        "expected_note": "Top-k queries may use LIMIT and should often be unknown. If compared, top increases should be contained in positive/increase queries.",
    },
    {
        "id": 38,
        "category": "top_k_unsupported",
        "name": "Top 10 establishment increases vs positive increases",
        "queries": [
            f"Which areas had the top 10 {INDUSTRY} establishment increases from 1990 Q1 to 1994 Q1?",
            f"Which areas had a positive {INDUSTRY} establishment increase from 1990 Q1 to 1994 Q1?",
            f"Which areas had {INDUSTRY} establishment counts increase from 1990 Q1 to 1994 Q1?",
            f"Which areas had the top 10 {INDUSTRY} establishment decreases from 1990 Q1 to 1994 Q1?",
        ],
        "expected_note": "Top-k increase should be contained in positive/increase if supported; top decreases should be incomparable/disjoint.",
    },
    {
        "id": 39,
        "category": "mixed_measure_comparison",
        "name": "Both wage and establishment increase/decrease combinations",
        "queries": [
            f"Which areas had both {INDUSTRY} weekly wages and establishment counts increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts increase from the first quarter of 1990 to the first quarter of 1994?",
            f"Which areas had both {INDUSTRY} weekly wages and establishment counts decrease from the first quarter of 1990 to the first quarter of 1994?",
        ],
        "expected_note": "Both-increase should be contained in wage-increase and establishment-increase; both-decrease should be incomparable/disjoint.",
    },
    {
        "id": 40,
        "category": "mixed_measure_comparison",
        "name": "Positive wage increase but negative establishment change",
        "queries": [
            f"Which areas had a positive {INDUSTRY} wage increase from 1990 Q1 to 1994 Q1 but a negative establishment change over the same period?",
            f"Which areas had a positive {INDUSTRY} wage increase from 1990 Q1 to 1994 Q1?",
            f"Which areas had a negative {INDUSTRY} establishment change from 1990 Q1 to 1994 Q1?",
            f"Which areas had a positive {INDUSTRY} establishment increase from 1990 Q1 to 1994 Q1 but a negative wage change over the same period?",
        ],
        "expected_note": "The first query should be contained in positive-wage and negative-establishment; the last mixed-opposite query should be incomparable/disjoint.",
    },
    {
        "id": 41,
        "category": "quarter_average_condition",
        "name": "Above yearly average in every quarter of 1990",
        "queries": [
            f"Which areas had their {INDUSTRY} weekly wages above the yearly average in every quarter of 1990?",
            f"Which areas had {INDUSTRY} weekly wages above the yearly average in the first quarter of 1990?",
            f"Which areas had {INDUSTRY} weekly wages above the yearly average in at least one quarter of 1990?",
            f"Which areas had their {INDUSTRY} establishment counts below the yearly average in every quarter of 1990?",
        ],
        "expected_note": "Every-quarter above-average should be contained in Q1 above-average and at-least-one above-average; establishment condition likely incomparable.",
    },
    {
        "id": 42,
        "category": "quarter_average_condition",
        "name": "Below yearly average establishment counts in every quarter of 1990",
        "queries": [
            f"Which areas had their {INDUSTRY} establishment counts below the yearly average in every quarter of 1990?",
            f"Which areas had {INDUSTRY} establishment counts below the yearly average in the first quarter of 1990?",
            f"Which areas had {INDUSTRY} establishment counts below the yearly average in at least one quarter of 1990?",
            f"Which areas had their {INDUSTRY} weekly wages above the yearly average in every quarter of 1990?",
        ],
        "expected_note": "Every-quarter below-count should be contained in Q1 below-count and at-least-one below-count; wage condition likely incomparable.",
    },
    {
        "id": 43,
        "category": "cross_quarter_average",
        "name": "Quarter-average wages in Q1 1991 and Q1 1992",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages above the quarter average in both the first quarter of 1991 and the first quarter of 1992?",
            f"Which areas had {INDUSTRY} weekly wages above the quarter average in the first quarter of 1991?",
            f"Which areas had {INDUSTRY} weekly wages above the quarter average in the first quarter of 1992?",
            f"Which areas had {INDUSTRY} weekly wages below the quarter average in both the first quarter of 1991 and the first quarter of 1992?",
        ],
        "expected_note": "Above-average in both quarters should be contained in each single above-average quarter; below-both likely incomparable/disjoint.",
    },
    {
        "id": 44,
        "category": "cross_quarter_average",
        "name": "Quarter-average establishments in Q3 1993 and Q3 1994",
        "queries": [
            f"Which areas had {INDUSTRY} establishment counts below the quarter average in both the third quarter of 1993 and the third quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts below the quarter average in the third quarter of 1993?",
            f"Which areas had {INDUSTRY} establishment counts below the quarter average in the third quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts above the quarter average in both the third quarter of 1993 and the third quarter of 1994?",
        ],
        "expected_note": "Below-average in both quarters should be contained in each single below-average query; above-both likely incomparable/disjoint.",
    },
    {
        "id": 45,
        "category": "large_change_comparison",
        "name": "Large wage increase from 1990 Q3 to 1994 Q3",
        "queries": [
            f"Which areas had {INDUSTRY} weekly wages increase by at least 100 from the third quarter of 1990 to the third quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages increase from the third quarter of 1990 to the third quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages increase by at least 50 from the third quarter of 1990 to the third quarter of 1994?",
            f"Which areas had {INDUSTRY} weekly wages decrease from the third quarter of 1990 to the third quarter of 1994?",
        ],
        "expected_note": ">=100 increase should be contained in >=50 increase and simple increase; decrease should be incomparable/disjoint.",
    },
    {
        "id": 46,
        "category": "large_change_comparison",
        "name": "Large establishment increase from 1990 Q4 to 1994 Q4",
        "queries": [
            f"Which areas had {INDUSTRY} establishment counts increase by at least 5 from the fourth quarter of 1990 to the fourth quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts increase from the fourth quarter of 1990 to the fourth quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts increase by at least 2 from the fourth quarter of 1990 to the fourth quarter of 1994?",
            f"Which areas had {INDUSTRY} establishment counts decrease from the fourth quarter of 1990 to the fourth quarter of 1994?",
        ],
        "expected_note": ">=5 increase should be contained in >=2 and simple increase; decrease should be incomparable/disjoint.",
    },
    {
        "id": 47,
        "category": "directional_trend",
        "name": "Quarter-to-quarter wage increases throughout 1992",
        "queries": [
            f"Which areas increased their {INDUSTRY} weekly wages from quarter to quarter throughout 1992?",
            f"Which areas had higher {INDUSTRY} weekly wages in the second quarter of 1992 than in the first quarter of 1992?",
            f"Which areas had higher {INDUSTRY} weekly wages in the fourth quarter of 1992 than in the third quarter of 1992?",
            f"Which areas decreased their {INDUSTRY} weekly wages from quarter to quarter throughout 1992?",
        ],
        "expected_note": "Increase-throughout should be contained in each adjacent increase condition; decrease-throughout likely incomparable/disjoint.",
    },
    {
        "id": 48,
        "category": "directional_trend",
        "name": "Quarter-to-quarter establishment decreases throughout 1992",
        "queries": [
            f"Which areas decreased their {INDUSTRY} establishment count from quarter to quarter throughout 1992?",
            f"Which areas had lower {INDUSTRY} establishment counts in the second quarter of 1992 than in the first quarter of 1992?",
            f"Which areas had lower {INDUSTRY} establishment counts in the fourth quarter of 1992 than in the third quarter of 1992?",
            f"Which areas increased their {INDUSTRY} establishment count from quarter to quarter throughout 1992?",
        ],
        "expected_note": "Decrease-throughout should be contained in each adjacent decrease condition; increase-throughout likely incomparable/disjoint.",
    },
    {
        "id": 49,
        "category": "relative_change_comparison",
        "name": "Wage increase Q1 vs Q4 comparison",
        "queries": [
            f"Which areas had a larger {INDUSTRY} wage increase from 1990 Q1 to 1994 Q1 than from 1990 Q4 to 1994 Q4?",
            f"Which areas had a positive {INDUSTRY} wage increase from 1990 Q1 to 1994 Q1?",
            f"Which areas had a positive {INDUSTRY} wage increase from 1990 Q4 to 1994 Q4?",
            f"Which areas had a larger {INDUSTRY} wage increase from 1990 Q4 to 1994 Q4 than from 1990 Q1 to 1994 Q1?",
        ],
        "expected_note": "The larger-Q1-than-Q4 comparison may not be contained in either positive increase query unless generated logic includes positivity; opposite comparison should be incomparable/disjoint.",
    },
    {
        "id": 50,
        "category": "relative_change_comparison",
        "name": "Establishment increase Q1 vs Q4 comparison",
        "queries": [
            f"Which areas had a larger {INDUSTRY} establishment increase from 1990 Q1 to 1994 Q1 than from 1990 Q4 to 1994 Q4?",
            f"Which areas had a positive {INDUSTRY} establishment increase from 1990 Q1 to 1994 Q1?",
            f"Which areas had a positive {INDUSTRY} establishment increase from 1990 Q4 to 1994 Q4?",
            f"Which areas had a larger {INDUSTRY} establishment increase from 1990 Q4 to 1994 Q4 than from 1990 Q1 to 1994 Q1?",
        ],
        "expected_note": "The Q1-vs-Q4 comparison and the opposite comparison should generally be incomparable; positive single-period increases may or may not contain them depending on sign.",
    },
]


def post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        return json.loads(text)


def qlabel(query_id: int) -> str:
    return f"Q{query_id}"


def fmt_list(values: List[Any]) -> str:
    if not values:
        return "-"
    return ", ".join(qlabel(int(v)) for v in values)


def relationship_counts(response: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for p in response.get("pairwise_relationships", []) or []:
        rel = str(p.get("relationship") or "missing")
        counts[rel] = counts.get(rel, 0) + 1
    return counts


def summarize_query_result(q: Dict[str, Any]) -> List[str]:
    lines = []
    query_id = q.get("query_id", "?")
    lines.append(f"{qlabel(int(query_id))}. {q.get('question', '')}")
    lines.append(
        f"   success: {q.get('success')} | safe: {q.get('safe')} | "
        f"rows: {q.get('row_count')} | empty: {q.get('empty_result')}"
    )
    if q.get("safety_reason"):
        lines.append(f"   safety_reason: {q.get('safety_reason')}")
    if q.get("low_confidence"):
        lines.append("   low_confidence: true")
    if q.get("has_fatal_validation"):
        lines.append("   has_fatal_validation: true")
    warnings = q.get("warnings") or []
    if warnings:
        lines.append(f"   warnings: {warnings}")
    lines.append(f"   columns: {q.get('execution_columns')}")
    sql = (q.get("sql") or "").replace("\n", " ").strip()
    lines.append(f"   sql: {sql}")
    return lines


def summarize_query_summary(s: Dict[str, Any]) -> str:
    return (
        f"{qlabel(int(s.get('query_id')))} | status={s.get('status')} | empty={s.get('empty_result')} | "
        f"contained_in={fmt_list(s.get('contained_in') or [])} | "
        f"contains={fmt_list(s.get('contains') or [])} | "
        f"equivalent_to={fmt_list(s.get('equivalent_to') or [])} | "
        f"incomparable_with={fmt_list(s.get('incomparable_with') or [])} | "
        f"unknown_with={fmt_list(s.get('unknown_with') or [])}"
    )


def summarize_pairwise(p: Dict[str, Any]) -> List[str]:
    a = int(p.get("query_a"))
    b = int(p.get("query_b"))
    rel = p.get("relationship")
    lines = [f"{qlabel(a)} vs {qlabel(b)}: {rel}"]
    if p.get("explanation"):
        lines.append(f"   {p.get('explanation')}")
    a_rows = p.get("a_minus_b_rows") or []
    b_rows = p.get("b_minus_a_rows") or []
    if a_rows:
        lines.append(f"   {qlabel(a)} rows missing from {qlabel(b)}: {len(a_rows)} sample rows")
        lines.append(f"   sample: {a_rows[:5]}")
    if b_rows:
        lines.append(f"   {qlabel(b)} rows missing from {qlabel(a)}: {len(b_rows)} sample rows")
        lines.append(f"   sample: {b_rows[:5]}")
    return lines


def write_case_report(f, case: Dict[str, Any], response: Dict[str, Any], elapsed: float) -> None:
    f.write("\n" + "=" * 100 + "\n")
    f.write(f"TEST {case['id']:02d}: {case['name']}\n")
    f.write("=" * 100 + "\n")
    f.write(f"Category: {case.get('category')}\n")
    f.write(f"Expected note: {case['expected_note']}\n")
    f.write(f"Elapsed seconds: {elapsed:.2f}\n")
    f.write(
        f"success: {response.get('success')} | proof_type: {response.get('proof_type')} | "
        f"checked_on_current_database: {response.get('checked_on_current_database')}\n"
    )
    if response.get("limitations"):
        f.write(f"limitations: {response.get('limitations')}\n")
    warnings = response.get("warnings") or []
    if warnings:
        f.write(f"warnings: {warnings}\n")

    f.write("\nINPUT QUERIES\n")
    for i, q in enumerate(case["queries"], 1):
        f.write(f"  Q{i}: {q}\n")

    f.write("\nGENERATED SQL / QUERY RESULTS\n")
    for q in response.get("query_results", []):
        for line in summarize_query_result(q):
            f.write(line + "\n")

    f.write("\nRELATIONSHIP SUMMARY\n")
    for s in response.get("query_summaries", []):
        f.write("  " + summarize_query_summary(s) + "\n")

    counts = relationship_counts(response)
    f.write("\nRELATIONSHIP COUNTS\n")
    if counts:
        for rel, count in sorted(counts.items()):
            f.write(f"  {rel}: {count}\n")
    else:
        f.write("  -\n")

    f.write("\nPAIRWISE RELATIONSHIPS\n")
    for p in response.get("pairwise_relationships", []):
        for line in summarize_pairwise(p):
            f.write("  " + line + "\n")

    f.write("\nRAW JSON\n")
    f.write(json.dumps(response, indent=2, ensure_ascii=False))
    f.write("\n")


def main() -> int:
    output_dir = Path("benchmarks") / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"containment_batch_50_results_db{DATABASE_ID}_{timestamp}.txt"

    endpoint = f"{BASE_URL}/database/{DATABASE_ID}/check_containment_batch"
    started = datetime.now()
    pass_count = 0
    fail_count = 0

    category_counts: Dict[str, int] = {}
    for case in TEST_CASES:
        cat = str(case.get("category") or "uncategorized")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    with output_path.open("w", encoding="utf-8") as f:
        f.write("SpiderSQL Containment Batch Benchmark - 50 Complicated Tests for bq075\n")
        f.write(f"Started: {started.isoformat(timespec='seconds')}\n")
        f.write(f"Base URL: {BASE_URL}\n")
        f.write(f"Database ID: {DATABASE_ID}\n")
        f.write(f"Endpoint: {endpoint}\n")
        f.write("\nManual scoring note:\n")
        f.write("These tests are for manual review. The script records generated SQL, row counts, pairwise relationships, and counterexamples.\n")
        f.write("A backend response can be executable but semantically wrong, so manually inspect SQL and relationships.\n")
        f.write("\nTest categories:\n")
        for cat, count in sorted(category_counts.items()):
            f.write(f"  {cat}: {count}\n")

        for case in TEST_CASES:
            print(f"[{case['id']:02d}/50] {case['name']} ...", flush=True)
            payload = {"queries": case["queries"]}
            t0 = time.time()
            try:
                response = post_json(endpoint, payload)
                elapsed = time.time() - t0
                write_case_report(f, case, response, elapsed)
                if response.get("success"):
                    pass_count += 1
                    print(f"  OK ({elapsed:.2f}s)", flush=True)
                else:
                    fail_count += 1
                    print(f"  RESPONSE success=false ({elapsed:.2f}s)", flush=True)
            except urllib.error.HTTPError as e:
                fail_count += 1
                elapsed = time.time() - t0
                body = e.read().decode("utf-8", errors="replace")
                f.write("\n" + "=" * 100 + "\n")
                f.write(f"TEST {case['id']:02d}: {case['name']}\n")
                f.write("HTTP ERROR\n")
                f.write(f"status: {e.code}\n")
                f.write(f"body: {body}\n")
                print(f"  HTTP ERROR {e.code} ({elapsed:.2f}s)", flush=True)
            except Exception:
                fail_count += 1
                elapsed = time.time() - t0
                err = traceback.format_exc()
                f.write("\n" + "=" * 100 + "\n")
                f.write(f"TEST {case['id']:02d}: {case['name']}\n")
                f.write("PYTHON ERROR\n")
                f.write(err + "\n")
                print(f"  ERROR ({elapsed:.2f}s)", flush=True)

        finished = datetime.now()
        f.write("\n" + "=" * 100 + "\n")
        f.write("FINAL SUMMARY\n")
        f.write("=" * 100 + "\n")
        f.write(f"Finished: {finished.isoformat(timespec='seconds')}\n")
        f.write(f"Total tests: {len(TEST_CASES)}\n")
        f.write(f"Backend success responses: {pass_count}\n")
        f.write(f"Failed requests/responses: {fail_count}\n")
        f.write("\nCategory counts:\n")
        for cat, count in sorted(category_counts.items()):
            f.write(f"  {cat}: {count}\n")

    print("\nDONE")
    print(f"Results written to: {output_path}")
    print(f"Backend success responses: {pass_count}/{len(TEST_CASES)}")
    if fail_count:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
