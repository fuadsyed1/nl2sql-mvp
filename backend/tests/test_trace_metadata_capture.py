"""Task 7 regression: optional X-SpiderSQL-* headers are captured into the trace
metadata, accepting both the canonical and the -Test- header spellings, and
absent headers yield empty metadata (rendered as "(not provided)")."""
import os
import importlib
from diagnostics import full_trace


def test_meta_from_headers_canonical_spelling():
    m = full_trace.request_meta_from_headers({
        "X-SpiderSQL-Test-ID": "12",
        "X-SpiderSQL-Category": "aggregation",
        "X-SpiderSQL-Difficulty": "easy",
        "X-SpiderSQL-Trace-Run": "run01",
        "Authorization": "secret-should-be-ignored",
    })
    assert m == {"test_id": "12", "category": "aggregation",
                 "difficulty": "easy", "trace_run": "run01"}


def test_meta_from_headers_test_prefixed_spelling():
    m = full_trace.request_meta_from_headers({
        "x-spidersql-test-id": "7",
        "x-spidersql-test-category": "join",
        "x-spidersql-test-difficulty": "hard",
    })
    assert m == {"test_id": "7", "category": "join", "difficulty": "hard"}


def test_meta_from_headers_absent_and_empty():
    assert full_trace.request_meta_from_headers({}) == {}
    assert full_trace.request_meta_from_headers(None) == {}
    # empty values are dropped
    assert full_trace.request_meta_from_headers({"x-spidersql-test-id": ""}) == {}


def test_meta_flows_into_trace_record_when_enabled(monkeypatch):
    monkeypatch.setenv("SPIDERSQL_FULL_TRACE", "1")
    importlib.reload(full_trace)
    full_trace.set_request_meta(
        full_trace.request_meta_from_headers({"X-SpiderSQL-Test-ID": "99",
                                              "X-SpiderSQL-Category": "agg"}))
    full_trace.begin(54, "how many?")
    rec = full_trace._RECORD_VAR.get()
    assert rec is not None
    assert rec["meta"].get("test_id") == "99"
    assert rec["meta"].get("category") == "agg"
    # cleanup: disable so no trace files are emitted by later code
    monkeypatch.delenv("SPIDERSQL_FULL_TRACE", raising=False)
    importlib.reload(full_trace)


def test_meta_defaults_when_no_headers(monkeypatch):
    monkeypatch.setenv("SPIDERSQL_FULL_TRACE", "1")
    importlib.reload(full_trace)
    full_trace.set_request_meta(full_trace.request_meta_from_headers({}))
    full_trace.begin(54, "how many?")
    rec = full_trace._RECORD_VAR.get()
    assert rec["meta"] == {}   # renders as "(not provided)" downstream
    monkeypatch.delenv("SPIDERSQL_FULL_TRACE", raising=False)
    importlib.reload(full_trace)
