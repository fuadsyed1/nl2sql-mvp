#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BASE_URL = "http://127.0.0.1:8000"
DATABASE_ID = 35  # Change this if SpiderSQL assigned a different local database id.
TIMEOUT_SECONDS = 240
OUTPUT_FILE = "bq046_tcga_30_generated_sql_db46.sql"

QUESTIONS: List[str] = [
    "Find case barcodes and their corresponding GDC file URLs for female TCGA BRCA patients age 30 or younger, excluding any cases with radiation therapy or prior malignancy, and include only current files.",
    "List cases that have at least one current file and at least one legacy file, showing the case barcode, current file count, legacy file count, and total distinct GDC file IDs.",
    "Find patients whose case appears in PanCanAtlas_manifest but has no matching row in rel12_caseData, returning the case barcode and manifest file identifiers.",
    "Show current files whose GDC file ID maps to more than one GCS URL, grouped by file ID, with the number of distinct URLs.",
    "Find cases with both active and obsolete GDC sync records in 2019, returning the case barcode or file ID, active status date, obsolete status date, and file name if available.",
    "List cancer types where the number of distinct cases with current files is greater than the number of distinct cases with legacy files.",
    "Find case barcodes that have files in both the 2019-01-04 active sync table and the 2019-01-15 active sync table, but where the file metadata changed between the two dates.",
    "For each disease code, list the top 5 data categories by distinct current file count, including total file size if size metadata exists.",
    "Find aliquots that map to multiple case IDs, returning the aliquot barcode, number of distinct cases, and the associated case IDs.",
    "Find cases that have multiple aliquots but only one distinct GDC file URL across current file data.",
    "List current files for BRCA cases where the same case also appears in legacy file data with a different data type.",
    "Find files that are present in GDC_sync_legacy_20190115 but absent from GDC_sync_legacy_20190104, grouped by data category and project if available.",
    "Show cases where clinical gender is female but any linked file or manifest metadata indicates a conflicting sex or gender value, if such columns exist.",
    "Find case barcodes with current files in every available data category represented for their cancer type.",
    "List GDC file IDs that are present in rel12_fileData_current but do not have a matching GCS URL in the GDC file ID to GCS URL mapping table.",
    "Find patients diagnosed at age 30 or younger who have more than five distinct current files, grouped by disease code and sorted by file count descending.",
    "For each case, compare current and legacy file counts and return only cases where legacy files outnumber current files.",
    "Find data types that appear in current file data for BRCA but not in legacy file data for BRCA.",
    "List cases whose current files include both open-access and controlled-access files, returning counts for each access type.",
    "Find current GDC files whose file name appears in both active and obsolete sync tables, returning the latest sync status and the mapped GCS URL.",
    "Find cases with at least one aliquot mapping but no current file data, returning the case ID, aliquot count, and clinical disease code if available.",
    "For every project or disease code, list cases whose current file count is above the average current file count for that same project or disease code.",
    "Find duplicate file records where the same GDC file ID appears with different file names, data types, or data formats across current and legacy file tables.",
    "List GDC file URLs for cases that are in PanCanAtlas_manifest and also have clinical data in rel12_caseData, but exclude files marked obsolete.",
    "Find current files linked to cases whose age at diagnosis is missing, null, or unknown, grouped by data category and data type.",
    "Show cases where every current file has a GCS URL mapping, but at least one legacy file does not have a GCS URL mapping.",
    "Find disease codes where the same aliquot barcode maps to cases from more than one disease code.",
    "List current files for female BRCA cases where diagnosis age is 30 or younger and the file also appears in the active sync table but not in the obsolete sync table.",
    "For each case, return the latest available current file record per data type based on file updated date or sync date, using ties if multiple files share the latest date.",
    "Find cases that have current files from all data formats represented in their disease code, and return the case barcode with the number of distinct formats.",
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
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                sql = f"-- ERROR: HTTPError {exc.code}: {body}"
            except Exception as exc:
                sql = f"-- ERROR: {type(exc).__name__}: {exc}"
            print(sql)
            print()
            out.write(sql + "\n\n")


if __name__ == "__main__":
    main()
