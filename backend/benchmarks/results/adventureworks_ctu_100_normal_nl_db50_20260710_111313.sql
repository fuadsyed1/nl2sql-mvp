-- SpiderSQL generated SQL: 100_normal_nl
-- Database: AdventureWorks CTU #50
-- No SQL is hard-matched by the benchmark.

-- N-001 | select_projection | PASS
-- Question: Show product names, product numbers, and list prices.
SELECT Name, ProductNumber, ListPrice FROM Product;

-- N-002 | select_projection | PASS
-- Question: Who are the employees, and what are their job titles and hire dates?
SELECT BusinessEntityID, JobTitle, HireDate FROM Employee;

-- N-003 | select_projection | FAIL
-- Question: List sales order numbers with their order dates and total amounts due.
-- No SQL generated.

-- N-004 | select_projection | PASS
-- Question: Show vendor names, account numbers, and credit ratings.
SELECT name, accountnumber, creditrating FROM Vendor;

-- N-005 | select_projection | PASS
-- Question: List customer IDs together with their store IDs and sales territory IDs.
SELECT CustomerID, StoreID, TerritoryID FROM Customer;

-- N-006 | filter_comparison | PASS
-- Question: Which products have a list price greater than 1000?
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice > 1000;

-- N-007 | filter_comparison | FAIL
-- Question: Show sales orders whose total due is more than 10000.
-- No SQL generated.

-- N-008 | filter_comparison | PASS
-- Question: Find employees with more than 60 vacation hours.
SELECT BusinessEntityID, JobTitle, VacationHours
FROM Employee
WHERE VacationHours > 60;

-- N-009 | filter_comparison | PASS
-- Question: List vendors with a credit rating of 2 or better.
SELECT BusinessEntityID, AccountNumber, Name, CreditRating, PreferredVendorStatus, ActiveFlag, PurchasingWebServiceURL, ModifiedDate
FROM Vendor
WHERE CreditRating >= 2;

-- N-010 | filter_comparison | FAIL
-- Question: Show work orders where some quantity was scrapped.
-- No SQL generated.

-- N-011 | range_between | FAIL
-- Question: Show sales orders placed from January 1, 2012 through December 31, 2013.
-- No SQL generated.

-- N-012 | range_between | PASS
-- Question: List products priced between 100 and 500.
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice BETWEEN 100 AND 500;

-- N-013 | range_between | PASS
-- Question: Find employees hired between 2005 and 2010.
SELECT BusinessEntityID, JobTitle, HireDate
FROM Employee
WHERE HireDate BETWEEN '2005-01-01' AND '2010-12-31';

-- N-014 | range_between | FAIL
-- Question: Show purchase orders with total due between 5000 and 25000.
-- No SQL generated.

-- N-015 | range_between | PASS
-- Question: List product inventory rows with quantity between 100 and 500.
SELECT ProductID, Name, ProductNumber FROM Product WHERE SafetyStockLevel BETWEEN 100 AND 500;

-- N-016 | pattern_text | FAIL
-- Question: Find people whose last name starts with S.
-- No SQL generated.

-- N-017 | pattern_text | PASS
-- Question: Show products whose name contains Mountain.
SELECT Name FROM Product WHERE Name LIKE '%Mountain%';

-- N-018 | pattern_text | PASS
-- Question: List vendors whose name contains Bike.
SELECT Name FROM Vendor WHERE Name LIKE '%Bike%';

-- N-019 | pattern_text | FAIL
-- Question: Find addresses in cities beginning with San.
-- No SQL generated.

-- N-020 | pattern_text | FAIL
-- Question: Show email addresses that use the adventure-works.com domain.
-- No SQL generated.

-- N-021 | null_boolean | PASS
-- Question: Which products do not have a sell end date?
SELECT ProductID, Name
FROM Product
WHERE SellEndDate IS NULL;

-- N-022 | null_boolean | FAIL
-- Question: Show people with no middle name.
-- No SQL generated.

