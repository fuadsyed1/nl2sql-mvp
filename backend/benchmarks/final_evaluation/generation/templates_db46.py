"""
final_evaluation/generation/templates_db46.py

DB46 ("appointments", database_id 46) template families.

Per category: 6 easy + 8 medium + 6 hard = 20 semantic templates
(x 4 paraphrased cases = 80 cases). Literals are drawn from the frozen
database's real value pools so references return data. Every T carries 4
paraphrase wordings; structural variety lives in `variants` (each variant is
one semantic template).
"""

from benchmarks.final_evaluation.generation.genlib import T

DB = 46
TS = []


def add(*ts):
    TS.extend(ts)


# =====================================================================
# 1. join  (E6 / M8 / H6 templates)
# =====================================================================
add(
T("j46_child_parent", "join", DB, "easy", "multiset_rows",
  ["two_table_join"],
  "SELECT c.{csel}, p.{psel} FROM {child} c JOIN {parent} p "
  "ON c.{fk} = p.{pk} WHERE c.{fcol} = '{fval}'",
  ["List the {cnoun} {cdesc} together with the {pdesc} for {fcol} '{fval}'.",
   "For every {cnoun} whose {fcol} is '{fval}', show its {cdesc} and the {pdesc}.",
   "Show {cdesc} and {pdesc} for {cnoun}s with {fcol} equal to '{fval}'.",
   "Which {cdesc} values and {pdesc}s belong to {cnoun}s where {fcol} = '{fval}'?"],
  variants=[
   dict(child="appointments", parent="patients", fk="patient_id",
        pk="patient_id", csel="appointment_date", psel="patient_name",
        fcol="status", fval="completed", cnoun="appointment",
        cdesc="appointment date", pdesc="patient name"),
   dict(child="appointments", parent="doctors", fk="doctor_id",
        pk="doctor_id", csel="appointment_date", psel="doctor_name",
        fcol="visit_type", fval="urgent", cnoun="appointment",
        cdesc="appointment date", pdesc="doctor name"),
   dict(child="invoices", parent="appointments", fk="appointment_id",
        pk="appointment_id", csel="total_amount", psel="appointment_date",
        fcol="payment_status", fval="unpaid", cnoun="invoice",
        cdesc="total amount", pdesc="appointment date"),
   dict(child="orders", parent="customers", fk="customer_id",
        pk="customer_id", csel="order_date", psel="customer_name",
        fcol="order_status", fval="delivered", cnoun="order",
        cdesc="order date", pdesc="customer name"),
   dict(child="prescriptions", parent="medications", fk="medication_id",
        pk="medication_id", csel="dosage", psel="medication_name",
        fcol="refill_allowed", fval="yes", cnoun="prescription",
        cdesc="dosage", pdesc="medication name"),
   dict(child="lab_results", parent="appointments", fk="appointment_id",
        pk="appointment_id", csel="test_name", psel="appointment_date",
        fcol="result_flag", fval="critical", cnoun="lab result",
        cdesc="test name", pdesc="appointment date"),
  ]),
T("j46_parent_filter", "join", DB, "medium", "multiset_rows",
  ["two_table_join", "multiple_conditions"],
  "SELECT c.{csel}, p.{psel} FROM {child} c JOIN {parent} p "
  "ON c.{fk} = p.{pk} WHERE p.{pfcol} = '{pfval}' AND c.{cfcol} = '{cfval}'",
  ["Show each {cnoun}'s {cdesc} with the {pdesc} where the {pnoun}'s "
   "{pfcol} is '{pfval}' and the {cnoun}'s {cfcol} is '{cfval}'.",
   "List {cdesc} and {pdesc} for {cnoun}s with {cfcol} '{cfval}' whose "
   "{pnoun} has {pfcol} '{pfval}'.",
   "For {pnoun}s with {pfcol} '{pfval}', show their {cnoun}s' {cdesc} and "
   "the {pdesc}, keeping only {cfcol} '{cfval}' {cnoun}s.",
   "Which {cdesc} and {pdesc} pairs have {pfcol} = '{pfval}' and "
   "{cfcol} = '{cfval}'?"],
  variants=[
   dict(child="appointments", parent="doctors", fk="doctor_id",
        pk="doctor_id", csel="appointment_date", psel="doctor_name",
        pfcol="specialty", pfval="cardiology", cfcol="status",
        cfval="completed", cnoun="appointment", pnoun="doctor",
        cdesc="appointment date", pdesc="doctor name"),
   dict(child="appointments", parent="patients", fk="patient_id",
        pk="patient_id", csel="appointment_date", psel="patient_name",
        pfcol="insurance_provider", pfval="Medicaid", cfcol="visit_type",
        cfval="checkup", cnoun="appointment", pnoun="patient",
        cdesc="appointment date", pdesc="patient name"),
   dict(child="orders", parent="customers", fk="customer_id",
        pk="customer_id", csel="order_date", psel="customer_name",
        pfcol="loyalty_level", pfval="gold", cfcol="order_status",
        cfval="shipped", cnoun="order", pnoun="customer",
        cdesc="order date", pdesc="customer name"),
   dict(child="orders", parent="customers", fk="customer_id",
        pk="customer_id", csel="shipping_city", psel="customer_name",
        pfcol="city", pfval="Spokane", cfcol="order_status",
        cfval="delivered", cnoun="order", pnoun="customer",
        cdesc="shipping city", pdesc="customer name"),
  ]),
T("j46_range_join", "join", DB, "medium", "multiset_rows",
  ["two_table_join", "range_filter"],
  "SELECT c.{csel}, p.{psel} FROM {child} c JOIN {parent} p "
  "ON c.{fk} = p.{pk} WHERE c.{ncol} {op} {nval}",
  ["List {cdesc} and {pdesc} for {cnoun}s whose {ncol} is {opw} {nval}.",
   "Show every {cnoun}'s {cdesc} with its {pdesc} where {ncol} {opw} {nval}.",
   "Which {cnoun}s have {ncol} {opw} {nval}? Show {cdesc} and {pdesc}.",
   "Give the {cdesc} and {pdesc} of {cnoun}s with {ncol} {opw} {nval}."],
  variants=[
   dict(child="invoices", parent="appointments", fk="appointment_id",
        pk="appointment_id", csel="total_amount", psel="appointment_date",
        ncol="total_amount", op=">", opw="greater than", nval=400,
        cnoun="invoice", cdesc="total amount", pdesc="appointment date"),
   dict(child="order_items", parent="products", fk="product_id",
        pk="product_id", csel="quantity", psel="product_name",
        ncol="quantity", op=">=", opw="at least", nval=4,
        cnoun="order item", cdesc="quantity", pdesc="product name"),
   dict(child="appointments", parent="doctors", fk="doctor_id",
        pk="doctor_id", csel="appointment_date", psel="doctor_name",
        ncol="base_fee", op=">", opw="above", nval=150,
        cnoun="appointment", cdesc="date", pdesc="doctor name"),
   dict(child="lab_results", parent="appointments", fk="appointment_id",
        pk="appointment_id", csel="test_value", psel="appointment_date",
        ncol="test_value", op="<", opw="below", nval=60,
        cnoun="lab result", cdesc="test value", pdesc="appointment date"),
  ]),
T("j46_anti_join", "join", DB, "hard", "multiset_rows",
  ["two_table_join", "null_handling"],
  "SELECT p.{psel} FROM {parent} p LEFT JOIN {child} c "
  "ON c.{fk} = p.{pk} WHERE c.{fk} IS NULL",
  ["List the {pdesc} of every {pnoun} that has no {cnoun} at all.",
   "Which {pnoun}s never appear in {child}? Show the {pdesc}.",
   "Show {pdesc}s for {pnoun}s without any matching {cnoun}.",
   "Find {pnoun}s with zero {cnoun}s and list their {pdesc}."],
  variants=[
   dict(parent="customers", child="orders", fk="customer_id",
        pk="customer_id", psel="customer_name", pnoun="customer",
        pdesc="customer name", cnoun="order"),
   dict(parent="medications", child="prescriptions", fk="medication_id",
        pk="medication_id", psel="medication_name", pnoun="medication",
        pdesc="medication name", cnoun="prescription"),
   dict(parent="products", child="order_items", fk="product_id",
        pk="product_id", psel="product_name", pnoun="product",
        pdesc="product name", cnoun="order item"),
  ]),
T("j46_self_join", "join", DB, "hard", "set_rows",
  ["two_table_join", "multiple_conditions"],
  "SELECT DISTINCT a.{name1} AS left_{col}, b.{name1} AS right_{col} "
  "FROM {tbl} a JOIN {tbl} b ON a.{key} = b.{key} "
  "AND a.{idc} < b.{idc}",
  ["List every pair of {noun}s that share the same {key}.",
   "Which two {noun}s have an identical {key}? Show both names in each pair.",
   "Find all distinct pairs of {noun}s with matching {key} values.",
   "Show pairs of different {noun}s whose {key} is the same."],
  variants=[
   dict(tbl="doctors", key="specialty", idc="doctor_id",
        name1="doctor_name", col="doctor", noun="doctor"),
   dict(tbl="patients", key="city", idc="patient_id",
        name1="patient_name", col="patient", noun="patient"),
   dict(tbl="products", key="category", idc="product_id",
        name1="product_name", col="product", noun="product"),
  ]),
)

