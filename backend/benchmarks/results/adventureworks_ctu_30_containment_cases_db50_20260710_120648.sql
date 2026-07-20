-- SpiderSQL containment generated SQL: 30_containment_cases
-- Database: AdventureWorks CTU #50

-- CASE 01 | normal | filter_threshold | PASS
-- Q1: Which products cost more than 1500?
SELECT ProductID, Name, StandardCost, ListPrice FROM Product WHERE StandardCost > 1500;

-- Q2: Which products cost more than 1000?
SELECT ProductID, Name, StandardCost, ListPrice FROM Product WHERE StandardCost > 1000;

-- Q3: Which products cost more than 500?
SELECT ProductID, Name, StandardCost FROM Product WHERE StandardCost > 500;

-- Q4: Which products cost more than 2000?
SELECT ProductID, Name, StandardCost FROM Product WHERE StandardCost > 2000;

-- CASE 02 | normal | filter_threshold | FAIL
-- Q1: Show sales orders with total due above 20000.
-- No SQL generated.

-- Q2: Show sales orders with total due above 10000.
-- No SQL generated.

-- Q3: Show sales orders with total due above 5000.
-- No SQL generated.

-- Q4: Show sales orders with total due above 30000.
-- No SQL generated.

-- CASE 03 | normal | conjunction | PASS
-- Q1: Find employees hired after 2010 who have more than 50 vacation hours.
SELECT BusinessEntityID, JobTitle, HireDate, VacationHours
FROM Employee
WHERE HireDate > '2010-12-31'
  AND VacationHours > 50;

-- Q2: Find employees hired after 2010.
SELECT BusinessEntityID, JobTitle, HireDate FROM Employee WHERE HireDate > '2010-12-31';

-- Q3: Find employees with more than 50 vacation hours.
SELECT BusinessEntityID, JobTitle, VacationHours
FROM Employee
WHERE VacationHours > 50;

-- Q4: Find employees hired after 2005 who have more than 30 vacation hours.
SELECT BusinessEntityID, JobTitle, HireDate, VacationHours
FROM Employee
WHERE HireDate > '2005-12-31' AND VacationHours > 30;

-- CASE 04 | normal | conjunction | PASS
-- Q1: List active vendors with credit rating 1.
SELECT BusinessEntityID, Name, CreditRating, ActiveFlag
FROM Vendor
WHERE CreditRating = 1 AND ActiveFlag = 1;

-- Q2: List active vendors.
SELECT BusinessEntityID, AccountNumber, Name, CreditRating, PreferredVendorStatus, ActiveFlag, PurchasingWebServiceURL, ModifiedDate FROM Vendor WHERE ActiveFlag = 1;

-- Q3: List vendors with credit rating 1.
SELECT BusinessEntityID, AccountNumber, Name, CreditRating, PreferredVendorStatus, ActiveFlag, PurchasingWebServiceURL, ModifiedDate FROM Vendor WHERE CreditRating = 1;

-- Q4: List active vendors with credit rating 2 or better.
SELECT vendor.BusinessEntityID, vendor.Name, vendor.CreditRating
FROM Vendor
WHERE vendor.CreditRating <= 2 AND vendor.ActiveFlag = 1;

-- CASE 05 | normal | conjunction | PASS
-- Q1: Show red products priced above 1000.
SELECT ProductID, Name, ProductNumber, Color, ListPrice FROM Product WHERE Color = 'Red' AND ListPrice > 1000;

-- Q2: Show red products.
SELECT ProductID, Name, ProductNumber, Color FROM Product WHERE Color = 'Red';

-- Q3: Show products priced above 1000.
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice > 1000;

-- Q4: Show colored products priced above 500.
SELECT Name, Color, ListPrice FROM Product WHERE Color IS NOT NULL AND ListPrice > 500;

-- CASE 06 | normal | join | FAIL
-- CASE 07 | normal | multi_join | FAIL
-- Q1: List bikes priced above 1000 with their category and subcategory.
-- No SQL generated.

