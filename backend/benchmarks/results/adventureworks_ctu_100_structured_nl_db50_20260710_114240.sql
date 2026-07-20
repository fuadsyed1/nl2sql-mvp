-- SpiderSQL generated SQL: 100_structured_nl
-- Database: AdventureWorks CTU #50
-- No SQL is hard-matched by the benchmark.

-- S-001 | select_projection | PASS
-- Question: From Product, return ProductID, Name, ProductNumber, and ListPrice.
SELECT ProductID, Name, ProductNumber, ListPrice FROM Product;

-- S-002 | select_projection | PASS
-- Question: From Employee, return BusinessEntityID, JobTitle, and HireDate.
SELECT BusinessEntityID, JobTitle, HireDate FROM Employee;

-- S-003 | select_projection | PASS
-- Question: From SalesOrderHeader, return SalesOrderID, SalesOrderNumber, OrderDate, and TotalDue.
SELECT SalesOrderID, SalesOrderNumber, OrderDate, TotalDue FROM SalesOrderHeader;

-- S-004 | select_projection | PASS
-- Question: From Vendor, return BusinessEntityID, Name, AccountNumber, and CreditRating.
SELECT v.BusinessEntityID, v.Name, v.AccountNumber, v.CreditRating
FROM Vendor v;

-- S-005 | select_projection | PASS
-- Question: From Customer, return CustomerID, PersonID, StoreID, and TerritoryID.
SELECT CustomerID, PersonID, StoreID, TerritoryID
FROM Customer;

-- S-006 | filter_comparison | PASS
-- Question: Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 1000.
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice > 1000;

-- S-007 | filter_comparison | PASS
-- Question: Return SalesOrderID, OrderDate, CustomerID, and TotalDue from SalesOrderHeader where TotalDue is greater than 10000.
SELECT SalesOrderID, OrderDate, CustomerID, TotalDue
FROM SalesOrderHeader
WHERE TotalDue > 10000;

-- S-008 | filter_comparison | PASS
-- Question: Return BusinessEntityID, JobTitle, and VacationHours from Employee where VacationHours is greater than 60.
SELECT BusinessEntityID, JobTitle, VacationHours FROM Employee WHERE VacationHours > 60;

-- S-009 | filter_comparison | PASS
-- Question: Return BusinessEntityID, Name, and CreditRating from Vendor where CreditRating is less than or equal to 2.
SELECT Vendor.BusinessEntityID, Vendor.Name, Vendor.CreditRating
FROM Vendor
WHERE Vendor.CreditRating <= 2;

-- S-010 | filter_comparison | PASS
-- Question: Return WorkOrderID, ProductID, OrderQty, and ScrappedQty from WorkOrder where ScrappedQty is greater than 0.
SELECT WorkOrderID, ProductID, OrderQty, ScrappedQty
FROM WorkOrder
WHERE ScrappedQty > 0;

-- S-011 | range_between | FAIL
-- Question: From SalesOrderHeader, return SalesOrderID, OrderDate, and TotalDue where OrderDate is between 2012-01-01 and 2013-12-31.
-- No SQL generated.

-- S-012 | range_between | PASS
-- Question: From Product, return ProductID, Name, and ListPrice where ListPrice is between 100 and 500.
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice BETWEEN 100 AND 500;

-- S-013 | range_between | FAIL
-- Question: From Employee, return BusinessEntityID, JobTitle, and HireDate where HireDate is between 2005-01-01 and 2010-12-31.
-- No SQL generated.

-- S-014 | range_between | PASS
-- Question: From PurchaseOrderHeader, return PurchaseOrderID, VendorID, OrderDate, and TotalDue where TotalDue is between 5000 and 25000.
SELECT PurchaseOrderID, VendorID, OrderDate, TotalDue
FROM PurchaseOrderHeader
WHERE TotalDue BETWEEN 5000 AND 25000;

-- S-015 | range_between | PASS
-- Question: From ProductInventory, return ProductID, LocationID, and Quantity where Quantity is between 100 and 500.
SELECT ProductID, LocationID, Quantity
FROM ProductInventory
WHERE Quantity BETWEEN 100 AND 500;

