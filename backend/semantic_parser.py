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
            "aggregation": None,
            "group_by": None
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

def parse_schema(schema_text):
    tables = {}

    pattern = r"(\w+)\s*\((.*?)\)"
    matches = re.findall(pattern, schema_text)

    for table_name, columns_text in matches:
        columns = [
            col.strip().lower()
            for col in columns_text.split(",")
        ]

        tables[table_name.lower()] = columns
    
    return tables

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


def parse_relational_query(
    text,
    semantic,
    tables,
    schema_info
):
    semantic["query_type"] = "relational_query"
    semantic["domain"] = "database"
    semantic["intent"] = "retrieve"

    table_name = list(tables.keys())[0]

    semantic["relational"]["entity"] = table_name

    semantic["relational"]["group_by"] = schema_info["group_by"]

    semantic["relational"]["sort"] = schema_info["sort"]

    semantic["relational"]["limit"] = schema_info["limit"]

    possible_fields = []

    for table_columns in tables.values():
        possible_fields.extend(table_columns)

    if schema_info["aggregation"] == "COUNT":
        semantic["relational"]["aggregation"] = {
            "function": "COUNT",
            "field": "*"
        }

    elif schema_info["aggregation"] == "AVG":
        avg_field = None

        for field in possible_fields:
            if field in text:
                avg_field = field
                break

        semantic["relational"]["aggregation"] = {
            "function": "AVG",
            "field": avg_field
        }

    else:
        semantic["relational"]["aggregation"] = None

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

    is_sort_query = (
        "sorted by" in text
        or "order by" in text
        or "highest" in text
        or "lowest" in text
        or "top" in text
    )

    if not is_sort_query and not filter_part:
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


def parse_natural_language(prompt, schema_info):
    text = prompt.lower()
    semantic = create_semantic_object()
    
    tables = {
        schema_info["table"]:
        schema_info["columns"]
    }

    print("TABLES:", tables)

    design_keywords = ["design", "dye", "molecule", "rdkit", "askcos", "dft", "matflow"]
    relational_keywords = ["show", "find", "list", "get", "student", "students", "gpa", "count", "average"]

    if any(word in text for word in design_keywords):
        return parse_design_query(text, semantic)

    if any(word in text for word in relational_keywords):
        return parse_relational_query(text, semantic, tables, schema_info)

    semantic["query_type"] = "unknown"
    semantic["intent"] = "unknown"

    return semantic