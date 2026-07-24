# Day 3 — 64-Query Live Targeted Verification (Runbook)

The live run **must be executed on your local Windows machine**. It cannot run in
the assistant sandbox. Three independent, verified blockers:

1. **Runner is local-only.** `run_day2_targeted.py`'s own header says
   *"LOCAL-ONLY — do NOT run in the sandbox … against a locally-running backend
   that has MindRouter access."*
2. **LLM endpoint blocked.** The backend needs Ollama/MindRouter at
   `localhost:11434`. From the sandbox that is unreachable — the network
   allowlist returns `403 blocked-by-allowlist`. With no LLM, no candidates are
   generated, so any "run" would be empty/fabricated.
3. **Windows venv.** The environment ships `venv/Scripts/python.exe` (Windows);
   it cannot execute under the Linux sandbox.

Everything that does **not** need the live LLM has already been done for you
(see "Already done", below). Run the steps here, then hand the artifacts back to
the assistant for the full semantic audit (STEPS 4–8).

---

## Pre-run facts (confirmed)

- DB files present: `uploads\user_4\databases\db_5{4,5,6,7}\data.db` ✓
- Runner present and captures selected SQL from `generated_sql.sql`
  (`resp["generated_sql"]["sql"]`) ✓ — **do not modify the runner**.
- Branch `main`, HEAD `2420f67e5b2e20f2189b1107c22ed7dd54830ace`.
- Current uncommitted verified work is intact (selector, derived arithmetic,
  repaired-SQL HAVING→WHERE validity, tests, day2c replays).

## Already done (STEP 1 — evidence preserved)

Timestamped backup created at:
`benchmarks\go_live_day2\_day3_preverify_backup_20260723_170222\`
containing the before/after CSV, results txt, reviewed CSVs, all `day2c_*`
replays, the four most-recent DB54–57 targeted full traces, and
`PRERUN_STATE.txt` (branch, HEAD, python, port, LLM status, dirty files).

---

## STEP 2 — Start exactly ONE full-trace backend (PowerShell, from `backend\`)

```powershell
# ensure nothing is already on port 8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }

# confirm Ollama is up and the model is present
curl http://localhost:11434/api/tags

# full-trace env, current venv, NO --reload, single worker
$env:SPIDERSQL_FULL_TRACE = "true"
$env:SPIDERSQL_TRACE_DEBUG = "true"
.\venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log `
  *>&1 | Tee-Object -FilePath ("benchmarks\go_live_day2\day3_backend_console_" + (Get-Date -Format yyyyMMdd_HHmmss) + ".log")
```

Wait until startup logs confirm **full trace is enabled**. Leave this window
open. Do **not** start a second backend.

## STEP 3 — Run the 64 targeted queries (a SECOND PowerShell, from `backend\`)

```powershell
.\venv\Scripts\python.exe benchmarks\go_live_day2\run_day2_targeted.py `
  --base-url http://127.0.0.1:8000 `
  *>&1 | Tee-Object -FilePath ("benchmarks\go_live_day2\day3_runner_" + (Get-Date -Format yyyyMMdd_HHmmss) + ".log")
```

Expect `done: 64 rows; after_sql captured …`. Then stop the backend
(Ctrl-C in the STEP 2 window). Do **not** run the 64 a second time.

---

## What to hand back to the assistant (for STEPS 4–8)

- `benchmarks\go_live_day2\day2_targeted_before_after.csv` (now filled with
  `after_sql` / `rerun_status`)
- the four fresh `benchmarks\results\day2_targeted_full_trace_db5{4,5,6,7}_<newTS>.txt`
- both `day3_backend_console_*.log` and `day3_runner_*.log`

The assistant will then, **without changing production code**:
verify 64 rows + no blank SQL; audit every SQL semantically; confirm the four
release-critical queries (DB56 t52, DB57 t62, DB57 t91, DB56 t96); confirm
32/32 protected controls and 0 regressions; classify every remaining failure
A–K with trace evidence; and produce the reviewed CSV + the Day-3 Markdown
summary with net change vs the prior live result (17/32 recovered, 53.1%).

## Do NOT
commit · push · deploy · start the 2,000-query benchmark · start containment ·
rerun all 64 twice · modify the runner · alter the current verified implementation.
