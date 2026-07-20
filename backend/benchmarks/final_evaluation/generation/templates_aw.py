"""
final_evaluation/generation/templates_aw.py

AdventureWorks CTU (database_id 50) template families.
Per category: 5 easy + 6 medium + 4 hard = 15 semantic templates
(x 4 cases = 60 cases). Reserved-word columns ("Group") are avoided or
quoted; date literals use the frozen 2011-2014 OrderDate range.
"""

from benchmarks.final_evaluation.generation.genlib import T

DB = 50
TS = []


def add(*ts):
    TS.extend(ts)


# ---------------------------------------------------------------- join
add(
T("j50_product_sub", "join", DB, "easy", "multiset_rows",
  ["two_table_join"],
  "SELECT p.Name, s.Name FROM Product p "
  "JOIN ProductSubcategory s ON p.ProductSubcategoryID = "
  "s.ProductSubcategoryID WHERE p.Color = '{color}'",
  ["List {color} products with their subcategory names.",
   "Which products are {color}? Show product and subcategory.",
   "Show product name and subcategory for every {color} product.",
   "For {color}-colored products, list the product and its subcategory."],
  variants=[
   dict(color="Red"), dict(color="Black"), dict(color="Silver"),
   dict(color="Blue"), dict(color="Yellow"),
  ]),
T("j50_emp_person", "join", DB, "medium", "multiset_rows",
  ["two_table_join", "multiple_conditions"],
  "SELECT pe.FirstName, pe.LastName, e.JobTitle FROM Employee e "
  "JOIN Person pe ON e.BusinessEntityID = pe.BusinessEntityID "
  "WHERE e.{col} = '{val}' AND e.Gender = '{g}'",
  ["List {g}-gender employees whose {cdesc} is '{val}', with job titles.",
   "Which employees have {cdesc} '{val}' and gender {g}? Show names and "
   "title.",
   "Show first name, last name, and job title where {cdesc} = '{val}' "
   "and gender = {g}.",
   "Find employees with {cdesc} '{val}' (gender {g})."],
  variants=[
   dict(col="MaritalStatus", val="S", g="F", cdesc="marital status"),
   dict(col="MaritalStatus", val="M", g="M", cdesc="marital status"),
   dict(col="SalariedFlag", val="1", g="F", cdesc="salaried flag"),
  ]),
T("j50_order_territory", "join", DB, "medium", "multiset_rows",
  ["two_table_join", "range_filter"],
  "SELECT h.SalesOrderID, t.Name FROM SalesOrderHeader h "
  "JOIN SalesTerritory t ON h.TerritoryID = t.TerritoryID "
  "WHERE t.Name = '{terr}' AND h.TotalDue > {amt}",
  ["List {terr} sales orders with total due above {amt}, plus the "
   "territory name.",
   "Which {terr} orders exceed {amt}? Show order id and territory.",
   "Show order id and territory for {terr} orders over {amt}.",
   "Find sales orders in {terr} whose total due is greater than {amt}."],
  variants=[
   dict(terr="Canada", amt=100000),
   dict(terr="Northwest", amt=80000),
   dict(terr="Australia", amt=50000),
  ]),
T("j50_vendor_product", "join", DB, "hard", "multiset_rows",
  ["two_table_join", "multiple_conditions"],
  "SELECT v.Name, p.Name, pv.StandardPrice FROM ProductVendor pv "
  "JOIN Vendor v ON pv.BusinessEntityID = v.BusinessEntityID "
  "JOIN Product p ON pv.ProductID = p.ProductID "
  "WHERE v.CreditRating = {cr} AND pv.StandardPrice > {sp}",
  ["For vendors with credit rating {cr}, list vendor, product, and "
   "standard price above {sp}.",
   "Which credit-rating-{cr} vendors supply products priced over {sp}?",
   "Show vendor name, product name, and price where the vendor rating "
   "is {cr} and the standard price exceeds {sp}.",
   "List supplier/product pairs (rating {cr}) with standard price > "
   "{sp}."],
  variants=[
   dict(cr=1, sp=40), dict(cr=2, sp=30),
  ]),
T("j50_anti", "join", DB, "hard", "multiset_rows",
  ["two_table_join", "null_handling"],
  "SELECT p.Name FROM Product p LEFT JOIN {child} c "
  "ON c.ProductID = p.ProductID WHERE c.ProductID IS NULL "
  "AND p.FinishedGoodsFlag = '1'",
  ["Which finished products never appear in {cdesc}? Show the name.",
   "List finished-goods products with no {cdesc} records.",
   "Find sellable products missing from {cdesc}.",
   "Show names of finished products that have zero {cdesc} rows."],
  variants=[
   dict(child="SalesOrderDetail", cdesc="sales order lines"),
   dict(child="ProductReview", cdesc="product reviews"),
  ]),
)

