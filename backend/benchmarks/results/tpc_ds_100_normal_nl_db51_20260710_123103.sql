-- SpiderSQL generated SQL: 100_normal_nl
-- Database: TPC-DS #51
-- No SQL is hard-matched by the benchmark.

-- N-001 | select_projection | PASS
-- Question: Show customer IDs, first names, last names, and birth years.
SELECT c.c_customer_id, c.c_first_name, c.c_last_name, c.c_birth_year
FROM customer c;

-- N-002 | select_projection | PASS
-- Question: List item IDs, descriptions, current prices, and categories.
SELECT i_item_id, i_item_desc, i_current_price, i_category FROM item;

-- N-003 | select_projection | PASS
-- Question: Show store IDs, store names, cities, and states.
SELECT s_store_id, s_store_name, s_city, s_state FROM store;

-- N-004 | select_projection | PASS
-- Question: List web site IDs, names, and classes.
SELECT web_site_id, web_name, web_class FROM web_site;

-- N-005 | select_projection | PASS
-- Question: Show warehouse IDs, names, square footage, and states.
SELECT w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft, w_state FROM warehouse;

-- N-006 | filter_comparison | PASS
-- Question: Which items have a current price greater than 100?
SELECT i_item_sk, i_item_id, i_item_desc, i_current_price FROM item WHERE i_current_price > 100;

-- N-007 | filter_comparison | PASS
-- Question: Show store sales rows with quantity greater than 5.
SELECT * FROM store_sales WHERE ss_quantity > 5;

-- N-008 | filter_comparison | PASS
-- Question: List web sales where net paid is above 500.
SELECT * FROM web_sales WHERE ws_net_paid > 500;

-- N-009 | filter_comparison | PASS
-- Question: Show catalog sales with discount amount above 50.
SELECT * FROM catalog_sales WHERE cs_ext_discount_amt > 50;

-- N-010 | filter_comparison | PASS
-- Question: List store returns where return amount is above 100.
SELECT * FROM store_returns WHERE sr_return_amt > 100;

-- N-011 | range_between | PASS
-- Question: Show calendar dates from January 1, 1999 through December 31, 2000.
SELECT d_date FROM date_dim WHERE d_date BETWEEN '1999-01-01' AND '2000-12-31';

-- N-012 | range_between | PASS
-- Question: List items priced between 20 and 80.
SELECT i_item_sk, i_item_id, i_current_price FROM item WHERE i_current_price BETWEEN 20 AND 80;

-- N-013 | range_between | PASS
-- Question: Find customers born between 1940 and 1960.
SELECT c_customer_sk, c_customer_id, c_first_name, c_last_name, c_birth_year
FROM customer
WHERE c_birth_year BETWEEN 1940 AND 1960;

-- N-014 | range_between | PASS
-- Question: Show inventory rows with quantity between 100 and 500.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
FROM inventory
WHERE inv_quantity_on_hand BETWEEN 100 AND 500;

-- N-015 | range_between | PASS
-- Question: List stores with floor space between 50000 and 100000 square feet.
SELECT s_store_id, s_store_name, s_floor_space FROM store WHERE s_floor_space BETWEEN 50000 AND 100000;

-- N-016 | pattern_text | PASS
-- Question: Find items whose description contains cotton.
SELECT i_item_sk, i_item_id, i_item_desc FROM item WHERE i_item_desc LIKE '%Cotton%' OR i_item_desc LIKE '%cotton%';

-- N-017 | pattern_text | PASS
-- Question: Show customers whose last name starts with A.
SELECT c_customer_sk, c_last_name FROM customer WHERE c_last_name LIKE 'A%';

-- N-018 | pattern_text | PASS
-- Question: List customer addresses in cities beginning with New.
SELECT ca.ca_address_sk, ca.ca_city, ca.ca_state, ca.ca_zip
FROM customer c
JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
WHERE ca.ca_city LIKE 'New%';