-- S-016 | pattern_text | PASS
-- Question: From Person, return BusinessEntityID, FirstName, and LastName where LastName starts with S.
SELECT p.BusinessEntityID, p.FirstName, p.LastName
FROM Person p
WHERE p.LastName LIKE 'S%';

-- S-017 | pattern_text | PASS
-- Question: From Product, return ProductID and Name where Name contains the text Mountain.
SELECT ProductID, Name FROM Product WHERE Name LIKE '%Mountain%';

-- S-018 | pattern_text | PASS
-- Question: From Vendor, return BusinessEntityID and Name where Name contains the text Bike.
SELECT BusinessEntityID, Name FROM Vendor WHERE Name LIKE '%Bike%';

-- S-019 | pattern_text | FAIL
-- Question: From Address, return AddressID, AddressLine1, and City where City starts with San.
-- No SQL generated.

-- S-020 | pattern_text | FAIL
-- Question: From EmailAddress, return BusinessEntityID and EmailAddress where EmailAddress ends with @adventure-works.com.
-- No SQL generated.

-- S-021 | null_boolean | PASS
-- Question: From Product, return ProductID, Name, and SellEndDate where SellEndDate is null.
SELECT ProductID, Name, SellEndDate FROM Product WHERE SellEndDate IS NULL;

-- S-022 | null_boolean | PASS
-- Question: From Person, return BusinessEntityID, FirstName, MiddleName, and LastName where MiddleName is null.
SELECT BusinessEntityID, FirstName, MiddleName, LastName
FROM Person
WHERE MiddleName IS NULL;

-- S-023 | null_boolean | PASS
-- Question: From SalesOrderHeader, return SalesOrderID, OrderDate, and ShipDate where ShipDate is null.
SELECT SalesOrderID, OrderDate, ShipDate FROM SalesOrderHeader WHERE ShipDate IS NULL;

-- S-024 | null_boolean | PASS
-- Question: From SalesPerson, return BusinessEntityID and TerritoryID where TerritoryID is null.
SELECT BusinessEntityID, TerritoryID FROM SalesPerson WHERE TerritoryID IS NULL;

-- S-025 | null_boolean | PASS
-- Question: From Product, return ProductID, Name, and Color where Color is not null.
SELECT ProductID, Name, Color FROM Product WHERE Color IS NOT NULL;

-- S-026 | join | PASS
-- Question: Join Product to ProductSubcategory and return ProductID, product Name, ProductSubcategoryID, and subcategory Name.
SELECT p.ProductID, p.Name, p.ProductSubcategoryID, ps.Name
FROM Product p
JOIN ProductSubcategory ps ON p.ProductSubcategoryID = ps.ProductSubcategoryID;

-- S-027 | join | PASS
-- Question: Join SalesOrderHeader to Customer and return SalesOrderID, CustomerID, OrderDate, TotalDue, and customer TerritoryID.
SELECT soh.SalesOrderID, soh.CustomerID, soh.OrderDate, soh.TotalDue, c.TerritoryID
FROM SalesOrderHeader soh
JOIN Customer c ON soh.CustomerID = c.CustomerID;

-- S-028 | join | PASS
-- Question: Join Employee to Person on BusinessEntityID and return employee BusinessEntityID, FirstName, LastName, JobTitle, and HireDate.
SELECT e.BusinessEntityID, p.FirstName, p.LastName, e.JobTitle, e.HireDate
FROM Employee e
JOIN Person p ON e.BusinessEntityID = p.BusinessEntityID;

-- S-029 | join | PASS
-- Question: Join PurchaseOrderHeader to Vendor and return PurchaseOrderID, OrderDate, TotalDue, VendorID, and vendor Name.
SELECT poh.PurchaseOrderID, poh.OrderDate, poh.TotalDue, poh.VendorID, v.Name
FROM PurchaseOrderHeader poh
JOIN Vendor v ON poh.VendorID = v.BusinessEntityID;

-- S-030 | join | FAIL
-- Question: Join Address to StateProvince and CountryRegion and return AddressID, City, state or province Name, and country Name.
-- No SQL generated.

-- S-031 | multi_join | FAIL
-- Question: Join SalesOrderDetail, SalesOrderHeader, Customer, and Product; return SalesOrderID, CustomerID, ProductID, product Name, OrderDate, OrderQty, and LineTotal.
-- No SQL generated.