# ------------------------------------------------------ multi_table_join
add(
T("m50_order_chain", "multi_table_join", DB, "easy", "multiset_rows",
  ["three_plus_table_join"],
  "SELECT d.SalesOrderID, p.Name, d.OrderQty FROM SalesOrderDetail d "
  "JOIN Product p ON d.ProductID = p.ProductID "
  "JOIN SalesOrderHeader h ON d.SalesOrderID = h.SalesOrderID "
  "WHERE h.TerritoryID = {tid} AND d.OrderQty >= {q}",
  ["For territory {tid} orders, list order id, product, and quantity of "
   "{q} or more.",
   "Which order lines in territory {tid} have quantity >= {q}?",
   "Show order, product, and quantity for territory-{tid} lines with "
   "at least {q} units.",
   "List territory {tid} order lines of {q}+ units."],
  variants=[
   dict(tid=1, q=20), dict(tid=4, q=25), dict(tid=6, q=20),
   dict(tid=9, q=15), dict(tid=10, q=12),
  ]),
T("m50_cat_chain", "multi_table_join", DB, "medium", "multiset_rows",
  ["three_plus_table_join"],
  "SELECT p.Name, s.Name, c.Name FROM Product p "
  "JOIN ProductSubcategory s ON p.ProductSubcategoryID = "
  "s.ProductSubcategoryID "
  "JOIN ProductCategory c ON s.ProductCategoryID = c.ProductCategoryID "
  "WHERE c.Name = '{cat}' AND p.ListPrice {op} {lp}",
  ["In the {cat} category, list product, subcategory, and category for "
   "list prices {opw} {lp}.",
   "Which {cat} products have a list price {opw} {lp}?",
   "Show {cat} products ({opw} {lp}) with subcategory and category "
   "names.",
   "List product/subcategory/category rows for {cat} where price is "
   "{opw} {lp}."],
  variants=[
   dict(cat="Bikes", op=">", lp=3000, opw="above"),
   dict(cat="Components", op=">", lp=1000, opw="above"),
   dict(cat="Clothing", op="<", lp=40, opw="below"),
   dict(cat="Accessories", op=">", lp=50, opw="above"),
  ]),
T("m50_emp_dept", "multi_table_join", DB, "medium", "multiset_rows",
  ["three_plus_table_join", "temporal"],
  "SELECT pe.FirstName, pe.LastName, d.Name FROM "
  "EmployeeDepartmentHistory h "
  "JOIN Employee e ON h.BusinessEntityID = e.BusinessEntityID "
  "JOIN Person pe ON e.BusinessEntityID = pe.BusinessEntityID "
  "JOIN Department d ON h.DepartmentID = d.DepartmentID "
  "WHERE d.GroupName = '{grp}' AND h.EndDate IS NULL",
  ["List current employees in {grp} departments with the department "
   "name.",
   "Who currently works in a {grp} department? Show name and "
   "department.",
   "Show current staff (no end date) of {grp}-group departments.",
   "Which employees are presently assigned to {grp} departments?"],
  variants=[
   dict(grp="Manufacturing"),
   dict(grp="Sales and Marketing"),
  ]),
T("m50_po_chain", "multi_table_join", DB, "hard", "multiset_rows",
  ["three_plus_table_join", "range_filter"],
  "SELECT v.Name, p.Name, d.OrderQty, d.UnitPrice FROM "
  "PurchaseOrderDetail d "
  "JOIN PurchaseOrderHeader h ON d.PurchaseOrderID = h.PurchaseOrderID "
  "JOIN Vendor v ON h.VendorID = v.BusinessEntityID "
  "JOIN Product p ON d.ProductID = p.ProductID "
  "WHERE d.RejectedQty > {rq} AND d.UnitPrice > {up}",
  ["List purchase lines with rejected quantity above {rq} and unit "
   "price over {up}: vendor, product, quantity, price.",
   "Which vendor/product purchase lines had {rq}+ rejections at prices "
   "above {up}?",
   "Show vendor, product, order quantity, and unit price for rejected "
   "purchases (> {rq} rejected, > {up} price).",
   "Find problematic purchase lines: rejections over {rq}, unit price "
   "over {up}."],
  variants=[
   dict(rq=100, up=30), dict(rq=50, up=50),
  ]),
T("m50_sales_person_chain", "multi_table_join", DB, "hard",
  "multiset_rows", ["three_plus_table_join"],
  "SELECT pe.FirstName, pe.LastName, t.Name, s.SalesYTD FROM "
  "SalesPerson s "
  "JOIN Person pe ON s.BusinessEntityID = pe.BusinessEntityID "
  "JOIN SalesTerritory t ON s.TerritoryID = t.TerritoryID "
  "WHERE s.SalesYTD > {ytd}",
  ["List salespeople with YTD sales above {ytd}: name, territory, and "
   "amount.",
   "Which salespeople exceed {ytd} in YTD sales? Include territory.",
   "Show name, territory, and SalesYTD for salespeople over {ytd}.",
   "Find territory-assigned salespeople whose YTD sales top {ytd}."],
  variants=[
   dict(ytd=2000000), dict(ytd=3000000),
  ]),
)

# --------------------------------------------------------------- group_by
add(
T("g50_count_per", "group_by", DB, "easy", "multiset_rows", [],
  "SELECT {gcol}, COUNT(*) FROM {tbl} {where} GROUP BY {gcol}",
  ["How many {noun}s per {gdesc}?",
   "Count {noun}s for each {gdesc}.",
   "Per {gdesc}, how many {noun}s exist?",
   "Show each {gdesc} with its {noun} count."],
  variants=[
   dict(tbl="Product", gcol="Color", where="WHERE Color IS NOT NULL",
        gdesc="color", noun="product"),
   dict(tbl="Employee", gcol="JobTitle", where="", gdesc="job title",
        noun="employee"),
   dict(tbl="Vendor", gcol="CreditRating", where="",
        gdesc="credit rating", noun="vendor"),
   dict(tbl="CreditCard", gcol="CardType", where="",
        gdesc="card type", noun="credit card"),
   dict(tbl="Address", gcol="City", where="WHERE City LIKE 'S%'",
        gdesc="city starting with S", noun="address"),
  ]),
T("g50_sum_join", "group_by", DB, "medium", "multiset_rows",
  ["two_table_join"],
  "SELECT {gexp}, {agg} FROM {frm} {where} GROUP BY {gexp}",
  ["Per {gdesc}, what is the {adesc}?",
   "Compute the {adesc} for each {gdesc}.",
   "Show the {adesc} by {gdesc}.",
   "For every {gdesc}, report the {adesc}."],
  variants=[
   dict(gexp="t.Name", agg="SUM(h.TotalDue)",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON h.TerritoryID "
            "= t.TerritoryID",
        where="", gdesc="sales territory", adesc="total order value"),
   dict(gexp="c.Name", agg="COUNT(*)",
        frm="Product p JOIN ProductSubcategory s ON "
            "p.ProductSubcategoryID = s.ProductSubcategoryID "
            "JOIN ProductCategory c ON s.ProductCategoryID = "
            "c.ProductCategoryID",
        where="", gdesc="product category", adesc="product count"),
   dict(gexp="d.Name", agg="COUNT(*)",
        frm="EmployeeDepartmentHistory h JOIN Department d ON "
            "h.DepartmentID = d.DepartmentID",
        where="WHERE h.EndDate IS NULL", gdesc="department",
        adesc="current headcount"),
   dict(gexp="substr(h.OrderDate, 1, 4)", agg="SUM(h.TotalDue)",
        frm="SalesOrderHeader h", where="", gdesc="order year",
        adesc="total sales value"),
   dict(gexp="p.ProductLine", agg="AVG(p.ListPrice)",
        frm="Product p",
        where="WHERE p.ProductLine IS NOT NULL AND p.ListPrice > 0",
        gdesc="product line", adesc="average list price"),
   dict(gexp="sm.Name", agg="COUNT(*)",
        frm="SalesOrderHeader h JOIN ShipMethod sm ON h.ShipMethodID = "
            "sm.ShipMethodID",
        where="", gdesc="ship method", adesc="order count"),
  ]),
T("g50_two_key", "group_by", DB, "hard", "multiset_rows",
  ["two_table_join", "temporal"],
  "SELECT {g1}, {g2}, {agg} FROM {frm} {where} GROUP BY {g1}, {g2}",
  ["Break down the {adesc} by {g1d} and {g2d}.",
   "Per ({g1d}, {g2d}), compute the {adesc}.",
   "Show {g1d}, {g2d}, and the {adesc}.",
   "For each {g1d} and {g2d} combination, report the {adesc}."],
  variants=[
   dict(g1="t.Name", g2="substr(h.OrderDate, 1, 4)",
        agg="SUM(h.TotalDue)",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON h.TerritoryID "
            "= t.TerritoryID",
        where="", g1d="territory", g2d="year", adesc="sales total"),
   dict(g1="p.Color", g2="p.ProductLine", agg="COUNT(*)",
        frm="Product p",
        where="WHERE p.Color IS NOT NULL AND p.ProductLine IS NOT NULL",
        g1d="color", g2d="product line", adesc="product count"),
   dict(g1="e.Gender", g2="e.MaritalStatus", agg="COUNT(*)",
        frm="Employee e", where="", g1d="gender", g2d="marital status",
        adesc="employee count"),
   dict(g1="v.CreditRating", g2="v.PreferredVendorStatus",
        agg="COUNT(*)", frm="Vendor v", where="",
        g1d="credit rating", g2d="preferred status",
        adesc="vendor count"),
  ]),
)

