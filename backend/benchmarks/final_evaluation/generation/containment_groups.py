"""
final_evaluation/generation/containment_groups.py

240 containment groups: 12 categories x 20 groups, 2-5 NL queries each.
DATA-DEPENDENT containment evaluation on the frozen databases — never a
symbolic proof. Expected relations are computed at build time by executing
every reference SQL and comparing normalized result SETS on the group's
canonical comparison columns.

Group sizes are mixed by construction (pairs, 3/4/5-chains, branching trees,
multiple maximal sets, equivalence classes, incomparable branches).
"""

DB46, LAH, AW = 46, 49, 50
GROUPS = []


def g(category, db, difficulty, queries, tags=(), note=""):
    """queries: list of (question, sql, comparison_columns)."""
    GROUPS.append({
        "category": category,
        "database_id": db,
        "difficulty": difficulty,
        "queries": [
            {"query_id": f"Q{i+1}", "question": q, "reference_sql":
             " ".join(s.split()), "comparison_columns": cols}
            for i, (q, s, cols) in enumerate(queries)],
        "tags": list(tags),
        "notes": note,
    })


# ---------------------------------------------------------------------
# 1. simple_filter_chain — each filter strictly narrows one table
# ---------------------------------------------------------------------
def _simple_filter_chain():
    K = ["patient_id"]
    for city, cond in [("Boise", "chronic_condition = 'yes'"),
                       ("Spokane", "chronic_condition = 'yes'"),
                       ("Pullman", "insurance_provider = 'BlueCross'"),
                       ("Moscow", "insurance_provider = 'Medicaid'")]:
        g("simple_filter_chain", DB46, "easy", [
          ("List the ids of all patients.",
           "SELECT patient_id FROM patients", K),
          (f"List the ids of patients living in {city}.",
           f"SELECT patient_id FROM patients WHERE city = '{city}'", K),
          (f"List the ids of {city} patients where {cond.replace('_', ' ')}.",
           f"SELECT patient_id FROM patients WHERE city = '{city}' "
           f"AND {cond}", K),
         ], tags=["strict_subset", "transitive_chain"])
    for st, vt in [("completed", "checkup"), ("cancelled", "urgent"),
                   ("completed", "screening"), ("no_show", "followup")]:
        g("simple_filter_chain", DB46, "easy", [
          ("Show every appointment id.",
           "SELECT appointment_id FROM appointments", ["appointment_id"]),
          (f"Show ids of appointments with status '{st}'.",
           f"SELECT appointment_id FROM appointments WHERE status = '{st}'",
           ["appointment_id"]),
          (f"Show ids of '{st}' appointments of visit type '{vt}'.",
           f"SELECT appointment_id FROM appointments WHERE status = '{st}' "
           f"AND visit_type = '{vt}'", ["appointment_id"]),
          (f"Show ids of '{st}' {vt} appointments with a base fee above "
           f"100.",
           f"SELECT appointment_id FROM appointments WHERE status = '{st}' "
           f"AND visit_type = '{vt}' AND base_fee > 100",
           ["appointment_id"]),
         ], tags=["strict_subset", "transitive_chain"])
    for cat in ["electronics", "furniture", "stationery", "home"]:
        g("simple_filter_chain", DB46, "medium", [
          ("List all product ids.", "SELECT product_id FROM products",
           ["product_id"]),
          (f"List ids of {cat} products.",
           f"SELECT product_id FROM products WHERE category = '{cat}'",
           ["product_id"]),
          (f"List ids of {cat} products priced above 100.",
           f"SELECT product_id FROM products WHERE category = '{cat}' "
           f"AND unit_price > 100", ["product_id"]),
          (f"List ids of {cat} products priced above 100 with stock "
           f"below 50.",
           f"SELECT product_id FROM products WHERE category = '{cat}' "
           f"AND unit_price > 100 AND stock_quantity < 50",
           ["product_id"]),
          (f"List ids of {cat} products priced above 300 with stock "
           f"below 50.",
           f"SELECT product_id FROM products WHERE category = '{cat}' "
           f"AND unit_price > 300 AND stock_quantity < 50",
           ["product_id"]),
         ], tags=["strict_subset", "transitive_chain", "5_query"])
    for yr, hr in [(2015, 20), (2019, 25), (2010, 30), (2005, 35)]:
        g("simple_filter_chain", LAH, "medium", [
          (f"Player ids with a batting record in {yr}.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr}",
           ["playerID"]),
          (f"Player ids with at least {hr} home runs in {yr}.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr} AND "
           f"HR >= {hr}", ["playerID"]),
          (f"Player ids with at least {hr} home runs and 100 RBIs in "
           f"{yr}.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr} AND "
           f"HR >= {hr} AND RBI >= 100", ["playerID"]),
         ], tags=["strict_subset", "transitive_chain"])
    for color, lp in [("Red", 500), ("Black", 1000), ("Silver", 800),
                      ("Blue", 1500)]:
        g("simple_filter_chain", AW, "hard", [
          ("All product ids.", "SELECT ProductID FROM Product",
           ["ProductID"]),
          (f"Ids of {color} products.",
           f"SELECT ProductID FROM Product WHERE Color = '{color}'",
           ["ProductID"]),
          (f"Ids of {color} products with a list price above {lp}.",
           f"SELECT ProductID FROM Product WHERE Color = '{color}' AND "
           f"ListPrice > {lp}", ["ProductID"]),
         ], tags=["strict_subset", "transitive_chain"])


# ---------------------------------------------------------------------
# 2. conjunction_disjunction — OR ⊇ single ⊇ AND
# ---------------------------------------------------------------------
def _conjunction_disjunction():
    combos46 = [
        ("patients", "patient_id", "city = 'Boise'",
         "insurance_provider = 'Aetna'", "Boise residents",
         "Aetna-insured patients"),
        ("patients", "patient_id", "chronic_condition = 'yes'",
         "insurance_provider = 'Medicaid'", "chronic patients",
         "Medicaid patients"),
        ("orders", "order_id", "order_status = 'delivered'",
         "shipping_city = 'Portland'", "delivered orders",
         "orders shipped to Portland"),
        ("appointments", "appointment_id", "status = 'completed'",
         "visit_type = 'checkup'", "completed appointments",
         "checkup visits"),
        ("products", "product_id", "category = 'electronics'",
         "unit_price > 200", "electronics products",
         "products above 200"),
        ("invoices", "invoice_id", "payment_status = 'unpaid'",
         "total_amount > 300", "unpaid invoices",
         "invoices above 300"),
        ("lab_results", "lab_id", "result_flag = 'high'",
         "test_name = 'glucose'", "high-flag results",
         "glucose tests"),
        ("customers", "customer_id", "loyalty_level = 'gold'",
         "city = 'Tacoma'", "gold customers", "Tacoma customers"),
    ]
    for tbl, key, a, b, da, db_ in combos46:
        g("conjunction_disjunction", DB46, "easy", [
          (f"Ids of {da} or {db_} (either condition).",
           f"SELECT {key} FROM {tbl} WHERE {a} OR {b}", [key]),
          (f"Ids of {da}.", f"SELECT {key} FROM {tbl} WHERE {a}", [key]),
          (f"Ids of {da} that are also {db_}.",
           f"SELECT {key} FROM {tbl} WHERE {a} AND {b}", [key]),
         ], tags=["and_vs_or", "strict_subset", "branching"])
    for tbl, key, a, b, da, db_ in combos46[:6]:
        g("conjunction_disjunction", DB46, "medium", [
          (f"Ids of {da} or {db_}.",
           f"SELECT {key} FROM {tbl} WHERE {a} OR {b}", [key]),
          (f"Ids of {db_}.", f"SELECT {key} FROM {tbl} WHERE {b}", [key]),
          (f"Ids of rows that are {da} and also {db_}.",
           f"SELECT {key} FROM {tbl} WHERE {a} AND {b}", [key]),
          (f"Ids of {da}.", f"SELECT {key} FROM {tbl} WHERE {a}", [key]),
         ], tags=["and_vs_or", "branching", "multiple_maximal"])
    for lst, single in [("('gold', 'platinum')", "'gold'"),
                        ("('bronze', 'silver')", "'silver'"),
                        ("('gold', 'platinum', 'silver')", "'platinum'")]:
        g("conjunction_disjunction", DB46, "medium", [
          (f"Customer ids with loyalty in {lst}.",
           f"SELECT customer_id FROM customers WHERE loyalty_level IN "
           f"{lst}", ["customer_id"]),
          (f"Customer ids with loyalty {single}.",
           f"SELECT customer_id FROM customers WHERE loyalty_level = "
           f"{single}", ["customer_id"]),
         ], tags=["in_list", "strict_subset", "pair"])
    for lst, sub in [("('AL')", "('AL', 'NL')"),
                     ("('NL')", "('AL', 'NL')"),
                     ("('CHN', 'BOS')", "('CHN', 'BOS', 'NYA')")]:
        g("conjunction_disjunction", LAH, "hard", [
          (f"Player ids on 2015 batting records for teams in {sub}.",
           f"SELECT playerID FROM Batting WHERE yearID = 2015 AND "
           f"teamID IN {sub}", ["playerID"]),
          (f"Player ids on 2015 batting records for teams in {lst}.",
           f"SELECT playerID FROM Batting WHERE yearID = 2015 AND "
           f"teamID IN {lst}", ["playerID"]),
         ], tags=["in_list", "strict_subset", "pair"])


