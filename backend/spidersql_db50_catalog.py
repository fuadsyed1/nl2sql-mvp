#!/usr/bin/env python3
"""Natural-language benchmark catalog for AdventureWorks CTU #50."""

from __future__ import annotations

from typing import Any

DATABASE_ID = 50
DATABASE_NAME = 'AdventureWorks CTU'
EXPECTED_TABLES = 71
EXPECTED_RELATIONSHIPS = 91

QUERY_CATEGORIES: dict[str, dict[str, list[str]]] = {'select_projection': {'normal': ['Show product names, product numbers, and list prices.',
                                  'Who are the employees, and what are their job titles and hire dates?',
                                  'List sales order numbers with their order dates and total amounts due.',
                                  'Show vendor names, account numbers, and credit ratings.',
                                  'List customer IDs together with their store IDs and sales territory IDs.'],
                       'structured': ['From Product, return ProductID, Name, ProductNumber, and ListPrice.',
                                      'From Employee, return BusinessEntityID, JobTitle, and HireDate.',
                                      'From SalesOrderHeader, return SalesOrderID, SalesOrderNumber, OrderDate, and '
                                      'TotalDue.',
                                      'From Vendor, return BusinessEntityID, Name, AccountNumber, and CreditRating.',
                                      'From Customer, return CustomerID, PersonID, StoreID, and TerritoryID.']},
 'filter_comparison': {'normal': ['Which products have a list price greater than 1000?',
                                  'Show sales orders whose total due is more than 10000.',
                                  'Find employees with more than 60 vacation hours.',
                                  'List vendors with a credit rating of 2 or better.',
                                  'Show work orders where some quantity was scrapped.'],
                       'structured': ['Return ProductID, Name, and ListPrice from Product where ListPrice is greater '
                                      'than 1000.',
                                      'Return SalesOrderID, OrderDate, CustomerID, and TotalDue from SalesOrderHeader '
                                      'where TotalDue is greater than 10000.',
                                      'Return BusinessEntityID, JobTitle, and VacationHours from Employee where '
                                      'VacationHours is greater than 60.',
                                      'Return BusinessEntityID, Name, and CreditRating from Vendor where CreditRating '
                                      'is less than or equal to 2.',
                                      'Return WorkOrderID, ProductID, OrderQty, and ScrappedQty from WorkOrder where '
                                      'ScrappedQty is greater than 0.']},
 'range_between': {'normal': ['Show sales orders placed from January 1, 2012 through December 31, 2013.',
                              'List products priced between 100 and 500.',
                              'Find employees hired between 2005 and 2010.',
                              'Show purchase orders with total due between 5000 and 25000.',
                              'List product inventory rows with quantity between 100 and 500.'],
                   'structured': ['From SalesOrderHeader, return SalesOrderID, OrderDate, and TotalDue where OrderDate '
                                  'is between 2012-01-01 and 2013-12-31.',
                                  'From Product, return ProductID, Name, and ListPrice where ListPrice is between 100 '
                                  'and 500.',
                                  'From Employee, return BusinessEntityID, JobTitle, and HireDate where HireDate is '
                                  'between 2005-01-01 and 2010-12-31.',
                                  'From PurchaseOrderHeader, return PurchaseOrderID, VendorID, OrderDate, and TotalDue '
                                  'where TotalDue is between 5000 and 25000.',
                                  'From ProductInventory, return ProductID, LocationID, and Quantity where Quantity is '
                                  'between 100 and 500.']},
 'pattern_text': {'normal': ['Find people whose last name starts with S.',
                             'Show products whose name contains Mountain.',
                             'List vendors whose name contains Bike.',
                             'Find addresses in cities beginning with San.',
                             'Show email addresses that use the adventure-works.com domain.'],
                  'structured': ['From Person, return BusinessEntityID, FirstName, and LastName where LastName starts '
                                 'with S.',
                                 'From Product, return ProductID and Name where Name contains the text Mountain.',
                                 'From Vendor, return BusinessEntityID and Name where Name contains the text Bike.',
                                 'From Address, return AddressID, AddressLine1, and City where City starts with San.',
                                 'From EmailAddress, return BusinessEntityID and EmailAddress where EmailAddress ends '
                                 'with @adventure-works.com.']},
 'null_boolean': {'normal': ['Which products do not have a sell end date?',
                             'Show people with no middle name.',
                             'List sales orders that have not been shipped yet.',
                             'Find salespeople who are not assigned to a territory.',
                             'Show products that have a color recorded.'],
                  'structured': ['From Product, return ProductID, Name, and SellEndDate where SellEndDate is null.',
                                 'From Person, return BusinessEntityID, FirstName, MiddleName, and LastName where '
                                 'MiddleName is null.',
                                 'From SalesOrderHeader, return SalesOrderID, OrderDate, and ShipDate where ShipDate '
                                 'is null.',
                                 'From SalesPerson, return BusinessEntityID and TerritoryID where TerritoryID is null.',
                                 'From Product, return ProductID, Name, and Color where Color is not null.']},
 'join': {'normal': ['Show each product with its product subcategory name.',
                     'List sales orders with the customer ID and customer territory.',
                     'Show employees with their first and last names.',
                     'List purchase orders with the vendor name.',
                     'Show addresses with their state or province and country.'],
          'structured': ['Join Product to ProductSubcategory and return ProductID, product Name, ProductSubcategoryID, '
                         'and subcategory Name.',
                         'Join SalesOrderHeader to Customer and return SalesOrderID, CustomerID, OrderDate, TotalDue, '
                         'and customer TerritoryID.',
                         'Join Employee to Person on BusinessEntityID and return employee BusinessEntityID, FirstName, '
                         'LastName, JobTitle, and HireDate.',
                         'Join PurchaseOrderHeader to Vendor and return PurchaseOrderID, OrderDate, TotalDue, '
                         'VendorID, and vendor Name.',
                         'Join Address to StateProvince and CountryRegion and return AddressID, City, state or '
                         'province Name, and country Name.']},
 'multi_join': {'normal': ['List sales order lines with the customer, product name, order date, quantity, and line '
                           'total.',
                           'Show employees with their names and current department.',
                           'List products with their subcategory and category names.',
                           'Show purchase order lines with vendor name, product name, quantity, and line total.',
                           'List stores with their customer record and assigned salesperson name.'],
                'structured': ['Join SalesOrderDetail, SalesOrderHeader, Customer, and Product; return SalesOrderID, '
                               'CustomerID, ProductID, product Name, OrderDate, OrderQty, and LineTotal.',
                               'Join Employee, Person, EmployeeDepartmentHistory, and Department; keep current '
                               'department assignments and return employee ID, name, JobTitle, and department Name.',
                               'Join Product, ProductSubcategory, and ProductCategory; return ProductID, product Name, '
                               'subcategory Name, and category Name.',
                               'Join PurchaseOrderDetail, PurchaseOrderHeader, Vendor, and Product; return '
                               'PurchaseOrderID, vendor Name, product Name, OrderQty, and LineTotal.',
                               'Join Store, Customer, SalesPerson, and Person; return Store BusinessEntityID, store '
                               'Name, CustomerID, salesperson BusinessEntityID, and salesperson name.']},
 'aggregation': {'normal': ['How many products are in the product table?',
                            'What is the average product list price?',
                            'What is the total amount due across all sales orders?',
                            'What is the largest sales order total due?',
                            'Show the minimum, average, and maximum product standard cost.'],
                 'structured': ['Return COUNT of all rows in Product as product_count.',
                                'Return AVG of ListPrice from Product as average_list_price.',
                                'Return SUM of TotalDue from SalesOrderHeader as total_sales_due.',
                                'Return MAX of TotalDue from SalesOrderHeader as maximum_order_total.',
                                'Return MIN, AVG, and MAX of StandardCost from Product.']},
 'group_by': {'normal': ['For each customer, show order count and total amount due.',
                         'Show total sales due by sales territory.',
                         'Count products in each product subcategory.',
                         'Count current employees in each department.',
                         'Show total purchase order value by vendor.'],
              'structured': ['Group SalesOrderHeader by CustomerID and return CustomerID, COUNT of orders, and SUM of '
                             'TotalDue.',
                             'Group SalesOrderHeader by TerritoryID and return TerritoryID, COUNT of orders, and SUM '
                             'of TotalDue.',
                             'Group Product by ProductSubcategoryID and return ProductSubcategoryID and COUNT of '
                             'products.',
                             'Join current EmployeeDepartmentHistory rows to Department, group by DepartmentID and '
                             'Name, and return employee count.',
                             'Join PurchaseOrderHeader to Vendor, group by VendorID and vendor Name, and return order '
                             'count and SUM of TotalDue.']},
 'having': {'normal': ['Find customers who have placed more than 10 orders.',
                       'Show product subcategories that contain more than 20 products.',
                       'Find sales territories with total order value above 1000000.',
                       'Show vendors that have received more than 5 purchase orders.',
                       'Find departments with more than 10 current employees.'],
            'structured': ['Group SalesOrderHeader by CustomerID and keep groups where COUNT of orders is greater than '
                           '10.',
                           'Group Product by ProductSubcategoryID and keep groups where COUNT of products is greater '
                           'than 20.',
                           'Group SalesOrderHeader by TerritoryID and keep groups where SUM of TotalDue is greater '
                           'than 1000000.',
                           'Group PurchaseOrderHeader by VendorID and keep groups where COUNT of PurchaseOrderID is '
                           'greater than 5.',
                           'Join current EmployeeDepartmentHistory to Department, group by DepartmentID and Name, and '
                           'keep departments with COUNT of employees greater than 10.']},
 'distinct': {'normal': ['List the distinct product colors.',
                         'Show all distinct employee job titles.',
                         'List distinct ship method names used by sales orders.',
                         'Show distinct state or province names that have sales tax rates.',
                         'List distinct product class and style combinations.'],
              'structured': ['Return DISTINCT Color from Product where Color is not null.',
                             'Return DISTINCT JobTitle from Employee.',
                             'Join SalesOrderHeader to ShipMethod and return DISTINCT ShipMethod Name.',
                             'Join SalesTaxRate to StateProvince and return DISTINCT StateProvince Name.',
                             'Return DISTINCT Class and Style from Product where at least one is not null.']},
 'count_distinct': {'normal': ['How many different customers have placed a sales order?',
                               'How many distinct products have been sold?',
                               'How many different vendors have purchase orders?',
                               'How many distinct employees have department history records?',
                               'How many distinct cities are in the address table?'],
                    'structured': ['Return COUNT DISTINCT CustomerID from SalesOrderHeader.',
                                   'Return COUNT DISTINCT ProductID from SalesOrderDetail.',
                                   'Return COUNT DISTINCT VendorID from PurchaseOrderHeader.',
                                   'Return COUNT DISTINCT BusinessEntityID from EmployeeDepartmentHistory.',
                                   'Return COUNT DISTINCT City from Address.']},
 'order_by': {'normal': ['List products from highest to lowest list price.',
                         'Show sales orders from oldest to newest order date.',
                         'List employees from most recently hired to earliest hired.',
                         'Show vendors ordered by credit rating and then by name.',
                         'List work orders from highest to lowest scrapped quantity.'],
              'structured': ['Return ProductID, Name, and ListPrice from Product ordered by ListPrice descending and '
                             'Name ascending.',
                             'Return SalesOrderID, OrderDate, CustomerID, and TotalDue from SalesOrderHeader ordered '
                             'by OrderDate ascending.',
                             'Return BusinessEntityID, JobTitle, and HireDate from Employee ordered by HireDate '
                             'descending.',
                             'Return BusinessEntityID, Name, and CreditRating from Vendor ordered by CreditRating '
                             'ascending and Name ascending.',
                             'Return WorkOrderID, ProductID, and ScrappedQty from WorkOrder ordered by ScrappedQty '
                             'descending.']},
 'top_k_limit': {'normal': ['Show the 10 most expensive products.',
                            'List the 20 sales orders with the highest total due.',
                            'Which 10 customers have spent the most in total?',
                            'Show the 15 vendors with the greatest total purchase order value.',
                            'List the 10 products with the highest total quantity sold.'],
                 'structured': ['Return the top 10 Product rows ordered by ListPrice descending, including ProductID, '
                                'Name, and ListPrice.',
                                'Return the top 20 SalesOrderHeader rows ordered by TotalDue descending, including '
                                'SalesOrderID, CustomerID, OrderDate, and TotalDue.',
                                'Group SalesOrderHeader by CustomerID, order by SUM of TotalDue descending, and return '
                                'the top 10 customers.',
                                'Group PurchaseOrderHeader by VendorID, order by SUM of TotalDue descending, and '
                                'return the top 15 vendors.',
                                'Group SalesOrderDetail by ProductID, order by SUM of OrderQty descending, and return '
                                'the top 10 products.']},
 'subquery': {'normal': ['Find products priced above the average product list price.',
                         'Show sales orders whose total due is above the average sales order total.',
                         'List employees with more vacation hours than the employee average.',
                         'Find customers whose total spending is above the average customer spending.',
                         'Show vendors whose total purchase order value is above the average vendor purchase total.'],
              'structured': ['Return products where ListPrice is greater than a scalar subquery that computes AVG '
                             'ListPrice from Product.',
                             'Return SalesOrderHeader rows where TotalDue is greater than a scalar subquery that '
                             'computes AVG TotalDue.',
                             'Return Employee rows where VacationHours is greater than a scalar subquery that computes '
                             'AVG VacationHours.',
                             'Aggregate SalesOrderHeader by CustomerID and keep customer totals greater than the '
                             'average of all customer totals.',
                             'Aggregate PurchaseOrderHeader by VendorID and keep vendor totals greater than the '
                             'average of all vendor totals.']},
 'exists_not_exists': {'normal': ['List customers who have at least one sales order.',
                                  'Find products that have never appeared on a sales order.',
                                  'Show vendors that have at least one purchase order.',
                                  'Find employees who do not have a current department assignment.',
                                  'List products that have inventory in more than one location.'],
                       'structured': ['Return Customer rows for which an EXISTS subquery finds a SalesOrderHeader with '
                                      'the same CustomerID.',
                                      'Return Product rows for which a NOT EXISTS subquery finds no SalesOrderDetail '
                                      'with the same ProductID.',
                                      'Return Vendor rows for which an EXISTS subquery finds a PurchaseOrderHeader '
                                      'with the same VendorID.',
                                      'Return Employee rows for which a NOT EXISTS subquery finds a current '
                                      'EmployeeDepartmentHistory row with the same BusinessEntityID.',
                                      'Return Product rows where an EXISTS or grouped subquery finds inventory records '
                                      'in more than one distinct LocationID.']},
 'set_operation': {'normal': ['List cities that appear in both customer-related addresses and vendor-related '
                              'addresses.',
                              'Find products that have been both sold to customers and ordered from vendors.',
                              'List people who are employees or salespeople, without duplicates.',
                              'Find customers who have sales orders but are not linked to a store.',
                              'Combine product names from finished goods and purchased components into one distinct '
                              'list.'],
                   'structured': ['Use INTERSECT to return City values appearing in customer addresses and vendor '
                                  'addresses.',
                                  'Use INTERSECT to return ProductID values from SalesOrderDetail and '
                                  'PurchaseOrderDetail.',
                                  'Use UNION to return distinct BusinessEntityID values from Employee and SalesPerson.',
                                  'Use EXCEPT to return CustomerID values from SalesOrderHeader that do not appear as '
                                  'store-linked Customer rows.',
                                  'Use UNION to combine distinct Product Name values for finished goods and purchased '
                                  'components.']},
 'case_expression': {'normal': ['Label each product as budget, midrange, or premium based on list price.',
                                'Classify sales orders as small, medium, or large based on total due.',
                                'Label product inventory as out of stock, low stock, or well stocked.',
                                'Group employees into new, experienced, or long-tenure bands using hire date.',
                                'Label vendors as low, medium, or high credit risk from credit rating.'],
                     'structured': ['Return ProductID, Name, ListPrice, and a CASE expression: budget below 100, '
                                    'midrange from 100 through 1000, premium above 1000.',
                                    'Return SalesOrderID, TotalDue, and a CASE expression: small below 1000, medium '
                                    'from 1000 through 10000, large above 10000.',
                                    'Return ProductID, LocationID, Quantity, and a CASE expression: out_of_stock when '
                                    '0, low_stock below 50, well_stocked otherwise.',
                                    'Return BusinessEntityID, HireDate, and a CASE expression that assigns tenure '
                                    'bands from HireDate.',
                                    'Return Vendor BusinessEntityID, Name, CreditRating, and a CASE expression that '
                                    'maps rating to low, medium, or high risk.']},
 'derived_metric': {'normal': ['For each sales order line, calculate net line revenue after discount.',
                               "Show each product's gross margin amount and margin percentage using list price and "
                               'standard cost.',
                               'For each sales order, calculate the average line value.',
                               'For each work order, calculate the scrap rate as scrapped quantity divided by order '
                               'quantity.',
                               'For each salesperson, calculate year-to-date sales as a percentage of sales quota.'],
                    'structured': ['From SalesOrderDetail, return SalesOrderID, SalesOrderDetailID, OrderQty, '
                                   'UnitPrice, UnitPriceDiscount, and OrderQty times UnitPrice times one minus '
                                   'UnitPriceDiscount as net_line_revenue.',
                                   'From Product, return ProductID, Name, ListPrice, StandardCost, ListPrice minus '
                                   'StandardCost as margin_amount, and margin_amount divided by ListPrice as '
                                   'margin_percent.',
                                   'Group SalesOrderDetail by SalesOrderID and return SUM of LineTotal divided by '
                                   'COUNT of lines as average_line_value.',
                                   'From WorkOrder, return WorkOrderID, OrderQty, ScrappedQty, and ScrappedQty divided '
                                   'by NULLIF OrderQty as scrap_rate.',
                                   'From SalesPerson, return BusinessEntityID, SalesQuota, SalesYTD, and SalesYTD '
                                   'divided by NULLIF SalesQuota as quota_attainment.']},
 'window_cte': {'normal': ['Rank products by sales revenue within each product category.',
                           'Show a running total of sales order value by order date.',
                           'Return only the latest sales order for each customer.',
                           'Find the top salesperson by year-to-date sales within each territory.',
                           "Compare each territory's yearly sales with the previous year's sales."],
                'structured': ['Using joins from ProductCategory through Product to SalesOrderDetail, calculate '
                               'product revenue and apply RANK partitioned by category ordered by revenue descending.',
                               'Aggregate SalesOrderHeader by OrderDate and return a cumulative SUM of daily TotalDue '
                               'ordered by OrderDate.',
                               'Use ROW_NUMBER partitioned by CustomerID ordered by OrderDate descending and keep row '
                               'number 1.',
                               'Use ROW_NUMBER or RANK partitioned by TerritoryID and ordered by SalesYTD descending '
                               'to return the top SalesPerson in each territory.',
                               'Build yearly territory sales in a CTE and use LAG to return current-year sales, '
                               'previous-year sales, and year-over-year change.']}}