# ----------------------------------------------------------------- having
add(
T("h50_count", "having", DB, "easy", "multiset_rows", [],
  "SELECT {gcol}, COUNT(*) FROM {tbl} {where} GROUP BY {gcol} "
  "HAVING COUNT(*) {op} {n}",
  ["Which {gdesc}s have {opw} {n} {noun}s?",
   "List {gdesc}s with {opw} {n} {noun}s and the count.",
   "Find {gdesc}s where the {noun} count is {opw} {n}.",
   "Show {gdesc}s having {opw} {n} {noun}s."],
  variants=[
   dict(tbl="Product", gcol="Color", where="WHERE Color IS NOT NULL",
        op=">=", n=50, opw="at least", gdesc="color", noun="product"),
   dict(tbl="SalesOrderDetail", gcol="ProductID", where="",
        op=">", n=1000, opw="more than", gdesc="product id",
        noun="order line"),
   dict(tbl="Employee", gcol="JobTitle", where="", op=">=", n=10,
        opw="at least", gdesc="job title", noun="employee"),
   dict(tbl="Address", gcol="City", where="", op=">=", n=200,
        opw="at least", gdesc="city", noun="address"),
   dict(tbl="WorkOrder", gcol="ProductID", where="", op=">", n=500,
        opw="more than", gdesc="product id", noun="work order"),
  ]),
T("h50_sum", "having", DB, "medium", "multiset_rows",
  ["two_table_join"],
  "SELECT {gexp}, {agg} FROM {frm} {where} GROUP BY {gexp} "
  "HAVING {agg} {op} {n}",
  ["Which {gdesc}s have {adesc} {opw} {n}? Show the value.",
   "List {gdesc}s whose {adesc} is {opw} {n}.",
   "Find {gdesc}s with {adesc} {opw} {n}.",
   "Show {gdesc}s where the {adesc} {opw} {n}."],
  variants=[
   dict(gexp="h.CustomerID", agg="SUM(h.TotalDue)",
        frm="SalesOrderHeader h", where="", op=">", n=500000,
        opw="above", gdesc="customer", adesc="total order value"),
   dict(gexp="t.Name", agg="SUM(h.TotalDue)",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON "
            "h.TerritoryID = t.TerritoryID",
        where="", op=">", n=15000000, opw="above", gdesc="territory",
        adesc="sales total"),
   dict(gexp="d.ProductID", agg="SUM(d.OrderQty)",
        frm="SalesOrderDetail d", where="", op=">", n=3000,
        opw="more than", gdesc="product", adesc="units sold"),
   dict(gexp="h.VendorID", agg="SUM(h.TotalDue)",
        frm="PurchaseOrderHeader h", where="", op=">", n=1000000,
        opw="above", gdesc="vendor", adesc="purchase total"),
   dict(gexp="w.ProductID", agg="SUM(w.ScrappedQty)",
        frm="WorkOrder w", where="", op=">", n=100, opw="more than",
        gdesc="product", adesc="scrapped quantity"),
   dict(gexp="s.Name", agg="AVG(p.ListPrice)",
        frm="Product p JOIN ProductSubcategory s ON "
            "p.ProductSubcategoryID = s.ProductSubcategoryID",
        where="WHERE p.ListPrice > 0", op=">", n=800, opw="above",
        gdesc="subcategory", adesc="average list price"),
  ]),
T("h50_two_conditions", "having", DB, "hard", "multiset_rows",
  ["multiple_conditions", "nested_aggregation"],
  "SELECT {gexp}, COUNT(*), {agg2} FROM {frm} {where} GROUP BY {gexp} "
  "HAVING COUNT(*) {op1} {n1} AND {agg2} {op2} {n2}",
  ["Which {gdesc}s have {op1w} {n1} {noun}s and {a2desc} {op2w} {n2}?",
   "List {gdesc}s meeting both thresholds: {noun} count {op1w} {n1}, "
   "{a2desc} {op2w} {n2}.",
   "Find {gdesc}s with {op1w} {n1} {noun}s whose {a2desc} is also "
   "{op2w} {n2}.",
   "Show {gdesc}s where count {op1w} {n1} and {a2desc} {op2w} {n2}."],
  variants=[
   dict(gexp="h.CustomerID", agg2="AVG(h.TotalDue)",
        frm="SalesOrderHeader h", where="", op1=">=", n1=10,
        op2=">", n2=5000, op1w="at least", op2w="above",
        gdesc="customer", noun="order", a2desc="average order value"),
   dict(gexp="d.ProductID", agg2="SUM(d.LineTotal)",
        frm="SalesOrderDetail d", where="", op1=">", n1=500,
        op2=">", n2=1000000, op1w="more than", op2w="above",
        gdesc="product", noun="order line", a2desc="line revenue"),
   dict(gexp="w.ProductID", agg2="AVG(w.OrderQty)",
        frm="WorkOrder w", where="", op1=">=", n1=100, op2=">",
        n2=300, op1w="at least", op2w="above", gdesc="product",
        noun="work order", a2desc="average order quantity"),
   dict(gexp="h.SalesPersonID", agg2="SUM(h.TotalDue)",
        frm="SalesOrderHeader h",
        where="WHERE h.SalesPersonID IS NOT NULL", op1=">=", n1=100,
        op2=">", n2=5000000, op1w="at least", op2w="above",
        gdesc="salesperson", noun="order", a2desc="sales total"),
  ]),
)

