"""
day1_common.py — shared, side-effect-free parsers for the Day 1 go-live audit.

Everything here PARSES existing benchmark artifacts. Nothing hardcodes a
benchmark result, an expected SQL, a per-question answer, or a per-test verdict.
The only constants are structural tokens of the artifact file formats and the
generic root-cause / failure-pattern vocabulary derived from the trace text.
"""
import os, re, json, hashlib, datetime

# --------------------------------------------------------------------------
# generic helpers
# --------------------------------------------------------------------------
def file_meta(path):
    """(exists, sha1, size_bytes, mtime_iso) for provenance recording."""
    if not path or not os.path.exists(path):
        return {"exists": False, "sha1": None, "size_bytes": None, "mtime": None}
    data = open(path, "rb").read()
    return {
        "exists": True,
        "sha1": hashlib.sha1(data).hexdigest(),
        "size_bytes": len(data),
        "mtime": datetime.datetime.fromtimestamp(
            os.path.getmtime(path)).isoformat(timespec="seconds"),
    }


def _balanced(text, start):
    """Return the balanced {..}/[..] substring beginning at index `start`."""
    open_ch = text[start]
    close_ch = {"{": "}", "[": "]"}[open_ch]
    depth, i, in_str, esc = 0, start, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def _json_after(text, marker):
    m = re.search(re.escape(marker), text)
    if not m:
        return None
    i = m.end()
    while i < len(text) and text[i] not in "{[":
        i += 1
    if i >= len(text):
        return None
    blob = _balanced(text, i)
    if blob is None:
        return None
    try:
        return json.loads(blob)
    except Exception:
        return None


