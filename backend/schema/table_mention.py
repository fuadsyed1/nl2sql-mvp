"""
schema/table_mention.py

Single source of truth for "which schema tables did the QUESTION explicitly
name?" — used by the schema-linker lock, the graph-forcing step, and the
direct-SQL enforcement gate.

The problem this fixes: an ordinary business noun that merely happens to match a
table name ("... for the same customer", "assigned to a department") must NOT be
treated as an explicit request to use that physical table. Previously any name
>= 8 characters locked on a bare mention, so `customer` / `employee` /
`department` locked constantly and the enforcement layer then REJECTED correct
SQL for "omitting" a table the user never actually asked for.

Rule (generic, nothing hardcoded):
  * A "schema-like" name — multi-token, digit-bearing, underscore/hyphenated, or
    a very long single token (>= 13 chars, e.g. `salesorderheader`) — is a
    deliberate, distinctive reference and locks on a contiguous, separator-
    INSENSITIVE phrase match, exactly as before.
  * A plain single-word name (`customer`, `employee`, `department`, `vendor`,
    `product`) locks ONLY when the question gives an explicit TABLE CUE:
        - "<name> table"                     ("the customer table")
        - "table [named/called] <name>"      ("table named customer")
        - "from|join|into|update <name>"     ("from customer")
        - "using <name>"                     ("using customer")
        - qualified "<name>.<column>"        ("customer.customerid")
    so a bare noun can never force its table.
"""

import re

__all__ = ["explicit_table_mentions"]

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")

# A single-token name this long is almost never an ordinary English word, so a
# verbatim mention of it is a deliberate table reference even without a cue.
_LONG_SINGLE_TOKEN = 13


def _name_tokens(s):
    return [t for t in _WORD_SPLIT.split(str(s or "").lower()) if t]


def _schema_like(real, toks):
    """True when a name is distinctive enough that a bare mention is a
    deliberate reference (multi-token / digit / separator / very long token)."""
    return (len(toks) >= 2
            or any(ch.isdigit() for ch in real)
            or "_" in real or "-" in real
            or (len(toks) == 1 and len(toks[0]) >= _LONG_SINGLE_TOKEN))


def _has_table_cue(token, qraw):
    """True when the raw (lower) question refers to `token` as a physical table
    via an explicit cue rather than as an ordinary noun."""
    n = re.escape(token)
    patterns = (
        rf"(?<![a-z0-9]){n}\s+tables?\b",                        # "customer table"
        rf"\btables?\s+(?:named\s+|called\s+)?{n}(?![a-z0-9])",  # "table [named] customer"
        rf"\b(?:from|join|into|update)\s+(?:the\s+)?{n}(?![a-z0-9])",  # "from customer"
        rf"\busing\s+(?:the\s+)?{n}(?![a-z0-9])",                # "using customer"
        rf"(?<![a-z0-9]){n}\s*\.\s*[a-z0-9_*]",                  # "customer.customerid"
    )
    return any(re.search(p, qraw) for p in patterns)


def explicit_table_mentions(question, names):
    """Return the subset of `names` (original casing preserved) the question
    explicitly references. Never raises."""
    try:
        qn = " " + " ".join(_name_tokens(question)) + " "
        qraw = " " + str(question or "").lower() + " "
        found = set()
        for t in names or []:
            real = str(t)
            toks = _name_tokens(real)
            if not toks:
                continue
            pat = (r"(?<![a-z0-9])" + r"\s+".join(re.escape(tk) for tk in toks)
                   + r"(?![a-z0-9])")
            if not re.search(pat, qn):
                continue
            if _schema_like(real, toks) or _has_table_cue(toks[0], qraw):
                found.add(real)
        return found
    except Exception:
        return set()