-- S-032 | multi_join | FAIL
-- Question: Join Employee, Person, EmployeeDepartmentHistory, and Department; keep current department assignments and return employee ID, name, JobTitle, and department Name.
-- No SQL generated.

-- S-033 | multi_join | FAIL
-- Question: Join Product, ProductSubcategory, and ProductCategory; return ProductID, product Name, subcategory Name, and category Name.
-- No SQL generated.

-- S-034 | multi_join | FAIL
-- Question: Join PurchaseOrderDetail, PurchaseOrderHeader, Vendor, and Product; return PurchaseOrderID, vendor Name, product Name, OrderQty, and LineTotal.
-- No SQL generated.

-- S-035 | multi_join | PASS
-- Question: Join Store, Customer, SalesPerson, and Person; return Store BusinessEntityID, store Name, CustomerID, salesperson BusinessEntityID, and salesperson name.
SELECT s.BusinessEntityID, s.Name, c.CustomerID, sp.BusinessEntityID, p.FirstName, p.LastName
FROM Store s
JOIN Customer c ON c.StoreID = s.BusinessEntityID
JOIN SalesPerson sp ON s.SalesPersonID = sp.BusinessEntityID
JOIN Person p ON sp.BusinessEntityID = p.BusinessEntityID;

-- S-036 | aggregation | PASS
-- Question: Return COUNT of all rows in Product as product_count.
SELECT COUNT(*) AS product_count FROM Product;

-- S-037 | aggregation | PASS
-- Question: Return AVG of ListPrice from Product as average_list_price.
SELECT AVG(ListPrice) AS average_list_price FROM Product;

-- S-038 | aggregation | PASS
-- Question: Return SUM of TotalDue from SalesOrderHeader as total_sales_due.
SELECT SUM(TotalDue) AS total_sales_due FROM SalesOrderHeader;

-- S-039 | aggregation | PASS
-- Question: Return MAX of TotalDue from SalesOrderHeader as maximum_order_total.
SELECT MAX(TotalDue) AS maximum_order_total FROM SalesOrderHeader;

-- S-040 | aggregation | PASS
-- Question: Return MIN, AVG, and MAX of StandardCost from Product.
SELECT MIN(StandardCost), AVG(StandardCost), MAX(StandardCost) FROM Product;

-- S-041 | group_by | PASS
-- Question: Group SalesOrderHeader by CustomerID and return CustomerID, COUNT of orders, and SUM of TotalDue.
SELECT CustomerID, COUNT(*) AS order_count, SUM(TotalDue) AS total_due
FROM SalesOrderHeader
GROUP BY CustomerID;

-- S-042 | group_by | PASS
-- Question: Group SalesOrderHeader by TerritoryID and return TerritoryID, COUNT of orders, and SUM of TotalDue.
SELECT TerritoryID, COUNT(*) AS order_count, SUM(TotalDue) AS total_due
FROM SalesOrderHeader
GROUP BY TerritoryID;

-- S-043 | group_by | PASS
-- Question: Group Product by ProductSubcategoryID and return ProductSubcategoryID and COUNT of products.
SELECT ProductSubcategoryID, COUNT(ProductID)
FROM Product
GROUP BY ProductSubcategoryID;

-- S-044 | group_by | PASS
-- Question: Join current EmployeeDepartmentHistory rows to Department, group by DepartmentID and Name, and return employee count.
SELECT d.DepartmentID, d.Name, COUNT(e.BusinessEntityID) AS employee_count
FROM Department d
JOIN EmployeeDepartmentHistory edh ON d.DepartmentID = edh.DepartmentID
JOIN Employee e ON edh.BusinessEntityID = e.BusinessEntityID
WHERE edh.EndDate IS NULL
GROUP BY d.DepartmentID, d.Name;

-- S-045 | group_by | PASS
-- Question: Join PurchaseOrderHeader to Vendor, group by VendorID and vendor Name, and return order count and SUM of TotalDue.
SELECT poh.VendorID, v.Name, COUNT(*) AS order_count, SUM(poh.TotalDue) AS total_due
FROM PurchaseOrderHeader AS poh
JOIN Vendor AS v ON poh.VendorID = v.BusinessEntityID
GROUP BY poh.VendorID, v.Name;

