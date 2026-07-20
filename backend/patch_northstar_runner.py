"""
Patch the Northstar 500-query runner with OPTIONAL trace headers.

    python patch_northstar_runner.py path\\to\\northstar_500_test_run.py

Minimal, behavior-preserving changes:
  * post_query() accepts optional extra_headers (default None — normal
    behavior unchanged);
  * a --trace-run-id CLI option (default northstar_500_<timestamp>);
  * the main loop sends X-SpiderSQL-Trace-Run / -Test-ID / -Test-Category /
    -Test-Difficulty with every request.
The headers are ignored by the backend unless SPIDERSQL_FULL_TRACE=true.
A .bak backup is written next to the runner. Idempotent: refuses to patch
twice. PASS/FAIL behavior and the existing TXT output are untouched.
"""

import sys
import time
from pathlib import Path

OLD_SIG = (
    "def post_query(base_url: str, database_id: int, question: str, "
    "timeout: int) -> tuple[int, dict[str, Any]]:\n"
    "    url = f\"{base_url.rstrip('/')}/database/{database_id}/execute_sql\"\n"
    "    request_body = json.dumps({\"question\": question}).encode(\"utf-8\")\n"
    "    request = urllib.request.Request(\n"
    "        url,\n"
    "        data=request_body,\n"
    "        headers={\"Content-Type\": \"application/json\", "
    "\"Accept\": \"application/json\"},\n"
    "        method=\"POST\",\n"
    "    )\n")
NEW_SIG = (
    "def post_query(base_url: str, database_id: int, question: str, "
    "timeout: int, extra_headers: dict | None = None) "
    "-> tuple[int, dict[str, Any]]:\n"
    "    url = f\"{base_url.rstrip('/')}/database/{database_id}/execute_sql\"\n"
    "    request_body = json.dumps({\"question\": question}).encode(\"utf-8\")\n"
    "    _headers = {\"Content-Type\": \"application/json\", "
    "\"Accept\": \"application/json\"}\n"
    "    _headers.update(extra_headers or {})\n"
    "    request = urllib.request.Request(\n"
    "        url,\n"
    "        data=request_body,\n"
    "        headers=_headers,\n"
    "        method=\"POST\",\n"
    "    )\n")

OLD_ARG = (
    "    parser.add_argument(\n"
    "        \"--timeout\",\n")
NEW_ARG = (
    "    parser.add_argument(\n"
    "        \"--trace-run-id\",\n"
    "        default=f\"northstar_500_{time.strftime('%Y%m%d_%H%M%S')}\",\n"
    "        help=\"Trace run id sent as X-SpiderSQL-Trace-Run \"\n"
    "             \"(used only when the backend enables "
    "SPIDERSQL_FULL_TRACE).\",\n"
    "    )\n"
    "    parser.add_argument(\n"
    "        \"--timeout\",\n")

OLD_CALL = (
    "            http_status, payload = post_query(\n"
    "                base_url=args.base_url,\n"
    "                database_id=args.database_id,\n"
    "                question=case[\"query\"],\n"
    "                timeout=args.timeout,\n"
    "            )\n")
NEW_CALL = (
    "            http_status, payload = post_query(\n"
    "                base_url=args.base_url,\n"
    "                database_id=args.database_id,\n"
    "                question=case[\"query\"],\n"
    "                timeout=args.timeout,\n"
    "                extra_headers={\n"
    "                    \"X-SpiderSQL-Trace-Run\": args.trace_run_id,\n"
    "                    \"X-SpiderSQL-Test-ID\": f\"{case['id']:03d}\",\n"
    "                    \"X-SpiderSQL-Test-Category\": case[\"category\"],\n"
    "                    \"X-SpiderSQL-Test-Difficulty\": "
    "case[\"difficulty\"],\n"
    "                },\n"
    "            )\n")

OLD_IMPORT = "import sys\nimport time\n"


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    src = path.read_text(encoding="utf-8")
    if "extra_headers" in src:
        print("already patched — nothing to do")
        return 0
    for old, name in ((OLD_SIG, "post_query"), (OLD_ARG, "parse_args"),
                      (OLD_CALL, "main loop call")):
        if old not in src:
            print(f"ERROR: expected {name} block not found; runner differs "
                  f"from the audited version — not patching")
            return 1
    if OLD_IMPORT not in src:
        print("ERROR: import block not found")
        return 1
    path.with_suffix(".py.bak").write_text(src, encoding="utf-8")
    src = src.replace(OLD_SIG, NEW_SIG, 1)
    src = src.replace(OLD_ARG, NEW_ARG, 1)
    src = src.replace(OLD_CALL, NEW_CALL, 1)
    path.write_text(src, encoding="utf-8")
    print(f"patched: {path}  (backup: {path.with_suffix('.py.bak')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
