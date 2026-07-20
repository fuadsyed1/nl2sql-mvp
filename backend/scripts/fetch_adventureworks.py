"""
scripts/fetch_adventureworks.py

Download a full AdventureWorks (OLTP) SQLite database into the local benchmark
folder. RUN THIS LOCALLY (it needs network access):

    python backend/scripts/fetch_adventureworks.py

It writes:
    backend/local_benchmarks/relational_sample_dbs/sqlite/adventureworks.sqlite

Source (default): Spider 2.0's curated AdventureWorks.sqlite hosted on HuggingFace
(dataset `sarus-tech/spider_12`, file `spider2-localdb/AdventureWorks.sqlite`).
This is the FULL OLTP schema (~68 tables), already in SQLite — no conversion.

Do NOT use the martinandersen3d / nuitsjp SQLite repos: those are
AdventureWorks*LT* (12 tables) and must be rejected.

After downloading, verify it meets the target with the profiler:
    python backend/scripts/profile_local_benchmark_db.py \
        --db backend/local_benchmarks/relational_sample_dbs/sqlite/adventureworks.sqlite \
        --name adventureworks
"""

import os
import sys
import urllib.request

HF_REPO = "sarus-tech/spider_12"
HF_FILE = "spider2-localdb/AdventureWorks.sqlite"
HF_RESOLVE_URL = (
    f"https://huggingface.co/datasets/{HF_REPO}/resolve/main/{HF_FILE}"
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
TARGET = os.path.join(
    _BACKEND, "local_benchmarks", "relational_sample_dbs", "sqlite",
    "adventureworks.sqlite",
)


def _via_hf_hub():
    """Preferred: official HuggingFace client (handles auth/LFS/redirects)."""
    from huggingface_hub import hf_hub_download  # pip install huggingface_hub
    path = hf_hub_download(
        repo_id=HF_REPO, repo_type="dataset", filename=HF_FILE)
    return path


def _via_urllib(dest):
    """Fallback: direct download of the resolved file URL."""
    req = urllib.request.Request(HF_RESOLVE_URL, headers={"User-Agent": "spidersql"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    return dest


def main():
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    print(f"Downloading full AdventureWorks (OLTP) SQLite -> {TARGET}")
    try:
        src = _via_hf_hub()
        import shutil
        shutil.copyfile(src, TARGET)
        print("Downloaded via huggingface_hub.")
    except Exception as exc:  # noqa: BLE001 - fall back to a plain download
        print(f"huggingface_hub unavailable/failed ({exc}); trying direct URL...")
        _via_urllib(TARGET)
        print("Downloaded via direct URL.")

    size = os.path.getsize(TARGET)
    print(f"Wrote {TARGET} ({size/1_048_576:.1f} MB)")
    if size < 4_000_000:
        print("WARNING: file is small (<4 MB). Full AdventureWorks OLTP is "
              "usually larger; verify it is NOT the LT version with the profiler.")
    print("\nNext: profile it")
    print("  python backend/scripts/profile_local_benchmark_db.py "
          f"--db {os.path.relpath(TARGET, os.path.dirname(_BACKEND))} "
          "--name adventureworks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