-- N-019 | pattern_text | PASS
-- Question: Find web pages whose URL contains catalog.
SELECT wp_web_page_sk, wp_url FROM web_page WHERE wp_url LIKE '%catalog%';

-- N-020 | pattern_text | PASS
-- Question: Show promotions whose name contains holiday.
SELECT p_promo_name FROM promotion WHERE LOWER(p_promo_name) LIKE '%holiday%';

-- N-021 | null_boolean | PASS
-- Question: Show customers that do not have a current address key.
SELECT c.c_customer_sk, c.c_customer_id
FROM customer c
WHERE c.c_current_addr_sk IS NULL;

-- N-022 | null_boolean | PASS
-- Question: List items with no brand recorded.
SELECT "item"."i_item_sk", "item"."i_item_id", "item"."i_item_desc" FROM "item" WHERE "item"."i_brand" IS NULL OR "item"."i_brand" = '';

-- N-023 | null_boolean | PASS
-- Question: Show web sales that do not have a ship date.
SELECT * FROM web_sales WHERE ws_ship_date_sk IS NULL;

-- N-024 | null_boolean | PASS
-- Question: List stores that do not have a closed date.
SELECT s_store_sk, s_store_id, s_store_name FROM store WHERE s_closed_date_sk IS NULL;

-- N-025 | null_boolean | PASS
-- Question: Show promotions where the email channel flag is present.
SELECT p.p_promo_id, p.p_promo_name
FROM promotion p
WHERE p.p_channel_email IS NOT NULL AND p.p_channel_email != '';

-- N-026 | join | PASS
-- Question: Show store sales with the item description and category.
SELECT ss.ss_sold_date_sk, ss.ss_item_sk, i.i_item_desc, i.i_category
FROM store_sales ss, item i
WHERE ss.ss_item_sk = i.i_item_sk;

-- N-027 | join | PASS
-- Question: List store sales with the customer's name.
SELECT ss.ss_sold_date_sk, ss.ss_item_sk, ss.ss_customer_sk, ss.ss_ticket_number, ss.ss_quantity, ss.ss_sales_price, c.c_first_name, c.c_last_name
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk;

-- N-028 | join | PASS
-- Question: Show web sales with the web site name.
SELECT ws.ws_sold_date_sk, ws.ws_item_sk, ws.ws_order_number, w.web_name
FROM web_sales ws
JOIN web_site w ON ws.ws_web_site_sk = w.web_site_sk;

-- N-029 | join | PASS
-- Question: List catalog sales with the catalog page description.
SELECT cp.cp_description
FROM catalog_sales cs
JOIN catalog_page cp ON cs.cs_catalog_page_sk = cp.cp_catalog_page_sk;

-- N-030 | join | PASS
-- Question: Show store returns with the return reason description.
SELECT reason.r_reason_desc
FROM store_returns
JOIN reason ON store_returns.sr_reason_sk = reason.r_reason_sk;

-- N-031 | multi_join | PASS
-- Question: List store sales with customer name, item description, store name, sales date, quantity, and net paid.
SELECT c.c_first_name, c.c_last_name, i.i_item_desc, s.s_store_name, d.d_date, ss.ss_quantity, ss.ss_net_paid
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
JOIN item i ON ss.ss_item_sk = i.i_item_sk
JOIN store s ON ss.ss_store_sk = s.s_store_sk
JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk;

-- N-032 | multi_join | PASS
-- Question: Show web sales with customer, item, web site, sold date, quantity, and net paid.
SELECT ws.ws_sold_date_sk, ws.ws_item_sk, ws.ws_bill_customer_sk, web.web_site_sk, ws.ws_quantity, ws.ws_net_paid
FROM web_sales ws
JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk
JOIN item i ON ws.ws_item_sk = i.i_item_sk
JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
JOIN web_site web ON ws.ws_web_site_sk = web.web_site_sk;

