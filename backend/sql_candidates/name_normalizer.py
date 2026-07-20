"""
sql_candidates/name_normalizer.py

Normalize hallucinated SQL-Server-style schema-qualified table names
(`Purchasing.PurchaseOrderHeader`) down to the FLAT name the imported SQLite
database actually uses (`PurchaseOrderHeader`) — but ONLY when the physical
schema confirms the mapping (the flat table exists and the 2-part name does
not). This lets an otherwise-correct candidate execute instead of failing and
losing to an executable-but-meaningless one.

Conservative on purpose:
  * The 2-part rewrite fires ONLY in FROM/JOIN position, where a TABLE name is
    expected — so a qualified COLUMN reference `alias.column` is never touched,
    even if some column happens to share a table's name.
  * A `<prefix>.<Table>` is rewritten only when `<Table>` is a real physical
    table and `<prefix>` is NOT itself a real table (i.e. a schema namespace,
    not a table alias).
Never raises.
"""

import re

__all__ = ["normalize_schema_prefixes"]


def normalize_schema_prefixes(sql, physical_table_names):
    """Return sql with confirmed `schema.Table` -> `Table` rewrites applied
    in FROM/JOIN position (plus safe 3-part `schema.table.col` -> `table.col`)."""
    if not sql or not physical_table_names:
        return sql
    try:
        real = {str(t).lower() for t in physical_table_names}

        def _is_table(tok):
            return tok.lower() in real

        # 3-part `schema.table.column` -> `table.column` (mid is a real table,
        # prefix is not): a SQL-Server 3-part reference flattened to 2-part.
        def _sub3(m):
            pre, mid, col = m.group(1), m.group(2), m.group(3)
            if _is_table(mid) and not _is_table(pre):
                return f"{mid}.{col}"
            return m.group(0)

        sql = re.sub(r'\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b',
                     _sub3, sql)

        # 2-part `FROM|JOIN schema.table` -> `FROM|JOIN table`.
        def _sub2(m):
            kw, pre, tbl = m.group(1), m.group(2), m.group(3)
            if _is_table(tbl) and not _is_table(pre):
                return f"{kw} {tbl}"
            return m.group(0)

        sql = re.sub(r'\b(FROM|JOIN)\s+([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b',
                     _sub2, sql, flags=re.IGNORECASE)
        return sql
    except Exception:
        return sql