# ------------------------------------------------------------ subquery_cte
add(
T("s50_above_avg", "subquery_cte", DB, "easy", "multiset_rows",
  ["population_comparison"],
  "SELECT {sel} FROM {tbl} WHERE {w} AND {col} > "
  "(SELECT AVG({col}) FROM {tbl} WHERE {w})",
  ["Among {dom}, which have {cdesc} above the average? Show {seld}.",
   "List {seld} where the {cdesc} exceeds the {dom} average.",
   "Find {dom} rows with above-average {cdesc}.",
   "Show {seld} for {dom} beating the mean {cdesc}."],
  variants=[
   dict(tbl="Product", w="ListPrice > 0", col="ListPrice",
        sel="Name, ListPrice", seld="name and price", dom="priced "
        "products", cdesc="list price"),
   dict(tbl="SalesOrderHeader", w="1=1", col="TotalDue",
        sel="SalesOrderID, TotalDue", seld="order id and total",
        dom="sales orders", cdesc="total due"),
   dict(tbl="Employee", w="1=1", col="VacationHours",
        sel="BusinessEntityID, VacationHours",
        seld="employee id and hours", dom="employees",
        cdesc="vacation hours"),
   dict(tbl="Vendor", w="1=1", col="CreditRating",
        sel="Name, CreditRating", seld="vendor and rating",
        dom="vendors", cdesc="credit rating"),
   dict(tbl="SalesPerson", w="1=1", col="SalesYTD",
        sel="BusinessEntityID, SalesYTD", seld="id and YTD",
        dom="salespeople", cdesc="year-to-date sales"),
  ]),
T("s50_correlated", "subquery_cte", DB, "medium", "multiset_rows",
  ["correlated_subquery", "population_comparison"],
  "SELECT p.Name, p.ListPrice FROM Product p WHERE "
  "p.ProductSubcategoryID IS NOT NULL AND p.ListPrice > "
  "(SELECT AVG(p2.ListPrice) FROM Product p2 "
  "WHERE p2.ProductSubcategoryID = p.ProductSubcategoryID "
  "AND p2.ListPrice > {floor})",
  ["Which products cost more than their subcategory's average (over "
   "products above {floor})?",
   "List products priced above their own subcategory average, counting "
   "only prices over {floor}.",
   "Find products beating the same-subcategory average price (floor "
   "{floor}).",
   "Show name and price for products above their subcategory's mean "
   "({floor}+ prices)."],
  variants=[
   dict(floor=0), dict(floor=10), dict(floor=100), dict(floor=500),
   dict(floor=50), dict(floor=1),
  ]),
T("s50_cte_totals", "subquery_cte", DB, "hard", "multiset_rows",
  ["nested_aggregation", "population_comparison"],
  "WITH totals AS (SELECT {ent} AS ek, SUM({m}) AS total FROM {frm} "
  "GROUP BY {ent}) SELECT ek, total FROM totals WHERE total > "
  "{mult} * (SELECT AVG(total) FROM totals)",
  ["Which {edesc}s have a total {mdesc} above {mult}x the average "
   "{edesc} total?",
   "Total the {mdesc} per {edesc}; list those beyond {mult} times the "
   "average.",
   "Find {edesc}s whose summed {mdesc} exceeds {mult}x the mean total.",
   "Show {edesc} totals larger than {mult} times the cross-{edesc} "
   "average."],
  variants=[
   dict(ent="h.CustomerID", m="h.TotalDue", frm="SalesOrderHeader h",
        mult=10, edesc="customer", mdesc="order value"),
   dict(ent="d.ProductID", m="d.LineTotal", frm="SalesOrderDetail d",
        mult=5, edesc="product", mdesc="line revenue"),
   dict(ent="h.VendorID", m="h.TotalDue", frm="PurchaseOrderHeader h",
        mult=2, edesc="vendor", mdesc="purchase value"),
   dict(ent="t.ProductID", m="t.Quantity", frm="TransactionHistory t",
        mult=3, edesc="product", mdesc="transacted quantity"),
  ]),
)

