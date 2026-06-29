"""
test_partition_filter.py — offline tests for redundant partition-date filter
removal (large-mode helper). No server, no DB, no LLM.

    python -m tests.test_partition_filter
"""

from schema.partition_filter import (
    remove_redundant_partition_date_filters as rm,
    detect_partitioned_ambiguity as amb,
)


def _ir(value, col="event_date", op="=", tbl="events_20210110",
        table="events_20210110"):
    return {
        "tables": [table],
        "filters": [
            {"table": tbl, "column": col, "op": op, "value": value,
             "connector": "AND"}
        ],
    }


def test_same_date_removed():
    for v in ("2021-01-10", "20210110", "01/10/2021", "January 10 2021"):
        ir = _ir(v)
        diag = rm(ir)
        assert ir["filters"] == [], (v, ir["filters"])
        assert diag["removed_redundant_partition_date_filter"] is True
        assert diag["partition_date"] == "20210110"
    print("[1] same-date filter removed (dashed/compact/slash/words) -> OK")


def test_different_date_kept():
    ir = _ir("2021-01-11")
    diag = rm(ir)
    assert len(ir["filters"]) == 1 and diag == {}
    print("[2] different-date filter kept -> OK")


def test_range_and_nondate_kept():
    ir1 = _ir("2021-01-10", op=">=")  # range operator, not equality
    rm(ir1)
    assert len(ir1["filters"]) == 1
    ir2 = _ir("2021-01-10", col="user_id")  # not a date-like column
    rm(ir2)
    assert len(ir2["filters"]) == 1
    print("[3] range op + non-date column kept -> OK")


def test_nonpartition_table_kept():
    ir = _ir("2021-01-10", tbl="users", table="users")
    rm(ir)
    assert len(ir["filters"]) == 1
    print("[4] non-partition table kept -> OK")


def test_partition_ambiguity():
    ev = [f"events_2020110{d}" for d in range(1, 9)]  # 8 same-prefix partitions

    # 1) generic "events" with many candidates, no date -> ambiguous
    d = amb("Show event names from events", ev)
    assert d.get("error") == "ambiguous_partitioned_table_query"
    assert d.get("matched_prefix") == "events"
    assert len(d.get("candidate_tables", [])) == 8 and d.get("example_table")

    # 2) exact partition table named -> not ambiguous
    assert amb("Show all rows from events_20201101", ev) == {}

    # 3) date phrase present -> not ambiguous (date guard handles dates)
    assert amb("Show events from January 10 2021", ev) == {}

    # 4) single / non-partition / mixed-prefix -> not ambiguous
    assert amb("Show events", ["events_20201101"]) == {}
    assert amb("users orders", ["users", "orders"]) == {}
    assert amb("join", ["events_20201101", "sales_20201101"]) == {}
    print("[5] ambiguous partitioned-table query detection -> OK")


if __name__ == "__main__":
    test_same_date_removed()
    test_different_date_kept()
    test_range_and_nondate_kept()
    test_nonpartition_table_kept()
    test_partition_ambiguity()
    print("\nRESULT: 5/5 passed — partition_filter.py verified")