-- S-046 | having | PASS
-- Question: Group SalesOrderHeader by CustomerID and keep groups where COUNT of orders is greater than 10.
SELECT CustomerID
FROM SalesOrderHeader
GROUP BY CustomerID
HAVING COUNT(SalesOrderID) > 10;

-- S-047 | having | PASS
-- Question: Group Product by ProductSubcategoryID and keep groups where COUNT of products is greater than 20.
SELECT ProductSubcategoryID
FROM Product
GROUP BY ProductSubcategoryID
HAVING COUNT(ProductID) > 20;

-- S-048 | having | PASS
-- Question: Group SalesOrderHeader by TerritoryID and keep groups where SUM of TotalDue is greater than 1000000.
SELECT TerritoryID
FROM SalesOrderHeader
GROUP BY TerritoryID
HAVING SUM(TotalDue) > 1000000;

-- S-049 | having | PASS
-- Question: Group PurchaseOrderHeader by VendorID and keep groups where COUNT of PurchaseOrderID is greater than 5.
SELECT VendorID
FROM PurchaseOrderHeader
GROUP BY VendorID
HAVING COUNT(PurchaseOrderID) > 5;

-- S-050 | having | PASS
-- Question: Join current EmployeeDepartmentHistory to Department, group by DepartmentID and Name, and keep departments with COUNT of employees greater than 10.
SELECT d.DepartmentID, d.Name
FROM Department d
JOIN EmployeeDepartmentHistory edh ON d.DepartmentID = edh.DepartmentID
GROUP BY d.DepartmentID, d.Name
HAVING COUNT(edh.BusinessEntityID) > 10;

-- S-051 | distinct | PASS
-- Question: Return DISTINCT Color from Product where Color is not null.
SELECT DISTINCT Color FROM Product WHERE Color IS NOT NULL;

-- S-052 | distinct | PASS
-- Question: Return DISTINCT JobTitle from Employee.
SELECT DISTINCT JobTitle FROM Employee;

-- S-053 | distinct | PASS
-- Question: Join SalesOrderHeader to ShipMethod and return DISTINCT ShipMethod Name.
SELECT DISTINCT sm.Name
FROM SalesOrderHeader soh
JOIN ShipMethod sm ON soh.ShipMethodID = sm.ShipMethodID;

-- S-054 | distinct | PASS
-- Question: Join SalesTaxRate to StateProvince and return DISTINCT StateProvince Name.
SELECT DISTINCT sp.Name
FROM SalesTaxRate str
JOIN StateProvince sp ON str.StateProvinceID = sp.StateProvinceID;

-- S-055 | distinct | PASS
-- Question: Return DISTINCT Class and Style from Product where at least one is not null.
SELECT DISTINCT Class, Style
FROM Product
WHERE Class IS NOT NULL OR Style IS NOT NULL;

-- S-056 | count_distinct | PASS
-- Question: Return COUNT DISTINCT CustomerID from SalesOrderHeader.
SELECT COUNT(DISTINCT CustomerID) FROM SalesOrderHeader;

-- S-057 | count_distinct | PASS
-- Question: Return COUNT DISTINCT ProductID from SalesOrderDetail.
SELECT COUNT(DISTINCT ProductID) FROM SalesOrderDetail;

-- S-058 | count_distinct | PASS
-- Question: Return COUNT DISTINCT VendorID from PurchaseOrderHeader.
SELECT COUNT(DISTINCT VendorID) FROM PurchaseOrderHeader;

-- S-059 | count_distinct | PASS
-- Question: Return COUNT DISTINCT BusinessEntityID from EmployeeDepartmentHistory.
SELECT COUNT(DISTINCT BusinessEntityID) FROM EmployeeDepartmentHistory;

-- S-060 | count_distinct | FAIL
-- Question: Return COUNT DISTINCT City from Address.
-- No SQL generated.

-- S-061 | order_by | PASS
-- Question: Return ProductID, Name, and ListPrice from Product ordered by ListPrice descending and Name ascending.
SELECT ProductID, Name, ListPrice FROM Product ORDER BY ListPrice DESC, Name ASC LIMIT 1;