# --------------------------------------------------------- set_operations
add(
T("o50_product_sets", "set_operations", DB, "easy", "set_rows", [],
  "SELECT ProductID FROM {t1} WHERE {w1} {setop} "
  "SELECT ProductID FROM {t2} WHERE {w2}",
  ["{setw} of {d1} and {d2}: list product ids.",
   "Which product ids are in the {setw} of {d1} and {d2}?",
   "Apply {setop}: ({d1}) versus ({d2}).",
   "List ids from {d1} {setop} {d2}."],
  variants=[
   dict(t1="SalesOrderDetail", w1="OrderQty >= 20",
        t2="WorkOrder", w2="ScrappedQty > 0", setop="INTERSECT",
        setw="intersection", d1="bulk-ordered products",
        d2="products with scrap"),
   dict(t1="Product", w1="Color = 'Red'",
        t2="Product", w2="ListPrice > 1000", setop="INTERSECT",
        setw="intersection", d1="red products",
        d2="products above 1000"),
   dict(t1="ProductInventory", w1="Quantity > 500",
        t2="SalesOrderDetail", w2="1=1", setop="EXCEPT",
        setw="difference", d1="well-stocked products",
        d2="ever-sold products"),
   dict(t1="ProductReview", w1="Rating >= 4",
        t2="SalesOrderDetail", w2="OrderQty >= 10", setop="UNION",
        setw="union", d1="well-reviewed products",
        d2="products ordered 10+ at once"),
   dict(t1="WorkOrder", w1="ScrappedQty > 0",
        t2="ProductCostHistory", w2="StandardCost > 1000",
        setop="INTERSECT", setw="intersection",
        d1="products with any scrap", d2="high-cost products"),
  ]),
T("o50_person_sets", "set_operations", DB, "medium", "set_rows", [],
  "SELECT BusinessEntityID FROM {t1} WHERE {w1} {setop} "
  "SELECT BusinessEntityID FROM {t2} WHERE {w2}",
  ["{setw2} ({d1}) with ({d2}); list the entity ids.",
   "Which ids are in the {setw} of {d1} and {d2}?",
   "Compute {d1} {setop} {d2}.",
   "List entity ids from the {setw} of {d1} and {d2}."],
  variants=[
   dict(t1="Employee", w1="SalariedFlag = '1'",
        t2="Employee", w2="VacationHours > 50", setop="INTERSECT",
        setw="intersection", setw2="Intersect",
        d1="salaried employees", d2="employees with 50+ vacation hours"),
   dict(t1="Employee", w1="Gender = 'F'",
        t2="SalesPerson", w2="1=1", setop="INTERSECT",
        setw="intersection", setw2="Intersect",
        d1="female employees", d2="salespeople"),
   dict(t1="Employee", w1="1=1", t2="SalesPerson", w2="1=1",
        setop="EXCEPT", setw="difference", setw2="Subtract",
        d1="employees", d2="salespeople"),
   dict(t1="SalesPerson", w1="SalesYTD > 1000000",
        t2="SalesPersonQuotaHistory", w2="SalesQuota > 700000",
        setop="EXCEPT", setw="difference", setw2="Subtract",
        d1="million-plus-YTD salespeople",
        d2="salespeople with quotas above 700000"),
   dict(t1="Employee", w1="MaritalStatus = 'S'",
        t2="Employee", w2="Gender = 'M'", setop="EXCEPT",
        setw="difference", setw2="Subtract", d1="single employees",
        d2="male employees"),
   dict(t1="Person", w1="PersonType = 'SP'",
        t2="Employee", w2="1=1", setop="INTERSECT",
        setw="intersection", setw2="Intersect",
        d1="salesperson-type persons", d2="employees"),
  ]),
T("o50_threeway", "set_operations", DB, "hard", "set_rows",
  ["multiple_conditions"],
  "SELECT ProductID FROM {t1} WHERE {w1} {op1} SELECT ProductID FROM "
  "{t2} WHERE {w2} {op2} SELECT ProductID FROM {t3} WHERE {w3}",
  ["Combine ({d1}) {op1w} ({d2}) {op2w} ({d3}); list product ids.",
   "Chain: {d1} {op1} {d2} {op2} {d3}.",
   "Which products remain after {d1} {op1w} {d2} {op2w} {d3}?",
   "Evaluate the set expression ({d1}) {op1} ({d2}) {op2} ({d3})."],
  variants=[
   dict(t1="SalesOrderDetail", w1="OrderQty >= 10",
        t2="ProductInventory", w2="Quantity > 100",
        t3="WorkOrder", w3="ScrappedQty > 20",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect", op2w="minus",
        d1="bulk-sold products", d2="in-stock products",
        d3="high-scrap products"),
   dict(t1="Product", w1="FinishedGoodsFlag = '1'",
        t2="SalesOrderDetail", w2="1=1",
        t3="ProductReview", w3="Rating <= 2",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect", op2w="minus",
        d1="finished-goods products", d2="ever-sold products",
        d3="poorly reviewed products"),
   dict(t1="TransactionHistory", w1="TransactionType = 'S'",
        t2="TransactionHistory", w2="TransactionType = 'W'",
        t3="TransactionHistory", w3="TransactionType = 'P'",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect", op2w="minus",
        d1="sold products", d2="work-order products",
        d3="purchased products"),
   dict(t1="SpecialOfferProduct", w1="SpecialOfferID > 1",
        t2="SalesOrderDetail", w2="UnitPriceDiscount > 0",
        t3="ProductCostHistory", w3="StandardCost > 500",
        op1="INTERSECT", op2="EXCEPT", op1w="intersect", op2w="minus",
        d1="promoted products", d2="discount-sold products",
        d3="expensive-to-make products"),
  ]),
)