-- Q2: List all bike products with their category and subcategory.
SELECT "product"."name", "product"."productline", "product"."productsubcategoryid" FROM "product" WHERE "product"."productline" = ?;

-- Q3: List all products priced above 1000 with their category and subcategory.
SELECT Name, ProductSubcategoryID, ProductModelID
FROM Product
WHERE ListPrice > 1000;

-- Q4: List products in any category priced above 500 with category and subcategory.
SELECT Name, ProductSubcategoryID, ListPrice FROM Product WHERE ListPrice > 500;

-- CASE 08 | normal | derived_metric | FAIL
-- Q1: Show sales order lines with net line revenue above 5000 and quantity above 5.
-- No SQL generated.

-- Q2: Show sales order lines with net line revenue above 5000.
-- No SQL generated.

-- Q3: Show sales order lines with quantity above 5.
-- No SQL generated.

-- Q4: Show sales order lines with net line revenue above 2500 and quantity above 2.
-- No SQL generated.

-- CASE 09 | normal | join | PASS
-- Q1: List active vendors with purchase orders above 20000.
SELECT "vendor"."name" FROM "vendor" WHERE "vendor"."activeflag" = ?;

-- Q2: List active vendors with any purchase order.
SELECT "vendor"."businessentityid", "vendor"."name" FROM "vendor" WHERE "vendor"."activeflag" = ?;

-- Q3: List vendors with purchase orders above 20000.
SELECT "vendor"."businessentityid", "vendor"."name" FROM "vendor";

-- Q4: List active vendors with purchase orders above 10000.
SELECT "vendor"."businessentityid", "vendor"."name" FROM "vendor" WHERE "vendor"."activeflag" = ?;

-- CASE 10 | normal | filter_threshold | FAIL
-- Q1: Show work orders with more than 10 scrapped units.
-- No SQL generated.

-- Q2: Show work orders with more than 5 scrapped units.
-- No SQL generated.

-- Q3: Show work orders with any scrapped units.
-- No SQL generated.

-- Q4: Show work orders with more than 20 scrapped units.
-- No SQL generated.

-- CASE 11 | normal | join | FAIL
-- CASE 12 | normal | group_having | PASS
-- Q1: Show departments with more than 20 current employees.
SELECT d.Name
FROM Department d
JOIN Employee e ON 1=1
WHERE e.CurrentFlag = 1
GROUP BY d.DepartmentID, d.Name
HAVING COUNT(e.BusinessEntityID) > 20;

-- Q2: Show departments with more than 10 current employees.
SELECT d.Name
FROM Department d
JOIN Employee e ON 1=1
WHERE e.CurrentFlag = 1
GROUP BY d.DepartmentID
HAVING COUNT(e.BusinessEntityID) > 10;

-- Q3: Show departments with at least one current employee.
SELECT d.Name
FROM Department d
JOIN Employee e ON 1=1
WHERE e.CurrentFlag = 1
GROUP BY d.DepartmentID, d.Name
HAVING COUNT(*) >= 1;

-- Q4: Show departments with more than 30 current employees.
SELECT d.Name
FROM Department d
JOIN Employee e ON d.DepartmentID = e.BusinessEntityID
WHERE e.CurrentFlag = '1'
GROUP BY d.DepartmentID
HAVING COUNT(e.BusinessEntityID) > 30;

-- CASE 13 | normal | derived_metric | FAIL
-- Q1: List salespeople whose year-to-date sales exceed 150 percent of quota.
-- No SQL generated.

-- Q2: List salespeople whose year-to-date sales exceed quota.
-- No SQL generated.

-- Q3: List salespeople who have a nonzero sales quota.
-- No SQL generated.

-- Q4: List salespeople whose year-to-date sales exceed 200 percent of quota.
-- No SQL generated.

-- CASE 14 | normal | filter_threshold | PASS
-- Q1: Show product inventory rows with quantity above 500.
SELECT "product".* FROM "product" WHERE "product"."safetystocklevel" > ?;

