"""
tests/test_table_mention_parentchild.py

Parent/child table-mention disambiguation (RC-B):
  * a question about a "sales order" must NOT flag the child sales_order_items
    (matched only via shared tokens), but MUST keep sales_orders;
  * the child is kept when its distinctive token ("items") is present;
  * single-word recall is preserved ("orders" -> sales_orders);
  * the scorer's strict matcher (explicit_table_mentions) does not flag a table
    without an explicit cue, but does with one.
"""
from query_families.slot_extractor import index_schema, mentioned_tables
from schema.table_mention import explicit_table_mentions


def _idx():
    def t(name, cols):
        return {"table_name": name,
                "columns": [{"column_name": c, "data_type": "INTEGER"} for c in cols]}
    graph = {"tables": [
        t("sales_orders", ["order_id", "sales_rep_id", "customer_id"]),
        t("sales_order_items", ["order_item_id", "order_id", "product_id"]),
        t("customers", ["customer_id", "city"]),
        t("employees", ["employee_id"]),
    ]}
    return index_schema(graph)


def test_parent_only_when_child_tokens_absent():
    idx = _idx()
    got = mentioned_tables("Show each sales order number with its customer.", idx)
    assert "sales_orders" in got
    assert "sales_order_items" not in got


def test_child_kept_when_distinctive_token_present():
    idx = _idx()
    got = mentioned_tables("List the sales order items for each order.", idx)
    assert "sales_order_items" in got


def test_single_word_recall_preserved():
    idx = _idx()
    got = mentioned_tables("How many orders were placed?", idx)
    assert "sales_orders" in got


def test_strict_matcher_needs_cue():
    names = ["sales_orders", "sales_order_items", "customers"]
    # bare business phrase, no explicit table cue -> nothing flagged
    assert explicit_table_mentions("Show each sales order number.", names) == set()
    # explicit cue -> flagged
    assert "sales_orders" in explicit_table_mentions(
        "select * from sales_orders", names)