# ------------------------------------------------------ order_limit_topk
add(
T("t50_topk", "order_limit_topk", DB, "easy", "ordered_rows", [],
  "SELECT {sel}, {col} FROM {tbl} {where} ORDER BY {col} DESC, {tie} "
  "ASC LIMIT {k}",
  ["Top {k} {dom} by {cdesc}.",
   "Which {k} {dom} have the highest {cdesc}?",
   "Rank {dom} by {cdesc} and return the first {k}.",
   "List the {k} largest {dom} by {cdesc}."],
  variants=[
   dict(tbl="Product", sel="Name", col="ListPrice", tie="ProductID",
        where="", k=10, dom="products", cdesc="list price"),
   dict(tbl="SalesOrderHeader", sel="SalesOrderID", col="TotalDue",
        tie="SalesOrderID", where="", k=10, dom="sales orders",
        cdesc="total due"),
   dict(tbl="Employee", sel="BusinessEntityID", col="VacationHours",
        tie="BusinessEntityID", where="", k=10, dom="employees",
        cdesc="vacation hours"),
   dict(tbl="SalesPerson", sel="BusinessEntityID", col="SalesYTD",
        tie="BusinessEntityID", where="", k=5, dom="salespeople",
        cdesc="YTD sales"),
   dict(tbl="PurchaseOrderHeader", sel="PurchaseOrderID",
        col="TotalDue", tie="PurchaseOrderID", where="", k=10,
        dom="purchase orders", cdesc="total due"),
  ]),
T("t50_topk_agg", "order_limit_topk", DB, "medium", "ordered_rows",
  ["nested_aggregation", "two_table_join"],
  "SELECT {gexp} AS grp, {agg} AS agg_value FROM {frm} {where} "
  "GROUP BY {gexp} ORDER BY agg_value DESC, grp ASC LIMIT {k}",
  ["Top {k} {gdesc}s by {adesc}.",
   "Which {k} {gdesc}s lead on {adesc}?",
   "Rank {gdesc}s by {adesc}; give the top {k}.",
   "List the {k} {gdesc}s with the greatest {adesc}."],
  variants=[
   dict(gexp="h.CustomerID", agg="SUM(h.TotalDue)",
        frm="SalesOrderHeader h", where="", k=10, gdesc="customer",
        adesc="lifetime order value"),
   dict(gexp="p.Name", agg="SUM(d.OrderQty)",
        frm="SalesOrderDetail d JOIN Product p ON d.ProductID = "
            "p.ProductID",
        where="", k=10, gdesc="product", adesc="units sold"),
   dict(gexp="t.Name", agg="COUNT(*)",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON "
            "h.TerritoryID = t.TerritoryID",
        where="", k=5, gdesc="territory", adesc="order count"),
   dict(gexp="v.Name", agg="SUM(h.TotalDue)",
        frm="PurchaseOrderHeader h JOIN Vendor v ON h.VendorID = "
            "v.BusinessEntityID",
        where="", k=10, gdesc="vendor", adesc="purchase spend"),
   dict(gexp="c.Name", agg="SUM(d.LineTotal)",
        frm="SalesOrderDetail d JOIN Product p ON d.ProductID = "
            "p.ProductID JOIN ProductSubcategory s ON "
            "p.ProductSubcategoryID = s.ProductSubcategoryID "
            "JOIN ProductCategory c ON s.ProductCategoryID = "
            "c.ProductCategoryID",
        where="", k=4, gdesc="category", adesc="revenue"),
   dict(gexp="w.ProductID", agg="SUM(w.ScrappedQty)",
        frm="WorkOrder w", where="", k=10, gdesc="product",
        adesc="total scrap"),
  ]),
T("t50_topk_derived", "order_limit_topk", DB, "hard", "ordered_rows",
  ["derived_measure"],
  "SELECT {sel} AS entity, {expr} AS metric FROM {frm} {where} "
  "ORDER BY metric DESC, entity ASC LIMIT {k}",
  ["Top {k} {dom} by {mdesc}.",
   "Which {k} {dom} score highest on {mdesc}?",
   "Rank {dom} by {mdesc}; return {k}.",
   "List the {k} best {dom} by {mdesc}."],
  variants=[
   dict(sel="p.Name", expr="p.ListPrice - p.StandardCost",
        frm="Product p", where="WHERE p.ListPrice > 0", k=10,
        dom="products", mdesc="unit margin"),
   dict(sel="h.SalesOrderID", expr="h.TaxAmt * 100.0 / h.SubTotal",
        frm="SalesOrderHeader h", where="WHERE h.SubTotal > 0", k=10,
        dom="orders", mdesc="tax percentage"),
   dict(sel="w.WorkOrderID",
        expr="w.ScrappedQty * 100.0 / w.OrderQty",
        frm="WorkOrder w", where="WHERE w.OrderQty > 0 AND "
        "w.ScrappedQty > 0", k=10, dom="work orders",
        mdesc="scrap rate"),
   dict(sel="d.SalesOrderDetailID",
        expr="d.OrderQty * d.UnitPrice * d.UnitPriceDiscount",
        frm="SalesOrderDetail d", where="WHERE d.UnitPriceDiscount > 0",
        k=10, dom="order lines", mdesc="discount value"),
  ]),
)

