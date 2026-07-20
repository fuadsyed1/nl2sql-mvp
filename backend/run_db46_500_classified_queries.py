#!/usr/bin/env python3
"""
Run 500 classified natural-language queries against SpiderSQL database 46.

Classifications (50 queries each):
- simple_retrieval_filters
- joins
- aggregation
- group_by
- having
- distinct_set_logic
- subquery_cte
- order_limit_topk
- derived_metrics
- temporal_complex

Difficulty inside each classification:
- positions 1-15: easy
- positions 16-35: medium
- positions 36-50: hard

The script prints PASS only when SQL execution succeeds. It prints FAIL otherwise.
It saves the classification, difficulty, question, generated SQL, selected
candidate, row count, warnings, error, and latency to a TXT file after every query.

Examples:
    python run_db46_500_classified_queries.py
    python run_db46_500_classified_queries.py --classification joins
    python run_db46_500_classified_queries.py --start-index 201 --append --output results.txt
    python run_db46_500_classified_queries.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DATABASE_ID = 46
QUERY_GROUPS: dict[str, list[str]] = {'simple_retrieval_filters': ['Show all patients.',
                              'List every patient ID and patient name.',
                              'Show all doctors.',
                              'List every doctor name and specialty.',
                              'Show all appointments.',
                              'Show all invoices.',
                              'Show all lab results.',
                              'Find patients from Idaho.',
                              'Find patients whose insurance provider is BlueCross.',
                              'Find patients whose insurance provider is Medicaid.',
                              'Find patients whose insurance provider is Aetna.',
                              'Find patients who have a recorded chronic condition.',
                              'Find patients born before January 1, 1980.',
                              'Find patients born on or after January 1, 1990.',
                              'Find doctors with more than 10 years of experience.',
                              'Find doctors with 10 or fewer years of experience.',
                              'Find completed appointments.',
                              'Find appointments that are not completed.',
                              'Find checkup appointments.',
                              'Find follow-up appointments.',
                              'Find appointments whose base fee is greater than 200.',
                              'Find appointments whose base fee is between 100 and 300.',
                              'Find appointments dated on or after January 1, 2025.',
                              'Find unpaid invoices.',
                              'Find partially paid invoices.',
                              'Find fully paid invoices.',
                              'Find invoices with a total amount greater than 450.',
                              'Find invoices with a total amount between 200 and 500.',
                              'Find invoices where insurance paid nothing.',
                              'Find invoices where the insurance payment is less than the total amount.',
                              'Find invoices dated on or after January 1, 2025.',
                              'Find lab results marked critical.',
                              'Find lab results marked high.',
                              'Find lab results marked low.',
                              'Find lab results marked normal.',
                              'Find lab results with a test value greater than 100.',
                              'Find lab results with a test value between 50 and 150.',
                              'Find lab results dated on or after January 1, 2025.',
                              "Find patients whose name starts with 'Patient 1'.",
                              "Find doctors whose name contains the word 'Doctor'.",
                              'Find patients whose city is recorded.',
                              'Find patients who are not from Idaho.',
                              'Find patients insured by BlueCross, Medicaid, or Aetna.',
                              'Find invoices whose payment status is unpaid or partial.',
                              'Find lab results whose flag is high, low, or critical.',
                              'Find appointments whose status is completed or scheduled.',
                              'Find appointments whose visit type is not checkup.',
                              'Find invoices whose total amount is different from the insurance-paid amount.',
                              'Find lab results whose test name is recorded.',
                              'Find appointments whose base fee is recorded.'],
 'joins': ['Show each appointment with its patient name.',
           "Show each appointment with its doctor's name.",
           'Show each invoice with its appointment date.',
           'Show each lab result with its appointment date.',
           'Show every invoice with the patient ID and patient name.',
           'Show every lab result with the patient ID and patient name.',
           'Show every appointment with the patient name and doctor specialty.',
           'Show every invoice with the patient name and doctor name.',
           'Show every lab result with the patient name and doctor specialty.',
           'Show a complete appointment summary with patient name, doctor name, visit type, status, and base fee.',
           'List patients who have at least one appointment.',
           'List doctors who have handled at least one appointment.',
           'List patients who have at least one invoice.',
           'List patients who have at least one lab result.',
           'Show completed appointments with the patient name.',
           'Show unpaid invoices with the patient name.',
           'Show critical lab results with the patient name.',
           'Show checkup appointments with the doctor name.',
           'Show invoices over 450 with the patient and doctor names.',
           'Show high lab results with the patient and doctor names.',
           'List patients who were treated by doctors with more than 10 years of experience.',
           'Show appointments belonging to patients from Idaho.',
           'Show invoices belonging to BlueCross patients.',
           'Show lab results belonging to Medicaid patients.',
           'List doctors who treated at least one patient from Idaho.',
           "Show patient-doctor meetings where the patient's city matches the doctor's clinic city.",
           "Show appointments where the patient's city matches the doctor's clinic city.",
           'Show each patient, appointment, invoice total, insurance payment, and outstanding amount.',
           'Show each patient, lab result, and invoice that belong to the same appointment.',
           'List patients who had an appointment containing both an invoice and a lab result.',
           'Show appointments that do not have an invoice.',
           'Show appointments that do not have any lab result.',
           'List patients who do not have any appointment.',
           'List doctors who have not handled any appointment.',
           'List patients who have appointments but no invoices.',
           'Show patients with a lab result on an appointment that has no invoice.',
           'List doctors who handled appointments with unpaid invoices.',
           'List patients who had a completed appointment with a high lab result on that same appointment.',
           'List every distinct patient-doctor pair that has met.',
           'List distinct patient, doctor, and specialty combinations from appointments.',
           'Show completed appointments with patient and doctor names.',
           'Show invoice and lab-result pairs that belong to the same appointment.',
           'Show invoice details together with patient insurance provider.',
           "Show each invoice amount with the doctor's specialty for that appointment.",
           "Show each lab result flag with the patient's state.",
           "Show each appointment visit type with the patient's chronic condition.",
           'Show each appointment with patient birth date and doctor years of experience.',
           'Show each lab result with appointment status and visit type.',
           'Show each unpaid invoice with its appointment status and doctor specialty.',
           "Show each patient's appointments, invoices, and lab results when all three exist for the appointment."],
 'aggregation': ['Count all patients.',
                 'Count all doctors.',
                 'Count all appointments.',
                 'Count all invoices.',
                 'Count all lab results.',
                 'Calculate the total invoiced amount.',
                 'Calculate the average invoice amount.',
                 'Find the minimum invoice amount.',
                 'Find the maximum invoice amount.',
                 'Calculate the total amount paid by insurance.',
                 'Calculate the total outstanding amount across all invoices.',
                 'Calculate the average appointment base fee.',
                 'Find the minimum appointment base fee.',
                 'Find the maximum appointment base fee.',
                 'Calculate the average lab test value.',
                 'Find the minimum lab test value.',
                 'Find the maximum lab test value.',
                 'Count completed appointments.',
                 'Count unpaid invoices.',
                 'Count abnormal lab results, where abnormal means high, low, or critical.',
                 'Count the distinct patient states.',
                 'Count the distinct insurance providers.',
                 'Count the distinct doctor specialties.',
                 'Count the distinct appointment visit types.',
                 'Count the distinct appointment statuses.',
                 'Count the distinct lab test names.',
                 'Count the distinct lab result flags.',
                 'Count patients who have a recorded chronic condition.',
                 'Calculate the total invoice amount for patients from Idaho.',
                 'Calculate the average invoice amount for BlueCross patients.',
                 'Calculate the total outstanding balance of unpaid or partially paid invoices.',
                 'Calculate the average base fee of completed appointments.',
                 'Find the maximum test value among critical lab results.',
                 'Find the minimum test value among normal lab results.',
                 'Calculate the average years of experience among doctors.',
                 'Find the most years of experience held by any doctor.',
                 'Find the fewest years of experience held by any doctor.',
                 'Calculate the total of all appointment base fees.',
                 'Calculate the average insurance-paid amount per invoice.',
                 'Calculate the percentage of the total billed amount that was paid by insurance.',
                 'Calculate the average outstanding amount per invoice.',
                 'Count invoices whose total amount is greater than 450.',
                 'Calculate the sum of invoice amounts greater than 450.',
                 'Calculate the average test value among high lab results.',
                 'Count distinct patients who have at least one appointment.',
                 'Count distinct patients who have at least one invoice.',
                 'Count distinct doctors who have handled at least one appointment.',
                 'Count appointments that have at least one lab result.',
                 'Count appointments that have both an invoice and at least one lab result.',
                 'Calculate the percentage of appointments that are completed.'],
 'group_by': ['Count patients by state.',
              'Count patients by insurance provider.',
              'Count patients by city.',
              'Count patients by chronic condition.',
              'Count doctors by specialty.',
              'Count doctors by clinic city.',
              'Count doctors by years of experience.',
              'Count appointments by status.',
              'Count appointments by visit type.',
              'Count appointments for each doctor.',
              'Count appointments for each patient.',
              'Count appointments by appointment date.',
              'Count invoices by payment status.',
              'Count invoices by invoice date.',
              'Count lab results by result flag.',
              'Count lab results by test name.',
              'Count lab results by result date.',
              'Show the total invoiced amount by insurance provider.',
              'Show the average invoice amount by insurance provider.',
              'Show the maximum invoice amount by insurance provider.',
              'Show total outstanding balance by insurance provider.',
              'Count appointments by patient state.',
              'Count appointments by patient insurance provider.',
              'Count completed appointments by insurance provider.',
              'Count checkup appointments by patient state.',
              'Show total appointment base fees by doctor.',
              'Show average appointment base fee by doctor.',
              'Count appointments by doctor specialty.',
              'Count distinct patients seen by each specialty.',
              'Show total invoiced amount for each patient.',
              'Show average invoice amount for each patient.',
              'Show total outstanding balance for each patient.',
              'Count invoices for each patient.',
              'Count lab results for each patient.',
              'Count distinct lab test types for each patient.',
              'Show average test value for each test name.',
              'Show maximum test value for each test name.',
              'Count abnormal results for each test name.',
              'Count lab results by test name and result flag.',
              'Count invoices by insurance provider and payment status.',
              'Show total invoice amount by payment status.',
              'Show total insurance-paid amount by payment status.',
              'Count appointments by calendar month.',
              'Show total invoice amount by calendar month.',
              'Count lab results by calendar month.',
              'Count appointments by patient state and appointment status.',
              'Show invoice totals by insurance provider and payment status.',
              'Count lab results for each combination of test name and result flag.',
              'Count appointments by doctor specialty and visit type.',
              'Count patients by state and insurance provider.'],
 'having': ['Find states with more than 10 patients.',
            'Find insurance providers with more than 10 patients.',
            'Find cities with more than 5 patients.',
            'Find specialties with more than one doctor.',
            'Find clinic cities with more than two doctors.',
            'Find patients with more than 3 appointments.',
            'Find doctors who handled more than 5 appointments.',
            'Find appointment statuses that occur more than 20 times.',
            'Find visit types that occur more than 20 times.',
            'Find patients with more than 5 invoices.',
            'Find patients whose total invoiced amount is greater than 1000.',
            'Find patients whose average invoice amount is greater than 300.',
            'Find patients whose maximum invoice amount is greater than 500.',
            'Find insurance providers whose total invoiced amount is greater than 5000.',
            'Find insurance providers whose average invoice amount is greater than 300.',
            'Find insurance providers whose total outstanding balance is greater than 1000.',
            'Find payment statuses with more than 20 invoices.',
            'Find lab test names with more than 10 results.',
            'Find lab test names whose average value is greater than 100.',
            'Find result flags with more than 20 lab results.',
            'Find patients with more than one distinct lab test type.',
            'Find patients with more than two distinct abnormal lab test types.',
            'Find doctors who treated patients from more than one state.',
            'Find patients who were seen by doctors from more than one specialty.',
            'Find insurance providers whose patients were seen by more than two distinct doctors.',
            'Find patients with more than two completed appointments.',
            'Find patients with more than two unpaid invoices.',
            'Find doctors who handled more than five completed appointments.',
            'Find doctors whose total appointment base fees exceed 1000.',
            'Find specialties associated with more than 10 appointments.',
            'Find patient states whose total invoiced amount exceeds 2000.',
            'Find patient states whose total outstanding balance exceeds 500.',
            'Find insurance providers with more than five completed appointments.',
            'Find insurance providers with more than five unpaid invoices.',
            'Find test names with more than three critical results.',
            'Find patients with more than five lab results.',
            'Find patients whose average lab test value exceeds 100.',
            'Find patients whose maximum lab test value exceeds 150.',
            'Find appointment dates with more than two appointments.',
            'Find invoice dates whose total invoice amount exceeds 1000.',
            'Find patients whose insurance coverage ratio is below 50 percent.',
            'Find insurance providers whose average outstanding balance exceeds 100.',
            'Find doctors whose average appointment invoice amount exceeds 300.',
            'Find patients with more completed appointments than cancelled appointments.',
            'Find insurance providers with more unpaid invoices than fully paid invoices.',
            'Find test names with more abnormal results than normal results.',
            'Find patients with at least two distinct appointment visit types.',
            'Find doctors who handled at least two distinct visit types.',
            'Find patients whose invoices include at least two distinct payment statuses.',
            'Find insurance providers whose patients come from more than one state.'],
 'distinct_set_logic': ['List the distinct patient states.',
                        'List the distinct insurance providers.',
                        'List the distinct chronic conditions.',
                        'List the distinct doctor specialties.',
                        'List the distinct doctor clinic cities.',
                        'List the distinct appointment visit types.',
                        'List the distinct appointment statuses.',
                        'List the distinct invoice payment statuses.',
                        'List the distinct lab test names.',
                        'List the distinct lab result flags.',
                        'List distinct patients who have appointments.',
                        'List distinct doctors who have appointments.',
                        'List distinct patients who have invoices.',
                        'List distinct patients who have lab results.',
                        'List distinct patients with completed appointments.',
                        'List distinct patients with unpaid invoices.',
                        'List distinct patients with abnormal lab results.',
                        'List distinct patient-doctor pairs from appointments.',
                        'List distinct insurance-provider and doctor-specialty combinations.',
                        'List distinct patient-state and visit-type combinations.',
                        'List patients who have either a completed appointment or an unpaid invoice.',
                        'List patients who had either a checkup or a follow-up appointment.',
                        'List patients with either a high or critical lab result.',
                        'List patients insured by either BlueCross or Medicaid.',
                        'List doctors who handled either a completed appointment or a checkup appointment.',
                        'List patients who have both a completed appointment and an unpaid invoice.',
                        'List patients who had both a checkup and a follow-up appointment.',
                        'List patients who have both a critical lab result and an unpaid invoice.',
                        'List patients who have both invoices and lab results.',
                        'List doctors who handled both completed appointments and appointments with unpaid invoices.',
                        'List distinct patients who have at least one appointment but have no invoice records.',
                        'List patients who have invoices but no lab results.',
                        'List doctors who have appointments but no completed appointments.',
                        'List insurance providers that have patients but no unpaid invoices.',
                        'List test names that have high results but never normal results.',
                        'List Idaho patients who are not insured by BlueCross.',
                        'List doctors with more than 10 years of experience who never handled a completed appointment.',
                        'List patients with lab results but no critical lab results.',
                        'List patients with invoices but no unpaid invoices.',
                        'List appointments that have an invoice but no lab result.',
                        'List unique patients appearing in either invoice records or lab-result records.',
                        'List unique doctors who treated BlueCross or Medicaid patients.',
                        'List unique states of patients with completed appointments.',
                        'List unique specialties seen by Idaho patients.',
                        'List unique visit types associated with unpaid invoices.',
                        'List unique lab test names from completed appointments.',
                        'List patients who have both high and low lab results.',
                        'List patients who have at least one result under every lab result flag present in the '
                        'database.',
                        'List doctors who treated patients from every state present in the patients table.',
                        'List patients who have appointments under every appointment status present in the database.'],
 'subquery_cte': ['Find invoices whose total amount is above the average invoice amount.',
                  'Find invoices whose total amount is below the average invoice amount.',
                  'Find the invoice or invoices with the maximum total amount.',
                  'Find the invoice or invoices with the minimum total amount.',
                  'Find lab results whose test value is above the average for the same test name.',
                  'Find doctors whose appointment count is above the average doctor appointment count.',
                  'Find patients whose total invoiced amount is above the average patient total.',
                  'Find insurance providers whose total invoiced amount is above the average provider total.',
                  'Find patients whose average invoice amount is above the overall average invoice amount.',
                  'Find patients whose outstanding balance is above the average patient outstanding balance.',
                  'Find patients whose total invoiced amount is above the average for their insurance provider.',
                  'Find patients whose latest appointment was completed.',
                  'Find patients whose earliest appointment was a checkup.',
                  "Find each patient's latest appointment.",
                  "Find each patient's latest invoice.",
                  "Find each patient's latest lab result.",
                  'Find patients whose total invoice amount is greater than the largest individual invoice amount for '
                  'Idaho patients.',
                  'Find patients whose total invoiced amount is above the average patient total among BlueCross '
                  'patients.',
                  'Find doctors whose appointment count is greater than every doctor with fewer than five years of '
                  'experience.',
                  'Find patients whose lab-result count is above the average patient lab-result count.',
                  'Find patients whose number of distinct lab test types is above the average patient count of '
                  'distinct test types.',
                  'Find patients for whom at least one appointment exists.',
                  'Find patients for whom no appointment exists.',
                  'Find patients for whom at least one unpaid invoice exists.',
                  'Find patients for whom no unpaid invoice exists.',
                  'Find patients for whom at least one critical lab result exists.',
                  'Find patients who do not have any normal lab result.',
                  'Find patients whose every invoice total is greater than 200.',
                  'Find patients whose every appointment is completed.',
                  'Find doctors whose every appointment is completed.',
                  'Find insurance providers that have no unpaid invoices.',
                  'Find test names that have no normal results.',
                  'Find patients who independently have at least one completed appointment and at least one unpaid '
                  'invoice.',
                  'Find patients who have completed appointments but no cancelled appointments.',
                  'Find doctors who treated an Idaho patient insured by BlueCross.',
                  'Find insurance providers whose average patient total is above the overall average patient total.',
                  'Find test names whose average value is above the overall average lab value.',
                  'Find appointment statuses whose counts are above the average count per status.',
                  'Find visit types whose counts are below the average count per visit type.',
                  'Find patients whose maximum invoice amount is above the average patient maximum invoice amount.',
                  'Find patients whose minimum invoice amount is above the average patient minimum invoice amount.',
                  'Find patients whose latest invoice is unpaid.',
                  'Find patients whose latest lab result is critical.',
                  'Find doctors whose most recent appointment was completed.',
                  'Find patients whose total invoiced amount is above the average for patients from the same state.',
                  'Find doctors whose appointment count is above the average for doctors in the same specialty.',
                  'Find test names whose average value is above the average of all per-test averages.',
                  'Find patients whose abnormal lab-result count is above the average abnormal count per patient.',
                  'Find patients whose outstanding balance is above the average for their insurance provider.',
                  'Find patients whose lifetime invoiced amount is above their provider average and whose latest '
                  'appointment was completed.'],
 'order_limit_topk': ['Show the 10 newest appointments.',
                      'Show the 10 oldest appointments.',
                      'Show the 10 most expensive invoices.',
                      'Show the 10 least expensive invoices.',
                      'Show the 10 most recent lab results.',
                      'Show the 10 oldest lab results.',
                      'Show the five most experienced doctors.',
                      'Show the five least experienced doctors.',
                      'Show the 10 highest lab test values.',
                      'Show the 10 lowest lab test values.',
                      'Show the 10 appointments with the highest base fees.',
                      'Show the 10 appointments with the lowest base fees.',
                      'Show the five patients with the highest total invoiced amount.',
                      'Show the five patients with the lowest total invoiced amount.',
                      'Show the five doctors with the most appointments.',
                      'Show the five doctors with the fewest appointments.',
                      'Show insurance providers ranked by total invoiced amount.',
                      'Show patient states ranked by patient count.',
                      'Show visit types ranked by appointment count.',
                      'Show test names ranked by average test value.',
                      'Show result flags ranked by lab-result count.',
                      'Show payment statuses ranked by total invoice amount.',
                      'Show the five patients with the highest outstanding balance.',
                      'Show doctors ranked by total appointment base fees.',
                      'Show patients ranked by lab-result count.',
                      'Show patients ranked by number of distinct lab test types.',
                      'Show specialties ranked by appointment count.',
                      'Show clinic cities ranked by doctor count.',
                      'Find the most recent invoice for each patient.',
                      'Find the largest invoice for each patient.',
                      'Find the smallest invoice for each patient.',
                      'Find the highest lab value for each test name.',
                      'Find the lowest lab value for each test name.',
                      'Find the most experienced doctor in each specialty.',
                      'Find the busiest doctor in each specialty.',
                      'Find the patient with the highest total invoiced amount in each insurance provider.',
                      'Find the patient with the lowest total invoiced amount in each insurance provider.',
                      'Find the largest invoice under each payment status.',
                      'Find the highest lab value under each result flag.',
                      "Find each patient's latest completed appointment.",
                      "Find each patient's earliest appointment.",
                      'Find the top three doctors by appointment count within each specialty.',
                      'Find the top three patients by total invoiced amount within each insurance provider.',
                      'Find the two highest lab values for each test name.',
                      'Show the five invoice dates with the highest total invoiced amount.',
                      'Show the five appointment dates with the most appointments.',
                      'Show the five patients with the highest average invoice amount.',
                      'Rank patients by outstanding balance and return the top five.',
                      'Find the insurance provider with the highest average invoice amount.',
                      'Find the lab test name with the lowest average test value.'],
 'derived_metrics': ['Show each invoice with its outstanding amount, defined as total amount minus insurance paid.',
                     "Calculate each patient's total outstanding balance from all invoices.",
                     'Show average outstanding amount for each patient.',
                     'Show maximum outstanding amount for each patient.',
                     'Show total outstanding balance for each insurance provider.',
                     'Show the total amount covered by insurance.',
                     'Show the insurance coverage ratio for each invoice.',
                     'Show the average insurance coverage ratio for each insurance provider.',
                     'Show the uncovered amount for each invoice.',
                     "Show each patient's total billed amount and total insurance-paid amount.",
                     "Show each patient's total billed amount, insurance-paid amount, and outstanding balance.",
                     "Show the percentage of each patient's billed amount that remains outstanding.",
                     "Show each patient's outstanding balance considering only unpaid or partially paid invoices.",
                     "Show the difference between each appointment's invoice total and base fee.",
                     'Show total invoice markup over base fees for each patient.',
                     'Show average invoice markup over base fees for each doctor.',
                     'Show total billed amount minus total base fees for each insurance provider.',
                     "Show each patient's abnormal lab-result rate.",
                     "Show each patient's completed-appointment rate.",
                     "Show each patient's unpaid-invoice rate.",
                     "Show each patient's critical-lab-result rate.",
                     'Show the number of distinct lab test types for each patient.',
                     'Show the average number of lab results per appointment for each patient.',
                     'Show the invoice-per-appointment ratio for each patient.',
                     'Show the lab-result-per-appointment ratio for each patient.',
                     'Show average invoice amount per completed appointment for each patient.',
                     'Show total billed amount associated with each doctor.',
                     'Show total outstanding balance associated with each doctor.',
                     "Show each patient's lifetime invoiced amount.",
                     'Show the average patient lifetime invoiced amount for each insurance provider.',
                     "Show how far each patient's lifetime invoiced amount is above or below their provider average.",
                     "Show how far each doctor's appointment count is above or below the average for their specialty.",
                     'Show how far each lab result value is above or below the average for its test name.',
                     'Show how far each invoice total is above or below the overall average invoice total.',
                     "Show how far each patient's average invoice is above or below the overall patient average "
                     'invoice.',
                     'Show the number of days between each appointment date and its invoice date.',
                     'Show the number of days between each appointment date and each lab-result date.',
                     "Show each patient's approximate age in years at each appointment.",
                     'Classify doctors into experience groups of under 5 years, 5 to 10 years, and over 10 years.',
                     'Find patients whose total outstanding balance is positive.',
                     'Find insurance providers whose overall insurance coverage ratio is below 50 percent.',
                     'Find patients whose abnormal lab-result rate is greater than 50 percent.',
                     'Find doctors whose appointment completion rate is above the overall completion rate.',
                     'Find patients whose average outstanding amount is above the overall patient average.',
                     'Find insurance providers whose average patient outstanding balance is above the overall provider '
                     'average.',
                     'Find patients whose invoice-to-appointment ratio is greater than one.',
                     "Show each doctor's billed amount per appointment.",
                     'Show the critical-result share for each lab test name.',
                     'Find patients with more than one abnormal test type and an outstanding balance above the average '
                     'patient balance.',
                     'Find patients whose lifetime spend is above their provider average and whose abnormal-result '
                     'rate is above the overall patient abnormal-result rate.'],
 'temporal_complex': ['Identify patients for whom the most recent appointment has completed status.',
                      'Find patients whose latest appointment was cancelled.',
                      'Identify patients whose first appointment was a checkup.',
                      "Find each patient's most recent appointment date.",
                      "Find each patient's first appointment date.",
                      "Find each patient's most recent invoice.",
                      "Find each patient's earliest invoice.",
                      "Find each patient's most recent lab result.",
                      "Find each patient's earliest lab result.",
                      'Identify doctors whose latest handled appointment has completed status.',
                      'Identify patients whose newest invoice has unpaid status.',
                      'Identify patients whose newest lab result is critical.',
                      'Find patients with an appointment within 30 days of the latest appointment date in the '
                      'database.',
                      'Show appointments that occurred on the latest appointment date in the database.',
                      'Show invoices issued on the latest invoice date in the database.',
                      'Show lab results recorded on the latest result date in the database.',
                      'Find patients who had a completed appointment after the date of an unpaid invoice.',
                      'Find patients whose most recent completed appointment occurred after their most recent unpaid '
                      'invoice.',
                      'Find patients with a lab result recorded after their latest appointment.',
                      'Find patients whose most recent lab result is abnormal.',
                      'Find patients whose first lab result was normal.',
                      'Find doctors whose earliest appointment was completed.',
                      'Find patients with appointments on at least three distinct dates.',
                      'Find patients with invoices on at least two distinct dates.',
                      'Find patients with lab results on at least two distinct dates.',
                      'Find patients whose latest appointment was completed and whose lifetime invoiced amount exceeds '
                      '1000.',
                      'Find patients whose latest appointment was completed and whose lifetime invoiced amount is '
                      'above their insurance-provider average.',
                      'Find patients whose earliest appointment was a checkup and whose outstanding balance is '
                      'positive.',
                      'Find patients whose latest lab result was critical and whose lifetime invoiced amount is above '
                      'the average patient total.',
                      'Find patients whose latest invoice is unpaid and who also have at least one abnormal lab '
                      'result.',
                      'Find patients who have had no appointment after January 1, 2025.',
                      'Count appointments by year and month.',
                      'Show invoice totals by year and month.',
                      'Count lab results by year and month.',
                      "Show the number of days since each patient's latest appointment relative to the latest "
                      'appointment date in the database.',
                      'Find the longest gap between consecutive appointments for each patient.',
                      'Find patients whose second most recent appointment was completed.',
                      'Show the two most recent appointments for each patient.',
                      "Show the appointment immediately before each patient's latest appointment.",
                      'Find patients whose latest appointment status differs from their earliest appointment status.',
                      'Find patients whose latest invoice date is after their latest appointment date.',
                      'Find appointments whose invoice date is after the appointment date.',
                      'Find appointments whose lab-result date is after the appointment date.',
                      'Find patients whose latest completed appointment qualifies them and whose lifetime total is '
                      'above their provider average.',
                      'Find patients whose latest appointment was completed and who have more than one abnormal lab '
                      'test type.',
                      'Find patients whose latest appointment was completed and whose outstanding balance is above the '
                      'average patient outstanding balance.',
                      'Find patients whose latest appointment was completed, who have more than one abnormal lab test '
                      'type, and whose outstanding balance is above the average patient outstanding balance.',
                      'Find the doctor with the most recent appointment in each specialty.',
                      'Find patients whose latest appointment was completed, whose latest invoice is unpaid, and whose '
                      'latest lab result is abnormal.',
                      'Find patients whose latest appointment was completed and whose total invoiced amount, '
                      'outstanding balance, and abnormal-test count are all above their respective patient averages.']}
CLASSIFICATIONS = list(QUERY_GROUPS)

assert len(QUERY_GROUPS) == 10
assert all(len(items) == 50 for items in QUERY_GROUPS.values())
assert sum(len(items) for items in QUERY_GROUPS.values()) == 500
assert len({q for items in QUERY_GROUPS.values() for q in items}) == 500


def difficulty(position: int) -> str:
    if position <= 15:
        return "easy"
    if position <= 35:
        return "medium"
    return "hard"


def records() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    global_index = 0
    for classification, questions in QUERY_GROUPS.items():
        for position, question in enumerate(questions, start=1):
            global_index += 1
            result.append({
                "global_index": global_index,
                "classification": classification,
                "classification_index": position,
                "difficulty": difficulty(position),
                "question": question,
            })
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 500 classified NL queries against SpiderSQL DB46."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--classification",
        choices=["all", *CLASSIFICATIONS],
        default="all",
    )
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--output")
    parser.add_argument("--append", action="store_true")
    return parser.parse_args()


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {
                "success": False,
                "error": "non_object_response",
                "message": raw,
            }
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                parsed.setdefault("_http_status", exc.code)
                return parsed
        except json.JSONDecodeError:
            pass
        return {
            "success": False,
            "error": f"HTTP {exc.code}",
            "message": raw,
        }
    except URLError as exc:
        return {
            "success": False,
            "error": "connection_error",
            "message": str(exc.reason),
        }
    except TimeoutError:
        return {
            "success": False,
            "error": "timeout",
            "message": f"Request exceeded {timeout} seconds.",
        }
    except json.JSONDecodeError as exc:
        return {
            "success": False,
            "error": "invalid_json_response",
            "message": str(exc),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": type(exc).__name__,
            "message": str(exc),
        }


def extract_sql(result: dict[str, Any]) -> str:
    generated = result.get("generated_sql")
    if isinstance(generated, dict):
        sql = generated.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    if isinstance(generated, str) and generated.strip():
        return generated.strip()

    rejected = result.get("debug_rejected_sql")
    if isinstance(rejected, dict):
        sql = rejected.get("sql")
        if isinstance(sql, str) and sql.strip():
            return sql.strip()
    if isinstance(rejected, str) and rejected.strip():
        return rejected.strip()

    return "-- NO SQL RETURNED"


def passed(result: dict[str, Any]) -> bool:
    if result.get("success") is not True:
        return False
    execution = result.get("execution")
    return (
        isinstance(execution, dict)
        and execution.get("executed") is True
        and not execution.get("error")
    )


def warning_text(result: dict[str, Any]) -> str:
    warnings = result.get("warnings")
    if not warnings:
        return "None"
    if isinstance(warnings, list):
        return "\n".join(f"- {value}" for value in warnings)
    return str(warnings)


def save_one(
    handle,
    record: dict[str, Any],
    status: str,
    elapsed: float,
    response: dict[str, Any],
) -> None:
    execution = response.get("execution")
    execution = execution if isinstance(execution, dict) else {}
    error = (
        response.get("error")
        or execution.get("error")
        or response.get("message")
        or ""
    )

    handle.write("=" * 110 + "\n")
    handle.write(f"QUERY {record['global_index']:03d}\n")
    handle.write(f"CLASSIFICATION: {record['classification']}\n")
    handle.write(
        f"CLASSIFICATION POSITION: {record['classification_index']:02d}/50\n"
    )
    handle.write(f"DIFFICULTY: {record['difficulty']}\n")
    handle.write(f"STATUS: {status}\n")
    handle.write(f"ELAPSED: {elapsed:.2f} seconds\n")
    handle.write(f"QUESTION: {record['question']}\n")
    handle.write(
        f"SELECTED CANDIDATE: "
        f"{response.get('selected_candidate_source', '')}\n"
    )
    handle.write(f"ROW COUNT: {execution.get('row_count')}\n")
    handle.write(f"ERROR: {error}\n\n")
    handle.write("SQL:\n")
    handle.write(extract_sql(response) + "\n\n")
    handle.write("WARNINGS:\n")
    handle.write(warning_text(response) + "\n\n")
    handle.flush()


def main() -> int:
    args = parse_args()
    selected = records()

    if args.classification != "all":
        selected = [
            item for item in selected
            if item["classification"] == args.classification
        ]

    selected = [
        item for item in selected
        if item["global_index"] >= args.start_index
    ]

    if args.limit is not None:
        selected = selected[:max(args.limit, 0)]

    if not selected:
        print("No queries matched the selected options.")
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = Path(
        args.output
        or f"db46_500_classified_results_{args.classification}_{timestamp}.txt"
    ).resolve()
    endpoint = (
        f"{args.base_url.rstrip('/')}/database/{DATABASE_ID}/execute_sql"
    )

    pass_count = 0
    fail_count = 0
    by_classification: dict[str, dict[str, int]] = {}
    started = time.perf_counter()
    mode = "a" if args.append else "w"

    print(f"Endpoint: {endpoint}")
    print(f"Output: {output}")
    print(f"Selected queries: {len(selected)}")
    print("-" * 100)

    with output.open(mode, encoding="utf-8") as handle:
        handle.write(
            "SpiderSQL DB46 — 500 Classified Natural-Language Query Test\n"
        )
        handle.write(
            f"Started: {datetime.now().isoformat(timespec='seconds')}\n"
        )
        handle.write(f"Endpoint: {endpoint}\n")
        handle.write(f"Classification filter: {args.classification}\n")
        handle.write(f"Selected count: {len(selected)}\n\n")
        handle.flush()

        previous = None
        for run_index, record in enumerate(selected, start=1):
            category = record["classification"]
            if category != previous:
                heading = f"\n######## CLASSIFICATION: {category} ########\n"
                print(heading.strip(), flush=True)
                handle.write(heading)
                handle.flush()
                previous = category

            query_started = time.perf_counter()
            response = post_json(
                endpoint,
                {"question": record["question"]},
                args.timeout,
            )
            elapsed = time.perf_counter() - query_started
            status = "PASS" if passed(response) else "FAIL"

            if status == "PASS":
                pass_count += 1
            else:
                fail_count += 1

            stats = by_classification.setdefault(
                category, {"PASS": 0, "FAIL": 0}
            )
            stats[status] += 1

            print(
                f"[{run_index:03d}/{len(selected):03d}] "
                f"[Q{record['global_index']:03d}] "
                f"[{category}] [{record['difficulty']}] "
                f"{status} ({elapsed:.2f}s) — {record['question']}",
                flush=True,
            )
            save_one(handle, record, status, elapsed, response)

            if args.delay > 0 and run_index < len(selected):
                time.sleep(args.delay)

        elapsed_total = time.perf_counter() - started
        handle.write("\n" + "=" * 110 + "\nFINAL SUMMARY\n")
        handle.write(f"PASS: {pass_count}\n")
        handle.write(f"FAIL: {fail_count}\n")
        handle.write(f"TOTAL: {len(selected)}\n")
        handle.write(
            f"EXECUTION SUCCESS RATE: "
            f"{pass_count / len(selected) * 100:.2f}%\n"
        )
        handle.write(f"TOTAL ELAPSED: {elapsed_total:.2f} seconds\n")
        handle.write("\nBY CLASSIFICATION:\n")
        for category, stats in by_classification.items():
            total = stats["PASS"] + stats["FAIL"]
            rate = stats["PASS"] / total * 100 if total else 0.0
            handle.write(
                f"- {category}: PASS={stats['PASS']}, "
                f"FAIL={stats['FAIL']}, RATE={rate:.2f}%\n"
            )
        handle.flush()

    print("-" * 100)
    print(f"PASS: {pass_count}")
    print(f"FAIL: {fail_count}")
    print(f"TOTAL: {len(selected)}")
    print(
        f"Execution success rate: "
        f"{pass_count / len(selected) * 100:.2f}%"
    )
    print("By classification:")
    for category, stats in by_classification.items():
        total = stats["PASS"] + stats["FAIL"]
        rate = stats["PASS"] / total * 100 if total else 0.0
        print(
            f"  {category}: PASS={stats['PASS']}, "
            f"FAIL={stats['FAIL']}, RATE={rate:.2f}%"
        )
    print(f"Saved: {output}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