-- S-062 | order_by | PASS
-- Question: Return SalesOrderID, OrderDate, CustomerID, and TotalDue from SalesOrderHeader ordered by OrderDate ascending.
SELECT SalesOrderID, OrderDate, CustomerID, TotalDue
FROM SalesOrderHeader
ORDER BY OrderDate ASC;

-- S-063 | order_by | PASS
-- Question: Return BusinessEntityID, JobTitle, and HireDate from Employee ordered by HireDate descending.
SELECT BusinessEntityID, JobTitle, HireDate FROM Employee ORDER BY HireDate DESC;

-- S-064 | order_by | PASS
-- Question: Return BusinessEntityID, Name, and CreditRating from Vendor ordered by CreditRating ascending and Name ascending.
SELECT v.BusinessEntityID, v.Name, v.CreditRating
FROM Vendor v
ORDER BY v.CreditRating ASC, v.Name ASC
LIMIT 1;

-- S-065 | order_by | PASS
-- Question: Return WorkOrderID, ProductID, and ScrappedQty from WorkOrder ordered by ScrappedQty descending.
SELECT WorkOrderID, ProductID, ScrappedQty FROM WorkOrder ORDER BY ScrappedQty DESC;

-- S-066 | top_k_limit | PASS
-- Question: Return the top 10 Product rows ordered by ListPrice descending, including ProductID, Name, and ListPrice.
SELECT ProductID, Name, ListPrice FROM Product ORDER BY ListPrice DESC LIMIT 10;

-- S-067 | top_k_limit | PASS
-- Question: Return the top 20 SalesOrderHeader rows ordered by TotalDue descending, including SalesOrderID, CustomerID, OrderDate, and TotalDue.
SELECT SalesOrderID, CustomerID, OrderDate, TotalDue
FROM SalesOrderHeader
ORDER BY TotalDue DESC
LIMIT 20;

-- S-068 | top_k_limit | PASS
-- Question: Group SalesOrderHeader by CustomerID, order by SUM of TotalDue descending, and return the top 10 customers.
SELECT CustomerID, SUM(TotalDue) AS TotalDueSum
FROM SalesOrderHeader
GROUP BY CustomerID
ORDER BY TotalDueSum DESC
LIMIT 10;

-- S-069 | top_k_limit | PASS
-- Question: Group PurchaseOrderHeader by VendorID, order by SUM of TotalDue descending, and return the top 15 vendors.
SELECT VendorID
FROM PurchaseOrderHeader
GROUP BY VendorID
ORDER BY SUM(TotalDue) DESC
LIMIT 15;

-- S-070 | top_k_limit | PASS
-- Question: Group SalesOrderDetail by ProductID, order by SUM of OrderQty descending, and return the top 10 products.
SELECT ProductID
FROM SalesOrderDetail
GROUP BY ProductID
ORDER BY SUM(OrderQty) DESC
LIMIT 10;

-- S-071 | subquery | PASS
-- Question: Return products where ListPrice is greater than a scalar subquery that computes AVG ListPrice from Product.
SELECT ProductID, Name, ListPrice
FROM Product
WHERE ListPrice > (SELECT AVG(ListPrice) FROM Product);

-- S-072 | subquery | PASS
-- Question: Return SalesOrderHeader rows where TotalDue is greater than a scalar subquery that computes AVG TotalDue.
SELECT SalesOrderID, RevisionNumber, OrderDate, DueDate, ShipDate, Status, OnlineOrderFlag, SalesOrderNumber, PurchaseOrderNumber, AccountNumber, CustomerID, SalesPersonID, TerritoryID, BillToAddressID, ShipToAddressID, ShipMethodID, CreditCardID, CreditCardApprovalCode, CurrencyRateID, SubTotal, TaxAmt, Freight, TotalDue, Comment, rowguid, ModifiedDate FROM SalesOrderHeader WHERE TotalDue > (SELECT AVG(TotalDue) FROM SalesOrderHeader);

-- S-073 | subquery | PASS
-- Question: Return Employee rows where VacationHours is greater than a scalar subquery that computes AVG VacationHours.
SELECT BusinessEntityID, NationalIDNumber, LoginID, OrganizationNode, OrganizationLevel, JobTitle, BirthDate, MaritalStatus, Gender, HireDate, SalariedFlag, VacationHours, SickLeaveHours, CurrentFlag, rowguid, ModifiedDate
FROM Employee
WHERE VacationHours > (SELECT AVG(VacationHours) FROM Employee);