# ------------------------------------------------------------ aggregation
add(
T("a50_scalar", "aggregation", DB, "easy", "scalar", [],
  "SELECT {agg} FROM {tbl} {where}",
  ["{qw}?", "Compute {qw2}.", "What is {qw2}?", "Report {qw2}."],
  variants=[
   dict(agg="COUNT(*)", tbl="Product", where="",
        qw="How many products exist",
        qw2="the total product count"),
   dict(agg="AVG(TotalDue)", tbl="SalesOrderHeader", where="",
        qw="What is the average sales order total",
        qw2="the mean TotalDue across sales orders"),
   dict(agg="MAX(ListPrice)", tbl="Product", where="",
        qw="What is the highest product list price",
        qw2="the maximum list price"),
   dict(agg="COUNT(*)", tbl="Employee", where="WHERE Gender = 'F'",
        qw="How many female employees are there",
        qw2="the count of employees with gender F"),
   dict(agg="SUM(Quantity)", tbl="ProductInventory", where="",
        qw="How many units are in inventory overall",
        qw2="the total inventory quantity"),
  ]),
T("a50_filtered", "aggregation", DB, "medium", "scalar", [],
  "SELECT {agg} FROM {frm} WHERE {w}",
  ["{qw}?", "Compute {qw2}.", "What is {qw2}?", "Give {qw2}."],
  variants=[
   dict(agg="SUM(h.TotalDue)",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON "
            "h.TerritoryID = t.TerritoryID",
        w="t.Name = 'Canada'",
        qw="What is the total value of Canadian sales orders",
        qw2="the summed TotalDue for the Canada territory"),
   dict(agg="AVG(p.ListPrice)",
        frm="Product p JOIN ProductSubcategory s ON "
            "p.ProductSubcategoryID = s.ProductSubcategoryID",
        w="s.Name = 'Mountain Bikes'",
        qw="What is the average mountain bike list price",
        qw2="the mean list price in the Mountain Bikes subcategory"),
   dict(agg="COUNT(*)", frm="SalesOrderHeader h",
        w="h.OrderDate LIKE '2013%'",
        qw="How many sales orders were placed in 2013",
        qw2="the 2013 sales order count"),
   dict(agg="SUM(d.LineTotal)", frm="SalesOrderDetail d "
        "JOIN Product p ON d.ProductID = p.ProductID",
        w="p.Color = 'Red'",
        qw="What is the total revenue from red products",
        qw2="the summed line totals for red products"),
   dict(agg="AVG(e.VacationHours)", frm="Employee e",
        w="e.SalariedFlag = '0'",
        qw="What is the average vacation balance of hourly employees",
        qw2="the mean vacation hours where salaried flag is 0"),
   dict(agg="MAX(h.TotalDue)", frm="PurchaseOrderHeader h",
        w="h.Status = 4",
        qw="What is the largest completed purchase order",
        qw2="the maximum TotalDue among status-4 purchase orders"),
  ]),
T("a50_expr", "aggregation", DB, "hard", "scalar",
  ["derived_measure"],
  "SELECT {agg} FROM {frm} {where}",
  ["{qw}?", "Compute {qw2}.", "What is {qw2}?", "Determine {qw2}."],
  variants=[
   dict(agg="SUM(ListPrice - StandardCost)", frm="Product",
        where="WHERE ListPrice > 0",
        qw="What is the total unit margin across priced products",
        qw2="the sum of list price minus standard cost over priced "
            "products"),
   dict(agg="SUM(SubTotal + TaxAmt + Freight)",
        frm="SalesOrderHeader", where="WHERE OrderDate LIKE '2012%'",
        qw="What did 2012 orders total including tax and freight",
        qw2="the 2012 sum of subtotal plus tax plus freight"),
   dict(agg="SUM(OrderQty * UnitPrice * (1 - UnitPriceDiscount))",
        frm="SalesOrderDetail", where="",
        qw="What is the net detail revenue after discounts",
        qw2="the sum of quantity x price x (1 - discount) over all "
            "order lines"),
   dict(agg="AVG(ScrappedQty * 1.0 / OrderQty)", frm="WorkOrder",
        where="WHERE OrderQty > 0",
        qw="What is the average scrap fraction across work orders",
        qw2="the mean scrapped-to-ordered ratio"),
  ]),
)

# --------------------------------------------------------- distinct_count
add(
T("d50_simple", "distinct_count", DB, "easy", "scalar", ["distinct"],
  "SELECT COUNT(DISTINCT {col}) FROM {tbl} {where}",
  ["How many distinct {cdesc}s {wdesc}?",
   "Count the unique {cdesc}s {wdesc}.",
   "How many different {cdesc}s {wdesc}?",
   "What is the unique {cdesc} count {wdesc}?"],
  variants=[
   dict(tbl="SalesOrderHeader", col="CustomerID", where="",
        cdesc="customer", wdesc="ever placed a sales order"),
   dict(tbl="Product", col="Color", where="WHERE Color IS NOT NULL",
        cdesc="product color", wdesc="exist"),
   dict(tbl="Address", col="City", where="", cdesc="city",
        wdesc="appear among addresses"),
   dict(tbl="Employee", col="JobTitle", where="", cdesc="job title",
        wdesc="exist"),
   dict(tbl="SalesOrderDetail", col="ProductID", where="",
        cdesc="product", wdesc="were ever sold"),
  ]),
T("d50_filtered", "distinct_count", DB, "medium", "scalar",
  ["distinct", "two_table_join"],
  "SELECT COUNT(DISTINCT {col}) FROM {frm} WHERE {w}",
  ["How many distinct {cdesc}s {wdesc}?",
   "Count unique {cdesc}s {wdesc}.",
   "How many different {cdesc}s {wdesc}?",
   "Give the number of unique {cdesc}s {wdesc}."],
  variants=[
   dict(col="h.CustomerID",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON "
            "h.TerritoryID = t.TerritoryID",
        w="t.Name = 'Australia'", cdesc="customer",
        wdesc="ordered from Australia"),
   dict(col="d.ProductID", frm="SalesOrderDetail d",
        w="d.OrderQty >= 20", cdesc="product",
        wdesc="were sold 20+ at once"),
   dict(col="h.SalesPersonID", frm="SalesOrderHeader h",
        w="h.TotalDue > 100000 AND h.SalesPersonID IS NOT NULL",
        cdesc="salesperson", wdesc="closed an order above 100000"),
   dict(col="w.ProductID", frm="WorkOrder w", w="w.ScrappedQty > 0",
        cdesc="product", wdesc="ever had scrap"),
   dict(col="pv.BusinessEntityID", frm="ProductVendor pv",
        w="pv.StandardPrice > 50", cdesc="vendor",
        wdesc="supply products priced above 50"),
   dict(col="e.EmailAddress",
        frm="EmailAddress e JOIN Person p ON e.BusinessEntityID = "
            "p.BusinessEntityID",
        w="p.PersonType = 'EM'", cdesc="email address",
        wdesc="belong to employee-type persons"),
  ]),
T("d50_per_group", "distinct_count", DB, "hard", "multiset_rows",
  ["distinct", "two_table_join"],
  "SELECT {gexp}, COUNT(DISTINCT {dcol}) FROM {frm} {where} "
  "GROUP BY {gexp}",
  ["Per {gdesc}, how many distinct {ddesc}s?",
   "Count unique {ddesc}s per {gdesc}.",
   "For each {gdesc}, report the distinct {ddesc} count.",
   "Show each {gdesc} with its unique {ddesc} count."],
  variants=[
   dict(gexp="t.Name", dcol="h.CustomerID",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON "
            "h.TerritoryID = t.TerritoryID",
        where="", gdesc="territory", ddesc="customer"),
   dict(gexp="h.CustomerID", dcol="d.ProductID",
        frm="SalesOrderDetail d JOIN SalesOrderHeader h ON "
            "d.SalesOrderID = h.SalesOrderID",
        where="WHERE h.CustomerID <= 11200", gdesc="customer (id up to "
        "11200)", ddesc="product purchased"),
   dict(gexp="substr(h.OrderDate, 1, 4)", dcol="h.CustomerID",
        frm="SalesOrderHeader h", where="", gdesc="order year",
        ddesc="active customer"),
   dict(gexp="c.Name", dcol="d.ProductID",
        frm="SalesOrderDetail d JOIN Product p ON d.ProductID = "
            "p.ProductID JOIN ProductSubcategory s ON "
            "p.ProductSubcategoryID = s.ProductSubcategoryID "
            "JOIN ProductCategory c ON s.ProductCategoryID = "
            "c.ProductCategoryID",
        where="", gdesc="category", ddesc="distinct product sold"),
  ]),
)

