import re


def create_semantic_object():
    return {
        "query_type": None,
        "domain": None,
        "intent": None,
        "relational": {
            "entity": None,
            "select": [],
            "filters": [],
            "sort": None,
            "limit": None,
            "aggregation": None
        },
        "design": {
            "target": None,
            "clauses": {
                "target": [],
                "subject_to": [],
                "prefer": [],
                "avoid": [],
                "using_knowledge": [],
                "validate": [],
                "correct": [],
                "return": []
            }
        }
    }


def detect_operator(text):
    if "greater than or equal" in text or "at least" in text:
        return ">="
    if "less than or equal" in text or "at most" in text:
        return "<="
    if "greater than" in text or "above" in text or "over" in text:
        return ">"
    if "less than" in text or "below" in text or "under" in text:
        return "<"
    if "equal to" in text or "equals" in text:
        return "="
    return None


def extract_number(text):
    match = re.search(r"\d+\.?\d*", text)
    if not match:
        return None

    value = float(match.group())

    return int(value) if value.is_integer() else value


def parse_relational_query(text, semantic):
    semantic["query_type"] = "relational_query"
    semantic["domain"] = "database"
    semantic["intent"] = "retrieve"

    if "student" in text or "students" in text:
        semantic["relational"]["entity"] = "students"

    possible_fields = ["id", "name", "age", "major", "gpa"]

    filter_words = [" with ", " where ", " whose ", " that have ", " having "]

    output_part = text
    filter_part = ""

    for word in filter_words:
        if word in text:
            parts = text.split(word, 1)
            output_part = parts[0]
            filter_part = parts[1]
            break

    requested_fields = []

    selection_words = [
        "show",
        "list",
        "get",
        "display"
    ]

    explicit_column_request = False

    requested_fields = []

    is_sort_query = (
        "sorted by" in text
        or "order by" in text
        or "highest" in text
        or "lowest" in text
        or "top" in text
    )

    if not is_sort_query:
        for field in possible_fields:
            if field in output_part:
                requested_fields.append(field)

    semantic["relational"]["select"] = requested_fields if requested_fields else ["*"]

    semantic["relational"]["select"] = (
    requested_fields if requested_fields else ["*"]
)

    operator = detect_operator(filter_part)
    value = extract_number(filter_part)

    for field in possible_fields:
        if field in filter_part and operator and value is not None:
            condition = {
                "field": field,
                "operator": operator,
                "value": value
            }

            semantic["relational"]["filters"].append(condition)

    if "count" in text or "how many" in text:
        semantic["relational"]["aggregation"] = {
            "function": "COUNT",
            "field": "*"
        }

    if "average" in text or "avg" in text:
        for field in possible_fields:
            if field in text:
                semantic["relational"]["aggregation"] = {
                    "function": "AVG",
                    "field": field
                }

    if "highest" in text or "top" in text or "descending" in text:
        for field in possible_fields:
            if field in text:
                semantic["relational"]["sort"] = {
                    "field": field,
                    "direction": "DESC"
                }

    if "lowest" in text or "ascending" in text:
        for field in possible_fields:
            if field in text:
                semantic["relational"]["sort"] = {
                    "field": field,
                    "direction": "ASC"
                }

    top_match = re.search(r"top\s+(\d+)", text)
    limit_match = re.search(r"limit\s+(\d+)", text)

    if top_match:
        semantic["relational"]["limit"] = int(top_match.group(1))
    elif limit_match:
        semantic["relational"]["limit"] = int(limit_match.group(1))

    return semantic


def parse_design_query(text, semantic):
    semantic["query_type"] = "inverse_design"
    semantic["domain"] = "quantum_dye"
    semantic["intent"] = "design"

    if "dye" in text or "molecule" in text:
        semantic["design"]["target"] = "organic_dye_molecules"

    if "extinction coefficient" in text or "strong absorption" in text:
        semantic["design"]["clauses"]["target"].append({
            "property": "extinction_coefficient",
            "operator": detect_operator(text),
            "value": extract_number(text)
        })

    if "chemically valid" in text or "chemical validity" in text:
        semantic["design"]["clauses"]["subject_to"].append({
            "property": "chemical_validity",
            "operator": "=",
            "value": True
        })

    if "scsscore" in text:
        scs_match = re.search(
            r"scsscore.*?(less than or equal to|at most|<=|less than|below|under|greater than or equal to|at least|>=|greater than|above|over)?\s*(\d+\.?\d*)",
            text
        )

        if scs_match:
            scs_phrase = scs_match.group(1) or ""
            scs_value = float(scs_match.group(2))

            if scs_value.is_integer():
                scs_value = int(scs_value)

            semantic["design"]["clauses"]["subject_to"].append({
                "property": "SCSScore",
                "operator": detect_operator(scs_phrase) or "<=",
                "value": scs_value
            })

    if "novel" in text or "novelty" in text:
        semantic["design"]["clauses"]["prefer"].append({
            "property": "novelty",
            "direction": "HIGH"
        })

    if "aromatic" in text:
        semantic["design"]["clauses"]["prefer"].append({
            "property": "aromaticity",
            "direction": "HIGH"
        })

    if "training set" in text or "duplicate" in text:
        semantic["design"]["clauses"]["avoid"].append("training_set_duplicates")

    if "dye optics" in text:
        semantic["design"]["clauses"]["using_knowledge"].append("dye_optics_rules")

    if "rdkit" in text:
        semantic["design"]["clauses"]["validate"].append("RDKit")

    if "askcos" in text:
        semantic["design"]["clauses"]["validate"].append("ASKCOS")

    if "dft" in text:
        semantic["design"]["clauses"]["validate"].append("DFT")

    if "closed loop" in text:
        semantic["design"]["clauses"]["correct"].append("closed_loop")

    top_match = re.search(r"top\s+(\d+)", text)

    if top_match:
        semantic["design"]["clauses"]["return"].append({
            "top_k": int(top_match.group(1))
        })

    return semantic


def parse_natural_language(prompt):
    text = prompt.lower()
    semantic = create_semantic_object()

    design_keywords = ["design", "dye", "molecule", "rdkit", "askcos", "dft", "matflow"]
    relational_keywords = ["show", "find", "list", "get", "student", "students", "gpa", "count", "average"]

    if any(word in text for word in design_keywords):
        return parse_design_query(text, semantic)

    if any(word in text for word in relational_keywords):
        return parse_relational_query(text, semantic)

    semantic["query_type"] = "unknown"
    semantic["intent"] = "unknown"

    return semantic