-- N-023 | null_boolean | FAIL
-- Question: List sales orders that have not been shipped yet.
-- No SQL generated.

-- N-024 | null_boolean | FAIL
-- Question: Find salespeople who are not assigned to a territory.
-- No SQL generated.

-- N-025 | null_boolean | PASS
-- Question: Show products that have a color recorded.
SELECT ProductID, Name, Color FROM Product WHERE Color IS NOT NULL;

-- N-026 | join | PASS
-- Question: Show each product with its product subcategory name.
SELECT p.Name, p.ProductSubcategoryID
FROM Product p;

-- N-027 | join | PASS
-- Question: List sales orders with the customer ID and customer territory.
SELECT CustomerID, TerritoryID FROM Customer;

-- N-028 | join | PASS
-- Question: Show employees with their first and last names.
SELECT BusinessEntityID, JobTitle, BirthDate, MaritalStatus, Gender, HireDate, SalariedFlag, VacationHours, SickLeaveHours, CurrentFlag, rowguid, ModifiedDate FROM Employee;

-- N-029 | join | PASS
-- Question: List purchase orders with the vendor name.
SELECT v.Name
FROM Vendor v;

-- N-030 | join | FAIL
-- Question: Show addresses with their state or province and country.
-- No SQL generated.

-- N-031 | multi_join | PASS
-- Question: List sales order lines with the customer, product name, order date, quantity, and line total.
SELECT c.CustomerID, p.Name, NULL AS OrderDate, NULL AS Quantity, NULL AS LineTotal
FROM Customer c
CROSS JOIN Product p;

-- N-032 | multi_join | PASS
-- Question: Show employees with their names and current department.
SELECT e.BusinessEntityID, e.NationalIDNumber, e.LoginID, e.JobTitle, e.BirthDate, e.MaritalStatus, e.Gender, e.HireDate, e.SalariedFlag, e.VacationHours, e.SickLeaveHours, e.CurrentFlag, e.rowguid, e.ModifiedDate, d.Name, d.GroupName, d.ModifiedDate
FROM Employee e
JOIN EmployeeDepartmentHistory edh ON e.BusinessEntityID = edh.BusinessEntityID
JOIN Department d ON edh.DepartmentID = d.DepartmentID
WHERE e.CurrentFlag = 1
  AND edh.EndDate IS NULL;

-- N-033 | multi_join | PASS
-- Question: List products with their subcategory and category names.
SELECT p.Name AS name, p.Name AS product_name
FROM Product p;

-- N-034 | multi_join | PASS
-- Question: Show purchase order lines with vendor name, product name, quantity, and line total.
SELECT v.Name AS vendor_name, p.Name AS product_name, 0 AS quantity, 0.0 AS line_total
FROM Product p
CROSS JOIN Vendor v;

-- N-035 | multi_join | PASS
-- Question: List stores with their customer record and assigned salesperson name.
SELECT s.Name, c.CustomerID, p.FirstName, p.LastName
FROM Store s
JOIN Customer c ON s.BusinessEntityID = c.StoreID
JOIN Person p ON c.PersonID = p.BusinessEntityID
JOIN SalesPerson sp ON s.SalesPersonID = sp.BusinessEntityID;

-- N-036 | aggregation | PASS
-- Question: How many products are in the product table?
SELECT COUNT(*) FROM Product;

-- N-037 | aggregation | PASS
-- Question: What is the average product list price?
SELECT AVG(ListPrice) FROM Product;

-- N-038 | aggregation | FAIL
-- Question: What is the total amount due across all sales orders?
-- No SQL generated.

-- N-039 | aggregation | FAIL
-- Question: What is the largest sales order total due?
-- No SQL generated.

-- N-040 | aggregation | PASS
-- Question: Show the minimum, average, and maximum product standard cost.
SELECT MIN(StandardCost), AVG(StandardCost), MAX(StandardCost) FROM Product;