# ---------------------------------------------------------------------
# 3. numeric_range_boundary
# ---------------------------------------------------------------------
def _numeric_range_boundary():
    for col, tbl, key, lo, hi in [
            ("total_amount", "invoices", "invoice_id", 200, 400),
            ("base_fee", "appointments", "appointment_id", 100, 150),
            ("unit_price", "products", "product_id", 100, 300),
            ("test_value", "lab_results", "lab_id", 80, 120),
            ("insurance_paid", "invoices", "invoice_id", 100, 250),
            ("stock_quantity", "products", "product_id", 50, 150)]:
        g("numeric_range_boundary", DB46, "easy", [
          (f"Ids where {col} is greater than {lo}.",
           f"SELECT {key} FROM {tbl} WHERE {col} > {lo}", [key]),
          (f"Ids where {col} is at least {lo}.",
           f"SELECT {key} FROM {tbl} WHERE {col} >= {lo}", [key]),
          (f"Ids where {col} is greater than {hi}.",
           f"SELECT {key} FROM {tbl} WHERE {col} > {hi}", [key]),
         ], tags=["range_boundary", "strict_subset"])
    for col, tbl, key, lo, hi in [
            ("quantity", "order_items", "order_item_id", 2, 4),
            ("years_experience", "doctors", "doctor_id", 5, 15),
            ("days_supply", "prescriptions", "prescription_id", 10, 30),
            ("discount_percent", "order_items", "order_item_id", 0, 10)]:
        g("numeric_range_boundary", DB46, "medium", [
          (f"Ids with {col} between {lo} and {hi} inclusive.",
           f"SELECT {key} FROM {tbl} WHERE {col} BETWEEN {lo} AND {hi}",
           [key]),
          (f"Ids with {col} of at least {lo}.",
           f"SELECT {key} FROM {tbl} WHERE {col} >= {lo}", [key]),
          (f"Ids with {col} of at least {lo} but no more than "
           f"{hi - 1}.",
           f"SELECT {key} FROM {tbl} WHERE {col} >= {lo} AND {col} <= "
           f"{hi - 1}", [key]),
          (f"Ids with {col} above {hi}.",
           f"SELECT {key} FROM {tbl} WHERE {col} > {hi}", [key]),
         ], tags=["range_boundary", "incomparable_branch"])
    for yr, lo, hi in [(2019, 20, 40), (2015, 15, 30), (2010, 25, 45),
                       (2005, 10, 50), (2000, 20, 40), (1995, 15, 35)]:
        g("numeric_range_boundary", LAH, "medium", [
          (f"Player ids with more than {lo} homers in {yr}.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr} AND HR > "
           f"{lo}", ["playerID"]),
          (f"Player ids with {lo} or more homers in {yr}.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr} AND HR >= "
           f"{lo}", ["playerID"]),
          (f"Player ids with more than {hi} homers in {yr}.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr} AND HR > "
           f"{hi}", ["playerID"]),
         ], tags=["range_boundary", "strict_subset"])
    for lo, mid, hi in [(500, 1000, 2000), (100, 500, 1500),
                        (1000, 2000, 3000), (200, 800, 3200)]:
        g("numeric_range_boundary", AW, "hard", [
          (f"Product ids with list price above {lo}.",
           f"SELECT ProductID FROM Product WHERE ListPrice > {lo}",
           ["ProductID"]),
          (f"Product ids with list price above {mid}.",
           f"SELECT ProductID FROM Product WHERE ListPrice > {mid}",
           ["ProductID"]),
          (f"Product ids with list price above {hi}.",
           f"SELECT ProductID FROM Product WHERE ListPrice > {hi}",
           ["ProductID"]),
          (f"Product ids with list price between {lo} and {mid}.",
           f"SELECT ProductID FROM Product WHERE ListPrice BETWEEN "
           f"{lo} AND {mid}", ["ProductID"]),
         ], tags=["range_boundary", "transitive_chain",
                  "incomparable_branch"])


# ---------------------------------------------------------------------
# 4. join_refinement — joins add conditions, never multiply the key set
# ---------------------------------------------------------------------
def _join_refinement():
    for st in ["completed", "cancelled", "no_show"]:
        g("join_refinement", DB46, "easy", [
          ("Distinct ids of patients with any appointment.",
           "SELECT DISTINCT p.patient_id FROM patients p JOIN "
           "appointments a ON a.patient_id = p.patient_id",
           ["patient_id"]),
          (f"Distinct ids of patients with a '{st}' appointment.",
           f"SELECT DISTINCT p.patient_id FROM patients p JOIN "
           f"appointments a ON a.patient_id = p.patient_id WHERE "
           f"a.status = '{st}'", ["patient_id"]),
         ], tags=["join_refinement", "pair", "distinct"])
    for spec in ["cardiology", "primary", "pediatrics", "dermatology",
                 "orthopedics"]:
        g("join_refinement", DB46, "medium", [
          ("Distinct patient ids with any appointment.",
           "SELECT DISTINCT patient_id FROM appointments",
           ["patient_id"]),
          (f"Distinct patient ids seen by a {spec} doctor.",
           f"SELECT DISTINCT a.patient_id FROM appointments a JOIN "
           f"doctors d ON a.doctor_id = d.doctor_id WHERE d.specialty = "
           f"'{spec}'", ["patient_id"]),
          (f"Distinct patient ids with a completed {spec} appointment.",
           f"SELECT DISTINCT a.patient_id FROM appointments a JOIN "
           f"doctors d ON a.doctor_id = d.doctor_id WHERE d.specialty = "
           f"'{spec}' AND a.status = 'completed'", ["patient_id"]),
         ], tags=["join_refinement", "transitive_chain", "distinct"])
    for lvl in ["gold", "platinum", "silver"]:
        g("join_refinement", DB46, "medium", [
          ("Distinct customer ids that placed any order.",
           "SELECT DISTINCT customer_id FROM orders", ["customer_id"]),
          (f"Distinct ids of {lvl} customers that placed an order.",
           f"SELECT DISTINCT o.customer_id FROM orders o JOIN customers "
           f"c ON o.customer_id = c.customer_id WHERE c.loyalty_level = "
           f"'{lvl}'", ["customer_id"]),
          (f"Distinct ids of {lvl} customers with a delivered order.",
           f"SELECT DISTINCT o.customer_id FROM orders o JOIN customers "
           f"c ON o.customer_id = c.customer_id WHERE c.loyalty_level = "
           f"'{lvl}' AND o.order_status = 'delivered'", ["customer_id"]),
          (f"Distinct ids of {lvl} customers with a delivered order "
           f"shipped to Portland.",
           f"SELECT DISTINCT o.customer_id FROM orders o JOIN customers "
           f"c ON o.customer_id = c.customer_id WHERE c.loyalty_level = "
           f"'{lvl}' AND o.order_status = 'delivered' AND "
           f"o.shipping_city = 'Portland'", ["customer_id"]),
         ], tags=["join_refinement", "transitive_chain", "distinct"])
    for yr in [2010, 2015, 2005, 2019]:
        g("join_refinement", LAH, "hard", [
          (f"Distinct player ids with a {yr} batting record.",
           f"SELECT DISTINCT playerID FROM Batting WHERE yearID = {yr}",
           ["playerID"]),
          (f"Distinct player ids who batted for a {yr} World "
           f"Series-winning team.",
           f"SELECT DISTINCT b.playerID FROM Batting b JOIN Teams t ON "
           f"b.teamID = t.teamID AND b.yearID = t.yearID WHERE "
           f"b.yearID = {yr} AND t.WSWin = 'Y'", ["playerID"]),
         ], tags=["join_refinement", "pair", "distinct"])
    for terr, amt in [("Canada", 50000), ("Northwest", 50000),
                      ("Australia", 20000), ("Southwest", 80000),
                      ("Germany", 10000)]:
        g("join_refinement", AW, "hard", [
          ("Distinct customer ids with any sales order.",
           "SELECT DISTINCT CustomerID FROM SalesOrderHeader",
           ["CustomerID"]),
          (f"Distinct customer ids that ordered in the {terr} "
           f"territory.",
           f"SELECT DISTINCT h.CustomerID FROM SalesOrderHeader h JOIN "
           f"SalesTerritory t ON h.TerritoryID = t.TerritoryID WHERE "
           f"t.Name = '{terr}'", ["CustomerID"]),
          (f"Distinct {terr} customer ids with an order above {amt}.",
           f"SELECT DISTINCT h.CustomerID FROM SalesOrderHeader h JOIN "
           f"SalesTerritory t ON h.TerritoryID = t.TerritoryID WHERE "
           f"t.Name = '{terr}' AND h.TotalDue > {amt}", ["CustomerID"]),
         ], tags=["join_refinement", "transitive_chain", "distinct"])