# =====================================================================
# 2. multi_table_join  (E6 / M8 / H6)
# =====================================================================
add(
T("m46_three_chain", "multi_table_join", DB, "easy", "multiset_rows",
  ["three_plus_table_join"],
  "SELECT p.{psel}, d.{dsel} FROM appointments a "
  "JOIN {pt} p ON a.{pfk} = p.{ppk} JOIN {dt} d ON a.{dfk} = d.{dpk} "
  "WHERE a.{fcol} = '{fval}'",
  ["For appointments with {fcol} '{fval}', list the {pdesc} and the {ddesc}.",
   "Show the {pdesc} together with the {ddesc} for every appointment whose "
   "{fcol} is '{fval}'.",
   "Which {pdesc} and {ddesc} pairs appear on '{fval}' {fcol} appointments?",
   "List {pdesc} and {ddesc} for each appointment where {fcol} = '{fval}'."],
  variants=[
   dict(pt="patients", dt="doctors", pfk="patient_id", ppk="patient_id",
        dfk="doctor_id", dpk="doctor_id", psel="patient_name",
        dsel="doctor_name", fcol="status", fval="completed",
        pdesc="patient name", ddesc="doctor name"),
   dict(pt="patients", dt="doctors", pfk="patient_id", ppk="patient_id",
        dfk="doctor_id", dpk="doctor_id", psel="patient_name",
        dsel="specialty", fcol="visit_type", fval="screening",
        pdesc="patient name", ddesc="doctor's specialty"),
   dict(pt="patients", dt="doctors", pfk="patient_id", ppk="patient_id",
        dfk="doctor_id", dpk="doctor_id", psel="city",
        dsel="doctor_name", fcol="status", fval="no_show",
        pdesc="patient's city", ddesc="doctor name"),
  ]),
T("m46_invoice_chain", "multi_table_join", DB, "easy", "multiset_rows",
  ["three_plus_table_join"],
  "SELECT p.patient_name, i.{isel} FROM invoices i "
  "JOIN appointments a ON i.appointment_id = a.appointment_id "
  "JOIN patients p ON a.patient_id = p.patient_id "
  "WHERE {ftab}.{fcol} = '{fval}'",
  ["List each patient name with the invoice {idesc} where {fcol} is '{fval}'.",
   "Show patient names and invoice {idesc}s for {fcol} '{fval}'.",
   "Which patients have invoices with {fcol} '{fval}'? Include the {idesc}.",
   "For invoices whose {fcol} equals '{fval}', show the patient and {idesc}."],
  variants=[
   dict(isel="total_amount", ftab="i", fcol="payment_status", fval="unpaid",
        idesc="total amount"),
   dict(isel="invoice_date", ftab="i", fcol="payment_status", fval="partial",
        idesc="invoice date"),
   dict(isel="total_amount", ftab="p", fcol="insurance_provider",
        fval="Aetna", idesc="total amount"),
  ]),
T("m46_four_chain", "multi_table_join", DB, "medium", "multiset_rows",
  ["three_plus_table_join", "multiple_conditions"],
  "SELECT c.customer_name, pr.product_name, oi.quantity "
  "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id "
  "JOIN customers c ON o.customer_id = c.customer_id "
  "JOIN products pr ON oi.product_id = pr.product_id "
  "WHERE pr.category = '{cat}' AND o.order_status = '{ost}'",
  ["Show customer names, product names, and quantities for '{cat}' products "
   "on '{ost}' orders.",
   "For '{ost}' orders containing '{cat}' products, list the customer, "
   "product, and quantity.",
   "Which customers bought '{cat}' items on orders with status '{ost}'? "
   "Include product name and quantity.",
   "List every ({cat}) line item on {ost} orders with customer name, "
   "product name, and quantity."],
  variants=[
   dict(cat="electronics", ost="delivered"),
   dict(cat="furniture", ost="shipped"),
   dict(cat="stationery", ost="placed"),
   dict(cat="home", ost="delivered"),
  ]),
T("m46_rx_chain", "multi_table_join", DB, "medium", "multiset_rows",
  ["three_plus_table_join", "multiple_conditions"],
  "SELECT p.patient_name, m.medication_name, pr.days_supply "
  "FROM prescriptions pr "
  "JOIN appointments a ON pr.appointment_id = a.appointment_id "
  "JOIN patients p ON a.patient_id = p.patient_id "
  "JOIN medications m ON pr.medication_id = m.medication_id "
  "WHERE m.medication_class = '{mcls}' AND pr.days_supply {op} {n}",
  ["List patients prescribed {mcls} medications with a days supply {opw} "
   "{n}, including the medication name and days supply.",
   "Which patients received {mcls} prescriptions for {opw} {n} days? Show "
   "medication and days supply.",
   "Show patient, medication, and days supply for {mcls} prescriptions "
   "where days supply is {opw} {n}.",
   "For {mcls}-class medications with days supply {opw} {n}, list patient "
   "name, medication name, and days supply."],
  variants=[
   dict(mcls="antibiotic", op=">", n=10, opw="more than"),
   dict(mcls="painkiller", op=">=", n=14, opw="at least"),
   dict(mcls="statin", op=">", n=20, opw="more than"),
   dict(mcls="inhaler", op="<", n=30, opw="under"),
  ]),
T("m46_lab_doctor", "multi_table_join", DB, "hard", "multiset_rows",
  ["three_plus_table_join", "multiple_conditions"],
  "SELECT p.patient_name, d.doctor_name, l.test_name, l.test_value "
  "FROM lab_results l "
  "JOIN appointments a ON l.appointment_id = a.appointment_id "
  "JOIN patients p ON a.patient_id = p.patient_id "
  "JOIN doctors d ON a.doctor_id = d.doctor_id "
  "WHERE l.result_flag = '{flag}' AND d.specialty = '{spec}'",
  ["For '{flag}' lab results ordered by {spec} doctors, list patient, "
   "doctor, test name, and value.",
   "Which patients have '{flag}' {spec}-ordered lab results? Include "
   "doctor, test, and value.",
   "Show patient name, doctor name, test name, and test value where the "
   "result flag is '{flag}' and the doctor's specialty is {spec}.",
   "List '{flag}' results from {spec} doctors with patient, doctor, test, "
   "and value."],
  variants=[
   dict(flag="critical", spec="cardiology"),
   dict(flag="high", spec="primary"),
   dict(flag="low", spec="pediatrics"),
  ]),
T("m46_five_chain", "multi_table_join", DB, "hard", "multiset_rows",
  ["three_plus_table_join", "range_filter"],
  "SELECT c.customer_name, c.loyalty_level, pr.product_name, "
  "oi.quantity * pr.unit_price AS line_value "
  "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id "
  "JOIN customers c ON o.customer_id = c.customer_id "
  "JOIN products pr ON oi.product_id = pr.product_id "
  "WHERE c.loyalty_level = '{lvl}' AND oi.quantity * pr.unit_price > {v}",
  ["For {lvl} customers, list line items worth more than {v} (quantity "
   "times unit price), with customer, loyalty level, product, and value.",
   "Which order lines of {lvl}-loyalty customers exceed {v} in value? Show "
   "customer, level, product, and line value.",
   "Show {lvl} customers' order lines whose quantity times unit price is "
   "above {v}.",
   "List customer, loyalty level, product, and line value for {lvl} "
   "customers where the line value exceeds {v}."],
  variants=[
   dict(lvl="gold", v=500),
   dict(lvl="platinum", v=300),
   dict(lvl="silver", v=800),
  ]),
)