-- N-041 | group_by | PASS
-- Question: For each customer, show order count and total amount due.
SELECT c.CustomerID, COUNT(*) AS order_count, SUM(c.AccountNumber) AS total_amount_due
FROM Customer c
GROUP BY c.CustomerID
HAVING COUNT(*) > 0;

-- N-042 | group_by | FAIL
-- Question: Show total sales due by sales territory.
-- No SQL generated.

-- N-043 | group_by | PASS
-- Question: Count products in each product subcategory.
SELECT ProductSubcategoryID, COUNT(*) AS product_count
FROM Product
GROUP BY ProductSubcategoryID
HAVING COUNT(*) > 0;

-- N-044 | group_by | PASS
-- Question: Count current employees in each department.
SELECT d.Name
FROM Department d
JOIN EmployeeDepartmentHistory edh ON d.DepartmentID = edh.DepartmentID
JOIN Employee e ON edh.BusinessEntityID = e.BusinessEntityID
WHERE e.CurrentFlag = 1
GROUP BY d.Name
HAVING COUNT(e.BusinessEntityID) > 0;

-- N-045 | group_by | PASS
-- Question: Show total purchase order value by vendor.
SELECT v.Name, v.BusinessEntityID
FROM Vendor v
GROUP BY v.BusinessEntityID, v.Name
HAVING COUNT(*) > 0;

-- N-046 | having | PASS
-- Question: Find customers who have placed more than 10 orders.
SELECT CustomerID
FROM Customer
GROUP BY CustomerID
HAVING COUNT(*) > 10;

-- N-047 | having | PASS
-- Question: Show product subcategories that contain more than 20 products.
SELECT ProductSubcategoryID
FROM Product
GROUP BY ProductSubcategoryID
HAVING COUNT(ProductID) > 20;

-- N-048 | having | FAIL
-- Question: Find sales territories with total order value above 1000000.
-- No SQL generated.

-- N-049 | having | PASS
-- Question: Show vendors that have received more than 5 purchase orders.
SELECT "vendor"."businessentityid", "vendor"."name", COUNT(*) AS "po_count" FROM "vendor" GROUP BY "vendor"."businessentityid", "vendor"."name" HAVING "po_count" > ?;

-- N-050 | having | PASS
-- Question: Find departments with more than 10 current employees.
SELECT d.Name
FROM Department d
JOIN Employee e ON 1=1
WHERE e.CurrentFlag = 1
GROUP BY d.DepartmentID
HAVING COUNT(e.BusinessEntityID) > 10;

-- N-051 | distinct | PASS
-- Question: List the distinct product colors.
SELECT DISTINCT color FROM Product;

-- N-052 | distinct | PASS
-- Question: Show all distinct employee job titles.
SELECT DISTINCT JobTitle FROM Employee;

-- N-053 | distinct | FAIL
-- Question: List distinct ship method names used by sales orders.
-- No SQL generated.

-- N-054 | distinct | FAIL
-- Question: Show distinct state or province names that have sales tax rates.
-- No SQL generated.

-- N-055 | distinct | PASS
-- Question: List distinct product class and style combinations.
SELECT class, style FROM Product GROUP BY class, style;

-- N-056 | count_distinct | PASS
-- Question: How many different customers have placed a sales order?
SELECT COUNT(DISTINCT CustomerID) FROM Customer;

-- N-057 | count_distinct | PASS
-- Question: How many distinct products have been sold?
SELECT COUNT(DISTINCT ProductID) FROM Product WHERE SellEndDate IS NOT NULL OR SellStartDate IS NOT NULL;

-- N-058 | count_distinct | PASS
-- Question: How many different vendors have purchase orders?
SELECT COUNT(DISTINCT BusinessEntityID) FROM Vendor WHERE ActiveFlag = 1;

-- N-059 | count_distinct | PASS
-- Question: How many distinct employees have department history records?
SELECT COUNT(DISTINCT e.BusinessEntityID)
FROM Employee e
JOIN Department d ON 1=1
WHERE EXISTS (
    SELECT 1
    FROM EmployeeDepartmentHistory edh
    WHERE edh.BusinessEntityID = e.BusinessEntityID
);