# ---------------------------------------------------------------------
# 5. multi_table_refinement — 3-4 tables, each hop/filter narrows
# ---------------------------------------------------------------------
def _multi_table_refinement():
    for flag in ["critical", "high", "low", "normal"]:
        g("multi_table_refinement", DB46, "medium", [
          ("Distinct patient ids with any lab result.",
           "SELECT DISTINCT a.patient_id FROM appointments a JOIN "
           "lab_results l ON l.appointment_id = a.appointment_id",
           ["patient_id"]),
          (f"Distinct patient ids with a '{flag}' lab result.",
           f"SELECT DISTINCT a.patient_id FROM appointments a JOIN "
           f"lab_results l ON l.appointment_id = a.appointment_id "
           f"WHERE l.result_flag = '{flag}'", ["patient_id"]),
          (f"Distinct patient ids with a '{flag}' glucose result.",
           f"SELECT DISTINCT a.patient_id FROM appointments a JOIN "
           f"lab_results l ON l.appointment_id = a.appointment_id "
           f"WHERE l.result_flag = '{flag}' AND l.test_name = "
           f"'glucose'", ["patient_id"]),
         ], tags=["multi_table", "transitive_chain", "distinct"])
    for cat in ["electronics", "furniture", "home", "stationery"]:
        g("multi_table_refinement", DB46, "medium", [
          ("Distinct customer ids that bought anything.",
           "SELECT DISTINCT o.customer_id FROM orders o JOIN "
           "order_items oi ON oi.order_id = o.order_id",
           ["customer_id"]),
          (f"Distinct customer ids that bought a {cat} product.",
           f"SELECT DISTINCT o.customer_id FROM orders o JOIN "
           f"order_items oi ON oi.order_id = o.order_id JOIN products "
           f"p ON oi.product_id = p.product_id WHERE p.category = "
           f"'{cat}'", ["customer_id"]),
          (f"Distinct customer ids that bought a {cat} product in "
           f"quantity 3 or more.",
           f"SELECT DISTINCT o.customer_id FROM orders o JOIN "
           f"order_items oi ON oi.order_id = o.order_id JOIN products "
           f"p ON oi.product_id = p.product_id WHERE p.category = "
           f"'{cat}' AND oi.quantity >= 3", ["customer_id"]),
          (f"Distinct customer ids with a delivered order containing a "
           f"{cat} product in quantity 3 or more.",
           f"SELECT DISTINCT o.customer_id FROM orders o JOIN "
           f"order_items oi ON oi.order_id = o.order_id JOIN products "
           f"p ON oi.product_id = p.product_id WHERE p.category = "
           f"'{cat}' AND oi.quantity >= 3 AND o.order_status = "
           f"'delivered'", ["customer_id"]),
         ], tags=["multi_table", "transitive_chain", "distinct",
                  "4_query"])
    for mcls in ["antibiotic", "painkiller", "statin", "inhaler",
                 "allergy"]:
        g("multi_table_refinement", DB46, "hard", [
          ("Distinct patient ids with any prescription.",
           "SELECT DISTINCT a.patient_id FROM appointments a JOIN "
           "prescriptions pr ON pr.appointment_id = a.appointment_id",
           ["patient_id"]),
          (f"Distinct patient ids prescribed a {mcls} medication.",
           f"SELECT DISTINCT a.patient_id FROM appointments a JOIN "
           f"prescriptions pr ON pr.appointment_id = a.appointment_id "
           f"JOIN medications m ON pr.medication_id = m.medication_id "
           f"WHERE m.medication_class = '{mcls}'", ["patient_id"]),
          (f"Distinct patient ids prescribed a {mcls} medication with "
           f"refills allowed.",
           f"SELECT DISTINCT a.patient_id FROM appointments a JOIN "
           f"prescriptions pr ON pr.appointment_id = a.appointment_id "
           f"JOIN medications m ON pr.medication_id = m.medication_id "
           f"WHERE m.medication_class = '{mcls}' AND pr.refill_allowed "
           f"= 'yes'", ["patient_id"]),
         ], tags=["multi_table", "transitive_chain", "distinct"])
    for cat, q1 in [("Bikes", 5), ("Components", 10), ("Clothing", 6),
                    ("Accessories", 8)]:
        g("multi_table_refinement", AW, "hard", [
          (f"Distinct sales order ids containing a {cat} product.",
           f"SELECT DISTINCT d.SalesOrderID FROM SalesOrderDetail d "
           f"JOIN Product p ON d.ProductID = p.ProductID JOIN "
           f"ProductSubcategory s ON p.ProductSubcategoryID = "
           f"s.ProductSubcategoryID JOIN ProductCategory c ON "
           f"s.ProductCategoryID = c.ProductCategoryID WHERE c.Name = "
           f"'{cat}'", ["SalesOrderID"]),
          (f"Distinct sales order ids with a {cat} line of quantity "
           f"{q1} or more.",
           f"SELECT DISTINCT d.SalesOrderID FROM SalesOrderDetail d "
           f"JOIN Product p ON d.ProductID = p.ProductID JOIN "
           f"ProductSubcategory s ON p.ProductSubcategoryID = "
           f"s.ProductSubcategoryID JOIN ProductCategory c ON "
           f"s.ProductCategoryID = c.ProductCategoryID WHERE c.Name = "
           f"'{cat}' AND d.OrderQty >= {q1}", ["SalesOrderID"]),
         ], tags=["multi_table", "pair", "distinct"])
    for color in ["Red", "Black", "Silver"]:
        g("multi_table_refinement", AW, "medium", [
          (f"Distinct sales order ids containing a {color} product.",
           f"SELECT DISTINCT d.SalesOrderID FROM SalesOrderDetail d "
           f"JOIN Product p ON d.ProductID = p.ProductID WHERE "
           f"p.Color = '{color}'", ["SalesOrderID"]),
          (f"Distinct sales order ids with a {color} line priced above "
           f"1000.",
           f"SELECT DISTINCT d.SalesOrderID FROM SalesOrderDetail d "
           f"JOIN Product p ON d.ProductID = p.ProductID WHERE "
           f"p.Color = '{color}' AND d.UnitPrice > 1000",
           ["SalesOrderID"]),
         ], tags=["multi_table", "pair", "distinct"])


