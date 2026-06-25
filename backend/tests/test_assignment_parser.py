"""
test_assignment_parser.py

Standalone unit tests for assignment_parser (Mode B / Mode C text parsing).
No database, no Ollama. Run with:  python test_assignment_parser.py
"""

from assignment.assignment_parser import extract_assignment_spec, looks_like_assignment


def _rel_set(spec):
    return {
        (r["from_table"].lower(), r["from_column"].lower(),
         r["to_table"].lower(), r["to_column"].lower())
        for r in spec["relationships"]
    }


PETFOOD = """\
Pets(PetID, Name, Age, Street, City, ZipCode, State, TypeofPet)
Owners(OID, LastName, Street, City, ZipCode, State, Age, AnnualIncome)
Owns(PetID, Year, OID, PetAgeatOwnership, PricePaid)
Likes(PetID, TypeofFood)
Foods(FoodID, Name, Brand, TypeofFood, Price, ItemWeight, ClassofFood)
Purchases(OID, FoodID, PetID, Month, Year, Quantity)

Write SQL for:
1. List all cats with PetID, Name, TypeofPet aged at least 2 and live in Idaho except Moscow.
2. List all owners and their pets who own at least two pets.
"""


def test_tables_and_columns():
    spec = extract_assignment_spec(PETFOOD)
    names = [t["name"] for t in spec["tables"]]
    assert names == ["Pets", "Owners", "Owns", "Likes", "Foods", "Purchases"], names
    pets = spec["tables"][0]["columns"]
    assert pets == ["PetID", "Name", "Age", "Street", "City", "ZipCode", "State", "TypeofPet"], pets
    print("[1] six tables + columns parsed -> OK")


def test_inferred_relationships_match_data_detector():
    spec = extract_assignment_spec(PETFOOD)
    got = _rel_set(spec)
    expected = {
        ("owns", "petid", "pets", "petid"),
        ("owns", "oid", "owners", "oid"),
        ("likes", "petid", "pets", "petid"),
        ("purchases", "oid", "owners", "oid"),
        ("purchases", "foodid", "foods", "foodid"),
        ("purchases", "petid", "pets", "petid"),
    }
    assert got == expected, f"\n got:      {sorted(got)}\n expected: {sorted(expected)}"
    # the weak zipcode/domain links must NOT be invented
    assert not any("zipcode" in r[1] for r in got), got
    print("[2] inferred FKs match data-detector set; no zipcode link -> OK")


def test_questions_parsed():
    spec = extract_assignment_spec(PETFOOD)
    assert len(spec["questions"]) == 2, spec["questions"]
    assert spec["questions"][1].startswith("List all owners and their pets"), spec["questions"][1]
    print("[3] numbered questions extracted -> OK")


MODE_C = """\
Pets(PetID, Name, Age, Street#, City, ZipCode, State, TypeofPet)
Owners(OID, LastName, Street#, City, ZipCode, State, Age, AnnualIncome)
Owns(PetID, Year, OID, PetAgeatOwnership, PricePaid)
Write SQL for:
1. List all cats aged at least 2 and live in Idaho except Moscow.
2. List all owners and their pets who own at least two pets.
"""


def test_mode_c_paste_with_decorations():
    spec = extract_assignment_spec(MODE_C)
    # 'Street#' decoration stripped
    assert "Street" in spec["tables"][0]["columns"]
    assert "Street#" not in spec["tables"][0]["columns"]
    got = _rel_set(spec)
    assert ("owns", "petid", "pets", "petid") in got
    assert ("owns", "oid", "owners", "oid") in got
    assert len(spec["questions"]) == 2
    print("[4] Mode-C paste: '#' stripped, FKs + questions parsed -> OK")


def test_explicit_relationship_hints():
    text = """\
Owns(PetID, Year, OID)
Pets(PetID, Name)
Owns.PetID -> Pets.PetID
Owns.OID references Owners.OID
Owners(OID, LastName)
Write SQL for:
1. List all pets.
"""
    spec = extract_assignment_spec(text)
    got = _rel_set(spec)
    assert ("owns", "petid", "pets", "petid") in got
    assert ("owns", "oid", "owners", "oid") in got
    print("[5] explicit '->' and 'references' hints parsed -> OK")


def test_routing_heuristic():
    assert looks_like_assignment(PETFOOD) is True
    assert looks_like_assignment(MODE_C) is True
    assert looks_like_assignment("Pets(PetID, Name)\nOwners(OID, LastName)") is True   # 2 table defs
    assert looks_like_assignment("List all cats aged at least 2 in Idaho.") is False   # normal question
    assert looks_like_assignment("How many owners are there?") is False
    print("[6] assignment-vs-normal routing heuristic -> OK")


def test_no_false_table_from_question_functions():
    spec = extract_assignment_spec(PETFOOD)
    # COUNT(...) etc. appear only inside questions; must not become tables
    assert all(t["name"].lower() not in {"count", "sum", "avg", "max", "min"} for t in spec["tables"])
    print("[7] aggregate calls in questions not mistaken for tables -> OK")


def main():
    tests = [
        test_tables_and_columns,
        test_inferred_relationships_match_data_detector,
        test_questions_parsed,
        test_mode_c_paste_with_decorations,
        test_explicit_relationship_hints,
        test_routing_heuristic,
        test_no_false_table_from_question_functions,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed -- assignment_parser.py verified")


if __name__ == "__main__":
    main()