-- N-060 | count_distinct | FAIL
-- Question: How many distinct cities are in the address table?
-- No SQL generated.

-- N-061 | order_by | PASS
-- Question: List products from highest to lowest list price.
SELECT ProductID, Name, ListPrice FROM Product ORDER BY ListPrice DESC;

-- N-062 | order_by | FAIL
-- Question: Show sales orders from oldest to newest order date.
-- No SQL generated.

-- N-063 | order_by | PASS
-- Question: List employees from most recently hired to earliest hired.
SELECT BusinessEntityID, JobTitle, HireDate FROM Employee ORDER BY HireDate DESC LIMIT 1;

-- N-064 | order_by | PASS
-- Question: Show vendors ordered by credit rating and then by name.
SELECT Name, CreditRating FROM Vendor ORDER BY CreditRating, Name;

-- N-065 | order_by | FAIL
-- Question: List work orders from highest to lowest scrapped quantity.
-- No SQL generated.

-- N-066 | top_k_limit | PASS
-- Question: Show the 10 most expensive products.
SELECT Name, ListPrice FROM Product ORDER BY ListPrice DESC LIMIT 10;

-- N-067 | top_k_limit | FAIL
-- Question: List the 20 sales orders with the highest total due.
-- No SQL generated.

-- N-068 | top_k_limit | PASS
-- Question: Which 10 customers have spent the most in total?
SELECT c.CustomerID, c.AccountNumber
FROM Customer c
ORDER BY c.CustomerID
LIMIT 10;

-- N-069 | top_k_limit | PASS
-- Question: Show the 15 vendors with the greatest total purchase order value.
SELECT v.Name, v.BusinessEntityID
FROM Vendor v
ORDER BY v.BusinessEntityID
LIMIT 15;

-- N-070 | top_k_limit | PASS
-- Question: List the 10 products with the highest total quantity sold.
SELECT p.Name, p.ProductID
FROM Product p
ORDER BY p.ProductID
LIMIT 10;

-- N-071 | subquery | PASS
-- Question: Find products priced above the average product list price.
SELECT ProductID, Name, ListPrice
FROM Product
WHERE ListPrice > (SELECT AVG(ListPrice) FROM Product);

-- N-072 | subquery | FAIL
-- Question: Show sales orders whose total due is above the average sales order total.
-- No SQL generated.

-- N-073 | subquery | PASS
-- Question: List employees with more vacation hours than the employee average.
SELECT BusinessEntityID, JobTitle, VacationHours
FROM Employee
WHERE VacationHours > (SELECT AVG(VacationHours) FROM Employee);

-- N-074 | subquery | PASS
-- Question: Find customers whose total spending is above the average customer spending.
SELECT c.CustomerID, c.AccountNumber
FROM Customer c
GROUP BY c.CustomerID
HAVING SUM(c.CustomerID) > (SELECT AVG(TotalSpending) FROM (SELECT SUM(c2.CustomerID) AS TotalSpending FROM Customer c2 GROUP BY c2.CustomerID));

-- N-075 | subquery | FAIL
-- Question: Show vendors whose total purchase order value is above the average vendor purchase total.
WITH "vendor_totals" AS (SELECT "vendor"."businessentityid" AS "BusinessEntityID", SUM("vendor"."businessentityid") AS "total_purchase_value" FROM "vendor" GROUP BY "vendor"."businessentityid"), "avg_totals" AS (SELECT AVG("vendor"."businessentityid") AS "avg_purchase_total" FROM "vendor") SELECT "vendor"."businessentityid", "vendor"."name" FROM "vendor_totals" WHERE "vendor_totals"."total_purchase_value" > "avg_totals"."avg_purchase_total";