-- N-033 | multi_join | PASS
-- Question: List catalog sales with customer, item, catalog page, sold date, quantity, and net paid.
SELECT cs.cs_order_number, c.c_customer_id, i.i_item_id, cp.cp_catalog_page_number, d.d_date, cs.cs_quantity, cs.cs_net_paid
FROM catalog_sales cs
JOIN customer c ON cs.cs_bill_customer_sk = c.c_customer_sk
JOIN item i ON cs.cs_item_sk = i.i_item_sk
JOIN catalog_page cp ON cs.cs_catalog_page_sk = cp.cp_catalog_page_sk
JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk;

-- N-034 | multi_join | PASS
-- Question: Show store returns with customer, item, store, reason, return date, and return amount.
SELECT sr.sr_item_sk, sr.sr_customer_sk, sr.sr_store_sk, sr.sr_reason_sk, sr.sr_returned_date_sk, sr.sr_return_amt
FROM store_returns sr
JOIN customer c ON sr.sr_customer_sk = c.c_customer_sk
JOIN item i ON sr.sr_item_sk = i.i_item_sk
JOIN store s ON sr.sr_store_sk = s.s_store_sk
JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk
JOIN date_dim d ON sr.sr_returned_date_sk = d.d_date_sk;

-- N-035 | multi_join | PASS
-- Question: List inventory with item, warehouse, inventory date, and quantity on hand.
SELECT i.inv_item_sk, i.inv_warehouse_sk, i.inv_date_sk, i.inv_quantity_on_hand
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk;

-- N-036 | aggregation | PASS
-- Question: How many customers are in the customer table?
SELECT COUNT(*) FROM customer;

-- N-037 | aggregation | PASS
-- Question: What is the average current price of all items?
SELECT AVG(i_current_price) FROM item;

-- N-038 | aggregation | PASS
-- Question: What is the total net paid across store sales?
SELECT SUM(ss_net_paid) FROM store_sales;

-- N-039 | aggregation | PASS
-- Question: What is the largest extended sales price in web sales?
SELECT ws_ext_sales_price FROM web_sales ORDER BY ws_ext_sales_price DESC LIMIT 1;

-- N-040 | aggregation | PASS
-- Question: What is the total quantity sold through catalog sales?
SELECT SUM(cs_quantity) FROM catalog_sales;

-- N-041 | group_by | PASS
-- Question: Show store sales revenue by item category.
SELECT i.i_category, SUM(ss.ss_sales_price) AS total_revenue
FROM item i, store_sales ss
WHERE i.i_item_sk = ss.ss_item_sk
GROUP BY i.i_category;

-- N-042 | group_by | PASS
-- Question: Show store sales revenue by customer state.
SELECT ca.ca_state, SUM(ss.ss_net_paid) AS total_revenue
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
GROUP BY ca.ca_state;

-- N-043 | group_by | PASS
-- Question: Show store sales revenue by calendar year.
SELECT d.d_year, SUM(s.ss_net_paid) AS total_revenue
FROM store_sales s, date_dim d
WHERE s.ss_sold_date_sk = d.d_date_sk
GROUP BY d.d_year;

-- N-044 | group_by | PASS
-- Question: Show web sales revenue by web site.
SELECT ws.web_site_id, ws.web_name, SUM(wb.ws_sales_price) AS total_revenue
FROM web_sales wb
JOIN web_site ws ON wb.ws_web_site_sk = ws.web_site_sk
GROUP BY ws.web_site_id, ws.web_name;

-- N-045 | group_by | PASS
-- Question: Show inventory quantity by warehouse.
SELECT w.w_warehouse_name, SUM(i.inv_quantity_on_hand) AS total_quantity
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
GROUP BY w.w_warehouse_name
HAVING SUM(i.inv_quantity_on_hand) > 0;

-- N-046 | having | PASS
-- Question: Find item categories with more than 100000 in store sales revenue.
SELECT i.i_category
FROM item i, store_sales s
WHERE i.i_item_sk = s.ss_item_sk
GROUP BY i.i_category
HAVING SUM(s.ss_net_paid) > 100000;