# --------------------------------------------------------------------------
# 1. normal SQL result files  (execution STATUS only, NOT semantic verdict)
# --------------------------------------------------------------------------
def parse_result_file(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    chunks = re.split(r"(?m)^=+\s*$", text)
    out = []
    for ch in chunks:
        mt = re.search(r"(?m)^TEST\s+(\d+)\s*$", ch)
        if not mt:
            continue
        cat = re.search(r"(?m)^CATEGORY:\s*(.*)$", ch)
        dif = re.search(r"(?m)^DIFFICULTY:\s*(.*)$", ch)
        st = re.search(r"(?m)^STATUS:\s*(\w+)", ch)
        q = re.search(r"(?ms)^QUERY:\s*\n(.*?)\n\s*SQL:", ch)
        sql = re.search(r"(?ms)^SQL:\s*\n(.*)$", ch)
        out.append({
            "test_id": int(mt.group(1)),
            "category": (cat.group(1).strip() if cat else None),
            "difficulty": (dif.group(1).strip() if dif else None),
            "status": (st.group(1).strip() if st else None),
            "question": (q.group(1).strip() if q else None),
            "sql": (sql.group(1).strip() if sql else None),
        })
    return out


# --------------------------------------------------------------------------
# 2. full-trace files  (per-request pipeline record)
# --------------------------------------------------------------------------
# Ordered leading-phrase -> generic root_cause_layer. Each fatal reason begins
# with its violation category (e.g. "grain violation:", "required concept ...");
# classify by that leading phrase, never by an anywhere-substring, so tokens that
# merely appear inside another reason (e.g. "comparison" inside a grain message)
# do not misclassify. Vocabulary is generic, not per-test.
_FATAL_LAYER = [
    ("grain violation", "grain_contract"),
    ("fanout violation", "grain_contract"),
    ("required concept", "required_concept"),
    ("missing required concept", "required_concept"),
    ("missing table", "schema_binding"),
    ("missing column", "schema_binding"),
    ("unknown column", "schema_binding"),
    ("illegal join", "relationship"),
    ("relationship violation", "relationship"),
    ("comparison predicate", "comparison_semantics"),
    ("set operation", "set_semantics"),
    ("literal", "literal_semantics"),
]


def _reason_layer(reason):
    r = (reason or "").strip().lower()
    for tok, lay in _FATAL_LAYER:
        if r.startswith(tok):
            return lay
    return None


def classify_fatal_layer(reasons):
    """Map a list of fatal-reason strings to a generic root_cause_layer by the
    LEADING phrase of each reason. Returns (layer, needs_review_bool).
    A single dominant layer -> that layer; genuinely mixed distinct layers or
    unrecognized text -> needs_manual_review. No per-test special casing."""
    if not reasons:
        return "unknown", True
    layers = [l for l in (_reason_layer(x) for x in reasons) if l]
    hits = set(layers)
    if len(hits) == 1:
        return next(iter(hits)), False
    if len(hits) > 1:
        # report the dominant layer but flag for manual review
        from collections import Counter
        dom = Counter(layers).most_common(1)[0][0]
        return "mixed:" + dom, True
    return "other", True


def _candidate_blocks(body):
    idxs = [m.start() for m in re.finditer(r"(?m)^CANDIDATE\s+\d+\s*$", body)]
    end = re.search(r"(?m)^LAYER 9", body)
    stop = end.start() if end else len(body)
    blocks = []
    for k, s in enumerate(idxs):
        e = idxs[k + 1] if k + 1 < len(idxs) else stop
        blocks.append(body[s:e])
    return blocks


def parse_candidate(block):
    def g(pat, cast=str, default=None, flags=0, last=False):
        ms = list(re.finditer(pat, block, flags))
        if not ms:
            return default
        m = ms[-1] if last else ms[0]
        try:
            return cast(m.group(1))
        except Exception:
            return default
    num = g(r"(?m)^CANDIDATE\s+(\d+)", int)
    src = g(r"(?m)^generation_source:\s*(\S+)")
    exec_ok = g(r'"execution_success":\s*(true|false)',
                lambda v: v == "true")
    exec_err = g(r'"execution_error":\s*(null|"[^"]*")',
                 lambda v: None if v == "null" else v.strip('"'))
    rows = g(r'"row_count":\s*(\d+)', int)
    fatal = g(r'"fatal_count":\s*(\d+)', int, last=True)
    score = g(r'"total_recorded_score":\s*([\d.]+)', float)
    sqlm = re.search(r"(?ms)^extracted_sql:\s*\n(.*?)\n\s*--", block)
    sql = sqlm.group(1).strip() if sqlm else None
    return {"number": num, "source": src, "execution_success": exec_ok,
            "execution_error": exec_err, "row_count": rows,
            "fatal_count": fatal, "score": score, "sql": sql}


def parse_trace_file(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    starts = [m.start() for m in re.finditer(r"(?m)^TEST ID:", text)]
    records = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(text)
        rec = text[s:e]
        def one(pat, cast=str, default=None, flags=re.M):
            m = re.search(pat, rec, flags)
            if not m:
                return default
            try:
                return cast(m.group(1))
            except Exception:
                return default
        ffr = _json_after(rec, "final_fatal_reasons:") or []
        rej = _json_after(rec, "rejected_candidate_reasons:") or {}
        body = rec
        records.append({
            "index": k + 1,
            "database_id": one(r"^DATABASE ID:\s*(\d+)", int),
            "question": one(r"^QUESTION:\s*(.*)$"),
            "selected_number": one(r"^selected_candidate_number:\s*(\S+)"),
            "selected_label": one(r"^selected_candidate_label:\s*(\S+)"),
            "exact_selection_reason": one(r"^exact_selection_reason:\s*(.*)$"),
            "selected_sql": (lambda m: m.group(1).strip() if m else None)(re.search(r"(?ms)^selected_sql:\s*\n(.*?)\n\s*exact_selection_reason:", rec)),

            "controlled_failure": one(
                r"^controlled_failure:\s*(True|False)", lambda v: v == "True"),
            "endpoint_success": one(
                r"^endpoint_success:\s*(True|False)", lambda v: v == "True"),
            "endpoint_error": one(r"^endpoint_error:\s*(.*)$",
                                  lambda v: None if v.strip() == "None" else v.strip()),
            "no_sql_stage": one(r"^no_sql_stage:\s*(.*)$"),
            "repair_meta": _json_after(rec, "repair_meta:") or {},
            "final_fatal_reasons": ffr,
            "rejected_candidate_reasons": rej,
            "candidates": [parse_candidate(b) for b in _candidate_blocks(body)],
        })
    return records


# --------------------------------------------------------------------------
# 3. containment results file  (designed edges vs actual pairwise)
# --------------------------------------------------------------------------
_CASE_RE = re.compile(
    r"(?m)^CASE\s+(\d+)\s*\|\s*(DB\d+)\s+(\S+)\s*\|\s*(\S+)\s*\|\s*(.*)$")
# designed containment edge: "Qa is logically contained in Qb."
_DESIGNED_RE = re.compile(
    r"-\s*Q(\d+)\s+is logically contained in\s+Q(\d+)\.")

# a designed "a contained in b" edge counts as recovered when the actual
# pairwise relationship is containment in the same direction OR the queries are
# equivalent on the current database (explicitly acceptable per the design note).
_RECOVER_SAMEDIR = {"query_a_contained_in_query_b", "equivalent_on_current_database"}
_RECOVER_REVDIR = {"query_b_contained_in_query_a", "equivalent_on_current_database"}


def parse_containment_file(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    heads = list(_CASE_RE.finditer(text))
    cases = []
    for k, h in enumerate(heads):
        s = h.start()
        e = heads[k + 1].start() if k + 1 < len(heads) else len(text)
        seg = text[s:e]
        raw = _json_after(seg, "RAW RESPONSE JSON") or {}
        pair_index = {}
        for pr in raw.get("pairwise_relationships", []) or []:
            a, b = pr.get("query_a"), pr.get("query_b")
            pair_index[(a, b)] = pr.get("relationship")
        qmeta = {qr.get("query_id"): qr
                 for qr in raw.get("query_results", []) or []}
        designed = [(int(a), int(b)) for a, b in _DESIGNED_RE.findall(seg)]
        endpoint_ok = re.search(r"(?m)^ENDPOINT SUCCESS:\s*(True|False)", seg)
        cases.append({
            "case_id": int(h.group(1)),
            "db_label": h.group(2),
            "database_id": int(h.group(2)[2:]),
            "db_name": h.group(3),
            "difficulty": h.group(4),
            "description": h.group(5).strip(),
            "endpoint_success": (endpoint_ok.group(1) == "True") if endpoint_ok else None,
            "designed_edges": designed,
            "pairwise": pair_index,
            "query_meta": qmeta,
        })
    return cases


def evaluate_designed_edge(case, a, b):
    """Return (recovered_bool, failure_cause_or_None, actual_relationship)."""
    pw = case["pairwise"]
    if (a, b) in pw:
        rel = pw[(a, b)]
        recovered = rel in _RECOVER_SAMEDIR
    elif (b, a) in pw:
        rel = pw[(b, a)]
        recovered = rel in _RECOVER_REVDIR
    else:
        return False, "missing_pairwise_entry", None
    if recovered:
        return True, None, rel
    # classify the failure cause from the actual relationship / query health
    qa = case["query_meta"].get(a, {})
    qb = case["query_meta"].get(b, {})
    if rel == "unknown":
        bad = [q for q in (qa, qb)
               if not q.get("success", True) or not q.get("safe", True)
               or q.get("empty_result")]
        cause = "endpoint_or_query_failure" if bad else "unknown_relationship"
    elif rel in ("query_a_contained_in_query_b", "query_b_contained_in_query_a"):
        cause = "reversed_containment"
    elif rel == "incomparable_on_current_database":
        cause = "incomparable"
    else:
        cause = "unexpected_relationship"
    return False, cause, rel


# --------------------------------------------------------------------------
# 4. config + path resolution
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
CONFIG_PATH = os.path.join(HERE, "go_live_targets.json")


def load_config():
    return json.load(open(CONFIG_PATH, encoding="utf-8"))


def rp(rel):
    """Resolve a config path (relative to backend root) to an absolute path."""
    return os.path.normpath(os.path.join(BACKEND_ROOT, rel))


def out(name):
    return os.path.join(HERE, name)


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# 5. semantic audit files (CSV or Markdown) -> per-test CORRECT/INCORRECT
# --------------------------------------------------------------------------
import csv as _csv

_MD_ENTRY_RE = re.compile(
    r"(?ms)^###\s+Test\s+(\d+)\s+—\s*([^/\n]+?)\s*/\s*([^\n]+?)\s*$"
    r".*?\*\*Query:\*\*\s*(.*?)\s*\n"
    r".*?\*\*Finding:\*\*\s*(.*?)\s*\n"
    r".*?\*\*Generated SQL:\*\*\s*`(.*?)`")


def parse_semantic_audit(path, fmt=None):
    """Parse a per-DB semantic audit in CSV or Markdown form. Returns a dict:
      format, complete (True iff every test row is present), rows (list),
      incorrect_ids (set of INCORRECT test ids), header_totals (dict|None).
    CSV rows carry all 500 tests with an explicit verdict. Markdown lists only
    the INCORRECT tests (the audit convention), so complete=False and the caller
    fills CORRECT for the rest from the result file."""
    if fmt is None:
        fmt = "markdown" if path.lower().endswith((".md", ".markdown")) else "csv"
    if fmt == "csv":
        rows = []
        with open(path, newline="", encoding="utf-8") as fh:
            for r in _csv.DictReader(fh):
                rows.append({
                    "test_id": int(r["test_id"]),
                    "category": (r.get("category") or "").strip(),
                    "difficulty": (r.get("difficulty") or "").strip(),
                    "execution_status": (r.get("execution_status") or "").strip().upper(),
                    "semantic_verdict": (r.get("semantic_audit") or "").strip().upper(),
                    "query": (r.get("query") or "").strip(),
                    "sql": (r.get("sql") or "").strip(),
                    "audit_note": (r.get("audit_note") or "").strip(),
                })
        inc = {r["test_id"] for r in rows if r["semantic_verdict"] == "INCORRECT"}
        return {"format": "csv", "complete": True, "rows": rows,
                "incorrect_ids": inc, "header_totals": None}

    # markdown
    text = open(path, encoding="utf-8", errors="replace").read()
    rows = []
    for m in _MD_ENTRY_RE.finditer(text):
        rows.append({
            "test_id": int(m.group(1)),
            "category": m.group(2).strip(),
            "difficulty": m.group(3).strip(),
            "execution_status": None,
            "semantic_verdict": "INCORRECT",
            "query": m.group(4).strip(),
            "sql": m.group(6).strip(),
            "audit_note": m.group(5).strip(),
        })
    inc = {r["test_id"] for r in rows}

    def _num(pat):
        mm = re.search(pat, text)
        return int(mm.group(1)) if mm else None
    header = {
        "correct": _num(r"correct SQL:\s*\*\*(\d+)/"),
        "incorrect": _num(r"incorrect or incomplete SQL:\s*\*\*(\d+)/"),
        "exec_pass": _num(r"Execution PASS:\s*\*\*(\d+)/"),
        "exec_fail": _num(r"Execution FAIL[^:]*:\s*\*\*(\d+)/"),
    }
    return {"format": "markdown", "complete": False, "rows": rows,
            "incorrect_ids": inc, "header_totals": header}


def build_verdict_map(audit, result_recs):
    """Return {test_id: verdict_row} covering EVERY test. For a complete (CSV)
    audit the rows are used directly. For an incomplete (Markdown) audit the base
    is taken from the result file (all tests) and INCORRECT verdicts + findings
    are overlaid for the listed ids; all others are CORRECT."""
    if audit["complete"]:
        return {r["test_id"]: r for r in audit["rows"]}
    inc_by_id = {r["test_id"]: r for r in audit["rows"]}
    out = {}
    for rr in result_recs:
        tid = rr["test_id"]
        if tid in inc_by_id:
            row = dict(inc_by_id[tid])
            row["execution_status"] = rr.get("status")
            # prefer result-file category/difficulty/query when present
            row.setdefault("category", rr.get("category"))
            row.setdefault("difficulty", rr.get("difficulty"))
            if not row.get("query"):
                row["query"] = rr.get("question")
            out[tid] = row
        else:
            out[tid] = {
                "test_id": tid, "category": rr.get("category"),
                "difficulty": rr.get("difficulty"),
                "execution_status": rr.get("status"),
                "semantic_verdict": "CORRECT", "query": rr.get("question"),
                "sql": rr.get("sql"), "audit_note": "",
            }
    return out


# generic semantic-failure pattern from an audit finding (best effort; anything
# unmatched is flagged needs_manual_review, never force-labelled)
_SEM_PATTERNS = [
    ("grain_mismatch", ("grain", "per distinct", "distinct order", "line-item",
                        "line item", "order grain", "duplicat", "inflat", "fanout")),
    ("missing_metric_or_output", ("never calculat", "never divid", "does not subtract",
                                  "does not compute", "omits", "returns only",
                                  "is missing", "never computes", "not calculate")),
    ("wrong_filter_or_placement", ("unrequested", "adds an", "extra ", "restriction",
                                   "having", "never requires", "before averaging",
                                   "filter")),
    ("wrong_entity_or_role", ("instead of the", "default warehouse", "wrong relationship",
                              "role", "snapshot", "wrong entity", "ids instead",
                              "id instead", "name", "state instead")),
    ("aggregation_or_formula_error", ("mixes", "wrong", "incorrect", "formula",
                                      "averages", "sums", "treats", "divides by",
                                      "denominator", "profit", "cast")),
    ("set_logic_error", ("intersection", "except", "not exists", "excludes",
                         "set ", "both ", "never handled", "no additional")),
]


def classify_semantic_failure(finding):
    f = (finding or "").lower()
    if not f:
        return "needs_manual_review", True
    for name, toks in _SEM_PATTERNS:
        if any(t in f for t in toks):
            return name, False
    return "needs_manual_review", True


# detailed containment failure cause from actual relationship + explanation text
def classify_containment_cause(actual, explanation):
    """Return (cause, subtype). Definite relationships (reverse / incomparable)
    are wrong-relationship failures; 'cannot compare' (unknown) failures are
    classified by the normalization/key/base-entity reason in the explanation."""
    a = (actual or "").strip()
    e = (explanation or "").lower()
    if a == "query_b_contained_in_query_a":
        return "definite_wrong_relationship", "reverse_containment"
    if a == "incomparable_on_current_database":
        return "definite_wrong_relationship", "incomparable_rows_missing"
    if "no sql text was generated" in e:
        return "sql_generation_failure", None
    if "no single recoverable base table" in e:
        return "base_entity_recovery", None
    if "no canonical key" in e:
        return "canonical_key_failure", None
    if ("select distinct grouped query is not normalized" in e
            or "group by expression is not a simple column" in e):
        return "distinct_groupby_normalization", None
    if "cannot be key-normalized" in e:
        return "aggregate_normalization", None
    if "different group keys" in e:
        return "group_key_mismatch", None
    if "uses limit" in e:
        return "limit_orderby_normalization", None
    return "needs_manual_review", None


# --------------------------------------------------------------------------
# 6. robust selected-candidate matching
# --------------------------------------------------------------------------
def normalize_sql(s):
    return re.sub(r"\s+", " ", (s or "").strip().rstrip(";")).lower()


def normalize_source(src):
    """Canonical generator source: drop a trailing numeric disambiguator so the
    LAYER-9 label 'llm_variant_1'/'llm_variant_2' aligns with a candidate whose
    parsed source is 'llm_variant'. Non-numeric suffixes (e.g.
    'llm_sql_direct_variant') are preserved."""
    return re.sub(r"_\d+$", "", (src or "").strip().lower())


def match_selected_candidate(rec):
    """Identify the selected candidate of a trace record using several trace
    fields, not candidate number or exact source-string alone. Returns
    (candidate_or_None, method). Priority: selected_candidate_number (authoritative
    ordinal) -> selected_sql text -> exact source label -> normalized source
    label. Each fallback requires a UNIQUE match to avoid mislabelling."""
    cands = rec.get("candidates") or []
    if not cands:
        return None, "no_candidates"
    num = rec.get("selected_number")
    lbl = rec.get("selected_label")
    ssql = rec.get("selected_sql")

    # 1. authoritative ordinal
    if num is not None:
        for c in cands:
            if str(c.get("number")) == str(num):
                return c, "selected_number"
    # 2. exact selected SQL text (unique)
    if ssql:
        m = [c for c in cands if c.get("sql") and
             normalize_sql(c["sql"]) == normalize_sql(ssql)]
        if len(m) == 1:
            return m[0], "selected_sql"
    # 3. exact source label (unique)
    if lbl:
        m = [c for c in cands if c.get("source") == lbl]
        if len(m) == 1:
            return m[0], "exact_source"
    # 4. normalized source label (unique)
    if lbl:
        nl = normalize_source(lbl)
        m = [c for c in cands if normalize_source(c.get("source")) == nl]
        if len(m) == 1:
            return m[0], "normalized_source"
        # 4b. disambiguate normalized-source ties by selected SQL
        if len(m) > 1 and ssql:
            m2 = [c for c in m if c.get("sql") and
                  normalize_sql(c["sql"]) == normalize_sql(ssql)]
            if len(m2) == 1:
                return m2[0], "normalized_source+sql"
    return None, "unresolved"