# ---------------------------------------------------------------------
# 6. aggregate_having — HAVING thresholds nest
# ---------------------------------------------------------------------
def _aggregate_having():
    for n1, n2 in [(1, 2), (2, 3), (1, 3), (2, 4)]:
        g("aggregate_having", DB46, "easy", [
          (f"Patient ids with more than {n1} appointments.",
           f"SELECT patient_id FROM appointments GROUP BY patient_id "
           f"HAVING COUNT(*) > {n1}", ["patient_id"]),
          (f"Patient ids with more than {n2} appointments.",
           f"SELECT patient_id FROM appointments GROUP BY patient_id "
           f"HAVING COUNT(*) > {n2}", ["patient_id"]),
         ], tags=["having_threshold", "pair", "count"])
    for v1, v2, v3 in [(200, 500, 1000), (100, 400, 800),
                       (300, 600, 1200), (150, 450, 900)]:
        g("aggregate_having", DB46, "medium", [
          (f"Patient ids whose total invoiced amount exceeds {v1}.",
           f"SELECT a.patient_id FROM invoices i JOIN appointments a "
           f"ON i.appointment_id = a.appointment_id GROUP BY "
           f"a.patient_id HAVING SUM(i.total_amount) > {v1}",
           ["patient_id"]),
          (f"Patient ids whose total invoiced amount exceeds {v2}.",
           f"SELECT a.patient_id FROM invoices i JOIN appointments a "
           f"ON i.appointment_id = a.appointment_id GROUP BY "
           f"a.patient_id HAVING SUM(i.total_amount) > {v2}",
           ["patient_id"]),
          (f"Patient ids whose total invoiced amount exceeds {v3}.",
           f"SELECT a.patient_id FROM invoices i JOIN appointments a "
           f"ON i.appointment_id = a.appointment_id GROUP BY "
           f"a.patient_id HAVING SUM(i.total_amount) > {v3}",
           ["patient_id"]),
         ], tags=["having_threshold", "transitive_chain", "sum"])
    for n1, n2 in [(1, 2), (2, 3), (1, 3)]:
        g("aggregate_having", DB46, "medium", [
          (f"Patient ids with lab results in more than {n1} distinct "
           f"test types.",
           f"SELECT a.patient_id FROM appointments a JOIN lab_results "
           f"l ON l.appointment_id = a.appointment_id GROUP BY "
           f"a.patient_id HAVING COUNT(DISTINCT l.test_name) > {n1}",
           ["patient_id"]),
          (f"Patient ids with lab results in more than {n2} distinct "
           f"test types.",
           f"SELECT a.patient_id FROM appointments a JOIN lab_results "
           f"l ON l.appointment_id = a.appointment_id GROUP BY "
           f"a.patient_id HAVING COUNT(DISTINCT l.test_name) > {n2}",
           ["patient_id"]),
          (f"Patient ids with more than {n2} lab results overall.",
           f"SELECT a.patient_id FROM appointments a JOIN lab_results "
           f"l ON l.appointment_id = a.appointment_id GROUP BY "
           f"a.patient_id HAVING COUNT(*) > {n2}", ["patient_id"]),
         ], tags=["having_threshold", "count_distinct",
                  "incomparable_branch"])
    for a1, a2 in [(100, 130), (110, 140), (90, 120)]:
        g("aggregate_having", DB46, "hard", [
          (f"Doctor ids whose average appointment base fee exceeds "
           f"{a1}.",
           f"SELECT doctor_id FROM appointments GROUP BY doctor_id "
           f"HAVING AVG(base_fee) > {a1}", ["doctor_id"]),
          (f"Doctor ids whose average appointment base fee exceeds "
           f"{a2}.",
           f"SELECT doctor_id FROM appointments GROUP BY doctor_id "
           f"HAVING AVG(base_fee) > {a2}", ["doctor_id"]),
         ], tags=["having_threshold", "avg", "pair"])
    for hr1, hr2, hr3 in [(300, 400, 500), (200, 350, 550),
                          (250, 450, 600)]:
        g("aggregate_having", LAH, "hard", [
          (f"Player ids with career home runs above {hr1}.",
           f"SELECT playerID FROM Batting GROUP BY playerID HAVING "
           f"SUM(HR) > {hr1}", ["playerID"]),
          (f"Player ids with career home runs above {hr2}.",
           f"SELECT playerID FROM Batting GROUP BY playerID HAVING "
           f"SUM(HR) > {hr2}", ["playerID"]),
          (f"Player ids with career home runs above {hr3}.",
           f"SELECT playerID FROM Batting GROUP BY playerID HAVING "
           f"SUM(HR) > {hr3}", ["playerID"]),
         ], tags=["having_threshold", "transitive_chain", "sum"])
    for n1, n2 in [(1, 2), (2, 3), (1, 3)]:
        g("aggregate_having", DB46, "medium", [
          (f"Customer ids with more than {n1} orders.",
           f"SELECT customer_id FROM orders GROUP BY customer_id "
           f"HAVING COUNT(*) > {n1}", ["customer_id"]),
          (f"Customer ids with more than {n2} orders.",
           f"SELECT customer_id FROM orders GROUP BY customer_id "
           f"HAVING COUNT(*) > {n2}", ["customer_id"]),
         ], tags=["having_threshold", "pair", "count"])