-- N-047 | having | PASS
-- Question: Show customer states with more than 1000 store sales rows.
SELECT ca.ca_state
FROM customer c
JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk
GROUP BY ca.ca_state
HAVING COUNT(*) > 1000;

-- N-048 | having | PASS
-- Question: Find customers with more than 10 web orders.
SELECT c.c_customer_sk, c.c_customer_id
FROM customer c
JOIN web_sales ws ON c.c_customer_sk = ws.ws_bill_customer_sk
GROUP BY c.c_customer_sk, c.c_customer_id
HAVING COUNT(ws.ws_order_number) > 10;

-- N-049 | having | PASS
-- Question: Show promotions responsible for more than 50000 in catalog discount amount.
SELECT p.p_promo_id, p.p_promo_name
FROM catalog_sales cs
JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk
GROUP BY p.p_promo_id, p.p_promo_name
HAVING SUM(cs.cs_ext_discount_amt) > 50000;

-- N-050 | having | PASS
-- Question: Find warehouses holding more than 1000000 total units.
SELECT w.w_warehouse_id, w.w_warehouse_name
FROM inventory i, warehouse w
WHERE i.inv_warehouse_sk = w.w_warehouse_sk
GROUP BY w.w_warehouse_sk
HAVING SUM(i.inv_quantity_on_hand) > 1000000;

-- N-051 | distinct | PASS
-- Question: List the distinct customer states.
SELECT DISTINCT customer_address.ca_state
FROM customer
JOIN customer_address ON customer.c_current_addr_sk = customer_address.ca_address_sk;

-- N-052 | distinct | PASS
-- Question: Show all distinct item categories.
SELECT DISTINCT i_category FROM item;

-- N-053 | distinct | PASS
-- Question: List distinct item brands.
SELECT DISTINCT i_brand FROM item;

-- N-054 | distinct | PASS
-- Question: Show distinct shipping mode types.
SELECT DISTINCT sm_type FROM ship_mode;

-- N-055 | distinct | PASS
-- Question: List distinct store return reasons.
SELECT DISTINCT r_reason_desc
FROM reason
WHERE r_reason_sk IN (SELECT sr_reason_sk FROM store_returns);

-- N-056 | count_distinct | PASS
-- Question: How many distinct customers made store purchases?
SELECT COUNT(DISTINCT ss_customer_sk) FROM store_sales;

-- N-057 | count_distinct | PASS
-- Question: How many distinct items were sold through the web channel?
SELECT COUNT(DISTINCT ws_item_sk) FROM web_sales;

-- N-058 | count_distinct | PASS
-- Question: How many different stores have store sales?
SELECT COUNT(DISTINCT ss_store_sk) FROM store_sales;

-- N-059 | count_distinct | PASS
-- Question: How many distinct promotions were used in catalog sales?
SELECT COUNT(DISTINCT cs_promo_sk) FROM catalog_sales;

-- N-060 | count_distinct | PASS
-- Question: How many distinct warehouses have inventory records?
SELECT COUNT(DISTINCT inv_warehouse_sk) FROM inventory;

-- N-061 | order_by | PASS
-- Question: List items from highest to lowest current price.
SELECT i_item_id, i_current_price FROM item ORDER BY i_current_price DESC;

-- N-062 | order_by | PASS
-- Question: Show store sales from highest to lowest net paid.
SELECT ss_sold_date_sk, ss_item_sk, ss_customer_sk, ss_store_sk, ss_net_paid
FROM store_sales
ORDER BY ss_net_paid DESC
LIMIT 1000;

-- N-063 | order_by | PASS
-- Question: List customers from oldest to youngest birth year.
SELECT c_customer_id, c_first_name, c_last_name, c_birth_year
FROM customer
ORDER BY c_birth_year ASC
LIMIT 1000;

