from typing import Any
from semantic_parser import create_semantic_object


def ir_to_semantic(ir: dict[str, Any], schema_info: dict[str, Any]) -> dict[str, Any]:
    table = schema_info["table"]
    columns = schema_info["columns"]

    semantic = create_semantic_object()
    semantic.update({
        "query_type": "relational_query",
        "domain": "database",
        "intent": "retrieve",
    })

    rel = semantic["relational"]
    rel["entity"] = table

    operation = ir.get("operation")
    answer = ir.get("answer")
    measure = ir.get("measure")
    measure_operation = ir.get("measure_operation")
    group_by = ir.get("group_by")
    order = ir.get("order")
    limit = ir.get("limit")
    filters = ir.get("filters") or []

    rel["select"] = [answer] if answer in columns else ["*"]
    rel["filters"] = filters

    if group_by in columns:
        rel["group_by"] = group_by

    if operation in ["rank", "group_aggregate"]:
        # If answer and measure are the same, this is row-level ranking, not grouped aggregation
        if operation == "rank" and answer == measure and not group_by:
            if answer in columns:
                rel["select"] = [answer]

            if measure in columns and order:
                rel["sort"] = {
                    "field": measure,
                    "direction": "DESC" if order == "desc" else "ASC",
                }

            rel["limit"] = limit or 1
            return semantic

        if answer in columns:
            rel["group_by"] = answer
            rel["select"] = [answer]

        if measure in columns:
            rel["aggregation"] = {
                "function": (measure_operation or "SUM").upper(),
                "field": measure,
            }

        if measure in columns and order:
            rel["sort"] = {
                "field": measure,
                "direction": "DESC" if order == "desc" else "ASC",
            }

        rel["limit"] = limit or 50

    elif operation == "aggregate":
        if measure in columns:
            rel["aggregation"] = {
                "function": (measure_operation or "SUM").upper(),
                "field": measure,
            }
        rel["select"] = ["*"]
        rel["limit"] = limit

    else:
        rel["limit"] = limit or 50

    return semantic