-- S-074 | subquery | PASS
-- Question: Aggregate SalesOrderHeader by CustomerID and keep customer totals greater than the average of all customer totals.
SELECT soh.CustomerID
FROM SalesOrderHeader soh
JOIN Customer c ON soh.CustomerID = c.CustomerID
GROUP BY soh.CustomerID
HAVING SUM(soh.TotalDue) > (
    SELECT AVG(CustomerTotal)
    FROM (
        SELECT SUM(TotalDue) AS CustomerTotal
        FROM SalesOrderHeader
        GROUP BY CustomerID
    )
);

-- S-075 | subquery | PASS
-- Question: Aggregate PurchaseOrderHeader by VendorID and keep vendor totals greater than the average of all vendor totals.
SELECT VendorID
FROM PurchaseOrderHeader
GROUP BY VendorID
HAVING SUM(TotalDue) > (
    SELECT AVG(VendorTotal)
    FROM (
        SELECT SUM(TotalDue) AS VendorTotal
        FROM PurchaseOrderHeader
        GROUP BY VendorID
    )
);

-- S-076 | exists_not_exists | PASS
-- Question: Return Customer rows for which an EXISTS subquery finds a SalesOrderHeader with the same CustomerID.
SELECT c.CustomerID, c.PersonID, c.StoreID, c.TerritoryID, c.AccountNumber, c.rowguid, c.ModifiedDate
FROM Customer c
WHERE EXISTS (
    SELECT 1
    FROM SalesOrderHeader soh
    WHERE soh.CustomerID = c.CustomerID
);

-- S-077 | exists_not_exists | FAIL
-- Question: Return Product rows for which a NOT EXISTS subquery finds no SalesOrderDetail with the same ProductID.
-- No SQL generated.

-- S-078 | exists_not_exists | PASS
-- Question: Return Vendor rows for which an EXISTS subquery finds a PurchaseOrderHeader with the same VendorID.
SELECT v.BusinessEntityID, v.AccountNumber, v.Name, v.CreditRating, v.PreferredVendorStatus, v.ActiveFlag, v.PurchasingWebServiceURL, v.ModifiedDate
FROM Vendor v
WHERE EXISTS (
    SELECT 1
    FROM PurchaseOrderHeader poh
    WHERE poh.VendorID = v.BusinessEntityID
);

-- S-079 | exists_not_exists | PASS
-- Question: Return Employee rows for which a NOT EXISTS subquery finds a current EmployeeDepartmentHistory row with the same BusinessEntityID.
SELECT e.BusinessEntityID, e.NationalIDNumber, e.LoginID, e.OrganizationNode, e.OrganizationLevel, e.JobTitle, e.BirthDate, e.MaritalStatus, e.Gender, e.HireDate, e.SalariedFlag, e.VacationHours, e.SickLeaveHours, e.CurrentFlag, e.rowguid, e.ModifiedDate
FROM Employee e
WHERE NOT EXISTS (
    SELECT 1
    FROM EmployeeDepartmentHistory edh
    WHERE edh.BusinessEntityID = e.BusinessEntityID
      AND edh.EndDate IS NULL
);

-- S-080 | exists_not_exists | PASS
-- Question: Return Product rows where an EXISTS or grouped subquery finds inventory records in more than one distinct LocationID.
SELECT p.ProductID, p.Name, p.ProductNumber, p.MakeFlag, p.FinishedGoodsFlag, p.Color, p.SafetyStockLevel, p.ReorderPoint, p.StandardCost, p.ListPrice, p.Size, p.SizeUnitMeasureCode, p.WeightUnitMeasureCode, p.Weight, p.DaysToManufacture, p.ProductLine, p.Class, p.Style, p.ProductSubcategoryID, p.ProductModelID, p.SellStartDate, p.SellEndDate, p.DiscontinuedDate, p.rowguid, p.ModifiedDate
FROM Product p
WHERE EXISTS (
    SELECT 1
    FROM Location l
    GROUP BY l.LocationID
    HAVING COUNT(DISTINCT l.LocationID) > 1
);