-- N-064 | order_by | PASS
-- Question: Show stores ordered by state, city, and store name.
SELECT s_state, s_city, s_store_name FROM store ORDER BY s_state, s_city, s_store_name LIMIT 1;

-- N-065 | order_by | PASS
-- Question: List warehouses from largest to smallest square footage.
SELECT w_warehouse_name, w_warehouse_sq_ft FROM warehouse ORDER BY w_warehouse_sq_ft DESC;

-- N-066 | top_k_limit | PASS
-- Question: Show the 10 most expensive items.
SELECT i_item_id, i_item_desc, i_current_price
FROM item
ORDER BY i_current_price DESC
LIMIT 10;

-- N-067 | top_k_limit | PASS
-- Question: List the 20 store sales rows with the highest net paid.
SELECT ss_sold_date_sk, ss_sold_time_sk, ss_item_sk, ss_customer_sk, ss_cdemo_sk, ss_hdemo_sk, ss_addr_sk, ss_store_sk, ss_promo_sk, ss_ticket_number, ss_quantity, ss_wholesale_cost, ss_list_price, ss_sales_price, ss_ext_discount_amt, ss_ext_sales_price, ss_ext_wholesale_cost, ss_ext_list_price, ss_ext_tax, ss_coupon_amt, ss_net_paid, ss_net_paid_inc_tax, ss_net_profit FROM store_sales ORDER BY ss_net_paid DESC LIMIT 20;

-- N-068 | top_k_limit | PASS
-- Question: Which 10 customers spent the most in store sales?
SELECT c.c_customer_id
FROM customer c
JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk
GROUP BY c.c_customer_sk
ORDER BY SUM(ss.ss_net_paid) DESC
LIMIT 10;

-- N-069 | top_k_limit | PASS
-- Question: Show the 15 web sites with the greatest total web sales.
SELECT ws.web_site_id, ws.web_name
FROM web_site ws
JOIN web_sales w ON ws.web_site_sk = w.ws_web_site_sk
GROUP BY ws.web_site_sk, ws.web_site_id, ws.web_name
ORDER BY SUM(w.ws_sales_price) DESC
LIMIT 15;

-- N-070 | top_k_limit | PASS
-- Question: List the 10 warehouses with the most inventory units.
SELECT w.w_warehouse_id, w.w_warehouse_name
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
GROUP BY w.w_warehouse_sk, w.w_warehouse_id, w.w_warehouse_name
ORDER BY SUM(i.inv_quantity_on_hand) DESC
LIMIT 10;

-- N-071 | subquery | PASS
-- Question: Find items priced above the average current item price.
SELECT i_item_sk, i_item_id, i_current_price
FROM item
WHERE i_current_price > (SELECT AVG(i_current_price) FROM item);

-- N-072 | subquery | PASS
-- Question: Show store sales with net paid above the average store sale.
SELECT ss_sold_date_sk, ss_sold_time_sk, ss_item_sk, ss_customer_sk, ss_cdemo_sk, ss_hdemo_sk, ss_addr_sk, ss_store_sk, ss_promo_sk, ss_ticket_number, ss_quantity, ss_wholesale_cost, ss_list_price, ss_sales_price, ss_ext_discount_amt, ss_ext_sales_price, ss_ext_wholesale_cost, ss_ext_list_price, ss_ext_tax, ss_coupon_amt, ss_net_paid, ss_net_paid_inc_tax, ss_net_profit
FROM store_sales
WHERE ss_net_paid > (SELECT AVG(ss_net_paid) FROM store_sales);

-- N-073 | subquery | PASS
-- Question: List customers whose total store spending is above average customer spending.
SELECT c.c_customer_id, c.c_first_name, c.c_last_name
FROM customer c
JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk
JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
GROUP BY c.c_customer_sk, c.c_customer_id, c.c_first_name, c.c_last_name
HAVING SUM(ss.ss_net_paid) > (
    SELECT AVG(total_spending)
    FROM (
        SELECT SUM(ss2.ss_net_paid) AS total_spending
        FROM store_sales ss2
        JOIN customer c2 ON ss2.ss_customer_sk = c2.c_customer_sk
        JOIN date_dim d2 ON ss2.ss_sold_date_sk = d2.d_date_sk
        GROUP BY c2.c_customer_sk
    )
);

