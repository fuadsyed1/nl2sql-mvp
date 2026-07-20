"""Generic fatal semantic guards: Cartesian join, uncorrelated absence
NOT EXISTS, constant-as-measure, ranking-by-id. Uses the exact SQL shapes from
the AdventureWorks manual test (no DB / LLM needed)."""

from sql_candidates.semantic_sql_guards import (
    cartesian_join_violation, uncorrelated_absence_violation,
    constant_measure_violation, ranking_measure_violation, sql_guard_violations,
)

Q2 = ("Find customers who bought products from at least three different "
      "categories and spent more than 100000 dollars in total.")
Q3 = ("Find employees who are currently assigned to a department but have no "
      "pay-rate change recorded after 2010.")
Q4 = ("Find the three vendors with the greatest purchase order value within "
      "each credit rating.")
Q5 = "Show a running total of purchase order spending for each vendor over time."


def test_cartesian_join_flagged():
    bad = ("SELECT c.CustomerID FROM Customer c JOIN Product p ON 1=1 "
           "GROUP BY c.CustomerID HAVING SUM(p.ListPrice) > 100000")
    assert cartesian_join_violation(bad, Q2)
    good = ("SELECT c.CustomerID FROM Customer c "
            "JOIN SalesOrderHeader s ON s.CustomerID = c.CustomerID")
    assert cartesian_join_violation(good, Q2) is None


def test_uncorrelated_absence_flagged():
    bad = ("SELECT e.BusinessEntityID FROM Employee e WHERE NOT EXISTS "
           "(SELECT 1 FROM Department d WHERE d.ModifiedDate > '2010-12-31')")
    assert uncorrelated_absence_violation(bad, Q3)
    good = ("SELECT e.BusinessEntityID FROM Employee e WHERE NOT EXISTS "
            "(SELECT 1 FROM EmployeePayHistory ph WHERE ph.BusinessEntityID = "
            "e.BusinessEntityID AND ph.RateChangeDate > '2010-12-31')")
    assert uncorrelated_absence_violation(good, Q3) is None


def test_constant_measure_flagged():
    bad = ("WITH x AS (SELECT v.Name vn, 1 AS spending_amount FROM Vendor v) "
           "SELECT vn, SUM(spending_amount) OVER (PARTITION BY vn) FROM x")
    assert constant_measure_violation(bad, Q5)
    assert constant_measure_violation("SELECT SUM(1) FROM Vendor", Q5)
    good = ("SELECT v.Name, SUM(po.TotalDue) OVER (PARTITION BY v.Name) "
            "FROM Vendor v JOIN PurchaseOrderHeader po ON po.VendorID = v.BusinessEntityID")
    assert constant_measure_violation(good, Q5) is None


def test_constant_measure_ignores_count_questions():
    # "how many" is not a monetary/quantity total -> SUM(1) is not flagged
    assert constant_measure_violation("SELECT SUM(1) FROM t",
                                      "how many rows are there") is None


def test_ranking_by_id_flagged():
    bad = ("SELECT name FROM (SELECT v.name, ROW_NUMBER() OVER (PARTITION BY "
           "v.creditrating ORDER BY v.businessentityid DESC) rn FROM Vendor v) "
           "WHERE rn <= 3")
    assert ranking_measure_violation(bad, Q4)
    good = ("SELECT name FROM (SELECT v.name, ROW_NUMBER() OVER (PARTITION BY "
            "v.creditrating ORDER BY SUM(po.TotalDue) DESC) rn FROM Vendor v "
            "JOIN PurchaseOrderHeader po ON po.VendorID=v.BusinessEntityID "
            "GROUP BY v.BusinessEntityID) WHERE rn <= 3")
    assert ranking_measure_violation(good, Q4) is None


def test_aggregate_reports_all_reasons():
    q2bad = ("SELECT c.CustomerID FROM Customer c JOIN Product p ON 1=1 "
             "GROUP BY c.CustomerID")
    assert sql_guard_violations(Q2, q2bad)
    q1good = ("SELECT so.SalesOrderID FROM SalesOrderHeader so WHERE "
              "so.TotalDue > (SELECT AVG(so2.TotalDue) FROM SalesOrderHeader so2 "
              "WHERE so2.CustomerID = so.CustomerID)")
    q1 = ("Find sales orders placed in 2013 whose total due is higher than the "
          "average total due for the same customer.")
    assert sql_guard_violations(q1, q1good) == []