# ---------------------------------------------------------------------
# 7. distinct_projection_key — DISTINCT vs duplicates on the same key
# ---------------------------------------------------------------------
def _distinct_projection_key():
    for tbl, key, fk in [("appointments", "patient_id", "patients"),
                         ("orders", "customer_id", "customers"),
                         ("prescriptions", "appointment_id",
                          "appointments"),
                         ("lab_results", "appointment_id",
                          "appointments")]:
        g("distinct_projection_key", DB46, "easy", [
          (f"The distinct {key} values appearing in {tbl}.",
           f"SELECT DISTINCT {key} FROM {tbl}", [key]),
          (f"The {key} of every row in {tbl}, duplicates included.",
           f"SELECT {key} FROM {tbl}", [key]),
         ], tags=["distinct_vs_dup", "pair", "duplicate_rows",
                  "output_key_normalization"])
    for st in ["completed", "cancelled"]:
        g("distinct_projection_key", DB46, "medium", [
          (f"Distinct patient ids with a '{st}' appointment.",
           f"SELECT DISTINCT patient_id FROM appointments WHERE status "
           f"= '{st}'", ["patient_id"]),
          (f"Patient ids of '{st}' appointments (one per appointment).",
           f"SELECT patient_id FROM appointments WHERE status = '{st}'",
           ["patient_id"]),
          (f"Distinct patient ids with a '{st}' checkup appointment.",
           f"SELECT DISTINCT patient_id FROM appointments WHERE status "
           f"= '{st}' AND visit_type = 'checkup'", ["patient_id"]),
         ], tags=["distinct_vs_dup", "strict_subset"])
    for cat in ["electronics", "furniture", "home"]:
        g("distinct_projection_key", DB46, "medium", [
          (f"Distinct product ids ordered at least once ({cat} only).",
           f"SELECT DISTINCT oi.product_id FROM order_items oi JOIN "
           f"products p ON oi.product_id = p.product_id WHERE "
           f"p.category = '{cat}'", ["product_id"]),
          (f"Product ids of every {cat} order line (duplicates kept).",
           f"SELECT oi.product_id FROM order_items oi JOIN products p "
           f"ON oi.product_id = p.product_id WHERE p.category = "
           f"'{cat}'", ["product_id"]),
         ], tags=["distinct_vs_dup", "pair", "duplicate_rows"])
    # projection mismatch -> the service cannot compare (unknown expected)
    for tbl, key, other in [("patients", "patient_id", "patient_name"),
                            ("products", "product_id", "product_name"),
                            ("doctors", "doctor_id", "doctor_name")]:
        g("distinct_projection_key", DB46, "hard", [
          (f"All {key} values from {tbl}.",
           f"SELECT {key} FROM {tbl}", [key]),
          (f"Both {key} and {other} for every row of {tbl}.",
           f"SELECT {key}, {other} FROM {tbl}", [key, other]),
         ], tags=["projection_mismatch", "unsupported_keys", "pair"],
          note="different column counts: pairwise comparison is expected "
               "to be unknown/unsupported")
    for yr in [2015, 2019]:
        g("distinct_projection_key", LAH, "hard", [
          (f"Distinct player ids batting in {yr}.",
           f"SELECT DISTINCT playerID FROM Batting WHERE yearID = {yr}",
           ["playerID"]),
          (f"Player ids of all {yr} batting stints (duplicates kept).",
           f"SELECT playerID FROM Batting WHERE yearID = {yr}",
           ["playerID"]),
          (f"Distinct player ids batting in {yr} with 10+ homers.",
           f"SELECT DISTINCT playerID FROM Batting WHERE yearID = {yr} "
           f"AND HR >= 10", ["playerID"]),
         ], tags=["distinct_vs_dup", "strict_subset"])
    for color in ["Red", "Black", "Silver"]:
        g("distinct_projection_key", AW, "medium", [
          (f"Distinct product ids of {color} products ever sold.",
           f"SELECT DISTINCT d.ProductID FROM SalesOrderDetail d JOIN "
           f"Product p ON d.ProductID = p.ProductID WHERE p.Color = "
           f"'{color}'", ["ProductID"]),
          (f"Product ids of every {color} sale line, duplicates "
           f"included.",
           f"SELECT d.ProductID FROM SalesOrderDetail d JOIN Product p "
           f"ON d.ProductID = p.ProductID WHERE p.Color = '{color}'",
           ["ProductID"]),
         ], tags=["distinct_vs_dup", "pair", "duplicate_rows"])
    for st in ["shipped", "placed", "delivered"]:
        g("distinct_projection_key", DB46, "easy", [
          (f"Distinct shipping cities of '{st}' orders.",
           f"SELECT DISTINCT shipping_city FROM orders WHERE "
           f"order_status = '{st}'", ["shipping_city"]),
          (f"Shipping city of every '{st}' order (duplicates kept).",
           f"SELECT shipping_city FROM orders WHERE order_status = "
           f"'{st}'", ["shipping_city"]),
         ], tags=["distinct_vs_dup", "pair", "duplicate_rows"])


# ---------------------------------------------------------------------
# 8. equivalence — same set through different formulations
# ---------------------------------------------------------------------
def _equivalence():
    for a, b in [("'gold'", "'platinum'"), ("'bronze'", "'silver'"),
                 ("'gold'", "'silver'")]:
        g("equivalence", DB46, "easy", [
          (f"Customer ids with loyalty {a} or {b}.",
           f"SELECT customer_id FROM customers WHERE loyalty_level = "
           f"{a} OR loyalty_level = {b}", ["customer_id"]),
          (f"Customer ids whose loyalty is one of {a}, {b}.",
           f"SELECT customer_id FROM customers WHERE loyalty_level IN "
           f"({a}, {b})", ["customer_id"]),
         ], tags=["equivalence_class", "in_list", "pair"])
    for lo, hi in [(100, 300), (200, 500), (50, 150), (300, 700)]:
        g("equivalence", DB46, "easy", [
          (f"Invoice ids with total between {lo} and {hi} inclusive.",
           f"SELECT invoice_id FROM invoices WHERE total_amount "
           f"BETWEEN {lo} AND {hi}", ["invoice_id"]),
          (f"Invoice ids with total at least {lo} and at most {hi}.",
           f"SELECT invoice_id FROM invoices WHERE total_amount >= "
           f"{lo} AND total_amount <= {hi}", ["invoice_id"]),
         ], tags=["equivalence_class", "range_boundary", "pair"])
    for st in ["completed", "cancelled", "no_show"]:
        g("equivalence", DB46, "medium", [
          (f"Distinct ids of patients having at least one '{st}' "
           f"appointment (via join).",
           f"SELECT DISTINCT p.patient_id FROM patients p JOIN "
           f"appointments a ON a.patient_id = p.patient_id WHERE "
           f"a.status = '{st}'", ["patient_id"]),
          (f"Ids of patients for whom a '{st}' appointment exists "
           f"(via EXISTS).",
           f"SELECT p.patient_id FROM patients p WHERE EXISTS (SELECT "
           f"1 FROM appointments a WHERE a.patient_id = p.patient_id "
           f"AND a.status = '{st}')", ["patient_id"]),
          (f"Ids of patients whose id appears among '{st}' "
           f"appointments (via IN).",
           f"SELECT patient_id FROM patients WHERE patient_id IN "
           f"(SELECT patient_id FROM appointments WHERE status = "
           f"'{st}')", ["patient_id"]),
         ], tags=["equivalence_class", "paraphrase", "3_query"])
    for cat in ["electronics", "furniture"]:
        g("equivalence", DB46, "medium", [
          (f"Ids of {cat} products (positive filter).",
           f"SELECT product_id FROM products WHERE category = '{cat}'",
           ["product_id"]),
          (f"Ids of products whose category equals '{cat}' — worded "
           f"differently.",
           f"SELECT product_id FROM products WHERE category IN "
           f"('{cat}')", ["product_id"]),
          (f"Ids of products not in any category other than '{cat}'.",
           f"SELECT product_id FROM products WHERE NOT category <> "
           f"'{cat}'", ["product_id"]),
         ], tags=["equivalence_class", "paraphrase", "3_query"])
    for yr in [2010, 2015, 2019]:
        g("equivalence", LAH, "medium", [
          (f"Distinct ids of players who batted in {yr} (plain).",
           f"SELECT DISTINCT playerID FROM Batting WHERE yearID = {yr}",
           ["playerID"]),
          (f"Distinct {yr} batter ids, phrased again.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr} GROUP BY "
           f"playerID", ["playerID"]),
         ], tags=["equivalence_class", "paraphrase", "pair",
                  "output_key_normalization"])
    for color in ["Red", "Black"]:
        g("equivalence", AW, "hard", [
          (f"Ids of {color} products via equality.",
           f"SELECT ProductID FROM Product WHERE Color = '{color}'",
           ["ProductID"]),
          (f"Ids of {color} products via IN-list.",
           f"SELECT ProductID FROM Product WHERE Color IN ('{color}')",
           ["ProductID"]),
          (f"Ids of products whose color matches '{color}' exactly "
           f"(LIKE without wildcards).",
           f"SELECT ProductID FROM Product WHERE Color LIKE '{color}'",
           ["ProductID"]),
         ], tags=["equivalence_class", "paraphrase", "3_query"])
    # equivalence class + an outsider (multiple minimal sets)
    for st, other in [("unpaid", "partial"), ("paid", "unpaid"),
                      ("partial", "paid")]:
        g("equivalence", DB46, "hard", [
          (f"Invoice ids with payment status '{st}'.",
           f"SELECT invoice_id FROM invoices WHERE payment_status = "
           f"'{st}'", ["invoice_id"]),
          (f"Invoice ids whose payment status is exactly '{st}' "
           f"(reworded).",
           f"SELECT invoice_id FROM invoices WHERE payment_status IN "
           f"('{st}')", ["invoice_id"]),
          (f"Invoice ids with payment status '{other}'.",
           f"SELECT invoice_id FROM invoices WHERE payment_status = "
           f"'{other}'", ["invoice_id"]),
         ], tags=["equivalence_class", "incomparable_branch",
                  "multiple_minimal"])