-- S-081 | set_operation | FAIL
-- Question: Use INTERSECT to return City values appearing in customer addresses and vendor addresses.
-- No SQL generated.

-- S-082 | set_operation | FAIL
-- Question: Use INTERSECT to return ProductID values from SalesOrderDetail and PurchaseOrderDetail.
-- No SQL generated.

-- S-083 | set_operation | PASS
-- Question: Use UNION to return distinct BusinessEntityID values from Employee and SalesPerson.
SELECT DISTINCT "employee"."businessentityid", "salesperson"."businessentityid" FROM "employee" INNER JOIN "salesperson" ON "employee"."businessentityid" = "salesperson"."businessentityid";

-- S-084 | set_operation | PASS
-- Question: Use EXCEPT to return CustomerID values from SalesOrderHeader that do not appear as store-linked Customer rows.
SELECT CustomerID FROM SalesOrderHeader
EXCEPT
SELECT c.CustomerID
FROM Customer c
JOIN Store s ON c.StoreID = s.BusinessEntityID;

-- S-085 | set_operation | PASS
-- Question: Use UNION to combine distinct Product Name values for finished goods and purchased components.
SELECT DISTINCT "product"."name" FROM "product" WHERE "product"."finishedgoodsflag" = ? OR "product"."productline" = ?;

-- S-086 | case_expression | PASS
-- Question: Return ProductID, Name, ListPrice, and a CASE expression: budget below 100, midrange from 100 through 1000, premium above 1000.
SELECT ProductID, Name, ListPrice,
CASE
  WHEN ListPrice < 100 THEN 'budget'
  WHEN ListPrice >= 100 AND ListPrice <= 1000 THEN 'midrange'
  ELSE 'premium'
END AS category
FROM Product;

-- S-087 | case_expression | FAIL
-- Question: Return SalesOrderID, TotalDue, and a CASE expression: small below 1000, medium from 1000 through 10000, large above 10000.
-- No SQL generated.

-- S-088 | case_expression | PASS
-- Question: Return ProductID, LocationID, Quantity, and a CASE expression: out_of_stock when 0, low_stock below 50, well_stocked otherwise.
SELECT p.ProductID, l.LocationID, 0 AS Quantity,
       CASE
         WHEN 0 = 0 THEN 'out_of_stock'
         WHEN 0 < 50 THEN 'low_stock'
         ELSE 'well_stocked'
       END AS StockStatus
FROM Product p
CROSS JOIN Location l;

-- S-089 | case_expression | PASS
-- Question: Return BusinessEntityID, HireDate, and a CASE expression that assigns tenure bands from HireDate.
SELECT 
    be.BusinessEntityID,
    e.HireDate,
    CASE 
        WHEN julianday('now') - julianday(e.HireDate) < 365 THEN 'Less than 1 year'
        WHEN julianday('now') - julianday(e.HireDate) < 730 THEN '1 to 2 years'
        WHEN julianday('now') - julianday(e.HireDate) < 1095 THEN '2 to 3 years'
        ELSE 'More than 3 years'
    END AS TenureBand
FROM BusinessEntity be
JOIN Employee e ON be.BusinessEntityID = e.BusinessEntityID;

-- S-090 | case_expression | PASS
-- Question: Return Vendor BusinessEntityID, Name, CreditRating, and a CASE expression that maps rating to low, medium, or high risk.
SELECT "vendor"."businessentityid", "vendor"."name", "vendor"."creditrating", "vendor"."creditrating" AS "risk_level" FROM "vendor";

-- S-091 | derived_metric | PASS
-- Question: From SalesOrderDetail, return SalesOrderID, SalesOrderDetailID, OrderQty, UnitPrice, UnitPriceDiscount, and OrderQty times UnitPrice times one minus UnitPriceDiscount as net_line_revenue.
SELECT SalesOrderID, SalesOrderDetailID, OrderQty, UnitPrice, UnitPriceDiscount, OrderQty * UnitPrice * (1 - UnitPriceDiscount) AS net_line_revenue FROM SalesOrderDetail;

