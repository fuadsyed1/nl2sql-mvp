"""
scripts/fetch_omop.py

Download the OHDSI Eunomia "GiBleed" OMOP CDM sample (Synthea-derived synthetic
healthcare data) and extract its per-table CSVs into the raw/omop/ folder.
RUN THIS LOCALLY (needs network access):

    python backend/scripts/fetch_omop.py

Source (default): OHDSI/EunomiaDatasets -> datasets/GiBleed/GiBleed_5.3.zip.
The zip contains one CSV per OMOP CDM table (person, visit_occurrence,
condition_occurrence, drug_exposure, measurement, observation, concept, ...),
i.e. real synthetic healthcare data across the OMOP schema.

After extracting, import + profile with the existing tools:
    python backend/scripts/import_csv_dir_to_sqlite.py \
        --csv-dir backend/local_benchmarks/relational_sample_dbs/raw/omop \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/omop.sqlite --drop
    python backend/scripts/profile_local_benchmark_db.py \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/omop.sqlite --name omop

If the default version 404s, browse the repo for the current filename:
    https://github.com/OHDSI/EunomiaDatasets/tree/main/datasets/GiBleed
and pass it with --url.
"""

import argparse
import io
import os
import sys
import urllib.request
import zipfile

DEFAULT_URL = (
    "https://github.com/OHDSI/EunomiaDatasets/raw/main/"
    "datasets/GiBleed/GiBleed_5.3.zip"
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
RAW_DIR = os.path.join(
    _BACKEND, "local_benchmarks", "relational_sample_dbs", "raw", "omop")


def main(argv=None):
    p = argparse.ArgumentParser(description="Fetch the Eunomia GiBleed OMOP CSVs.")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--out", default=RAW_DIR, help="where to extract the CSVs")
    args = p.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    print(f"Downloading {args.url}")
    req = urllib.request.Request(args.url, headers={"User-Agent": "spidersql"})
    try:
        with urllib.request.urlopen(req) as resp:
            blob = resp.read()
    except Exception as exc:  # noqa: BLE001
        print(f"Download failed: {exc}", file=sys.stderr)
        print("Browse https://github.com/OHDSI/EunomiaDatasets/tree/main/datasets/GiBleed"
              " and pass the current zip with --url.", file=sys.stderr)
        return 2

    extracted = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for member in z.namelist():
            if not member.lower().endswith(".csv"):
                continue
            # flatten: write each CSV directly under out/ by its base name
            data = z.read(member)
            name = os.path.basename(member)
            with open(os.path.join(args.out, name), "wb") as f:
                f.write(data)
            extracted += 1
    print(f"Extracted {extracted} CSV files into {args.out}")
    if extracted == 0:
        print("No CSVs found in the archive; check --url.", file=sys.stderr)
        return 2

    print("\nNext: import + profile")
    print("  python backend/scripts/import_csv_dir_to_sqlite.py "
          "--csv-dir backend/local_benchmarks/relational_sample_dbs/raw/omop "
          "--db backend/local_benchmarks/relational_sample_dbs/sqlite/omop.sqlite --drop")
    print("  python backend/scripts/profile_local_benchmark_db.py "
          "--db backend/local_benchmarks/relational_sample_dbs/sqlite/omop.sqlite --name omop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
