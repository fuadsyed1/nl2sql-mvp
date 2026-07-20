"""
Write benchmark_freeze.json — the reproducibility record for the final
evaluation. Run on the machine that will execute the benchmarks (it reads
git state and hashes the pipeline files):

    python -m benchmarks.final_evaluation.generation.build_freeze

Never commits anything; it only RECORDS the current state.
"""

import datetime
import json
import os
import subprocess

from benchmarks.final_evaluation.common import db as bdb
from benchmarks.final_evaluation.common import manifest as mf

BASE = os.path.join(os.path.dirname(__file__), "..")
BACKEND = os.path.abspath(os.path.join(BASE, "..", ".."))

PIPELINE_FILES = [
    "app.py",
    "semantic/semantic_checklist.py",
    "semantic/semantic_contract.py",
    "semantic/llm_sql_direct.py",
    "semantic/llm_sql_repair.py",
    "sql_analysis/ast_tools.py",
    "validators/grain_validator.py",
    "validators/fanout_validator.py",
    "validators/temporal_validator.py",
    "sql_candidates/candidate_scorer.py",
    "sql_candidates/candidate_selector.py",
    "sql_candidates/semantic_sql_guards.py",
    "containment/checker.py",
    "containment/service.py",
]


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=BACKEND,
                              capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except Exception as exc:
        return f"unavailable: {exc}"


def main():
    manifests = {}
    for sub in ("sql", "containment"):
        d = os.path.join(BASE, sub, "manifests")
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if name.endswith(".jsonl"):
                    manifests[f"{sub}/{name}"] = mf.file_sha256(
                        os.path.join(d, name))
    freeze = {
        "created_at": datetime.datetime.now().isoformat(),
        "git_head": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "working_tree_dirty": bool(_git("status", "--porcelain")),
        "model_provider": os.environ.get("LLM_PROVIDER", "mindrouter"),
        "model_name": os.environ.get("LLM_MODEL_NAME",
                                     "qwen/qwen3.5-122b"),
        "benchmark_databases": {
            str(k): {"name": v[0], "path": v[1]}
            for k, v in bdb.BENCHMARK_DATABASES.items()},
        "pipeline_file_sha256": {
            f: (mf.file_sha256(os.path.join(BACKEND, f))
                if os.path.exists(os.path.join(BACKEND, f))
                else "missing")
            for f in PIPELINE_FILES},
        "manifest_sha256": manifests,
        "note": ("Data-dependent evaluation on the frozen databases above. "
                 "Containment verdicts hold for the frozen data only — "
                 "never a symbolic proof."),
    }
    out = os.path.join(BASE, "benchmark_freeze.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(freeze, f, indent=2)
    print(f"freeze written: {out}")
    print(f"  git_head={freeze['git_head'][:12]} "
          f"dirty={freeze['working_tree_dirty']} "
          f"manifests={len(manifests)}")


if __name__ == "__main__":
    main()