-- N-074 | subquery | PASS
-- Question: Find warehouses with inventory above the average warehouse inventory.
SELECT w.w_warehouse_id, w.w_warehouse_name
FROM warehouse w
JOIN inventory i ON w.w_warehouse_sk = i.inv_warehouse_sk
GROUP BY w.w_warehouse_sk, w.w_warehouse_id, w.w_warehouse_name
HAVING SUM(i.inv_quantity_on_hand) > (
    SELECT AVG(warehouse_total)
    FROM (
        SELECT SUM(inv_quantity_on_hand) AS warehouse_total
        FROM inventory
        GROUP BY inv_warehouse_sk
    )
);

-- N-075 | subquery | PASS
-- Question: Show stores whose floor space is above the average store floor space.
SELECT s.s_store_id, s.s_store_name, s.s_floor_space
FROM store s
WHERE s.s_floor_space > (SELECT AVG(s2.s_floor_space) FROM store s2);

-- N-076 | exists_not_exists | PASS
-- Question: List customers who have at least one store purchase.
SELECT c.c_customer_sk, c.c_customer_id
FROM customer c
JOIN store_sales ss ON c.c_customer_sk = ss.ss_customer_sk
GROUP BY c.c_customer_sk, c.c_customer_id
HAVING COUNT(*) >= 1;

-- N-077 | exists_not_exists | PASS
-- Question: Find items that have never been sold through the web channel.
SELECT i.i_item_sk, i.i_item_id
FROM item i
WHERE NOT EXISTS (
    SELECT 1
    FROM web_sales ws
    WHERE ws.ws_item_sk = i.i_item_sk
);

-- N-078 | exists_not_exists | PASS
-- Question: Show promotions that were used in at least one catalog sale.
SELECT p.p_promo_id, p.p_promo_name
FROM promotion p
JOIN catalog_sales cs ON p.p_promo_sk = cs.cs_promo_sk
GROUP BY p.p_promo_sk
HAVING COUNT(*) >= 1;

-- N-079 | exists_not_exists | PASS
-- Question: Find stores with no store sales.
SELECT s.s_store_sk, s.s_store_id, s.s_store_name
FROM store s
WHERE NOT EXISTS (
    SELECT 1
    FROM store_sales ss
    WHERE ss.ss_store_sk = s.s_store_sk
);

-- N-080 | exists_not_exists | PASS
-- Question: List warehouses that have inventory for more than one item.
SELECT w.w_warehouse_id, w.w_warehouse_name
FROM warehouse w
JOIN inventory i ON w.w_warehouse_sk = i.inv_warehouse_sk
GROUP BY w.w_warehouse_sk, w.w_warehouse_id, w.w_warehouse_name
HAVING COUNT(DISTINCT i.inv_item_sk) > 1;

-- N-081 | set_operation | PASS
-- Question: List customer IDs that appear in both store sales and web sales.
SELECT c.c_customer_id
FROM customer c
WHERE EXISTS (
    SELECT 1
    FROM store_sales ss
    WHERE ss.ss_customer_sk = c.c_customer_sk
)
AND EXISTS (
    SELECT 1
    FROM web_sales ws
    WHERE ws.ws_bill_customer_sk = c.c_customer_sk
);

-- N-082 | set_operation | PASS
-- Question: Find item IDs sold through both catalog and web channels.
SELECT DISTINCT i.i_item_id
FROM item i
WHERE i.i_item_sk IN (SELECT cs_item_sk FROM catalog_sales)
  AND i.i_item_sk IN (SELECT ws_item_sk FROM web_sales);