-- Q2: Show product inventory rows with quantity above 250.
SELECT ProductID, Name, ProductNumber, MakeFlag, FinishedGoodsFlag, Color, SafetyStockLevel, ReorderPoint, StandardCost, ListPrice, Size, SizeUnitMeasureCode, WeightUnitMeasureCode, Weight, DaysToManufacture, ProductLine, Class, Style, ProductSubcategoryID, ProductModelID, SellStartDate, SellEndDate, DiscontinuedDate, rowguid, ModifiedDate
FROM Product
WHERE SafetyStockLevel > 250 OR ReorderPoint > 250;

-- Q3: Show product inventory rows with quantity above 100.
SELECT "product".* FROM "product" WHERE "product"."safetystocklevel" > ?;

-- Q4: Show product inventory rows with quantity above 750.
SELECT ProductID, Name, ProductNumber, Color, SafetyStockLevel, ReorderPoint, StandardCost, ListPrice, Size, Weight, DaysToManufacture, ProductLine, Class, Style, ProductSubcategoryID, ProductModelID, SellStartDate, SellEndDate, DiscontinuedDate, rowguid, ModifiedDate
FROM Product
WHERE SafetyStockLevel > 750;

-- CASE 15 | normal | date_and_status | FAIL
-- Q1: Show shipped sales orders placed after 2013.
-- No SQL generated.

-- Q2: Show sales orders placed after 2013.
-- No SQL generated.

-- Q3: Show shipped sales orders.
-- No SQL generated.

-- Q4: Show completed sales orders placed after 2012.
-- No SQL generated.

-- CASE 16 | structured | filter_threshold | PASS
-- Q1: Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 1500.
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice > 1500;

-- Q2: Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 1000.
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice > 1000;

-- Q3: Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 500.
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice > 500;

-- Q4: Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 2000.
SELECT ProductID, Name, ListPrice FROM Product WHERE ListPrice > 2000;

-- CASE 17 | structured | filter_threshold | PASS
-- Q1: Return SalesOrderID, CustomerID, OrderDate, and TotalDue from SalesOrderHeader where TotalDue is greater than 20000.
SELECT SalesOrderID, CustomerID, OrderDate, TotalDue
FROM SalesOrderHeader
WHERE TotalDue > 20000;

-- Q2: Return SalesOrderID, CustomerID, OrderDate, and TotalDue from SalesOrderHeader where TotalDue is greater than 10000.
SELECT SalesOrderID, CustomerID, OrderDate, TotalDue FROM SalesOrderHeader WHERE TotalDue > 10000;

-- Q3: Return SalesOrderID, CustomerID, OrderDate, and TotalDue from SalesOrderHeader where TotalDue is greater than 5000.
SELECT SalesOrderID, CustomerID, OrderDate, TotalDue
FROM SalesOrderHeader
WHERE TotalDue > 5000;

-- Q4: Return SalesOrderID, CustomerID, OrderDate, and TotalDue from SalesOrderHeader where TotalDue is greater than 30000.
SELECT SalesOrderID, CustomerID, OrderDate, TotalDue
FROM SalesOrderHeader
WHERE TotalDue > 30000;

-- CASE 18 | structured | conjunction | FAIL
-- Q1: Return BusinessEntityID, JobTitle, HireDate, and VacationHours from Employee where HireDate is after 2010-01-01 and VacationHours is greater than 50.
-- No SQL generated.

-- Q2: Return BusinessEntityID, JobTitle, HireDate, and VacationHours from Employee where HireDate is after 2010-01-01.
-- No SQL generated.

-- Q3: Return BusinessEntityID, JobTitle, HireDate, and VacationHours from Employee where VacationHours is greater than 50.
SELECT BusinessEntityID, JobTitle, HireDate, VacationHours
FROM Employee
WHERE VacationHours > 50;

-- Q4: Return BusinessEntityID, JobTitle, HireDate, and VacationHours from Employee where HireDate is after 2005-01-01 and VacationHours is greater than 30.
-- No SQL generated.