CONTAINMENT_SCENARIOS: list[dict[str, Any]] = [{'category': 'filter_threshold',
  'name': 'Product list-price threshold chain',
  'normal_queries': ['Which products cost more than 1500?',
                     'Which products cost more than 1000?',
                     'Which products cost more than 500?',
                     'Which products cost more than 2000?'],
  'structured_queries': ['Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 1500.',
                         'Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 1000.',
                         'Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 500.',
                         'Return ProductID, Name, and ListPrice from Product where ListPrice is greater than 2000.'],
  'expected_note': 'Higher price thresholds should be contained in lower thresholds.'},
 {'category': 'filter_threshold',
  'name': 'Sales-order total threshold chain',
  'normal_queries': ['Show sales orders with total due above 20000.',
                     'Show sales orders with total due above 10000.',
                     'Show sales orders with total due above 5000.',
                     'Show sales orders with total due above 30000.'],
  'structured_queries': ['Return SalesOrderID, CustomerID, OrderDate, and TotalDue from SalesOrderHeader where '
                         'TotalDue is greater than 20000.',
                         'Return SalesOrderID, CustomerID, OrderDate, and TotalDue from SalesOrderHeader where '
                         'TotalDue is greater than 10000.',
                         'Return SalesOrderID, CustomerID, OrderDate, and TotalDue from SalesOrderHeader where '
                         'TotalDue is greater than 5000.',
                         'Return SalesOrderID, CustomerID, OrderDate, and TotalDue from SalesOrderHeader where '
                         'TotalDue is greater than 30000.'],
  'expected_note': 'Higher TotalDue thresholds should be subsets of lower thresholds.'},
 {'category': 'conjunction',
  'name': 'Employee hire date and vacation-hours narrowing',
  'normal_queries': ['Find employees hired after 2010 who have more than 50 vacation hours.',
                     'Find employees hired after 2010.',
                     'Find employees with more than 50 vacation hours.',
                     'Find employees hired after 2005 who have more than 30 vacation hours.'],
  'structured_queries': ['Return BusinessEntityID, JobTitle, HireDate, and VacationHours from Employee where HireDate '
                         'is after 2010-01-01 and VacationHours is greater than 50.',
                         'Return BusinessEntityID, JobTitle, HireDate, and VacationHours from Employee where HireDate '
                         'is after 2010-01-01.',
                         'Return BusinessEntityID, JobTitle, HireDate, and VacationHours from Employee where '
                         'VacationHours is greater than 50.',
                         'Return BusinessEntityID, JobTitle, HireDate, and VacationHours from Employee where HireDate '
                         'is after 2005-01-01 and VacationHours is greater than 30.'],
  'expected_note': 'The first query is narrower than each single-condition query and the weaker conjunction.'},
 {'category': 'conjunction',
  'name': 'Vendor credit and activity narrowing',
  'normal_queries': ['List active vendors with credit rating 1.',
                     'List active vendors.',
                     'List vendors with credit rating 1.',
                     'List active vendors with credit rating 2 or better.'],
  'structured_queries': ['Return BusinessEntityID, Name, CreditRating, and ActiveFlag from Vendor where ActiveFlag is '
                         'true and CreditRating equals 1.',
                         'Return BusinessEntityID, Name, CreditRating, and ActiveFlag from Vendor where ActiveFlag is '
                         'true.',
                         'Return BusinessEntityID, Name, CreditRating, and ActiveFlag from Vendor where CreditRating '
                         'equals 1.',
                         'Return BusinessEntityID, Name, CreditRating, and ActiveFlag from Vendor where ActiveFlag is '
                         'true and CreditRating is less than or equal to 2.'],
  'expected_note': 'Active rating-1 vendors should be contained in the broader vendor sets.'},
 {'category': 'conjunction',
  'name': 'Product color and price narrowing',
  'normal_queries': ['Show red products priced above 1000.',
                     'Show red products.',
                     'Show products priced above 1000.',
                     'Show colored products priced above 500.'],
  'structured_queries': ['Return ProductID, Name, Color, and ListPrice from Product where Color equals Red and '
                         'ListPrice is greater than 1000.',
                         'Return ProductID, Name, Color, and ListPrice from Product where Color equals Red.',
                         'Return ProductID, Name, Color, and ListPrice from Product where ListPrice is greater than '
                         '1000.',
                         'Return ProductID, Name, Color, and ListPrice from Product where Color is not null and '
                         'ListPrice is greater than 500.'],
  'expected_note': 'Red and expensive products should be narrower than red-only and expensive-only products.'},
 {'category': 'join',
  'name': 'Customer territory and order containment',
  'normal_queries': ['List customers in territory 1 who have a sales order.',
                     'List customers in territory 1.',
                     'List customers who have a sales order.',
                     'List customers in any assigned territory who have a sales order.'],
  'structured_queries': ['Return distinct CustomerID and TerritoryID by joining Customer to SalesOrderHeader, where '
                         'Customer TerritoryID equals 1.',
                         'Return CustomerID and TerritoryID from Customer where TerritoryID equals 1.',
                         'Return distinct CustomerID and TerritoryID by joining Customer to SalesOrderHeader.',
                         'Return distinct CustomerID and TerritoryID by joining Customer to SalesOrderHeader where '
                         'TerritoryID is not null.'],
  'expected_note': 'Territory-1 customers with orders should be contained in both broader parent sets.'},
 {'category': 'multi_join',
  'name': 'Category, subcategory, and product-price containment',
  'normal_queries': ['List bikes priced above 1000 with their category and subcategory.',
                     'List all bike products with their category and subcategory.',
                     'List all products priced above 1000 with their category and subcategory.',
                     'List products in any category priced above 500 with category and subcategory.'],
  'structured_queries': ['Join Product, ProductSubcategory, and ProductCategory; return ProductID, product Name, '
                         'subcategory Name, category Name, and ListPrice where category Name equals Bikes and '
                         'ListPrice is greater than 1000.',
                         'Join Product, ProductSubcategory, and ProductCategory; return the same columns where '
                         'category Name equals Bikes.',
                         'Join Product, ProductSubcategory, and ProductCategory; return the same columns where '
                         'ListPrice is greater than 1000.',
                         'Join Product, ProductSubcategory, and ProductCategory; return the same columns where '
                         'ListPrice is greater than 500.'],
  'expected_note': 'Expensive bikes should be contained in bikes, expensive products, and the weaker price threshold.'},
 {'category': 'derived_metric',
  'name': 'Sales-line revenue containment',
  'normal_queries': ['Show sales order lines with net line revenue above 5000 and quantity above 5.',
                     'Show sales order lines with net line revenue above 5000.',
                     'Show sales order lines with quantity above 5.',
                     'Show sales order lines with net line revenue above 2500 and quantity above 2.'],
  'structured_queries': ['From SalesOrderDetail, return SalesOrderID, SalesOrderDetailID, OrderQty, and net line '
                         'revenue where net line revenue is greater than 5000 and OrderQty is greater than 5.',
                         'From SalesOrderDetail, return the same columns where net line revenue is greater than 5000.',
                         'From SalesOrderDetail, return the same columns where OrderQty is greater than 5.',
                         'From SalesOrderDetail, return the same columns where net line revenue is greater than 2500 '
                         'and OrderQty is greater than 2.'],
  'expected_note': 'The strong revenue-and-quantity condition should be narrower than the three broader conditions.'},
 {'category': 'join',
  'name': 'Purchase-order vendor threshold containment',
  'normal_queries': ['List active vendors with purchase orders above 20000.',
                     'List active vendors with any purchase order.',
                     'List vendors with purchase orders above 20000.',
                     'List active vendors with purchase orders above 10000.'],
  'structured_queries': ['Join Vendor to PurchaseOrderHeader and return VendorID, vendor Name, PurchaseOrderID, and '
                         'TotalDue where ActiveFlag is true and TotalDue is greater than 20000.',
                         'Join Vendor to PurchaseOrderHeader and return the same columns where ActiveFlag is true.',
                         'Join Vendor to PurchaseOrderHeader and return the same columns where TotalDue is greater '
                         'than 20000.',
                         'Join Vendor to PurchaseOrderHeader and return the same columns where ActiveFlag is true and '
                         'TotalDue is greater than 10000.'],
  'expected_note': 'Active vendors with very large orders should be subsets of the broader vendor-order sets.'},
 {'category': 'filter_threshold',
  'name': 'Work-order scrap threshold containment',
  'normal_queries': ['Show work orders with more than 10 scrapped units.',
                     'Show work orders with more than 5 scrapped units.',
                     'Show work orders with any scrapped units.',
                     'Show work orders with more than 20 scrapped units.'],
  'structured_queries': ['Return WorkOrderID, ProductID, OrderQty, and ScrappedQty from WorkOrder where ScrappedQty is '
                         'greater than 10.',
                         'Return the same columns where ScrappedQty is greater than 5.',
                         'Return the same columns where ScrappedQty is greater than 0.',
                         'Return the same columns where ScrappedQty is greater than 20.'],
  'expected_note': 'Larger scrap thresholds should be contained in smaller thresholds.'},
 {'category': 'join',
  'name': 'Address geography containment',
  'normal_queries': ['List addresses in Seattle, Washington.',
                     'List addresses in Seattle.',
                     'List addresses in Washington.',
                     'List addresses in the United States.'],
  'structured_queries': ['Join Address to StateProvince and CountryRegion; return AddressID, City, state Name, and '
                         'country Name where City equals Seattle and state Name equals Washington.',
                         'Join Address to StateProvince and CountryRegion; return the same columns where City equals '
                         'Seattle.',
                         'Join Address to StateProvince and CountryRegion; return the same columns where state Name '
                         'equals Washington.',
                         'Join Address to StateProvince and CountryRegion; return the same columns where country Name '
                         'equals United States.'],
  'expected_note': 'Seattle, Washington addresses should be contained in Seattle, Washington, and United States sets.'},
 {'category': 'group_having',
  'name': 'Department employee-count containment',
  'normal_queries': ['Show departments with more than 20 current employees.',
                     'Show departments with more than 10 current employees.',
                     'Show departments with at least one current employee.',
                     'Show departments with more than 30 current employees.'],
  'structured_queries': ['Join current EmployeeDepartmentHistory to Department, group by DepartmentID and Name, and '
                         'keep departments with employee count greater than 20.',
                         'Use the same grouped output and keep departments with employee count greater than 10.',
                         'Use the same grouped output and keep departments with employee count greater than 0.',
                         'Use the same grouped output and keep departments with employee count greater than 30.'],
  'expected_note': 'Higher department headcount thresholds should be contained in lower thresholds.'},
 {'category': 'derived_metric',
  'name': 'Salesperson quota attainment containment',
  'normal_queries': ['List salespeople whose year-to-date sales exceed 150 percent of quota.',
                     'List salespeople whose year-to-date sales exceed quota.',
                     'List salespeople who have a nonzero sales quota.',
                     'List salespeople whose year-to-date sales exceed 200 percent of quota.'],
  'structured_queries': ['From SalesPerson, return BusinessEntityID, SalesQuota, SalesYTD, and quota attainment where '
                         'SalesYTD divided by SalesQuota is greater than 1.5.',
                         'Return the same columns where quota attainment is greater than 1.0.',
                         'Return the same columns where SalesQuota is not null and greater than 0.',
                         'Return the same columns where quota attainment is greater than 2.0.'],
  'expected_note': 'Higher quota-attainment thresholds should be narrower.'},
 {'category': 'filter_threshold',
  'name': 'Inventory quantity containment',
  'normal_queries': ['Show product inventory rows with quantity above 500.',
                     'Show product inventory rows with quantity above 250.',
                     'Show product inventory rows with quantity above 100.',
                     'Show product inventory rows with quantity above 750.'],
  'structured_queries': ['Return ProductID, LocationID, Shelf, Bin, and Quantity from ProductInventory where Quantity '
                         'is greater than 500.',
                         'Return the same columns where Quantity is greater than 250.',
                         'Return the same columns where Quantity is greater than 100.',
                         'Return the same columns where Quantity is greater than 750.'],
  'expected_note': 'Larger inventory thresholds should be subsets of lower thresholds.'},
 {'category': 'date_and_status',
  'name': 'Sales-order date and status containment',
  'normal_queries': ['Show shipped sales orders placed after 2013.',
                     'Show sales orders placed after 2013.',
                     'Show shipped sales orders.',
                     'Show completed sales orders placed after 2012.'],
  'structured_queries': ['Return SalesOrderID, OrderDate, Status, ShipDate, and TotalDue from SalesOrderHeader where '
                         'OrderDate is after 2013-01-01 and ShipDate is not null.',
                         'Return the same columns where OrderDate is after 2013-01-01.',
                         'Return the same columns where ShipDate is not null.',
                         'Return the same columns where OrderDate is after 2012-01-01 and Status indicates '
                         'completion.'],
  'expected_note': 'Recent shipped orders should be narrower than recent-only and shipped-only sets.'}]