-- S-092 | derived_metric | PASS
-- Question: From Product, return ProductID, Name, ListPrice, StandardCost, ListPrice minus StandardCost as margin_amount, and margin_amount divided by ListPrice as margin_percent.
SELECT ProductID, Name, ListPrice, StandardCost, (ListPrice - StandardCost) AS margin_amount, (ListPrice - StandardCost) / ListPrice AS margin_percent FROM Product;

-- S-093 | derived_metric | PASS
-- Question: Group SalesOrderDetail by SalesOrderID and return SUM of LineTotal divided by COUNT of lines as average_line_value.
SELECT SalesOrderID, SUM(LineTotal) * 1.0 / COUNT(*) AS average_line_value
FROM SalesOrderDetail
GROUP BY SalesOrderID;

-- S-094 | derived_metric | PASS
-- Question: From WorkOrder, return WorkOrderID, OrderQty, ScrappedQty, and ScrappedQty divided by NULLIF OrderQty as scrap_rate.
SELECT WorkOrderID, OrderQty, ScrappedQty, CAST(ScrappedQty AS REAL) / NULLIF(OrderQty, 0) AS scrap_rate
FROM WorkOrder;

-- S-095 | derived_metric | PASS
-- Question: From SalesPerson, return BusinessEntityID, SalesQuota, SalesYTD, and SalesYTD divided by NULLIF SalesQuota as quota_attainment.
SELECT BusinessEntityID, SalesQuota, SalesYTD, SalesYTD / NULLIF(SalesQuota, 0) AS quota_attainment FROM SalesPerson;

-- S-096 | window_cte | PASS
-- Question: Using joins from ProductCategory through Product to SalesOrderDetail, calculate product revenue and apply RANK partitioned by category ordered by revenue descending.
WITH ProductRevenue AS (
    SELECT
        pc.Name AS productcategory_name,
        p.Name AS product_name,
        SUM(sod.LineTotal) AS total_revenue,
        RANK() OVER (PARTITION BY pc.Name ORDER BY SUM(sod.LineTotal) DESC) AS revenue_rank
    FROM ProductCategory pc
    JOIN Product p ON pc.ProductCategoryID = p.ProductSubcategoryID
    JOIN SalesOrderDetail sod ON p.ProductID = sod.ProductID
    GROUP BY pc.Name, p.Name
)
SELECT productcategory_name
FROM ProductRevenue
WHERE revenue_rank = 1;

-- S-097 | window_cte | PASS
-- Question: Aggregate SalesOrderHeader by OrderDate and return a cumulative SUM of daily TotalDue ordered by OrderDate.
WITH DailyTotals AS (
    SELECT
        OrderDate,
        SUM(TotalDue) AS DailyTotalDue
    FROM SalesOrderHeader
    GROUP BY OrderDate
)
SELECT
    OrderDate,
    SUM(DailyTotalDue) OVER (ORDER BY OrderDate) AS CumulativeTotalDue
FROM DailyTotals
ORDER BY OrderDate;

-- S-098 | window_cte | PASS
-- Question: Use ROW_NUMBER partitioned by CustomerID ordered by OrderDate descending and keep row number 1.
WITH ranked_customers AS (
    SELECT 
        CustomerID,
        AccountNumber,
        ModifiedDate,
        ROW_NUMBER() OVER (PARTITION BY CustomerID ORDER BY ModifiedDate DESC) AS rn
    FROM Customer
)
SELECT 
    CustomerID,
    AccountNumber,
    ModifiedDate
FROM ranked_customers
WHERE rn = 1;

-- S-099 | window_cte | PASS
-- Question: Use ROW_NUMBER or RANK partitioned by TerritoryID and ordered by SalesYTD descending to return the top SalesPerson in each territory.
WITH RankedSales AS (
    SELECT 
        BusinessEntityID,
        TerritoryID,
        SalesYTD,
        ROW_NUMBER() OVER (PARTITION BY TerritoryID ORDER BY SalesYTD DESC) AS rn
    FROM SalesPerson
)
SELECT 
    BusinessEntityID,
    TerritoryID,
    SalesYTD
FROM RankedSales
WHERE rn = 1;

-- S-100 | window_cte | FAIL
-- Question: Build yearly territory sales in a CTE and use LAG to return current-year sales, previous-year sales, and year-over-year change.
-- No SQL generated.