-- CASE 19 | structured | conjunction | PASS
-- Q1: Return BusinessEntityID, Name, CreditRating, and ActiveFlag from Vendor where ActiveFlag is true and CreditRating equals 1.
SELECT BusinessEntityID, Name, CreditRating, ActiveFlag
FROM Vendor
WHERE ActiveFlag = 1 AND CreditRating = 1;

-- Q2: Return BusinessEntityID, Name, CreditRating, and ActiveFlag from Vendor where ActiveFlag is true.
SELECT BusinessEntityID, Name, CreditRating, ActiveFlag
FROM Vendor
WHERE ActiveFlag = 1;

-- Q3: Return BusinessEntityID, Name, CreditRating, and ActiveFlag from Vendor where CreditRating equals 1.
SELECT Vendor.BusinessEntityID, Vendor.Name, Vendor.CreditRating, Vendor.ActiveFlag
FROM Vendor
WHERE Vendor.CreditRating = 1;

-- Q4: Return BusinessEntityID, Name, CreditRating, and ActiveFlag from Vendor where ActiveFlag is true and CreditRating is less than or equal to 2.
SELECT BusinessEntityID, Name, CreditRating, ActiveFlag
FROM Vendor
WHERE ActiveFlag = 1 AND CreditRating <= 2;

-- CASE 20 | structured | conjunction | PASS
-- Q1: Return ProductID, Name, Color, and ListPrice from Product where Color equals Red and ListPrice is greater than 1000.
SELECT ProductID, Name, Color, ListPrice FROM Product WHERE Color = 'Red' AND ListPrice > 1000;

-- Q2: Return ProductID, Name, Color, and ListPrice from Product where Color equals Red.
SELECT ProductID, Name, Color, ListPrice FROM Product WHERE Color = 'Red';

-- Q3: Return ProductID, Name, Color, and ListPrice from Product where ListPrice is greater than 1000.
SELECT ProductID, Name, Color, ListPrice FROM Product WHERE ListPrice > 1000;

-- Q4: Return ProductID, Name, Color, and ListPrice from Product where Color is not null and ListPrice is greater than 500.
SELECT ProductID, Name, Color, ListPrice FROM Product WHERE Color IS NOT NULL AND ListPrice > 500;

-- CASE 21 | structured | join | PASS
-- Q1: Return distinct CustomerID and TerritoryID by joining Customer to SalesOrderHeader, where Customer TerritoryID equals 1.
SELECT DISTINCT c.CustomerID, c.TerritoryID
FROM Customer c
JOIN SalesOrderHeader soh ON c.CustomerID = soh.CustomerID
WHERE c.TerritoryID = 1;

-- Q2: Return CustomerID and TerritoryID from Customer where TerritoryID equals 1.
SELECT CustomerID, TerritoryID FROM Customer WHERE TerritoryID = 1;

-- Q3: Return distinct CustomerID and TerritoryID by joining Customer to SalesOrderHeader.
SELECT DISTINCT c.CustomerID, c.TerritoryID
FROM Customer c
JOIN SalesOrderHeader soh ON c.CustomerID = soh.CustomerID;

-- Q4: Return distinct CustomerID and TerritoryID by joining Customer to SalesOrderHeader where TerritoryID is not null.
SELECT DISTINCT c.CustomerID, c.TerritoryID
FROM Customer c
JOIN SalesOrderHeader soh ON c.CustomerID = soh.CustomerID
WHERE soh.TerritoryID IS NOT NULL;

-- CASE 22 | structured | multi_join | PASS
-- Q1: Join Product, ProductSubcategory, and ProductCategory; return ProductID, product Name, subcategory Name, category Name, and ListPrice where category Name equals Bikes and ListPrice is greater than 1000.
SELECT p.ProductID, p.Name, ps.Name AS SubcategoryName, pc.Name AS CategoryName, p.ListPrice
FROM Product p
JOIN ProductSubcategory ps ON p.ProductSubcategoryID = ps.ProductSubcategoryID
JOIN ProductCategory pc ON ps.ProductCategoryID = pc.ProductCategoryID
WHERE pc.Name = 'Bikes' AND p.ListPrice > 1000;