# --------------------------------------------------------- derived_metric
add(
T("x50_margin_rows", "derived_metric", DB, "easy", "multiset_rows",
  ["derived_measure"],
  "SELECT {idc}, {expr} FROM {tbl} WHERE {w}",
  ["For {dom}, list {idd} and the {mdesc}.",
   "Show {idd} with the {mdesc} for {dom}.",
   "Compute the {mdesc} for {dom}.",
   "What is the {mdesc} for each of {dom}?"],
  variants=[
   dict(idc="Name", expr="ListPrice - StandardCost", tbl="Product",
        w="ListPrice > 2000", idd="the product name",
        mdesc="unit margin", dom="products above 2000"),
   dict(idc="SalesOrderID", expr="SubTotal + TaxAmt + Freight",
        tbl="SalesOrderHeader", w="TotalDue > 150000",
        idd="the order id", mdesc="rebuilt grand total",
        dom="very large orders"),
   dict(idc="WorkOrderID", expr="OrderQty - ScrappedQty",
        tbl="WorkOrder", w="ScrappedQty > 50", idd="the work order id",
        mdesc="net good quantity", dom="high-scrap work orders"),
   dict(idc="BusinessEntityID", expr="SalesYTD - SalesLastYear",
        tbl="SalesPerson", w="SalesLastYear > 0", idd="the person id",
        mdesc="year-over-year sales change",
        dom="salespeople with prior-year sales"),
   dict(idc="ProductID", expr="ListPrice * 0.9", tbl="Product",
        w="ListPrice > 3000", idd="the product id",
        mdesc="price after a 10 percent discount",
        dom="premium products"),
  ]),
T("x50_grouped", "derived_metric", DB, "medium", "multiset_rows",
  ["derived_measure", "two_table_join"],
  "SELECT {gexp}, {agg} FROM {frm} {where} GROUP BY {gexp}",
  ["Per {gdesc}, compute the {mdesc}.",
   "Show each {gdesc}'s {mdesc}.",
   "For every {gdesc}, report the {mdesc}.",
   "Group by {gdesc} and calculate the {mdesc}."],
  variants=[
   dict(gexp="p.ProductLine",
        agg="AVG(p.ListPrice - p.StandardCost)", frm="Product p",
        where="WHERE p.ListPrice > 0 AND p.ProductLine IS NOT NULL",
        gdesc="product line", mdesc="average unit margin"),
   dict(gexp="t.Name", agg="SUM(h.TaxAmt + h.Freight)",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON "
            "h.TerritoryID = t.TerritoryID",
        where="", gdesc="territory",
        mdesc="total tax plus freight"),
   dict(gexp="substr(h.OrderDate, 1, 4)",
        agg="SUM(h.SubTotal) - SUM(h.Freight)",
        frm="SalesOrderHeader h", where="", gdesc="year",
        mdesc="subtotal minus freight"),
   dict(gexp="w.ProductID",
        agg="SUM(w.ScrappedQty) * 100.0 / SUM(w.OrderQty)",
        frm="WorkOrder w", where="", gdesc="product",
        mdesc="scrap percentage"),
   dict(gexp="v.Name",
        agg="SUM(d.LineTotal) / COUNT(DISTINCT h.PurchaseOrderID)",
        frm="PurchaseOrderDetail d JOIN PurchaseOrderHeader h ON "
            "d.PurchaseOrderID = h.PurchaseOrderID JOIN Vendor v ON "
            "h.VendorID = v.BusinessEntityID",
        where="", gdesc="vendor", mdesc="average PO line value per "
        "order"),
   dict(gexp="sm.Name", agg="AVG(h.Freight * 100.0 / h.SubTotal)",
        frm="SalesOrderHeader h JOIN ShipMethod sm ON "
            "h.ShipMethodID = sm.ShipMethodID",
        where="WHERE h.SubTotal > 0", gdesc="ship method",
        mdesc="average freight percentage"),
  ]),
T("x50_ratio", "derived_metric", DB, "hard", "multiset_rows",
  ["derived_measure", "nested_aggregation"],
  "SELECT {gexp}, {num} * 100.0 / {den} AS pct FROM {frm} {where} "
  "GROUP BY {gexp}",
  ["Per {gdesc}, what percent is {numd} of {dend}?",
   "Compute {numd} as a share of {dend} for each {gdesc}.",
   "Show each {gdesc}'s {numd}-to-{dend} percentage.",
   "Report {numd} over {dend} (as %) per {gdesc}."],
  variants=[
   dict(gexp="t.Name",
        num="SUM(CASE WHEN h.OnlineOrderFlag = '1' THEN 1 ELSE 0 END)",
        den="COUNT(*)",
        frm="SalesOrderHeader h JOIN SalesTerritory t ON "
            "h.TerritoryID = t.TerritoryID",
        where="", gdesc="territory", numd="online orders",
        dend="all orders"),
   dict(gexp="w.ProductID", num="SUM(w.ScrappedQty)",
        den="SUM(w.OrderQty)", frm="WorkOrder w",
        where="", gdesc="product", numd="scrapped units",
        dend="ordered units"),
   dict(gexp="p.ProductLine",
        num="SUM(CASE WHEN p.MakeFlag = '1' THEN 1 ELSE 0 END)",
        den="COUNT(*)", frm="Product p",
        where="WHERE p.ProductLine IS NOT NULL",
        gdesc="product line", numd="manufactured products",
        dend="all products"),
   dict(gexp="substr(h.OrderDate, 1, 4)", num="SUM(h.Freight)",
        den="SUM(h.SubTotal)", frm="SalesOrderHeader h", where="",
        gdesc="year", numd="freight cost", dend="order subtotal"),
  ]),
)

TEMPLATES = TS
