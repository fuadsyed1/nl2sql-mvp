"""
test_table_retriever.py — offline tests for query-time table retrieval.

Runnable as a plain script (no server, no DB): we inject docs directly into the
retriever's index cache so retrieve_tables() needs no database.

    python -m tests.test_table_retriever
"""

from retrieval import table_retriever as tr


def test_date_tokens():
    assert "20210110" in tr._date_tokens("Show me the January 10 2021 events table")
    assert "20210110" in tr._date_tokens("Jan 10 2021")
    assert "20210110" in tr._date_tokens("January 10, 2021")
    assert "20210110" in tr._date_tokens("2021-01-10")
    assert "20210110" in tr._date_tokens("01/10/2021")
    assert "20210110" in tr._date_tokens("10 January 2021")
    # no date phrase -> no tokens
    assert tr._date_tokens("show all events") == set()
    print("[1] date normalization -> 20210110 -> OK")


def _events_docs(db_id):
    names = [f"events_202101{str(d).zfill(2)}" for d in range(1, 15)] + ["users"]
    tr._INDEX_CACHE[db_id] = [(n, n, []) for n in names]


def test_fuzzy_date_ranking():
    _events_docs(901)
    res = tr.retrieve_tables(901, "Show me the January 10 2021 events table", k=5)
    assert res[0]["table_name"] == "events_20210110", res[0]
    assert "date_match" in res[0]["reason"]
    print("[2] 'January 10 2021' -> events_20210110 ranked #1 -> OK")


def test_exact_name_still_works():
    _events_docs(902)
    res = tr.retrieve_tables(902, "Show all rows from events_20210110", k=5)
    assert res[0]["table_name"] == "events_20210110", res[0]
    print("[3] exact table name still ranks #1 -> OK")


def test_date_guard():
    _events_docs(903)  # events_20210101..14 + users

    # 1) requested date exists -> satisfied (fallback allowed)
    res = tr.retrieve_tables(903, "Show event names from January 10 2021 events", k=8)
    toks, ok = tr.requested_dates_satisfied(
        "Show event names from January 10 2021 events", res
    )
    assert toks == ["20210110"] and ok is True

    # 2) requested date missing -> NOT satisfied (guard should trigger)
    res2 = tr.retrieve_tables(903, "Show event names from February 10 2021 events", k=8)
    toks2, ok2 = tr.requested_dates_satisfied(
        "Show event names from February 10 2021 events", res2
    )
    assert toks2 == ["20210210"] and ok2 is False

    # 3) no date in question -> guard not triggered (satisfied)
    toks3, ok3 = tr.requested_dates_satisfied("Show event names from events", res)
    assert toks3 == [] and ok3 is True

    # 4) exact table name (no parsed date phrase) -> guard not triggered
    toks4, ok4 = tr.requested_dates_satisfied("Show all rows from events_20210110", res)
    assert toks4 == [] and ok4 is True

    # December case still satisfied
    _events_docs(904)
    tr._INDEX_CACHE[904] = tr._INDEX_CACHE[904] + [("events_20201225", "events_20201225", [])]
    res5 = tr.retrieve_tables(904, "Show event names from December 25 2020 events", k=8)
    _, ok5 = tr.requested_dates_satisfied(
        "Show event names from December 25 2020 events", res5
    )
    assert ok5 is True
    print("[4] date guard: exists->ok, missing->fail, no-date->ok, exact->ok -> OK")


if __name__ == "__main__":
    test_date_tokens()
    test_fuzzy_date_ranking()
    test_exact_name_still_works()
    test_date_guard()
    print("\nRESULT: 4/4 passed — table_retriever.py verified")