-- Q2: Join Product, ProductSubcategory, and ProductCategory; return the same columns where category Name equals Bikes.
SELECT p.*, ps.*, pc.*
FROM Product p
JOIN ProductSubcategory ps ON p.ProductSubcategoryID = ps.ProductSubcategoryID
JOIN ProductCategory pc ON ps.ProductCategoryID = pc.ProductCategoryID
WHERE pc.Name = 'Bikes';

-- Q3: Join Product, ProductSubcategory, and ProductCategory; return the same columns where ListPrice is greater than 1000.
SELECT p.ProductID, p.Name, p.ProductNumber, p.MakeFlag, p.FinishedGoodsFlag, p.Color, p.SafetyStockLevel, p.ReorderPoint, p.StandardCost, p.ListPrice, p.Size, p.SizeUnitMeasureCode, p.WeightUnitMeasureCode, p.Weight, p.DaysToManufacture, p.ProductLine, p.Class, p.Style, p.ProductSubcategoryID, p.ProductModelID, p.SellStartDate, p.SellEndDate, p.DiscontinuedDate, p.rowguid, p.ModifiedDate, ps.ProductSubcategoryID, ps.ProductCategoryID, ps.Name, ps.rowguid, ps.ModifiedDate, pc.ProductCategoryID, pc.Name, pc.rowguid, pc.ModifiedDate
FROM Product p
JOIN ProductSubcategory ps ON p.ProductSubcategoryID = ps.ProductSubcategoryID
JOIN ProductCategory pc ON ps.ProductCategoryID = pc.ProductCategoryID
WHERE p.ListPrice > 1000;

-- Q4: Join Product, ProductSubcategory, and ProductCategory; return the same columns where ListPrice is greater than 500.
SELECT p.ProductID, p.Name, p.ProductNumber, p.MakeFlag, p.FinishedGoodsFlag, p.Color, p.SafetyStockLevel, p.ReorderPoint, p.StandardCost, p.ListPrice, p.Size, p.SizeUnitMeasureCode, p.WeightUnitMeasureCode, p.Weight, p.DaysToManufacture, p.ProductLine, p.Class, p.Style, p.ProductSubcategoryID, p.ProductModelID, p.SellStartDate, p.SellEndDate, p.DiscontinuedDate, p.rowguid, p.ModifiedDate, ps.ProductSubcategoryID, ps.ProductCategoryID, ps.Name, ps.rowguid, ps.ModifiedDate, pc.ProductCategoryID, pc.Name, pc.rowguid, pc.ModifiedDate
FROM Product p
JOIN ProductSubcategory ps ON p.ProductSubcategoryID = ps.ProductSubcategoryID
JOIN ProductCategory pc ON ps.ProductCategoryID = pc.ProductCategoryID
WHERE p.ListPrice > 500;

-- CASE 23 | structured | derived_metric | PASS
-- Q1: From SalesOrderDetail, return SalesOrderID, SalesOrderDetailID, OrderQty, and net line revenue where net line revenue is greater than 5000 and OrderQty is greater than 5.
SELECT SalesOrderID, SalesOrderDetailID, OrderQty, LineTotal
FROM SalesOrderDetail
WHERE LineTotal > 5000 AND OrderQty > 5;

-- Q2: From SalesOrderDetail, return the same columns where net line revenue is greater than 5000.
SELECT SalesOrderID, SalesOrderDetailID, CarrierTrackingNumber, OrderQty, ProductID, SpecialOfferID, UnitPrice, UnitPriceDiscount, LineTotal, rowguid, ModifiedDate
FROM SalesOrderDetail
WHERE LineTotal > 5000;

-- Q3: From SalesOrderDetail, return the same columns where OrderQty is greater than 5.
SELECT SalesOrderID, SalesOrderDetailID, CarrierTrackingNumber, OrderQty, ProductID, SpecialOfferID, UnitPrice, UnitPriceDiscount, LineTotal, rowguid, ModifiedDate
FROM SalesOrderDetail
WHERE OrderQty > 5;