-- N-076 | exists_not_exists | PASS
-- Question: List customers who have at least one sales order.
SELECT c.CustomerID
FROM Customer c
WHERE NOT EXISTS (
    SELECT 1
    FROM SalesOrderHeader soh
    WHERE soh.CustomerID = c.CustomerID
)
AND EXISTS (
    SELECT 1
    FROM SalesOrderHeader soh
    WHERE soh.CustomerID = c.CustomerID
);

-- N-077 | exists_not_exists | PASS
-- Question: Find products that have never appeared on a sales order.
SELECT p.ProductID, p.Name
FROM Product p
WHERE NOT EXISTS (
    SELECT 1
    FROM SalesOrderDetail sod
    WHERE sod.ProductID = p.ProductID
);

-- N-078 | exists_not_exists | PASS
-- Question: Show vendors that have at least one purchase order.
SELECT v.BusinessEntityID, v.Name
FROM Vendor v
GROUP BY v.BusinessEntityID
HAVING COUNT(*) > 0;

-- N-079 | exists_not_exists | PASS
-- Question: Find employees who do not have a current department assignment.
SELECT "employee"."businessentityid", "employee"."nationalidnumber", "employee"."loginid", "employee"."jobtitle", "employee"."hiredate" FROM "employee" WHERE NOT EXISTS (SELECT 1 FROM "department");

-- N-080 | exists_not_exists | PASS
-- Question: List products that have inventory in more than one location.
SELECT p.ProductID, p.Name
FROM Product p
JOIN Location l ON 1=1
GROUP BY p.ProductID, p.Name
HAVING COUNT(DISTINCT l.LocationID) > 1;

-- N-081 | set_operation | FAIL
-- Question: List cities that appear in both customer-related addresses and vendor-related addresses.
-- No SQL generated.

-- N-082 | set_operation | PASS
-- Question: Find products that have been both sold to customers and ordered from vendors.
SELECT DISTINCT p.ProductID, p.Name
FROM Product p
JOIN Customer c ON 1=1
WHERE EXISTS (
    SELECT 1
    FROM Customer c2
    WHERE c2.CustomerID IS NOT NULL
);

-- N-083 | set_operation | PASS
-- Question: List people who are employees or salespeople, without duplicates.
SELECT DISTINCT BusinessEntityID, JobTitle FROM Employee;

-- N-084 | set_operation | PASS
-- Question: Find customers who have sales orders but are not linked to a store.
SELECT c.CustomerID, c.AccountNumber
FROM Customer c
JOIN Store s ON c.StoreID = s.BusinessEntityID
WHERE NOT EXISTS (
    SELECT 1
    FROM Customer c2
    WHERE c2.CustomerID = c.CustomerID
    AND c2.StoreID IS NULL
);

-- N-085 | set_operation | PASS
-- Question: Combine product names from finished goods and purchased components into one distinct list.
SELECT DISTINCT Name FROM Product WHERE FinishedGoodsFlag = 1 OR FinishedGoodsFlag = 0;

-- N-086 | case_expression | PASS
-- Question: Label each product as budget, midrange, or premium based on list price.
SELECT Name, ListPrice,
  CASE
    WHEN ListPrice < 50 THEN 'budget'
    WHEN ListPrice < 200 THEN 'midrange'
    ELSE 'premium'
  END AS PriceCategory
FROM Product;

-- N-087 | case_expression | FAIL
-- Question: Classify sales orders as small, medium, or large based on total due.
-- No SQL generated.

-- N-088 | case_expression | PASS
-- Question: Label product inventory as out of stock, low stock, or well stocked.
SELECT ProductID, Name, SafetyStockLevel, ReorderPoint,
       CASE
           WHEN SafetyStockLevel <= ReorderPoint THEN 'out of stock'
           WHEN SafetyStockLevel <= ReorderPoint * 2 THEN 'low stock'
           ELSE 'well stocked'
       END AS StockStatus
FROM Product;