# ---------------------------------------------------------------------
# 9. incomparable — overlapping, neither contains the other
# ---------------------------------------------------------------------
def _incomparable():
    pairs46 = [
        ("Patient ids of completed appointments.",
         "SELECT DISTINCT patient_id FROM appointments WHERE status = "
         "'completed'",
         "Patient ids of urgent visits.",
         "SELECT DISTINCT patient_id FROM appointments WHERE "
         "visit_type = 'urgent'", "patient_id"),
        ("Ids of products above 200.",
         "SELECT product_id FROM products WHERE unit_price > 200",
         "Ids of electronics products.",
         "SELECT product_id FROM products WHERE category = "
         "'electronics'", "product_id"),
        ("Ids of Boise patients.",
         "SELECT patient_id FROM patients WHERE city = 'Boise'",
         "Ids of chronic patients.",
         "SELECT patient_id FROM patients WHERE chronic_condition = "
         "'yes'", "patient_id"),
        ("Ids of unpaid invoices.",
         "SELECT invoice_id FROM invoices WHERE payment_status = "
         "'unpaid'",
         "Ids of invoices above 400.",
         "SELECT invoice_id FROM invoices WHERE total_amount > 400",
         "invoice_id"),
        ("Ids of gold customers.",
         "SELECT customer_id FROM customers WHERE loyalty_level = "
         "'gold'",
         "Ids of Tacoma customers.",
         "SELECT customer_id FROM customers WHERE city = 'Tacoma'",
         "customer_id"),
        ("Ids of orders shipped to Portland.",
         "SELECT order_id FROM orders WHERE shipping_city = "
         "'Portland'",
         "Ids of delivered orders.",
         "SELECT order_id FROM orders WHERE order_status = "
         "'delivered'", "order_id"),
        ("Lab ids flagged high.",
         "SELECT lab_id FROM lab_results WHERE result_flag = 'high'",
         "Lab ids of glucose tests.",
         "SELECT lab_id FROM lab_results WHERE test_name = 'glucose'",
         "lab_id"),
        ("Doctor ids in cardiology.",
         "SELECT doctor_id FROM doctors WHERE specialty = "
         "'cardiology'",
         "Doctor ids with 10+ years of experience.",
         "SELECT doctor_id FROM doctors WHERE years_experience >= 10",
         "doctor_id"),
        ("Medication ids of controlled substances.",
         "SELECT medication_id FROM medications WHERE "
         "controlled_substance = 'yes'",
         "Medication ids of painkillers.",
         "SELECT medication_id FROM medications WHERE "
         "medication_class = 'painkiller'", "medication_id"),
        ("Product ids with stock below 30.",
         "SELECT product_id FROM products WHERE stock_quantity < 30",
         "Product ids priced above 250.",
         "SELECT product_id FROM products WHERE unit_price > 250",
         "product_id"),
    ]
    for qa, sa, qb, sb, key in pairs46:
        g("incomparable", DB46, "easy",
          [(qa, sa, [key]), (qb, sb, [key])],
          tags=["incomparable_branch", "pair"])
    tri46 = [
        ("completed", "urgent", "screening"),
        ("cancelled", "checkup", "followup"),
    ]
    for st, v1, v2 in tri46:
        g("incomparable", DB46, "medium", [
          (f"Distinct patient ids with '{st}' appointments.",
           f"SELECT DISTINCT patient_id FROM appointments WHERE status "
           f"= '{st}'", ["patient_id"]),
          (f"Distinct patient ids with '{v1}' visits.",
           f"SELECT DISTINCT patient_id FROM appointments WHERE "
           f"visit_type = '{v1}'", ["patient_id"]),
          (f"Distinct patient ids with '{v2}' visits.",
           f"SELECT DISTINCT patient_id FROM appointments WHERE "
           f"visit_type = '{v2}'", ["patient_id"]),
         ], tags=["incomparable_branch", "3_query",
                  "multiple_maximal", "multiple_minimal"])
    for yr in [2010, 2015]:
        g("incomparable", LAH, "medium", [
          (f"Player ids with 20+ homers in {yr}.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr} AND HR "
           f">= 20", ["playerID"]),
          (f"Player ids with 20+ steals in {yr}.",
           f"SELECT playerID FROM Batting WHERE yearID = {yr} AND SB "
           f">= 20", ["playerID"]),
         ], tags=["incomparable_branch", "pair"])
    for t1, t2 in [("Canada", "Australia"), ("Northwest", "Southwest")]:
        g("incomparable", AW, "medium", [
          (f"Distinct customer ids ordering from {t1}.",
           f"SELECT DISTINCT h.CustomerID FROM SalesOrderHeader h JOIN "
           f"SalesTerritory t ON h.TerritoryID = t.TerritoryID WHERE "
           f"t.Name = '{t1}'", ["CustomerID"]),
          (f"Distinct customer ids ordering from {t2}.",
           f"SELECT DISTINCT h.CustomerID FROM SalesOrderHeader h JOIN "
           f"SalesTerritory t ON h.TerritoryID = t.TerritoryID WHERE "
           f"t.Name = '{t2}'", ["CustomerID"]),
         ], tags=["incomparable_branch", "pair"])
    # 4-branch: two incomparable pairs + their union as single maximal
    for a, b in [("electronics", "furniture"), ("home", "stationery")]:
        g("incomparable", DB46, "hard", [
          (f"Product ids in {a} or {b}.",
           f"SELECT product_id FROM products WHERE category IN "
           f"('{a}', '{b}')", ["product_id"]),
          (f"Product ids in {a}.",
           f"SELECT product_id FROM products WHERE category = '{a}'",
           ["product_id"]),
          (f"Product ids in {b}.",
           f"SELECT product_id FROM products WHERE category = '{b}'",
           ["product_id"]),
          (f"Product ids in {a} priced above 150.",
           f"SELECT product_id FROM products WHERE category = '{a}' "
           f"AND unit_price > 150", ["product_id"]),
         ], tags=["incomparable_branch", "branching", "4_query",
                  "multiple_minimal"])
    for cc in [("BlueCross", "Aetna"), ("Medicaid", "None")]:
        g("incomparable", DB46, "hard", [
          (f"Patient ids insured by {cc[0]}.",
           f"SELECT patient_id FROM patients WHERE insurance_provider "
           f"= '{cc[0]}'", ["patient_id"]),
          (f"Patient ids insured by {cc[1]}.",
           f"SELECT patient_id FROM patients WHERE insurance_provider "
           f"= '{cc[1]}'", ["patient_id"]),
         ], tags=["incomparable_branch", "pair", "empty_intersection"])


