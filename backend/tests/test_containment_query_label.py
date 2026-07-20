"""Task 8 regression: containment display label must not double-offset the
already-1-based query_id (was rendering Q(n+1))."""
import spidersql_containment_500_four_databases as C


def test_query_label_is_one_based_ids_1_to_5():
    assert [C.query_label(i) for i in range(1, 6)] == ["Q1", "Q2", "Q3", "Q4", "Q5"]


def test_query_label_fallback_when_id_missing():
    assert C.query_label(None, 3) == "Q3"
    assert C.query_label(None) == "Q?"


def test_query_label_non_numeric_passthrough():
    assert C.query_label("Qx") == "Qx"