def _build_query_tests(mode: str, prefix: str) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    ordinal = 0
    for category, modes in QUERY_CATEGORIES.items():
        questions = modes[mode]
        if len(questions) != 5:
            raise ValueError(f"{category} must contain exactly 5 {mode} questions")
        for question in questions:
            ordinal += 1
            tests.append(
                {
                    "id": f"{prefix}-{ordinal:03d}",
                    "ordinal": ordinal,
                    "category": category,
                    "question": question,
                }
            )
    if len(tests) != 100:
        raise ValueError(f"Expected 100 {mode} tests, built {len(tests)}")
    return tests


def _build_containment_cases() -> list[dict[str, Any]]:
    if len(CONTAINMENT_SCENARIOS) != 15:
        raise ValueError("Expected exactly 15 containment scenarios")
    cases: list[dict[str, Any]] = []
    for index, scenario in enumerate(CONTAINMENT_SCENARIOS, start=1):
        cases.append(
            {
                "id": index,
                "mode": "normal",
                "category": scenario["category"],
                "name": scenario["name"] + " - normal NL",
                "queries": scenario["normal_queries"],
                "expected_note": scenario["expected_note"],
            }
        )
    for index, scenario in enumerate(CONTAINMENT_SCENARIOS, start=16):
        cases.append(
            {
                "id": index,
                "mode": "structured",
                "category": scenario["category"],
                "name": scenario["name"] + " - structured NL",
                "queries": scenario["structured_queries"],
                "expected_note": scenario["expected_note"],
            }
        )
    if len(cases) != 30:
        raise ValueError(f"Expected 30 containment cases, built {len(cases)}")
    return cases


NORMAL_TESTS = _build_query_tests("normal", "N")
STRUCTURED_TESTS = _build_query_tests("structured", "S")
CONTAINMENT_CASES = _build_containment_cases()