-- N-083 | set_operation | PASS
-- Question: Combine all customer IDs from store, catalog, and web sales without duplicates.
WITH all_customers AS (
    SELECT cs_bill_customer_sk AS customer_sk FROM catalog_sales
    UNION
    SELECT ss_customer_sk AS customer_sk FROM store_sales
    UNION
    SELECT ws_bill_customer_sk AS customer_sk FROM web_sales
)
SELECT DISTINCT c.c_customer_id
FROM customer c
JOIN all_customers ac ON c.c_customer_sk = ac.customer_sk;

-- N-084 | set_operation | PASS
-- Question: Find customers with store purchases but no web purchases.
SELECT c.c_customer_sk, c.c_customer_id
FROM customer c
WHERE EXISTS (
    SELECT 1
    FROM store_sales ss
    WHERE ss.ss_customer_sk = c.c_customer_sk
)
AND NOT EXISTS (
    SELECT 1
    FROM web_sales ws
    WHERE ws.ws_bill_customer_sk = c.c_customer_sk
);

-- N-085 | set_operation | PASS
-- Question: List item categories that appear in store sales or catalog sales.
SELECT i.i_category
FROM store_sales ss
JOIN catalog_sales cs ON ss.ss_item_sk = cs.cs_item_sk
JOIN item i ON ss.ss_item_sk = i.i_item_sk
GROUP BY i.i_category
HAVING COUNT(*) > 0;

-- N-086 | case_expression | PASS
-- Question: Label items as low, medium, or high price.
SELECT i_item_id, i_current_price,
  CASE
    WHEN i_current_price < 50 THEN 'low'
    WHEN i_current_price < 150 THEN 'medium'
    ELSE 'high'
  END AS price_label
FROM item;

-- N-087 | case_expression | PASS
-- Question: Classify store sales as small, medium, or large by net paid.
SELECT ss_net_paid,
       CASE
         WHEN ss_net_paid < 100 THEN 'small'
         WHEN ss_net_paid BETWEEN 100 AND 500 THEN 'medium'
         ELSE 'large'
       END AS category
FROM store_sales;

-- N-088 | case_expression | PASS
-- Question: Label inventory as out, low, or well stocked.
SELECT
  inv_item_sk,
  inv_warehouse_sk,
  inv_quantity_on_hand,
  CASE
    WHEN inv_quantity_on_hand = 0 THEN 'out'
    WHEN inv_quantity_on_hand > 0 AND inv_quantity_on_hand <= 10 THEN 'low'
    ELSE 'well stocked'
  END AS status
FROM inventory;

-- N-089 | case_expression | PASS
-- Question: Group customers into birth-year generations.
SELECT c_birth_year
FROM customer
GROUP BY c_birth_year
HAVING COUNT(*) > 0;

-- N-090 | case_expression | PASS
-- Question: Classify stores as small, medium, or large by floor space.
SELECT s_store_name, s_floor_space,
CASE
  WHEN s_floor_space < 5000 THEN 'small'
  WHEN s_floor_space < 15000 THEN 'medium'
  ELSE 'large'
END AS size_category
FROM store;

-- N-091 | derived_metric | PASS
-- Question: For each store sale, calculate the effective unit price using net paid divided by quantity.
SELECT ss_sold_date_sk, ss_item_sk, ss_ticket_number, ss_quantity, ss_net_paid, ss_net_paid / ss_quantity AS effective_unit_price FROM store_sales;

-- N-092 | derived_metric | PASS
-- Question: For each web sale, calculate discount percentage from list price and sales price.
SELECT ws_order_number, ws_list_price, ws_sales_price, ws_ext_discount_amt, (ws_list_price - ws_sales_price) * 100.0 / ws_list_price AS discount_percentage FROM web_sales;

-- N-093 | derived_metric | PASS
-- Question: For each catalog sale, calculate profit margin as net profit divided by net paid.
SELECT cs_order_number, cs_net_profit, cs_net_paid, (cs_net_profit * 1.0 / cs_net_paid) AS profit_margin FROM catalog_sales;