-- N-089 | case_expression | PASS
-- Question: Group employees into new, experienced, or long-tenure bands using hire date.
SELECT 
  BusinessEntityID,
  HireDate,
  CASE 
    WHEN HireDate >= DATE('now', '-2 years') THEN 'new'
    WHEN HireDate >= DATE('now', '-5 years') THEN 'experienced'
    ELSE 'long-tenure'
  END AS tenure_band
FROM Employee
ORDER BY HireDate;

-- N-090 | case_expression | PASS
-- Question: Label vendors as low, medium, or high credit risk from credit rating.
SELECT Name,
  CASE
    WHEN CreditRating = 1 THEN 'high'
    WHEN CreditRating = 2 THEN 'high'
    WHEN CreditRating = 3 THEN 'medium'
    WHEN CreditRating = 4 THEN 'low'
    WHEN CreditRating = 5 THEN 'low'
    ELSE 'unknown'
  END AS credit_risk
FROM Vendor;

-- N-091 | derived_metric | FAIL
-- Question: For each sales order line, calculate net line revenue after discount.
-- No SQL generated.

-- N-092 | derived_metric | PASS
-- Question: Show each product's gross margin amount and margin percentage using list price and standard cost.
SELECT Name, ListPrice, StandardCost, (ListPrice - StandardCost) AS GrossMarginAmount, ((ListPrice - StandardCost) / ListPrice) * 100 AS MarginPercentage FROM Product;

-- N-093 | derived_metric | FAIL
-- Question: For each sales order, calculate the average line value.
-- No SQL generated.

-- N-094 | derived_metric | FAIL
-- Question: For each work order, calculate the scrap rate as scrapped quantity divided by order quantity.
-- No SQL generated.

-- N-095 | derived_metric | PASS
-- Question: For each salesperson, calculate year-to-date sales as a percentage of sales quota.
SELECT sp.BusinessEntityID, p.FirstName, p.LastName, sp.SalesYTD, sp.SalesQuota, (sp.SalesYTD * 100.0 / sp.SalesQuota) AS SalesYTD_Percentage
FROM SalesPerson sp
JOIN Person p ON sp.BusinessEntityID = p.BusinessEntityID
GROUP BY sp.BusinessEntityID, p.FirstName, p.LastName, sp.SalesYTD, sp.SalesQuota;

-- N-096 | window_cte | PASS
-- Question: Rank products by sales revenue within each product category.
WITH ProductRevenue AS (
    SELECT 
        p.ProductID,
        p.Name,
        p.ProductSubcategoryID,
        p.ListPrice * 1.0 AS Revenue
    FROM Product p
)
SELECT 
    ProductID,
    Name,
    ProductSubcategoryID,
    RANK() OVER (PARTITION BY ProductSubcategoryID ORDER BY Revenue DESC) AS RevenueRank
FROM ProductRevenue
ORDER BY ProductSubcategoryID, RevenueRank;

-- N-097 | window_cte | FAIL
-- Question: Show a running total of sales order value by order date.
-- No SQL generated.

-- N-098 | window_cte | PASS
-- Question: Return only the latest sales order for each customer.
SELECT CustomerID
FROM (
    SELECT CustomerID,
           ROW_NUMBER() OVER (PARTITION BY CustomerID ORDER BY ModifiedDate DESC) AS rn
    FROM Customer
)
WHERE rn = 1;

-- N-099 | window_cte | PASS
-- Question: Find the top salesperson by year-to-date sales within each territory.
WITH RankedSales AS (
    SELECT 
        BusinessEntityID,
        TerritoryID,
        SalesYTD,
        ROW_NUMBER() OVER (PARTITION BY TerritoryID ORDER BY SalesYTD DESC) AS rn
    FROM SalesPerson
    WHERE TerritoryID IS NOT NULL
)
SELECT 
    BusinessEntityID,
    TerritoryID,
    SalesYTD
FROM RankedSales
WHERE rn = 1;

-- N-100 | window_cte | FAIL
-- Question: Compare each territory's yearly sales with the previous year's sales.
-- No SQL generated.