# ---------------------------------------------------------------------
# 10. temporal — date windows nest; latest-event narrows
# ---------------------------------------------------------------------
def _temporal():
    for m1, m2 in [("2025-04", "2025-07"), ("2025-03", "2025-06"),
                   ("2025-05", "2025-08"), ("2025-02", "2025-09")]:
        g("temporal", DB46, "easy", [
          ("Appointment ids from 2025 (all on record).",
           "SELECT appointment_id FROM appointments",
           ["appointment_id"]),
          (f"Appointment ids on or after {m1}-01.",
           f"SELECT appointment_id FROM appointments WHERE "
           f"appointment_date >= '{m1}-01'", ["appointment_id"]),
          (f"Appointment ids on or after {m2}-01.",
           f"SELECT appointment_id FROM appointments WHERE "
           f"appointment_date >= '{m2}-01'", ["appointment_id"]),
         ], tags=["temporal", "transitive_chain"])
    for q1, q2 in [("2025-01", "2025-03"), ("2025-04", "2025-06")]:
        g("temporal", DB46, "medium", [
          (f"Invoice ids dated between {q1}-01 and {q2}-31.",
           f"SELECT invoice_id FROM invoices WHERE invoice_date >= "
           f"'{q1}-01' AND invoice_date <= '{q2}-31'", ["invoice_id"]),
          (f"Invoice ids from month {q1}.",
           f"SELECT invoice_id FROM invoices WHERE invoice_date LIKE "
           f"'{q1}%'", ["invoice_id"]),
          (f"Invoice ids from month {q2}.",
           f"SELECT invoice_id FROM invoices WHERE invoice_date LIKE "
           f"'{q2}%'", ["invoice_id"]),
         ], tags=["temporal", "branching", "multiple_minimal"])
    for st in ["completed", "cancelled"]:
        g("temporal", DB46, "hard", [
          (f"Distinct patient ids with any '{st}' appointment.",
           f"SELECT DISTINCT patient_id FROM appointments WHERE status "
           f"= '{st}'", ["patient_id"]),
          (f"Patient ids whose most recent appointment is '{st}'.",
           f"SELECT a.patient_id FROM appointments a WHERE "
           f"a.status = '{st}' AND a.appointment_date = (SELECT "
           f"MAX(a2.appointment_date) FROM appointments a2 WHERE "
           f"a2.patient_id = a.patient_id)", ["patient_id"]),
         ], tags=["temporal", "latest_event", "pair"],
          note="latest-event qualification is a strict refinement of "
               "'ever had'")
    for yr1, yr2 in [(2010, 2015), (2000, 2010), (1990, 2000),
                     (2005, 2019)]:
        g("temporal", LAH, "medium", [
          (f"Distinct player ids batting between {yr1} and {yr2}.",
           f"SELECT DISTINCT playerID FROM Batting WHERE yearID "
           f"BETWEEN {yr1} AND {yr2}", ["playerID"]),
          (f"Distinct player ids batting in {yr1}.",
           f"SELECT DISTINCT playerID FROM Batting WHERE yearID = "
           f"{yr1}", ["playerID"]),
          (f"Distinct player ids batting in {yr2}.",
           f"SELECT DISTINCT playerID FROM Batting WHERE yearID = "
           f"{yr2}", ["playerID"]),
         ], tags=["temporal", "branching"])
    for y in ["2011", "2012", "2013", "2014"]:
        g("temporal", AW, "medium", [
          (f"Sales order ids from {y}.",
           f"SELECT SalesOrderID FROM SalesOrderHeader WHERE OrderDate "
           f"LIKE '{y}%'", ["SalesOrderID"]),
          (f"Sales order ids from the first half of {y}.",
           f"SELECT SalesOrderID FROM SalesOrderHeader WHERE OrderDate "
           f">= '{y}-01-01' AND OrderDate < '{y}-07-01'",
           ["SalesOrderID"]),
          (f"Sales order ids from {y} with total due above 10000.",
           f"SELECT SalesOrderID FROM SalesOrderHeader WHERE OrderDate "
           f"LIKE '{y}%' AND TotalDue > 10000", ["SalesOrderID"]),
         ], tags=["temporal", "branching", "incomparable_branch"])
    for m in ["2025-06", "2025-07", "2025-08", "2025-09"]:
        g("temporal", DB46, "medium", [
          (f"Order ids placed in {m}.",
           f"SELECT order_id FROM orders WHERE order_date LIKE "
           f"'{m}%'", ["order_id"]),
          (f"Order ids placed on or after {m}-01.",
           f"SELECT order_id FROM orders WHERE order_date >= "
           f"'{m}-01'", ["order_id"]),
         ], tags=["temporal", "pair", "strict_subset"])


# ---------------------------------------------------------------------
# 11. derived_metric — thresholds on computed expressions nest
# ---------------------------------------------------------------------
def _derived_metric():
    for v1, v2 in [(50, 150), (100, 250), (25, 75), (150, 300),
                   (75, 200), (10, 40)]:
        g("derived_metric", DB46, "medium", [
          (f"Invoice ids with an outstanding balance (total minus "
           f"insurance) above {v1}.",
           f"SELECT invoice_id FROM invoices WHERE total_amount - "
           f"insurance_paid > {v1}", ["invoice_id"]),
          (f"Invoice ids with an outstanding balance above {v2}.",
           f"SELECT invoice_id FROM invoices WHERE total_amount - "
           f"insurance_paid > {v2}", ["invoice_id"]),
         ], tags=["derived_measure", "pair", "strict_subset"])
    for v1, v2, v3 in [(100, 300, 600), (200, 400, 800)]:
        g("derived_metric", DB46, "medium", [
          (f"Order item ids with line value (quantity x unit price) "
           f"above {v1}.",
           f"SELECT oi.order_item_id FROM order_items oi JOIN products "
           f"p ON oi.product_id = p.product_id WHERE oi.quantity * "
           f"p.unit_price > {v1}", ["order_item_id"]),
          (f"Order item ids with line value above {v2}.",
           f"SELECT oi.order_item_id FROM order_items oi JOIN products "
           f"p ON oi.product_id = p.product_id WHERE oi.quantity * "
           f"p.unit_price > {v2}", ["order_item_id"]),
          (f"Order item ids with line value above {v3}.",
           f"SELECT oi.order_item_id FROM order_items oi JOIN products "
           f"p ON oi.product_id = p.product_id WHERE oi.quantity * "
           f"p.unit_price > {v3}", ["order_item_id"]),
         ], tags=["derived_measure", "transitive_chain"])
    for pct in [(30, 60), (40, 70), (20, 50)]:
        g("derived_metric", DB46, "hard", [
          (f"Invoice ids where insurance covered less than {pct[1]} "
           f"percent of the total.",
           f"SELECT invoice_id FROM invoices WHERE total_amount > 0 "
           f"AND insurance_paid * 100.0 / total_amount < {pct[1]}",
           ["invoice_id"]),
          (f"Invoice ids where insurance covered less than {pct[0]} "
           f"percent.",
           f"SELECT invoice_id FROM invoices WHERE total_amount > 0 "
           f"AND insurance_paid * 100.0 / total_amount < {pct[0]}",
           ["invoice_id"]),
         ], tags=["derived_measure", "pair", "strict_subset"])
    for m1, m2 in [(100, 500), (250, 750), (50, 300)]:
        g("derived_metric", AW, "hard", [
          (f"Product ids with unit margin (list minus standard cost) "
           f"above {m1}.",
           f"SELECT ProductID FROM Product WHERE ListPrice > 0 AND "
           f"ListPrice - StandardCost > {m1}", ["ProductID"]),
          (f"Product ids with unit margin above {m2}.",
           f"SELECT ProductID FROM Product WHERE ListPrice > 0 AND "
           f"ListPrice - StandardCost > {m2}", ["ProductID"]),
         ], tags=["derived_measure", "pair", "strict_subset"])
    for r1, r2 in [(1, 5), (2, 10), (3, 8)]:
        g("derived_metric", AW, "hard", [
          (f"Work order ids with scrap rate above {r1} percent.",
           f"SELECT WorkOrderID FROM WorkOrder WHERE OrderQty > 0 AND "
           f"ScrappedQty * 100.0 / OrderQty > {r1}", ["WorkOrderID"]),
          (f"Work order ids with scrap rate above {r2} percent.",
           f"SELECT WorkOrderID FROM WorkOrder WHERE OrderQty > 0 AND "
           f"ScrappedQty * 100.0 / OrderQty > {r2}", ["WorkOrderID"]),
          (f"Work order ids with any scrap at all.",
           f"SELECT WorkOrderID FROM WorkOrder WHERE ScrappedQty > 0",
           ["WorkOrderID"]),
         ], tags=["derived_measure", "transitive_chain"])
    for d1, d2 in [(10, 20), (5, 15), (0, 10)]:
        g("derived_metric", DB46, "medium", [
          (f"Order item ids discounted by more than {d1} percent.",
           f"SELECT order_item_id FROM order_items WHERE "
           f"discount_percent > {d1}", ["order_item_id"]),
          (f"Order item ids discounted by more than {d2} percent.",
           f"SELECT order_item_id FROM order_items WHERE "
           f"discount_percent > {d2}", ["order_item_id"]),
         ], tags=["derived_measure", "pair", "strict_subset"])