# =====================================================================
# 3. group_by  (E6 / M8 / H6)
# =====================================================================
add(
T("g46_count_per", "group_by", DB, "easy", "multiset_rows", [],
  "SELECT {gcol}, COUNT(*) FROM {tbl} GROUP BY {gcol}",
  ["How many {noun}s are there per {gdesc}?",
   "Count the {noun}s in each {gdesc}.",
   "For each {gdesc}, how many {noun}s exist?",
   "Show every {gdesc} with its number of {noun}s."],
  variants=[
   dict(tbl="appointments", gcol="status", gdesc="status",
        noun="appointment"),
   dict(tbl="patients", gcol="insurance_provider",
        gdesc="insurance provider", noun="patient"),
   dict(tbl="products", gcol="category", gdesc="product category",
        noun="product"),
   dict(tbl="orders", gcol="order_status", gdesc="order status",
        noun="order"),
   dict(tbl="doctors", gcol="specialty", gdesc="specialty", noun="doctor"),
   dict(tbl="medications", gcol="medication_class",
        gdesc="medication class", noun="medication"),
  ]),
T("g46_sum_join", "group_by", DB, "medium", "multiset_rows",
  ["two_table_join"],
  "SELECT {gexp}, {agg} FROM {frm} GROUP BY {gexp}",
  ["For each {gdesc}, what is the {adesc}?",
   "Show the {adesc} per {gdesc}.",
   "Group by {gdesc} and report the {adesc}.",
   "What is the {adesc} for every {gdesc}?"],
  variants=[
   dict(gexp="c.city", agg="SUM(o.order_id * 0) + COUNT(o.order_id)",
        frm="orders o JOIN customers c ON o.customer_id = c.customer_id",
        gdesc="customer city", adesc="number of orders"),
   dict(gexp="a.visit_type", agg="AVG(a.base_fee)",
        frm="appointments a", gdesc="visit type",
        adesc="average base fee"),
   dict(gexp="i.payment_status", agg="SUM(i.total_amount)",
        frm="invoices i", gdesc="payment status",
        adesc="total invoiced amount"),
   dict(gexp="l.test_name", agg="AVG(l.test_value)",
        frm="lab_results l", gdesc="lab test",
        adesc="average test value"),
   dict(gexp="p.insurance_provider", agg="SUM(i.total_amount)",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id JOIN patients p ON a.patient_id = "
            "p.patient_id",
        gdesc="insurance provider", adesc="total invoiced amount"),
   dict(gexp="pr.category", agg="SUM(oi.quantity)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        gdesc="product category", adesc="total quantity sold"),
   dict(gexp="m.medication_class", agg="AVG(pr.days_supply)",
        frm="prescriptions pr JOIN medications m ON pr.medication_id = "
            "m.medication_id",
        gdesc="medication class", adesc="average days supply"),
   dict(gexp="o.shipping_city", agg="COUNT(*)",
        frm="orders o", gdesc="shipping city", adesc="number of orders"),
  ]),
T("g46_two_keys", "group_by", DB, "hard", "multiset_rows",
  ["two_table_join", "multiple_conditions"],
  "SELECT {g1}, {g2}, {agg} FROM {frm} GROUP BY {g1}, {g2}",
  ["Break down the {adesc} by {g1d} and {g2d}.",
   "For each combination of {g1d} and {g2d}, report the {adesc}.",
   "What is the {adesc} per {g1d} per {g2d}?",
   "Show {g1d}, {g2d}, and the {adesc} for each pair."],
  variants=[
   dict(g1="d.specialty", g2="a.status", agg="COUNT(*)",
        frm="appointments a JOIN doctors d ON a.doctor_id = d.doctor_id",
        g1d="doctor specialty", g2d="appointment status",
        adesc="number of appointments"),
   dict(g1="c.loyalty_level", g2="pr.category", agg="SUM(oi.quantity)",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id "
            "JOIN customers c ON o.customer_id = c.customer_id "
            "JOIN products pr ON oi.product_id = pr.product_id",
        g1d="loyalty level", g2d="product category",
        adesc="total quantity purchased"),
   dict(g1="p.insurance_provider", g2="i.payment_status",
        agg="SUM(i.total_amount)",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id JOIN patients p ON a.patient_id = "
            "p.patient_id",
        g1d="insurance provider", g2d="payment status",
        adesc="total invoiced amount"),
   dict(g1="l.test_name", g2="l.result_flag", agg="COUNT(*)",
        frm="lab_results l", g1d="test name", g2d="result flag",
        adesc="number of results"),
  ]),
T("g46_month", "group_by", DB, "hard", "multiset_rows",
  ["temporal"],
  "SELECT substr({dcol}, 1, 7) AS month, {agg} FROM {tbl} "
  "GROUP BY substr({dcol}, 1, 7)",
  ["Per month, what is the {adesc}?",
   "Show the {adesc} for each month.",
   "Break the {adesc} down by month.",
   "For every month, report the {adesc}."],
  variants=[
   dict(dcol="appointment_date", tbl="appointments", agg="COUNT(*)",
        adesc="number of appointments"),
   dict(dcol="invoice_date", tbl="invoices", agg="SUM(total_amount)",
        adesc="total invoiced amount"),
  ]),
)

# =====================================================================
# 4. having  (E6 / M8 / H6)
# =====================================================================
add(
T("h46_count_gt", "having", DB, "easy", "multiset_rows", [],
  "SELECT {gcol}, COUNT(*) FROM {tbl} GROUP BY {gcol} "
  "HAVING COUNT(*) > {n}",
  ["Which {gdesc}s have more than {n} {noun}s? Show the count.",
   "List {gdesc}s with over {n} {noun}s and their counts.",
   "Find every {gdesc} having more than {n} {noun}s.",
   "Show {gdesc}s where the number of {noun}s exceeds {n}."],
  variants=[
   dict(tbl="appointments", gcol="doctor_id", gdesc="doctor id", n=8,
        noun="appointment"),
   dict(tbl="orders", gcol="customer_id", gdesc="customer id", n=2,
        noun="order"),
   dict(tbl="lab_results", gcol="test_name", gdesc="test name", n=25,
        noun="result"),
   dict(tbl="prescriptions", gcol="medication_id", gdesc="medication id",
        n=4, noun="prescription"),
   dict(tbl="appointments", gcol="patient_id", gdesc="patient id", n=2,
        noun="appointment"),
   dict(tbl="order_items", gcol="order_id", gdesc="order id", n=2,
        noun="line item"),
  ]),
T("h46_sum_threshold", "having", DB, "medium", "multiset_rows",
  ["two_table_join"],
  "SELECT {gexp}, {agg} AS agg_value FROM {frm} "
  "GROUP BY {gexp} HAVING {agg} {op} {n}",
  ["Which {gdesc}s have a {adesc} {opw} {n}? Include the value.",
   "List every {gdesc} whose {adesc} is {opw} {n}.",
   "Show {gdesc}s where the {adesc} {opw} {n}.",
   "Find {gdesc}s with {adesc} {opw} {n} and report it."],
  variants=[
   dict(gexp="p.patient_id", agg="SUM(i.total_amount)",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id JOIN patients p ON a.patient_id = "
            "p.patient_id",
        gdesc="patient", adesc="total invoiced amount", op=">",
        opw="above", n=1500),
   dict(gexp="c.customer_id", agg="SUM(oi.quantity * pr.unit_price)",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id "
            "JOIN customers c ON o.customer_id = c.customer_id "
            "JOIN products pr ON oi.product_id = pr.product_id",
        gdesc="customer", adesc="total purchase value", op=">",
        opw="over", n=2000),
   dict(gexp="d.doctor_id", agg="AVG(a.base_fee)",
        frm="appointments a JOIN doctors d ON a.doctor_id = d.doctor_id",
        gdesc="doctor", adesc="average base fee", op=">",
        opw="greater than", n=130),
   dict(gexp="l.test_name", agg="AVG(l.test_value)",
        frm="lab_results l", gdesc="lab test", adesc="average value",
        op=">", opw="above", n=100),
   dict(gexp="pr.category", agg="SUM(oi.quantity)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        gdesc="product category", adesc="total quantity sold", op=">",
        opw="more than", n=150),
   dict(gexp="m.medication_class", agg="SUM(p2.days_supply)",
        frm="prescriptions p2 JOIN medications m ON p2.medication_id = "
            "m.medication_id",
        gdesc="medication class", adesc="total days supply", op=">",
        opw="over", n=300),
   dict(gexp="o.shipping_city", agg="COUNT(*)",
        frm="orders o", gdesc="shipping city", adesc="order count",
        op=">=", opw="at least", n=15),
   dict(gexp="p.city", agg="COUNT(*)",
        frm="patients p", gdesc="patient city", adesc="patient count",
        op=">=", opw="at least", n=15),
  ]),
T("h46_filtered_having", "having", DB, "hard", "multiset_rows",
  ["two_table_join", "multiple_conditions"],
  "SELECT {gexp}, COUNT(*) FROM {frm} WHERE {wcol} = '{wval}' "
  "GROUP BY {gexp} HAVING COUNT(*) {op} {n}",
  ["Counting only '{wval}' {wnoun}s, which {gdesc}s have {opw} {n}?",
   "Which {gdesc}s have {opw} {n} {wnoun}s with {wcol} '{wval}'?",
   "Restrict to {wcol} '{wval}': list {gdesc}s with {opw} {n} {wnoun}s.",
   "Among '{wval}' {wnoun}s only, find {gdesc}s having {opw} {n}."],
  variants=[
   dict(gexp="a.doctor_id", frm="appointments a", wcol="a.status",
        wval="completed", gdesc="doctor id", op=">=", opw="at least", n=5,
        wnoun="appointment"),
   dict(gexp="a.patient_id", frm="appointments a", wcol="a.status",
        wval="cancelled", gdesc="patient id", op=">=", opw="at least",
        n=1, wnoun="appointment"),
   dict(gexp="o.customer_id", frm="orders o", wcol="o.order_status",
        wval="delivered", gdesc="customer id", op=">=", opw="at least",
        n=2, wnoun="order"),
   dict(gexp="l.appointment_id", frm="lab_results l",
        wcol="l.result_flag", wval="normal", gdesc="appointment id",
        op=">=", opw="at least", n=2, wnoun="lab result"),
  ]),
T("h46_two_aggs", "having", DB, "hard", "multiset_rows",
  ["nested_aggregation", "multiple_conditions"],
  "SELECT {gexp}, COUNT(*), {agg2} FROM {frm} GROUP BY {gexp} "
  "HAVING COUNT(*) > {n1} AND {agg2} > {n2}",
  ["Which {gdesc}s have more than {n1} {noun}s and a {a2desc} above {n2}?",
   "List {gdesc}s with over {n1} {noun}s whose {a2desc} also exceeds {n2}.",
   "Find {gdesc}s meeting both: {noun} count > {n1} and {a2desc} > {n2}.",
   "Show {gdesc}s having {n1}+ {noun}s and {a2desc} over {n2} (exclusive)."],
  variants=[
   dict(gexp="i.payment_status", agg2="SUM(i.total_amount)",
        frm="invoices i", gdesc="payment status", noun="invoice",
        n1=20, n2=8000, a2desc="total amount"),
   dict(gexp="a.visit_type", agg2="AVG(a.base_fee)",
        frm="appointments a", gdesc="visit type", noun="appointment",
        n1=20, n2=100, a2desc="average base fee"),
  ]),
)

# =====================================================================
# 5. subquery_cte  (E6 / M8 / H6)
# =====================================================================
add(
T("s46_above_avg", "subquery_cte", DB, "easy", "multiset_rows",
  ["population_comparison"],
  "SELECT {sel} FROM {tbl} WHERE {col} > (SELECT AVG({col}) FROM {tbl})",
  ["Which {noun}s have a {cdesc} above the overall average? Show {seld}.",
   "List {seld} for {noun}s whose {cdesc} exceeds the average {cdesc}.",
   "Find {noun}s with {cdesc} greater than the average across all "
   "{noun}s.",
   "Show {seld} of {noun}s with an above-average {cdesc}."],
  variants=[
   dict(tbl="products", col="unit_price", sel="product_name",
        seld="the product name", noun="product", cdesc="unit price"),
   dict(tbl="invoices", col="total_amount", sel="invoice_id",
        seld="the invoice id", noun="invoice", cdesc="total amount"),
   dict(tbl="appointments", col="base_fee", sel="appointment_id",
        seld="the appointment id", noun="appointment", cdesc="base fee"),
   dict(tbl="doctors", col="years_experience", sel="doctor_name",
        seld="the doctor name", noun="doctor",
        cdesc="years of experience"),
   dict(tbl="lab_results", col="test_value", sel="lab_id",
        seld="the lab id", noun="lab result", cdesc="test value"),
   dict(tbl="medications", col="unit_cost", sel="medication_name",
        seld="the medication name", noun="medication", cdesc="unit cost"),
  ]),
T("s46_correlated", "subquery_cte", DB, "medium", "multiset_rows",
  ["correlated_subquery", "population_comparison"],
  "SELECT t.{sel} FROM {tbl} t WHERE t.{col} > "
  "(SELECT AVG(t2.{col}) FROM {tbl} t2 WHERE t2.{grp} = t.{grp})",
  ["Which {noun}s have a {cdesc} above the average for the same {gdesc}?",
   "List {noun}s whose {cdesc} beats the average of their own {gdesc}.",
   "Find {noun}s with {cdesc} above their {gdesc}'s average.",
   "Show {noun}s exceeding the average {cdesc} within their {gdesc}."],
  variants=[
   dict(tbl="products", col="unit_price", grp="category",
        sel="product_name", noun="product", cdesc="unit price",
        gdesc="category"),
   dict(tbl="lab_results", col="test_value", grp="test_name",
        sel="lab_id", noun="lab result", cdesc="test value",
        gdesc="test"),
   dict(tbl="doctors", col="years_experience", grp="specialty",
        sel="doctor_name", noun="doctor", cdesc="experience",
        gdesc="specialty"),
   dict(tbl="appointments", col="base_fee", grp="visit_type",
        sel="appointment_id", noun="appointment", cdesc="base fee",
        gdesc="visit type"),
  ]),
T("s46_in_subquery", "subquery_cte", DB, "medium", "multiset_rows", [],
  "SELECT {sel} FROM {tbl} WHERE {key} IN "
  "(SELECT {fkey} FROM {sub} WHERE {scol} = '{sval}')",
  ["List the {seld} of {noun}s that have at least one {snoun} with {scol} "
   "'{sval}'.",
   "Which {noun}s are linked to a '{sval}' {snoun}? Show the {seld}.",
   "Show {seld}s for {noun}s having any {snoun} whose {scol} is '{sval}'.",
   "Find {noun}s with a {snoun} where {scol} = '{sval}'."],
  variants=[
   dict(tbl="patients", key="patient_id", sel="patient_name",
        sub="appointments", fkey="patient_id", scol="status",
        sval="no_show", seld="patient name", noun="patient",
        snoun="appointment"),
   dict(tbl="customers", key="customer_id", sel="customer_name",
        sub="orders", fkey="customer_id", scol="order_status",
        sval="cancelled", seld="customer name", noun="customer",
        snoun="order"),
   dict(tbl="doctors", key="doctor_id", sel="doctor_name",
        sub="appointments", fkey="doctor_id", scol="visit_type",
        sval="urgent", seld="doctor name", noun="doctor",
        snoun="appointment"),
   dict(tbl="products", key="product_id", sel="product_name",
        sub="order_items", fkey="product_id", scol="discount_percent",
        sval="0", seld="product name", noun="product",
        snoun="order line"),
  ]),
T("s46_cte_two_level", "subquery_cte", DB, "hard", "multiset_rows",
  ["nested_aggregation", "population_comparison", "derived_measure"],
  "WITH totals AS (SELECT {ent} AS ek, SUM({mcol}) AS total FROM {frm} "
  "GROUP BY {ent}) SELECT ek, total FROM totals "
  "WHERE total > (SELECT AVG(total) FROM totals)",
  ["Which {edesc}s have a total {mdesc} above the average total per "
   "{edesc}?",
   "First total the {mdesc} per {edesc}; list {edesc}s above the average "
   "of those totals.",
   "Find {edesc}s whose overall {mdesc} exceeds the average {edesc} "
   "total.",
   "Show each {edesc} and its total where the total {mdesc} is above the "
   "cross-{edesc} average."],
  variants=[
   dict(ent="a.patient_id", mcol="i.total_amount",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id",
        edesc="patient", mdesc="invoiced amount"),
   dict(ent="o.customer_id", mcol="oi.quantity * pr.unit_price",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id "
            "JOIN products pr ON oi.product_id = pr.product_id",
        edesc="customer", mdesc="purchase value"),
   dict(ent="a.doctor_id", mcol="i.total_amount",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id",
        edesc="doctor", mdesc="billed amount"),
  ]),
T("s46_not_exists", "subquery_cte", DB, "hard", "multiset_rows",
  ["correlated_subquery", "null_handling"],
  "SELECT p.{sel} FROM {tbl} p WHERE NOT EXISTS "
  "(SELECT 1 FROM {sub} s WHERE s.{fk} = p.{pk} AND s.{scol} = '{sval}')",
  ["Which {noun}s have no {snoun} with {scol} '{sval}'? Show {seld}.",
   "List {noun}s that never had a '{sval}' {snoun}.",
   "Find every {noun} without any {snoun} whose {scol} is '{sval}'.",
   "Show the {seld} of {noun}s lacking '{sval}' {snoun}s."],
  variants=[
   dict(tbl="patients", pk="patient_id", sel="patient_name",
        sub="appointments", fk="patient_id", scol="status",
        sval="cancelled", seld="patient name", noun="patient",
        snoun="appointment"),
   dict(tbl="customers", pk="customer_id", sel="customer_name",
        sub="orders", fk="customer_id", scol="order_status",
        sval="cancelled", seld="customer name", noun="customer",
        snoun="order"),
   dict(tbl="doctors", pk="doctor_id", sel="doctor_name",
        sub="appointments", fk="doctor_id", scol="status",
        sval="no_show", seld="doctor name", noun="doctor",
        snoun="appointment"),
  ]),
)

# =====================================================================
# 6. set_operations  (E6 / M8 / H6)
# =====================================================================
add(
T("o46_union_cities", "set_operations", DB, "easy", "set_rows", [],
  "SELECT {c1} FROM {t1} {setop} SELECT {c2} FROM {t2}",
  ["Give the {setw} of {d1} and {d2}.",
   "Combine {d1} with {d2} using {setw}; list the result.",
   "What is the {setw} of the {d1} and the {d2}?",
   "List values in the {setw} of {d1} and {d2}."],
  variants=[
   dict(c1="city", t1="patients", c2="city", t2="customers",
        setop="UNION", setw="union", d1="patient cities",
        d2="customer cities"),
   dict(c1="city", t1="patients", c2="clinic_city", t2="doctors",
        setop="INTERSECT", setw="intersection", d1="patient cities",
        d2="doctor clinic cities"),
   dict(c1="shipping_city", t1="orders", c2="city", t2="patients",
        setop="EXCEPT", setw="difference (first minus second)",
        d1="order shipping cities", d2="patient cities"),
   dict(c1="city", t1="customers", c2="city", t2="patients",
        setop="INTERSECT", setw="intersection", d1="customer cities",
        d2="patient cities"),
   dict(c1="shipping_city", t1="orders", c2="clinic_city", t2="doctors",
        setop="UNION", setw="union", d1="order shipping cities",
        d2="doctor clinic cities"),
   dict(c1="clinic_city", t1="doctors", c2="city", t2="patients",
        setop="EXCEPT", setw="difference (first minus second)",
        d1="doctor clinic cities", d2="patient cities",
        _tags=["controlled_empty_result"]),
  ]),
T("o46_cond_sets", "set_operations", DB, "medium", "set_rows",
  ["two_table_join", "multiple_conditions"],
  "SELECT {k1} FROM {f1} WHERE {w1} {setop} SELECT {k2} FROM {f2} "
  "WHERE {w2}",
  ["{setw2} the ids of {d1} and the ids of {d2}.",
   "Using {setop}, compare {d1} against {d2} and list the ids.",
   "Which ids result from {d1} {setw} {d2}?",
   "List ids from the {setw} of ({d1}) and ({d2})."],
  variants=[
   dict(k1="patient_id", f1="appointments", w1="status = 'completed'",
        k2="patient_id", f2="appointments", w2="status = 'cancelled'",
        setop="INTERSECT", setw="intersected with",
        setw2="Intersect", d1="patients with completed appointments",
        d2="patients with cancelled appointments"),
   dict(k1="patient_id", f1="appointments", w1="status = 'completed'",
        k2="patient_id", f2="appointments", w2="status = 'no_show'",
        setop="EXCEPT", setw="minus", setw2="Subtract",
        d1="patients with completed appointments",
        d2="patients who ever no-showed"),
   dict(k1="customer_id", f1="orders", w1="order_status = 'delivered'",
        k2="customer_id", f2="orders", w2="order_status = 'cancelled'",
        setop="INTERSECT", setw="intersected with", setw2="Intersect",
        d1="customers with delivered orders",
        d2="customers with cancelled orders"),
   dict(k1="customer_id", f1="orders", w1="order_status = 'placed'",
        k2="customer_id", f2="orders", w2="order_status = 'shipped'",
        setop="UNION", setw="unioned with", setw2="Union",
        d1="customers with placed orders",
        d2="customers with shipped orders"),
   dict(k1="a.doctor_id", f1="appointments a", w1="a.visit_type = 'urgent'",
        k2="a2.doctor_id", f2="appointments a2",
        w2="a2.visit_type = 'screening'", setop="INTERSECT",
        setw="intersected with", setw2="Intersect",
        d1="doctors with urgent visits",
        d2="doctors with screening visits"),
   dict(k1="appointment_id", f1="invoices", w1="payment_status = 'unpaid'",
        k2="appointment_id", f2="lab_results",
        w2="result_flag = 'critical'", setop="INTERSECT",
        setw="intersected with", setw2="Intersect",
        d1="appointments with unpaid invoices",
        d2="appointments with critical lab results"),
   dict(k1="product_id", f1="order_items", w1="discount_percent > 0",
        k2="product_id", f2="order_items", w2="quantity >= 4",
        setop="EXCEPT", setw="minus", setw2="Subtract",
        d1="products ever discounted", d2="products bought 4+ at once"),
   dict(k1="patient_id", f1="patients", w1="chronic_condition = 'yes'",
        k2="a.patient_id", f2="appointments a",
        w2="a.visit_type = 'checkup'", setop="EXCEPT", setw="minus",
        setw2="Subtract", d1="chronic patients",
        d2="patients with checkup visits"),
  ]),
T("o46_three_way", "set_operations", DB, "hard", "set_rows",
  ["multiple_conditions"],
  "SELECT {k} FROM {f1} WHERE {w1} {op1} SELECT {k} FROM {f2} WHERE {w2} "
  "{op2} SELECT {k} FROM {f3} WHERE {w3}",
  ["Take {d1}, {op1w} {d2}, then {op2w} {d3}; list the resulting ids.",
   "Starting from {d1}, apply {op1} with {d2} and {op2} with {d3}.",
   "Which ids remain after combining {d1} {op1w} {d2} {op2w} {d3}?",
   "Chain the sets: {d1}, {op1} {d2}, {op2} {d3}. List the ids."],
  variants=[
   dict(k="patient_id", f1="appointments", w1="status = 'completed'",
        f2="appointments", w2="visit_type = 'checkup'",
        f3="appointments", w3="status = 'no_show'",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect with",
        op2w="minus",
        d1="patients with completed appointments",
        d2="patients with checkup visits",
        d3="patients who ever no-showed"),
   dict(k="customer_id", f1="orders", w1="order_status = 'delivered'",
        f2="orders", w2="order_status = 'shipped'",
        f3="orders", w3="order_status = 'cancelled'",
        op1="UNION", op2="EXCEPT", op1w="union with", op2w="minus",
        d1="customers with delivered orders",
        d2="customers with shipped orders",
        d3="customers with cancelled orders"),
   dict(k="appointment_id", f1="invoices", w1="payment_status = 'paid'",
        f2="lab_results", w2="result_flag = 'normal'",
        f3="invoices", w3="total_amount > 400",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect with",
        op2w="minus",
        d1="appointments with paid invoices",
        d2="appointments with normal lab results",
        d3="appointments billed above 400"),
   dict(k="doctor_id", f1="doctors", w1="specialty = 'cardiology'",
        f2="doctors", w2="years_experience > 10",
        f3="doctors", w3="clinic_city = 'Boise'",
        op1="UNION", op2="EXCEPT", op1w="union with", op2w="minus",
        d1="cardiologists", d2="doctors with 10+ years experience",
        d3="Boise-based doctors"),
   dict(k="product_id", f1="products", w1="category = 'electronics'",
        f2="order_items", w2="quantity >= 5",
        f3="order_items", w3="discount_percent > 10",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect with",
        op2w="minus",
        d1="electronics products", d2="products bought 5+ at once",
        d3="products discounted above 10 percent"),
   dict(k="patient_id", f1="patients", w1="state = 'ID'",
        f2="patients", w2="chronic_condition = 'yes'",
        f3="patients", w3="insurance_provider = 'None'",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect with",
        op2w="minus",
        d1="Idaho patients", d2="chronic patients",
        d3="uninsured patients"),
  ]),
)

# =====================================================================
# 7. order_limit_topk  (E6 / M8 / H6)
# =====================================================================
add(
T("t46_topk_col", "order_limit_topk", DB, "easy", "ordered_rows", [],
  "SELECT {sel}, {col} FROM {tbl} ORDER BY {col} {dirn}, {tie} {dirn} "
  "LIMIT {k}",
  ["What are the top {k} {noun}s by {cdesc}? Show {seld} and {cdesc}.",
   "List the {k} {supw} {noun}s by {cdesc} with ties broken by {tie}.",
   "Show the {k} {noun}s with the {supw} {cdesc}.",
   "Rank {noun}s by {cdesc} ({dirw}) and return the first {k}."],
  variants=[
   dict(tbl="products", sel="product_name", col="unit_price",
        tie="product_id", dirn="DESC", k=5, noun="product",
        seld="the name", cdesc="unit price", supw="most expensive",
        dirw="highest first"),
   dict(tbl="doctors", sel="doctor_name", col="years_experience",
        tie="doctor_id", dirn="DESC", k=3, noun="doctor",
        seld="the name", cdesc="years of experience",
        supw="most experienced", dirw="highest first"),
   dict(tbl="invoices", sel="invoice_id", col="total_amount",
        tie="invoice_id", dirn="DESC", k=10, noun="invoice",
        seld="the id", cdesc="total amount", supw="largest",
        dirw="highest first"),
   dict(tbl="medications", sel="medication_name", col="unit_cost",
        tie="medication_id", dirn="ASC", k=5, noun="medication",
        seld="the name", cdesc="unit cost", supw="cheapest",
        dirw="lowest first"),
   dict(tbl="lab_results", sel="lab_id", col="test_value",
        tie="lab_id", dirn="DESC", k=8, noun="lab result",
        seld="the id", cdesc="test value", supw="highest",
        dirw="highest first"),
   dict(tbl="appointments", sel="appointment_id", col="base_fee",
        tie="appointment_id", dirn="DESC", k=7, noun="appointment",
        seld="the id", cdesc="base fee", supw="priciest",
        dirw="highest first"),
  ]),
T("t46_topk_agg", "order_limit_topk", DB, "medium", "ordered_rows",
  ["two_table_join", "nested_aggregation"],
  "SELECT {gexp} AS grp, {agg} AS agg_value FROM {frm} GROUP BY {gexp} "
  "ORDER BY agg_value DESC, grp ASC LIMIT {k}",
  ["Which {k} {gdesc}s have the highest {adesc}? Show both.",
   "Rank {gdesc}s by {adesc} and give the top {k}.",
   "List the top {k} {gdesc}s by {adesc}, ties broken alphabetically.",
   "Find the {k} {gdesc}s with the greatest {adesc}."],
  variants=[
   dict(gexp="p.patient_name", agg="SUM(i.total_amount)",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id JOIN patients p ON a.patient_id = "
            "p.patient_id",
        gdesc="patient", adesc="total invoiced amount", k=5),
   dict(gexp="c.customer_name", agg="SUM(oi.quantity * pr.unit_price)",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id "
            "JOIN customers c ON o.customer_id = c.customer_id "
            "JOIN products pr ON oi.product_id = pr.product_id",
        gdesc="customer", adesc="total spend", k=5),
   dict(gexp="d.doctor_name", agg="COUNT(*)",
        frm="appointments a JOIN doctors d ON a.doctor_id = d.doctor_id",
        gdesc="doctor", adesc="appointment count", k=3),
   dict(gexp="pr.product_name", agg="SUM(oi.quantity)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        gdesc="product", adesc="units sold", k=10),
   dict(gexp="pr.category", agg="SUM(oi.quantity * pr.unit_price)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        gdesc="product category", adesc="revenue", k=2),
   dict(gexp="l.test_name", agg="AVG(l.test_value)",
        frm="lab_results l", gdesc="lab test", adesc="average value",
        k=2),
   dict(gexp="o.shipping_city", agg="COUNT(*)",
        frm="orders o", gdesc="shipping city", adesc="order count", k=4),
   dict(gexp="m.medication_name", agg="COUNT(*)",
        frm="prescriptions p2 JOIN medications m ON p2.medication_id = "
            "m.medication_id",
        gdesc="medication", adesc="prescription count", k=5),
  ]),
T("t46_topk_derived", "order_limit_topk", DB, "hard", "ordered_rows",
  ["derived_measure", "two_table_join"],
  "SELECT {sel} AS entity, {expr} AS metric FROM {frm} {where} "
  "ORDER BY metric DESC, entity ASC LIMIT {k}",
  ["Which {k} {noun}s have the highest {mdesc}? Show entity and value.",
   "Rank by {mdesc} and return the top {k} {noun}s.",
   "List the {k} {noun}s with the largest {mdesc}.",
   "Top {k} {noun}s by {mdesc}, alphabetical on ties."],
  variants=[
   dict(sel="invoice_id", expr="total_amount - insurance_paid",
        frm="invoices", where="", k=5, noun="invoice",
        mdesc="outstanding balance"),
   dict(sel="oi.order_item_id",
        expr="oi.quantity * pr.unit_price * (1 - oi.discount_percent "
             "/ 100.0)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        where="", k=5, noun="order line", mdesc="discounted line value"),
   dict(sel="p2.prescription_id", expr="p2.days_supply * m.unit_cost",
        frm="prescriptions p2 JOIN medications m ON p2.medication_id = "
            "m.medication_id",
        where="", k=5, noun="prescription", mdesc="estimated cost"),
   dict(sel="invoice_id",
        expr="insurance_paid * 100.0 / total_amount",
        frm="invoices", where="WHERE total_amount > 0", k=5,
        noun="invoice", mdesc="insurance coverage percentage"),
   dict(sel="product_id", expr="unit_price * stock_quantity",
        frm="products", where="", k=5, noun="product",
        mdesc="inventory value"),
   dict(sel="appointment_id", expr="base_fee * 0.1",
        frm="appointments", where="WHERE status = 'completed'", k=5,
        noun="completed appointment", mdesc="ten-percent service charge"),
  ]),
)

# =====================================================================
# 8. aggregation  (E6 / M8 / H6)
# =====================================================================
add(
T("a46_scalar", "aggregation", DB, "easy", "scalar", [],
  "SELECT {agg} FROM {tbl} {where}",
  ["{qw}?", "Compute: {qw2}.", "What is {qw3}?", "Report {qw3}."],
  variants=[
   dict(agg="COUNT(*)", tbl="patients", where="",
        qw="How many patients are there in total",
        qw2="the total number of patients",
        qw3="the total patient count"),
   dict(agg="AVG(total_amount)", tbl="invoices", where="",
        qw="What is the average invoice total",
        qw2="the average total amount over all invoices",
        qw3="the mean invoice total"),
   dict(agg="MAX(unit_price)", tbl="products", where="",
        qw="What is the highest product unit price",
        qw2="the maximum unit price across products",
        qw3="the top product price"),
   dict(agg="MIN(appointment_date)", tbl="appointments", where="",
        qw="What is the earliest appointment date",
        qw2="the minimum appointment date",
        qw3="the first appointment date on record"),
   dict(agg="SUM(stock_quantity)", tbl="products", where="",
        qw="How many units are in stock across all products",
        qw2="the total stock quantity over all products",
        qw3="the summed stock quantity"),
   dict(agg="COUNT(*)", tbl="appointments",
        where="WHERE status = 'cancelled'",
        qw="How many appointments were cancelled",
        qw2="the number of cancelled appointments",
        qw3="the cancelled appointment count"),
  ]),
T("a46_filtered_scalar", "aggregation", DB, "medium", "scalar",
  ["two_table_join"],
  "SELECT {agg} FROM {frm} WHERE {w}",
  ["{qw}?", "Compute {qw2}.", "What is {qw2}?", "Give me {qw2}."],
  variants=[
   dict(agg="SUM(i.total_amount)",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id",
        w="a.visit_type = 'urgent'",
        qw="What is the total invoiced amount for urgent visits",
        qw2="the total invoiced amount across urgent appointments"),
   dict(agg="AVG(d.years_experience)",
        frm="doctors d", w="d.specialty = 'cardiology'",
        qw="What is the average experience of cardiologists",
        qw2="the average years of experience among cardiology doctors"),
   dict(agg="COUNT(*)",
        frm="orders o JOIN customers c ON o.customer_id = c.customer_id",
        w="c.loyalty_level = 'platinum'",
        qw="How many orders did platinum customers place",
        qw2="the number of orders from platinum-loyalty customers"),
   dict(agg="AVG(l.test_value)",
        frm="lab_results l", w="l.test_name = 'glucose'",
        qw="What is the average glucose test value",
        qw2="the mean value across glucose lab results"),
   dict(agg="SUM(oi.quantity)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        w="pr.category = 'electronics'",
        qw="How many electronics units were sold",
        qw2="the total quantity sold in the electronics category"),
   dict(agg="MAX(i.total_amount)",
        frm="invoices i", w="i.payment_status = 'unpaid'",
        qw="What is the largest unpaid invoice",
        qw2="the maximum total amount among unpaid invoices"),
   dict(agg="AVG(a.base_fee)",
        frm="appointments a JOIN doctors d ON a.doctor_id = d.doctor_id",
        w="d.specialty = 'dermatology'",
        qw="What is the average base fee for dermatology appointments",
        qw2="the mean base fee across dermatology appointments"),
   dict(agg="COUNT(*)",
        frm="prescriptions p2 JOIN medications m ON p2.medication_id = "
            "m.medication_id",
        w="m.controlled_substance = 'yes'",
        qw="How many prescriptions involve controlled substances",
        qw2="the count of controlled-substance prescriptions"),
  ]),
T("a46_expr_scalar", "aggregation", DB, "hard", "scalar",
  ["derived_measure"],
  "SELECT {agg} FROM {frm} {where}",
  ["{qw}?", "Compute {qw2}.", "What is {qw2}?", "Determine {qw2}."],
  variants=[
   dict(agg="SUM(total_amount - insurance_paid)", frm="invoices",
        where="",
        qw="What is the total outstanding balance across all invoices",
        qw2="the sum of total amount minus insurance paid over all "
            "invoices"),
   dict(agg="SUM(oi.quantity * pr.unit_price)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        where="",
        qw="What is the total gross revenue over all order lines",
        qw2="the sum of quantity times unit price across order items"),
   dict(agg="AVG(total_amount - insurance_paid)", frm="invoices",
        where="WHERE payment_status <> 'paid'",
        qw="What is the average outstanding balance on not-fully-paid "
           "invoices",
        qw2="the mean of total minus insurance paid over unpaid or "
            "partial invoices"),
   dict(agg="SUM(oi.quantity * pr.unit_price * oi.discount_percent "
            "/ 100.0)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        where="",
        qw="How much discount value was given across all order lines",
        qw2="the total discount amount (quantity x price x discount "
            "percent) over all order items"),
   dict(agg="COUNT(*) * 1.0 / (SELECT COUNT(*) FROM appointments)",
        frm="appointments", where="WHERE status = 'completed'",
        qw="What fraction of appointments were completed",
        qw2="the completed share of all appointments as a fraction"),
   dict(agg="SUM(p2.days_supply * m.unit_cost)",
        frm="prescriptions p2 JOIN medications m ON p2.medication_id = "
            "m.medication_id",
        where="",
        qw="What is the estimated total medication cost across all "
           "prescriptions",
        qw2="the sum of days supply times unit cost over all "
            "prescriptions"),
  ]),
)

# =====================================================================
# 9. distinct_count  (E6 / M8 / H6)
# =====================================================================
add(
T("d46_count_distinct", "distinct_count", DB, "easy", "scalar",
  ["distinct"],
  "SELECT COUNT(DISTINCT {col}) FROM {tbl}",
  ["How many distinct {cdesc}s appear in {tbl}?",
   "Count the unique {cdesc}s in {tbl}.",
   "How many different {cdesc}s are there in {tbl}?",
   "What is the number of unique {cdesc} values in {tbl}?"],
  variants=[
   dict(tbl="patients", col="city", cdesc="city"),
   dict(tbl="lab_results", col="test_name", cdesc="test name"),
   dict(tbl="orders", col="shipping_city", cdesc="shipping city"),
   dict(tbl="products", col="category", cdesc="category"),
   dict(tbl="doctors", col="specialty", cdesc="specialty"),
   dict(tbl="appointments", col="patient_id", cdesc="patient id"),
  ]),
T("d46_distinct_filtered", "distinct_count", DB, "medium", "scalar",
  ["distinct", "two_table_join"],
  "SELECT COUNT(DISTINCT {col}) FROM {frm} WHERE {w}",
  ["How many distinct {cdesc}s {wdesc}?",
   "Count the unique {cdesc}s {wdesc}.",
   "How many different {cdesc}s {wdesc}?",
   "What is the count of unique {cdesc}s {wdesc}?"],
  variants=[
   dict(col="a.patient_id", frm="appointments a",
        w="a.status = 'completed'", cdesc="patient",
        wdesc="had a completed appointment"),
   dict(col="o.customer_id", frm="orders o",
        w="o.order_status = 'delivered'", cdesc="customer",
        wdesc="received a delivered order"),
   dict(col="a.doctor_id",
        frm="appointments a JOIN lab_results l ON a.appointment_id = "
            "l.appointment_id",
        w="l.result_flag = 'critical'", cdesc="doctor",
        wdesc="are associated with a critical lab result"),
   dict(col="oi.product_id",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id",
        w="o.order_status = 'cancelled'", cdesc="product",
        wdesc="appear on cancelled orders"),
   dict(col="p2.medication_id",
        frm="prescriptions p2", w="p2.refill_allowed = 'yes'",
        cdesc="medication", wdesc="were prescribed with refills allowed"),
   dict(col="a.patient_id",
        frm="appointments a JOIN doctors d ON a.doctor_id = d.doctor_id",
        w="d.specialty = 'cardiology'", cdesc="patient",
        wdesc="saw a cardiologist"),
   dict(col="l.test_name", frm="lab_results l",
        w="l.result_flag <> 'normal'", cdesc="test type",
        wdesc="ever produced an out-of-range result"),
   dict(col="o.shipping_city",
        frm="orders o JOIN customers c ON o.customer_id = c.customer_id",
        w="c.loyalty_level = 'gold'", cdesc="shipping city",
        wdesc="received orders from gold customers"),
  ]),
T("d46_distinct_per_group", "distinct_count", DB, "hard",
  "multiset_rows", ["distinct", "two_table_join"],
  "SELECT {gexp}, COUNT(DISTINCT {dcol}) FROM {frm} GROUP BY {gexp}",
  ["For each {gdesc}, how many distinct {ddesc}s are there?",
   "Count unique {ddesc}s per {gdesc}.",
   "Per {gdesc}, report the number of different {ddesc}s.",
   "Show each {gdesc} with its distinct {ddesc} count."],
  variants=[
   dict(gexp="a.patient_id", dcol="a.doctor_id", frm="appointments a",
        gdesc="patient", ddesc="doctor seen"),
   dict(gexp="d.specialty", dcol="a.patient_id",
        frm="appointments a JOIN doctors d ON a.doctor_id = d.doctor_id",
        gdesc="specialty", ddesc="patient"),
   dict(gexp="c.customer_id", dcol="pr.category",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id "
            "JOIN customers c ON o.customer_id = c.customer_id "
            "JOIN products pr ON oi.product_id = pr.product_id",
        gdesc="customer", ddesc="product category purchased"),
   dict(gexp="a.patient_id", dcol="l.test_name",
        frm="appointments a JOIN lab_results l ON a.appointment_id = "
            "l.appointment_id",
        gdesc="patient", ddesc="lab test type"),
   dict(gexp="m.medication_class", dcol="a.patient_id",
        frm="prescriptions p2 JOIN medications m ON p2.medication_id = "
            "m.medication_id JOIN appointments a ON p2.appointment_id = "
            "a.appointment_id",
        gdesc="medication class", ddesc="patient"),
   dict(gexp="pr.category", dcol="o.customer_id",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id "
            "JOIN products pr ON oi.product_id = pr.product_id",
        gdesc="product category", ddesc="customer"),
  ]),
)

# =====================================================================
# 10. derived_metric  (E6 / M8 / H6)
# =====================================================================
add(
T("x46_row_expr", "derived_metric", DB, "easy", "multiset_rows",
  ["derived_measure"],
  "SELECT {idc}, {expr} FROM {tbl} WHERE {w}",
  ["For {wdesc}, list the {idd} and the {mdesc}.",
   "Show {idd} and {mdesc} for {wdesc}.",
   "Compute the {mdesc} for {wdesc}; include the {idd}.",
   "What is the {mdesc} of each of {wdesc}? Show the {idd} too."],
  variants=[
   dict(idc="invoice_id", expr="total_amount - insurance_paid",
        tbl="invoices", w="payment_status = 'partial'",
        idd="invoice id", mdesc="outstanding balance",
        wdesc="partially paid invoices"),
   dict(idc="invoice_id", expr="insurance_paid * 100.0 / total_amount",
        tbl="invoices", w="total_amount > 0 AND payment_status = 'paid'",
        idd="invoice id", mdesc="insurance coverage percent",
        wdesc="fully paid invoices"),
   dict(idc="product_id", expr="unit_price * stock_quantity",
        tbl="products", w="category = 'furniture'",
        idd="product id", mdesc="inventory value",
        wdesc="furniture products"),
   dict(idc="order_item_id",
        expr="quantity * discount_percent / 100.0",
        tbl="order_items", w="discount_percent > 0",
        idd="order item id", mdesc="discounted unit share",
        wdesc="discounted order lines"),
   dict(idc="appointment_id", expr="base_fee * 1.1",
        tbl="appointments", w="visit_type = 'urgent'",
        idd="appointment id", mdesc="fee including a 10 percent "
        "urgent surcharge", wdesc="urgent appointments"),
   dict(idc="medication_id", expr="unit_cost * 30",
        tbl="medications", w="controlled_substance = 'no'",
        idd="medication id", mdesc="30-day cost estimate",
        wdesc="non-controlled medications"),
  ]),
T("x46_grouped_expr", "derived_metric", DB, "medium", "multiset_rows",
  ["derived_measure", "two_table_join"],
  "SELECT {gexp}, {agg} FROM {frm} GROUP BY {gexp}",
  ["Per {gdesc}, what is the {mdesc}?",
   "Compute the {mdesc} for each {gdesc}.",
   "Show every {gdesc} with its {mdesc}.",
   "Report the {mdesc} per {gdesc}."],
  variants=[
   dict(gexp="p.insurance_provider",
        agg="SUM(i.total_amount - i.insurance_paid)",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id JOIN patients p ON a.patient_id = "
            "p.patient_id",
        gdesc="insurance provider", mdesc="total outstanding balance"),
   dict(gexp="pr.category",
        agg="SUM(oi.quantity * pr.unit_price * (1 - oi.discount_percent "
            "/ 100.0))",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        gdesc="product category", mdesc="net revenue after discounts"),
   dict(gexp="i.payment_status",
        agg="AVG(i.total_amount - i.insurance_paid)",
        frm="invoices i", gdesc="payment status",
        mdesc="average outstanding balance"),
   dict(gexp="m.medication_class",
        agg="SUM(p2.days_supply * m.unit_cost)",
        frm="prescriptions p2 JOIN medications m ON p2.medication_id = "
            "m.medication_id",
        gdesc="medication class", mdesc="total estimated cost"),
   dict(gexp="c.loyalty_level",
        agg="SUM(oi.quantity * pr.unit_price)",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id "
            "JOIN customers c ON o.customer_id = c.customer_id "
            "JOIN products pr ON oi.product_id = pr.product_id",
        gdesc="loyalty level", mdesc="gross purchase value"),
   dict(gexp="d.specialty", agg="SUM(a.base_fee)",
        frm="appointments a JOIN doctors d ON a.doctor_id = d.doctor_id",
        gdesc="doctor specialty", mdesc="total base fees"),
   dict(gexp="a.visit_type",
        agg="SUM(i.total_amount) - SUM(i.insurance_paid)",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id",
        gdesc="visit type", mdesc="outstanding amount (totals minus "
        "insurance)"),
   dict(gexp="o.order_status",
        agg="AVG(oi.quantity * pr.unit_price)",
        frm="order_items oi JOIN orders o ON oi.order_id = o.order_id "
            "JOIN products pr ON oi.product_id = pr.product_id",
        gdesc="order status", mdesc="average line value"),
  ]),
T("x46_ratio", "derived_metric", DB, "hard", "multiset_rows",
  ["derived_measure", "two_table_join", "nested_aggregation"],
  "SELECT {gexp}, {num} * 100.0 / {den} AS pct FROM {frm} "
  "GROUP BY {gexp}",
  ["Per {gdesc}, what percentage is {numd} out of {dend}?",
   "Compute {numd} as a percent of {dend} for each {gdesc}.",
   "Show each {gdesc} with its {numd}-to-{dend} percentage.",
   "For every {gdesc}, report {numd} divided by {dend} as a percent."],
  variants=[
   dict(gexp="p.insurance_provider", num="SUM(i.insurance_paid)",
        den="SUM(i.total_amount)",
        frm="invoices i JOIN appointments a ON i.appointment_id = "
            "a.appointment_id JOIN patients p ON a.patient_id = "
            "p.patient_id",
        gdesc="insurance provider", numd="insurance paid",
        dend="total billed"),
   dict(gexp="d.specialty",
        num="SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END)",
        den="COUNT(*)",
        frm="appointments a JOIN doctors d ON a.doctor_id = d.doctor_id",
        gdesc="specialty", numd="completed appointments",
        dend="all appointments"),
   dict(gexp="pr.category",
        num="SUM(CASE WHEN oi.discount_percent > 0 THEN oi.quantity "
            "ELSE 0 END)",
        den="SUM(oi.quantity)",
        frm="order_items oi JOIN products pr ON oi.product_id = "
            "pr.product_id",
        gdesc="product category", numd="discounted units",
        dend="all units"),
   dict(gexp="l.test_name",
        num="SUM(CASE WHEN l.result_flag <> 'normal' THEN 1 ELSE 0 END)",
        den="COUNT(*)",
        frm="lab_results l", gdesc="lab test",
        numd="abnormal results", dend="all results"),
   dict(gexp="c.loyalty_level",
        num="SUM(CASE WHEN o.order_status = 'cancelled' THEN 1 ELSE 0 "
            "END)",
        den="COUNT(*)",
        frm="orders o JOIN customers c ON o.customer_id = c.customer_id",
        gdesc="loyalty level", numd="cancelled orders",
        dend="all orders"),
   dict(gexp="i.payment_status",
        num="SUM(i.total_amount - i.insurance_paid)",
        den="SUM(i.total_amount)",
        frm="invoices i", gdesc="payment status",
        numd="outstanding amount", dend="billed amount"),
  ]),
)

TEMPLATES = TS