-- Q4: From SalesOrderDetail, return the same columns where net line revenue is greater than 2500 and OrderQty is greater than 2.
SELECT SalesOrderID, SalesOrderDetailID, CarrierTrackingNumber, OrderQty, ProductID, SpecialOfferID, UnitPrice, UnitPriceDiscount, LineTotal, rowguid, ModifiedDate
FROM SalesOrderDetail
WHERE LineTotal > 2500 AND OrderQty > 2;

-- CASE 24 | structured | join | PASS
-- Q1: Join Vendor to PurchaseOrderHeader and return VendorID, vendor Name, PurchaseOrderID, and TotalDue where ActiveFlag is true and TotalDue is greater than 20000.
SELECT poh.VendorID, v.Name, poh.PurchaseOrderID, poh.TotalDue
FROM PurchaseOrderHeader poh
JOIN Vendor v ON poh.VendorID = v.BusinessEntityID
WHERE v.ActiveFlag = 1 AND poh.TotalDue > 20000;

-- Q2: Join Vendor to PurchaseOrderHeader and return the same columns where ActiveFlag is true.
SELECT Vendor.BusinessEntityID, Vendor.AccountNumber, Vendor.Name, Vendor.CreditRating, Vendor.PreferredVendorStatus, Vendor.ActiveFlag, Vendor.PurchasingWebServiceURL, Vendor.ModifiedDate, PurchaseOrderHeader.PurchaseOrderID, PurchaseOrderHeader.RevisionNumber, PurchaseOrderHeader.Status, PurchaseOrderHeader.EmployeeID, PurchaseOrderHeader.VendorID, PurchaseOrderHeader.ShipMethodID, PurchaseOrderHeader.OrderDate, PurchaseOrderHeader.ShipDate, PurchaseOrderHeader.SubTotal, PurchaseOrderHeader.TaxAmt, PurchaseOrderHeader.Freight, PurchaseOrderHeader.TotalDue, PurchaseOrderHeader.ModifiedDate
FROM PurchaseOrderHeader
JOIN Vendor ON PurchaseOrderHeader.VendorID = Vendor.BusinessEntityID
WHERE Vendor.ActiveFlag = 1;

-- Q3: Join Vendor to PurchaseOrderHeader and return the same columns where TotalDue is greater than 20000.
SELECT poh.PurchaseOrderID, poh.RevisionNumber, poh.Status, poh.EmployeeID, poh.VendorID, poh.ShipMethodID, poh.OrderDate, poh.ShipDate, poh.SubTotal, poh.TaxAmt, poh.Freight, poh.TotalDue, poh.ModifiedDate, v.BusinessEntityID, v.AccountNumber, v.Name, v.CreditRating, v.PreferredVendorStatus, v.ActiveFlag, v.PurchasingWebServiceURL, v.ModifiedDate
FROM PurchaseOrderHeader poh
JOIN Vendor v ON poh.VendorID = v.BusinessEntityID
WHERE poh.TotalDue > 20000;

-- Q4: Join Vendor to PurchaseOrderHeader and return the same columns where ActiveFlag is true and TotalDue is greater than 10000.
SELECT poh.PurchaseOrderID, poh.RevisionNumber, poh.Status, poh.EmployeeID, poh.VendorID, poh.ShipMethodID, poh.OrderDate, poh.ShipDate, poh.SubTotal, poh.TaxAmt, poh.Freight, poh.TotalDue, poh.ModifiedDate, v.BusinessEntityID, v.AccountNumber, v.Name, v.CreditRating, v.PreferredVendorStatus, v.ActiveFlag, v.PurchasingWebServiceURL, v.ModifiedDate
FROM PurchaseOrderHeader poh
JOIN Vendor v ON poh.VendorID = v.BusinessEntityID
WHERE v.ActiveFlag = 1 AND poh.TotalDue > 10000;