-- N-094 | derived_metric | PASS
-- Question: For each store return, calculate return amount per returned unit.
SELECT "store_returns"."sr_return_quantity", SUM("store_returns"."sr_return_amt") AS "total_return_amt", SUM("store_returns"."sr_return_quantity") AS "total_return_quantity" FROM "store_returns";

-- N-095 | derived_metric | PASS
-- Question: For each inventory row, calculate units per thousand square feet of warehouse space.
SELECT i.inv_item_sk, i.inv_warehouse_sk, i.inv_quantity_on_hand, w.w_warehouse_sq_ft, (CAST(i.inv_quantity_on_hand AS REAL) / (w.w_warehouse_sq_ft / 1000.0)) AS units_per_thousand_sq_ft
FROM inventory i, warehouse w
WHERE i.inv_warehouse_sk = w.w_warehouse_sk;

-- N-096 | window_cte | PASS
-- Question: Rank items by store sales revenue within each item category.
WITH item_revenue AS (
  SELECT
    i.i_category,
    i.i_item_id,
    SUM(ss.ss_net_paid) AS total_revenue
  FROM item i
  JOIN store_sales ss ON i.i_item_sk = ss.ss_item_sk
  GROUP BY i.i_category, i.i_item_id
)
SELECT
  i_category,
  i_item_id,
  total_revenue AS ss_net_paid
FROM item_revenue
ORDER BY i_category, total_revenue DESC;

-- N-097 | window_cte | PASS
-- Question: Show a running total of daily store sales revenue.
WITH daily_sales AS (
  SELECT
    d.d_date,
    SUM(s.ss_net_paid) AS daily_revenue
  FROM date_dim d, store_sales s
  WHERE d.d_date_sk = s.ss_sold_date_sk
  GROUP BY d.d_date
)
SELECT
  d_date,
  SUM(daily_revenue) OVER (ORDER BY d_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
FROM daily_sales;

-- N-098 | window_cte | PASS
-- Question: Return the latest web order for each customer.
WITH ranked_orders AS (
  SELECT
    ws.ws_order_number,
    ws.ws_bill_customer_sk,
    ws.ws_sold_date_sk,
    ROW_NUMBER() OVER (
      PARTITION BY ws.ws_bill_customer_sk
      ORDER BY ws.ws_sold_date_sk DESC
    ) AS rn
  FROM web_sales ws
  JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
)
SELECT
  ws_order_number,
  ws_bill_customer_sk,
  ws_sold_date_sk
FROM ranked_orders
WHERE rn = 1;

-- N-099 | window_cte | PASS
-- Question: Find the highest-revenue store in each state.
WITH store_state_profit AS (
  SELECT
    s.s_state,
    s.s_store_name,
    SUM(ss.ss_net_profit) AS total_net_profit
  FROM store s
  JOIN store_sales ss ON s.s_store_sk = ss.ss_store_sk
  GROUP BY s.s_state, s.s_store_name
),
ranked_stores AS (
  SELECT
    s_state,
    s_store_name,
    total_net_profit,
    RANK() OVER (PARTITION BY s_state ORDER BY total_net_profit DESC) AS profit_rank
  FROM store_state_profit
)
SELECT
  s_state,
  s_store_name,
  total_net_profit
FROM ranked_stores
WHERE profit_rank = 1;

-- N-100 | window_cte | PASS
-- Question: Compare each year's catalog sales with the previous year's catalog sales.
WITH yearly_sales AS (
    SELECT
        d.d_year,
        SUM(cs.cs_net_paid) AS total_net_paid
    FROM catalog_sales cs
    JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk
    GROUP BY d.d_year
)
SELECT
    d_year,
    total_net_paid,
    LAG(total_net_paid) OVER (ORDER BY d_year) AS prev_year_net_paid
FROM yearly_sales
ORDER BY d_year;