# ---------------------------------------------------------------------
# 12. mixed_hierarchy_edge_cases
# ---------------------------------------------------------------------
def _mixed_edge_cases():
    # empty result set is contained in everything it is comparable with
    for cond, dsc in [("total_amount > 100000", "impossibly large"),
                      ("total_amount < 0", "negative"),
                      ("payment_status = 'refunded'", "refunded")]:
        g("mixed_hierarchy_edge_cases", DB46, "medium", [
          (f"Invoice ids with a {dsc} total (none should exist).",
           f"SELECT invoice_id FROM invoices WHERE {cond}",
           ["invoice_id"]),
          ("Invoice ids above 400.",
           "SELECT invoice_id FROM invoices WHERE total_amount > 400",
           ["invoice_id"]),
          ("All invoice ids.", "SELECT invoice_id FROM invoices",
           ["invoice_id"]),
         ], tags=["empty_result", "controlled_empty_result",
                  "transitive_chain"])
    # repeated / paraphrased duplicate question in one group
    for city in ["Boise", "Spokane", "Moscow"]:
        g("mixed_hierarchy_edge_cases", DB46, "easy", [
          (f"Ids of patients living in {city}.",
           f"SELECT patient_id FROM patients WHERE city = '{city}'",
           ["patient_id"]),
          (f"Which patients live in {city}? Give their ids.",
           f"SELECT patient_id FROM patients WHERE city = '{city}'",
           ["patient_id"]),
          ("All patient ids.", "SELECT patient_id FROM patients",
           ["patient_id"]),
         ], tags=["paraphrase", "equivalence_class",
                  "repeated_question"])
    # five-query mixed tree: root, two branches, deep chain, equivalent
    for cat, price in [("electronics", 150), ("furniture", 200),
                       ("home", 100)]:
        g("mixed_hierarchy_edge_cases", DB46, "hard", [
          ("All product ids.", "SELECT product_id FROM products",
           ["product_id"]),
          (f"Ids of {cat} products.",
           f"SELECT product_id FROM products WHERE category = '{cat}'",
           ["product_id"]),
          (f"Ids of products above {price}.",
           f"SELECT product_id FROM products WHERE unit_price > "
           f"{price}", ["product_id"]),
          (f"Ids of {cat} products above {price}.",
           f"SELECT product_id FROM products WHERE category = '{cat}' "
           f"AND unit_price > {price}", ["product_id"]),
          (f"Ids of products in the {cat} category (reworded).",
           f"SELECT product_id FROM products WHERE category IN "
           f"('{cat}')", ["product_id"]),
         ], tags=["branching", "5_query", "equivalence_class",
                  "multiple_minimal"])
    # NULL behavior
    g("mixed_hierarchy_edge_cases", AW, "medium", [
      ("Product ids with a recorded color.",
       "SELECT ProductID FROM Product WHERE Color IS NOT NULL",
       ["ProductID"]),
      ("Product ids with no recorded color.",
       "SELECT ProductID FROM Product WHERE Color IS NULL",
       ["ProductID"]),
      ("All product ids.", "SELECT ProductID FROM Product",
       ["ProductID"]),
     ], tags=["null_handling", "incomparable_branch",
              "empty_intersection"])
    g("mixed_hierarchy_edge_cases", AW, "medium", [
      ("Product ids with a subcategory assigned.",
       "SELECT ProductID FROM Product WHERE ProductSubcategoryID IS "
       "NOT NULL", ["ProductID"]),
      ("Product ids without any subcategory.",
       "SELECT ProductID FROM Product WHERE ProductSubcategoryID IS "
       "NULL", ["ProductID"]),
     ], tags=["null_handling", "pair", "empty_intersection"])
    g("mixed_hierarchy_edge_cases", AW, "medium", [
      ("Product ids still on sale (no sell end date).",
       "SELECT ProductID FROM Product WHERE SellEndDate IS NULL",
       ["ProductID"]),
      ("Product ids with a sell end date recorded.",
       "SELECT ProductID FROM Product WHERE SellEndDate IS NOT NULL",
       ["ProductID"]),
      ("All product ids.", "SELECT ProductID FROM Product",
       ["ProductID"]),
     ], tags=["null_handling", "incomparable_branch",
              "empty_intersection"])
    # multiple broadest sets (two overlapping supersets over one subset)
    for v1 in ["urgent", "screening", "checkup"]:
        g("mixed_hierarchy_edge_cases", DB46, "hard", [
          (f"Distinct patient ids with '{v1}' visits.",
           f"SELECT DISTINCT patient_id FROM appointments WHERE "
           f"visit_type = '{v1}'", ["patient_id"]),
          ("Distinct patient ids with completed appointments.",
           "SELECT DISTINCT patient_id FROM appointments WHERE status "
           "= 'completed'", ["patient_id"]),
          (f"Distinct patient ids with completed '{v1}' visits.",
           f"SELECT DISTINCT patient_id FROM appointments WHERE status "
           f"= 'completed' AND visit_type = '{v1}'", ["patient_id"]),
         ], tags=["multiple_maximal", "branching", "3_query"])
    # unsupported keys: different projections in one group
    g("mixed_hierarchy_edge_cases", DB46, "hard", [
      ("Patient ids and names.",
       "SELECT patient_id, patient_name FROM patients",
       ["patient_id", "patient_name"]),
      ("Only patient ids.", "SELECT patient_id FROM patients",
       ["patient_id"]),
     ], tags=["projection_mismatch", "unsupported_keys", "pair"],
      note="column-count mismatch: expected pairwise relation is "
           "unknown/unsupported")
    # Lahman deep chain with equivalent leaf
    for hr in [400, 500]:
        g("mixed_hierarchy_edge_cases", LAH, "hard", [
          ("Player ids with any career batting record.",
           "SELECT DISTINCT playerID FROM Batting", ["playerID"]),
          (f"Player ids with career homers above {hr}.",
           f"SELECT playerID FROM Batting GROUP BY playerID HAVING "
           f"SUM(HR) > {hr}", ["playerID"]),
          (f"Player ids whose summed home runs exceed {hr} "
           f"(reworded).",
           f"SELECT playerID FROM Batting GROUP BY playerID HAVING "
           f"SUM(HR) >= {hr + 1}", ["playerID"]),
         ], tags=["equivalence_class", "transitive_chain",
                  "output_key_normalization"],
          note="> hr and >= hr+1 coincide on integer home run totals")
    # empty vs empty (equivalent empties)
    g("mixed_hierarchy_edge_cases", DB46, "medium", [
      ("Ids of appointments with status 'rescheduled' (nonexistent).",
       "SELECT appointment_id FROM appointments WHERE status = "
       "'rescheduled'", ["appointment_id"]),
      ("Ids of appointments with visit type 'telehealth' "
       "(nonexistent).",
       "SELECT appointment_id FROM appointments WHERE visit_type = "
       "'telehealth'", ["appointment_id"]),
     ], tags=["empty_result", "controlled_empty_result", "pair",
              "equivalence_class"],
      note="two empty result sets are equivalent on the current data")
    g("mixed_hierarchy_edge_cases", DB46, "easy", [
      ("All doctor ids.", "SELECT doctor_id FROM doctors",
       ["doctor_id"]),
      ("Doctor ids of cardiologists.",
       "SELECT doctor_id FROM doctors WHERE specialty = 'cardiology'",
       ["doctor_id"]),
      ("Doctor ids of cardiologists in Boise.",
       "SELECT doctor_id FROM doctors WHERE specialty = 'cardiology' "
       "AND clinic_city = 'Boise'", ["doctor_id"]),
      ("Doctor ids with more than 20 years of experience.",
       "SELECT doctor_id FROM doctors WHERE years_experience > 20",
       ["doctor_id"]),
     ], tags=["branching", "4_query", "incomparable_branch"])


def build_all_groups():
    GROUPS.clear()
    _simple_filter_chain()
    _conjunction_disjunction()
    _numeric_range_boundary()
    _join_refinement()
    _multi_table_refinement()
    _aggregate_having()
    _distinct_projection_key()
    _equivalence()
    _incomparable()
    _temporal()
    _derived_metric()
    _mixed_edge_cases()
    # assign deterministic ids per category
    counters = {}
    for grp in GROUPS:
        cat = grp["category"]
        counters[cat] = counters.get(cat, 0) + 1
        grp["group_id"] = f"{cat}_{counters[cat]:03d}"
    return list(GROUPS)