-- CASE 25 | structured | filter_threshold | FAIL
-- Q1: Return WorkOrderID, ProductID, OrderQty, and ScrappedQty from WorkOrder where ScrappedQty is greater than 10.
SELECT WorkOrderID, ProductID, OrderQty, ScrappedQty FROM WorkOrder WHERE ScrappedQty > 10;

-- Q2: Return the same columns where ScrappedQty is greater than 5.
-- No SQL generated.

-- Q3: Return the same columns where ScrappedQty is greater than 0.
-- No SQL generated.

-- Q4: Return the same columns where ScrappedQty is greater than 20.
-- No SQL generated.

-- CASE 26 | structured | join | FAIL
-- CASE 27 | structured | group_having | PASS
-- Q1: Join current EmployeeDepartmentHistory to Department, group by DepartmentID and Name, and keep departments with employee count greater than 20.
SELECT d.DepartmentID, d.Name
FROM Department d
JOIN EmployeeDepartmentHistory edh ON d.DepartmentID = edh.DepartmentID
JOIN Employee e ON edh.BusinessEntityID = e.BusinessEntityID
WHERE e.CurrentFlag = 1
GROUP BY d.DepartmentID, d.Name
HAVING COUNT(e.BusinessEntityID) > 20;

-- Q2: Use the same grouped output and keep departments with employee count greater than 10.
SELECT d.Name
FROM Department d
JOIN Employee e ON 1=1
GROUP BY d.Name
HAVING COUNT(e.BusinessEntityID) > 10;

-- Q3: Use the same grouped output and keep departments with employee count greater than 0.
SELECT d.Name
FROM Department d
JOIN Employee e ON 1=1
GROUP BY d.Name
HAVING COUNT(e.BusinessEntityID) > 0;

-- Q4: Use the same grouped output and keep departments with employee count greater than 30.
SELECT d.Name
FROM Department d
JOIN Employee e ON 1=1
GROUP BY d.Name
HAVING COUNT(e.BusinessEntityID) > 30;

-- CASE 28 | structured | derived_metric | FAIL
-- Q1: From SalesPerson, return BusinessEntityID, SalesQuota, SalesYTD, and quota attainment where SalesYTD divided by SalesQuota is greater than 1.5.
SELECT BusinessEntityID, SalesQuota, SalesYTD, SalesYTD / SalesQuota AS quota_attainment
FROM SalesPerson
WHERE SalesQuota IS NOT NULL AND SalesQuota != 0 AND SalesYTD / SalesQuota > 1.5;

-- Q2: Return the same columns where quota attainment is greater than 1.0.
-- No SQL generated.

-- Q3: Return the same columns where SalesQuota is not null and greater than 0.
-- No SQL generated.

-- Q4: Return the same columns where quota attainment is greater than 2.0.
-- No SQL generated.

-- CASE 29 | structured | filter_threshold | FAIL
-- Q1: Return ProductID, LocationID, Shelf, Bin, and Quantity from ProductInventory where Quantity is greater than 500.
SELECT ProductID, LocationID, Shelf, Bin, Quantity FROM ProductInventory WHERE Quantity > 500;

-- Q2: Return the same columns where Quantity is greater than 250.
-- No SQL generated.

-- Q3: Return the same columns where Quantity is greater than 100.
-- No SQL generated.

-- Q4: Return the same columns where Quantity is greater than 750.
-- No SQL generated.

-- CASE 30 | structured | date_and_status | FAIL
-- Q1: Return SalesOrderID, OrderDate, Status, ShipDate, and TotalDue from SalesOrderHeader where OrderDate is after 2013-01-01 and ShipDate is not null.
-- No SQL generated.

-- Q2: Return the same columns where OrderDate is after 2013-01-01.
-- No SQL generated.

-- Q3: Return the same columns where ShipDate is not null.
-- No SQL generated.

-- Q4: Return the same columns where OrderDate is after 2012-01-01 and Status indicates completion.
-- No SQL generated.
