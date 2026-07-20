-- SpiderSQL generated SQL: 100_structured_nl
-- Database: TPC-DS #51
-- No SQL is hard-matched by the benchmark.

-- S-001 | select_projection | PASS
-- Question: From customer, return c_customer_sk, c_customer_id, c_first_name, c_last_name, and c_birth_year.
SELECT c_customer_sk, c_customer_id, c_first_name, c_last_name, c_birth_year FROM customer;

-- S-002 | select_projection | PASS
-- Question: From item, return i_item_sk, i_item_id, i_item_desc, i_current_price, and i_category.
SELECT i_item_sk, i_item_id, i_item_desc, i_current_price, i_category FROM item;

-- S-003 | select_projection | PASS
-- Question: From store, return s_store_sk, s_store_id, s_store_name, s_city, and s_state.
SELECT s_store_sk, s_store_id, s_store_name, s_city, s_state FROM store;

-- S-004 | select_projection | PASS
-- Question: From web_site, return web_site_sk, web_site_id, web_name, and web_class.
SELECT web_site_sk, web_site_id, web_name, web_class FROM web_site;

-- S-005 | select_projection | PASS
-- Question: From warehouse, return w_warehouse_sk, w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft, and w_state.
SELECT w_warehouse_sk, w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft, w_state FROM warehouse;

-- S-006 | filter_comparison | PASS
-- Question: From item, return i_item_sk, i_item_id, i_item_desc, and i_current_price where i_current_price is greater than 100.
SELECT i_item_sk, i_item_id, i_item_desc, i_current_price FROM item WHERE i_current_price > 100;

-- S-007 | filter_comparison | PASS
-- Question: From store_sales, return ss_ticket_number, ss_item_sk, ss_customer_sk, and ss_quantity where ss_quantity is greater than 5.
SELECT ss.ss_ticket_number, ss.ss_item_sk, ss.ss_customer_sk, ss.ss_quantity
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
WHERE ss.ss_quantity > 5;

-- S-008 | filter_comparison | PASS
-- Question: From web_sales, return ws_order_number, ws_item_sk, ws_bill_customer_sk, and ws_net_paid where ws_net_paid is greater than 500.
SELECT ws.ws_order_number, ws.ws_item_sk, ws.ws_bill_customer_sk, ws.ws_net_paid
FROM web_sales ws
JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
WHERE ws.ws_net_paid > 500;

-- S-009 | filter_comparison | PASS
-- Question: From catalog_sales, return cs_order_number, cs_item_sk, cs_bill_customer_sk, and cs_ext_discount_amt where cs_ext_discount_amt is greater than 50.
SELECT cs.cs_order_number, cs.cs_item_sk, cs.cs_bill_customer_sk, cs.cs_ext_discount_amt
FROM catalog_sales cs
JOIN customer c ON cs.cs_bill_customer_sk = c.c_customer_sk
WHERE cs.cs_ext_discount_amt > 50;

-- S-010 | filter_comparison | PASS
-- Question: From store_returns, return sr_ticket_number, sr_item_sk, sr_customer_sk, and sr_return_amt where sr_return_amt is greater than 100.
SELECT sr.sr_ticket_number, sr.sr_item_sk, sr.sr_customer_sk, sr.sr_return_amt
FROM store_returns sr
JOIN customer c ON sr.sr_customer_sk = c.c_customer_sk
WHERE sr.sr_return_amt > 100;

-- S-011 | range_between | PASS
-- Question: From date_dim, return d_date_sk, d_date, d_year, and d_moy where d_date is between 1999-01-01 and 2000-12-31.
SELECT d_date_sk, d_date, d_year, d_moy FROM date_dim WHERE d_date BETWEEN '1999-01-01' AND '2000-12-31';

-- S-012 | range_between | PASS
-- Question: From item, return i_item_sk, i_item_id, and i_current_price where i_current_price is between 20 and 80.
SELECT i_item_sk, i_item_id, i_current_price FROM item WHERE i_current_price BETWEEN 20 AND 80;

-- S-013 | range_between | PASS
-- Question: From customer, return c_customer_sk, c_first_name, c_last_name, and c_birth_year where c_birth_year is between 1940 and 1960.
SELECT c_customer_sk, c_first_name, c_last_name, c_birth_year FROM customer WHERE c_birth_year BETWEEN 1940 AND 1960;

-- S-014 | range_between | PASS
-- Question: From inventory, return inv_date_sk, inv_item_sk, inv_warehouse_sk, and inv_quantity_on_hand where inv_quantity_on_hand is between 100 and 500.
SELECT i.inv_date_sk, i.inv_item_sk, i.inv_warehouse_sk, i.inv_quantity_on_hand
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
WHERE i.inv_quantity_on_hand BETWEEN 100 AND 500;

-- S-015 | range_between | PASS
-- Question: From store, return s_store_sk, s_store_name, and s_floor_space where s_floor_space is between 50000 and 100000.
SELECT s_store_sk, s_store_name, s_floor_space FROM store WHERE s_floor_space BETWEEN 50000 AND 100000;

-- S-016 | pattern_text | PASS
-- Question: From item, return i_item_sk, i_item_id, and i_item_desc where i_item_desc contains cotton.
SELECT i_item_sk, i_item_id, i_item_desc FROM item WHERE i_item_desc LIKE '%cotton%';

-- S-017 | pattern_text | PASS
-- Question: From customer, return c_customer_sk, c_first_name, and c_last_name where c_last_name starts with A.
SELECT c_customer_sk, c_first_name, c_last_name FROM customer WHERE c_last_name LIKE 'A%';

-- S-018 | pattern_text | PASS
-- Question: From customer_address, return ca_address_sk, ca_city, ca_state, and ca_zip where ca_city starts with New.
SELECT ca.ca_address_sk, ca.ca_city, ca.ca_state, ca.ca_zip
FROM customer_address ca
JOIN customer c ON c.c_current_addr_sk = ca.ca_address_sk
WHERE ca.ca_city LIKE 'New%';

-- S-019 | pattern_text | PASS
-- Question: From web_page, return wp_web_page_sk, wp_web_page_id, and wp_url where wp_url contains catalog.
SELECT wp_web_page_sk, wp_web_page_id, wp_url FROM web_page WHERE wp_url LIKE '%catalog%';

-- S-020 | pattern_text | PASS
-- Question: From promotion, return p_promo_sk, p_promo_id, and p_promo_name where p_promo_name contains holiday.
SELECT p_promo_sk, p_promo_id, p_promo_name
FROM promotion
WHERE p_promo_name LIKE '%holiday%';

-- S-021 | null_boolean | PASS
-- Question: From customer, return c_customer_sk and c_current_addr_sk where c_current_addr_sk is null.
SELECT c_customer_sk, c_current_addr_sk FROM customer WHERE c_current_addr_sk IS NULL;

-- S-022 | null_boolean | PASS
-- Question: From item, return i_item_sk, i_item_id, and i_brand where i_brand is null.
SELECT i_item_sk, i_item_id, i_brand FROM item WHERE i_brand IS NULL;

-- S-023 | null_boolean | PASS
-- Question: From web_sales, return ws_order_number, ws_item_sk, and ws_ship_date_sk where ws_ship_date_sk is null.
SELECT ws_order_number, ws_item_sk, ws_ship_date_sk FROM web_sales WHERE ws_ship_date_sk IS NULL;

-- S-024 | null_boolean | PASS
-- Question: From store, return s_store_sk, s_store_name, and s_closed_date_sk where s_closed_date_sk is null.
SELECT s_store_sk, s_store_name, s_closed_date_sk FROM store WHERE s_closed_date_sk IS NULL;

-- S-025 | null_boolean | PASS
-- Question: From promotion, return p_promo_sk, p_promo_name, and p_channel_email where p_channel_email is not null.
SELECT p_promo_sk, p_promo_name, p_channel_email
FROM promotion
WHERE p_channel_email IS NOT NULL;

-- S-026 | join | PASS
-- Question: Join store_sales to item on ss_item_sk and return ss_ticket_number, i_item_id, i_item_desc, i_category, ss_quantity, and ss_net_paid.
SELECT ss.ss_ticket_number, i.i_item_id, i.i_item_desc, i.i_category, ss.ss_quantity, ss.ss_net_paid
FROM store_sales ss, item i
WHERE ss.ss_item_sk = i.i_item_sk;

-- S-027 | join | PASS
-- Question: Join store_sales to customer on ss_customer_sk and return ss_ticket_number, c_customer_id, customer name, ss_quantity, and ss_net_paid.
SELECT ss.ss_ticket_number, c.c_customer_id, c.c_first_name, c.c_last_name, ss.ss_quantity, ss.ss_net_paid
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk;

-- S-028 | join | PASS
-- Question: Join web_sales to web_site on ws_web_site_sk and return ws_order_number, web_site_id, web_name, ws_quantity, and ws_net_paid.
SELECT ws.ws_order_number, w.web_site_id, w.web_name, ws.ws_quantity, ws.ws_net_paid
FROM web_sales ws, web_site w
WHERE ws.ws_web_site_sk = w.web_site_sk;

-- S-029 | join | PASS
-- Question: Join catalog_sales to catalog_page on cs_catalog_page_sk and return cs_order_number, cp_catalog_page_id, cp_description, cs_quantity, and cs_net_paid.
SELECT cs.cs_order_number, cp.cp_catalog_page_id, cp.cp_description, cs.cs_quantity, cs.cs_net_paid
FROM catalog_sales cs
JOIN catalog_page cp ON cs.cs_catalog_page_sk = cp.cp_catalog_page_sk;

-- S-030 | join | PASS
-- Question: Join store_returns to reason on sr_reason_sk and return sr_ticket_number, r_reason_id, r_reason_desc, sr_return_quantity, and sr_return_amt.
SELECT sr.sr_ticket_number, r.r_reason_id, r.r_reason_desc, sr.sr_return_quantity, sr.sr_return_amt
FROM store_returns sr, reason r
WHERE sr.sr_reason_sk = r.r_reason_sk;

-- S-031 | multi_join | PASS
-- Question: Join store_sales, customer, item, store, and date_dim; return ticket number, customer ID, item ID, store ID, date, quantity, and net paid.
SELECT ss.ss_ticket_number, c.c_customer_id, i.i_item_id, s.s_store_id, d.d_date, ss.ss_quantity, ss.ss_net_paid
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
JOIN item i ON ss.ss_item_sk = i.i_item_sk
JOIN store s ON ss.ss_store_sk = s.s_store_sk
JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk;

-- S-032 | multi_join | PASS
-- Question: Join web_sales, customer, item, web_site, and date_dim; return order number, customer ID, item ID, web site ID, date, quantity, and net paid.
SELECT ws.ws_order_number, c.c_customer_id, i.i_item_id, w.web_site_id, d.d_date, ws.ws_quantity, ws.ws_net_paid
FROM web_sales ws
JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
JOIN item i ON ws.ws_item_sk = i.i_item_sk
JOIN web_site w ON ws.ws_web_site_sk = w.web_site_sk
JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk;

-- S-033 | multi_join | PASS
-- Question: Join catalog_sales, customer, item, catalog_page, and date_dim; return order number, customer ID, item ID, catalog page ID, date, quantity, and net paid.
SELECT cs.cs_order_number, c.c_customer_id, i.i_item_id, cp.cp_catalog_page_id, d.d_date, cs.cs_quantity, cs.cs_net_paid
FROM catalog_sales cs
JOIN customer c ON cs.cs_bill_customer_sk = c.c_customer_sk
JOIN item i ON cs.cs_item_sk = i.i_item_sk
JOIN catalog_page cp ON cs.cs_catalog_page_sk = cp.cp_catalog_page_sk
JOIN date_dim d ON cs.cs_sold_date_sk = d.d_date_sk;

-- S-034 | multi_join | PASS
-- Question: Join store_returns, customer, item, store, reason, and date_dim; return ticket number, customer ID, item ID, store ID, reason description, return date, and return amount.
SELECT sr.sr_ticket_number, c.c_customer_id, i.i_item_id, s.s_store_id, r.r_reason_desc, d.d_date, sr.sr_return_amt
FROM store_returns sr
JOIN customer c ON sr.sr_customer_sk = c.c_customer_sk
JOIN item i ON sr.sr_item_sk = i.i_item_sk
JOIN store s ON sr.sr_store_sk = s.s_store_sk
JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk
JOIN date_dim d ON sr.sr_returned_date_sk = d.d_date_sk;

-- S-035 | multi_join | PASS
-- Question: Join inventory, item, warehouse, and date_dim; return inventory date, item ID, warehouse ID, and quantity on hand.
SELECT i.inv_date_sk, it.i_item_id, w.w_warehouse_id, i.inv_quantity_on_hand
FROM inventory i
JOIN item it ON i.inv_item_sk = it.i_item_sk
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
JOIN date_dim d ON i.inv_date_sk = d.d_date_sk;

-- S-036 | aggregation | PASS
-- Question: Return COUNT of all rows in customer as customer_count.
SELECT COUNT(*) AS customer_count FROM customer;

-- S-037 | aggregation | PASS
-- Question: Return AVG of i_current_price from item as average_item_price.
SELECT AVG(i_current_price) AS average_item_price FROM item;

-- S-038 | aggregation | PASS
-- Question: Return SUM of ss_net_paid from store_sales as total_store_net_paid.
SELECT SUM(ss_net_paid) AS total_store_net_paid FROM store_sales;

-- S-039 | aggregation | PASS
-- Question: Return MAX of ws_ext_sales_price from web_sales as maximum_web_extended_price.
SELECT MAX(ws_ext_sales_price) AS maximum_web_extended_price FROM web_sales;

-- S-040 | aggregation | PASS
-- Question: Return SUM of cs_quantity from catalog_sales as total_catalog_quantity.
SELECT SUM(cs_quantity) AS total_catalog_quantity FROM catalog_sales;

-- S-041 | group_by | PASS
-- Question: Join store_sales to item, group by i_category, and return category, COUNT of rows, and SUM of ss_net_paid.
SELECT i.i_category, COUNT(*) AS row_count, SUM(ss.ss_net_paid) AS total_net_paid
FROM store_sales ss
JOIN item i ON ss.ss_item_sk = i.i_item_sk
GROUP BY i.i_category;

-- S-042 | group_by | PASS
-- Question: Join store_sales to customer and customer_address, group by ca_state, and return state, order count, and SUM of ss_net_paid.
SELECT ca.ca_state, COUNT(*) AS order_count, SUM(ss.ss_net_paid) AS total_net_paid
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
GROUP BY ca.ca_state;

-- S-043 | group_by | PASS
-- Question: Join store_sales to date_dim, group by d_year, and return year, sales count, and SUM of ss_net_paid.
SELECT d.d_year, COUNT(*) AS sales_count, SUM(s.ss_net_paid) AS total_net_paid
FROM store_sales s, date_dim d
WHERE s.ss_sold_date_sk = d.d_date_sk
GROUP BY d.d_year;

-- S-044 | group_by | PASS
-- Question: Join web_sales to web_site, group by web_site_sk and web_name, and return order count and SUM of ws_net_paid.
SELECT ws.web_site_sk, ws.web_name, COUNT(*) AS order_count, SUM(wa.ws_net_paid) AS total_net_paid
FROM web_sales wa
JOIN web_site ws ON wa.ws_web_site_sk = ws.web_site_sk
GROUP BY ws.web_site_sk, ws.web_name;

-- S-045 | group_by | PASS
-- Question: Join inventory to warehouse, group by warehouse ID and name, and return SUM of inv_quantity_on_hand.
SELECT w.w_warehouse_id, w.w_warehouse_name, SUM(i.inv_quantity_on_hand)
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
GROUP BY w.w_warehouse_id, w.w_warehouse_name;

-- S-046 | having | PASS
-- Question: Join store_sales to item, group by i_category, and keep categories where SUM of ss_net_paid is greater than 100000.
SELECT i.i_category
FROM item i
JOIN store_sales s ON i.i_item_sk = s.ss_item_sk
GROUP BY i.i_category
HAVING SUM(s.ss_net_paid) > 100000;

-- S-047 | having | PASS
-- Question: Join store_sales to customer and customer_address, group by ca_state, and keep states where COUNT of sales rows is greater than 1000.
SELECT ca.ca_state
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
JOIN customer_address ca ON ss.ss_addr_sk = ca.ca_address_sk
GROUP BY ca.ca_state
HAVING COUNT(*) > 1000;

-- S-048 | having | PASS
-- Question: Group web_sales by ws_bill_customer_sk and keep customers where COUNT DISTINCT ws_order_number is greater than 10.
SELECT ws_bill_customer_sk
FROM web_sales
JOIN customer ON web_sales.ws_bill_customer_sk = customer.c_customer_sk
GROUP BY ws_bill_customer_sk
HAVING COUNT(DISTINCT ws_order_number) > 10;

-- S-049 | having | PASS
-- Question: Group catalog_sales by cs_promo_sk and keep promotions where SUM of cs_ext_discount_amt is greater than 50000.
SELECT cs_promo_sk
FROM catalog_sales
GROUP BY cs_promo_sk
HAVING SUM(cs_ext_discount_amt) > 50000;

-- S-050 | having | PASS
-- Question: Group inventory by inv_warehouse_sk and keep warehouses where SUM of inv_quantity_on_hand is greater than 1000000.
SELECT i.inv_warehouse_sk
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
GROUP BY i.inv_warehouse_sk
HAVING SUM(i.inv_quantity_on_hand) > 1000000;

-- S-051 | distinct | PASS
-- Question: Return DISTINCT ca_state from customer_address where ca_state is not null.
SELECT DISTINCT ca_state
FROM customer_address
JOIN customer ON 1=1
WHERE ca_state IS NOT NULL;

-- S-052 | distinct | PASS
-- Question: Return DISTINCT i_category from item where i_category is not null.
SELECT DISTINCT i_category FROM item WHERE i_category IS NOT NULL;

-- S-053 | distinct | PASS
-- Question: Return DISTINCT i_brand from item where i_brand is not null.
SELECT DISTINCT i_brand FROM item WHERE i_brand IS NOT NULL;

-- S-054 | distinct | PASS
-- Question: Return DISTINCT sm_type from ship_mode.
SELECT DISTINCT sm_type FROM ship_mode;

-- S-055 | distinct | PASS
-- Question: Join store_returns to reason and return DISTINCT r_reason_desc.
SELECT DISTINCT r.r_reason_desc
FROM store_returns sr
JOIN reason r ON sr.sr_reason_sk = r.r_reason_sk;

-- S-056 | count_distinct | PASS
-- Question: Return COUNT DISTINCT ss_customer_sk from store_sales.
SELECT COUNT(DISTINCT ss.ss_customer_sk)
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk;

-- S-057 | count_distinct | PASS
-- Question: Return COUNT DISTINCT ws_item_sk from web_sales.
SELECT COUNT(DISTINCT ws_item_sk) FROM web_sales;

-- S-058 | count_distinct | PASS
-- Question: Return COUNT DISTINCT ss_store_sk from store_sales.
SELECT COUNT(DISTINCT ss_store_sk) FROM store_sales;

-- S-059 | count_distinct | PASS
-- Question: Return COUNT DISTINCT cs_promo_sk from catalog_sales where cs_promo_sk is not null.
SELECT COUNT(DISTINCT cs_promo_sk) FROM catalog_sales WHERE cs_promo_sk IS NOT NULL;

-- S-060 | count_distinct | PASS
-- Question: Return COUNT DISTINCT inv_warehouse_sk from inventory.
SELECT COUNT(DISTINCT i.inv_warehouse_sk)
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk;

-- S-061 | order_by | PASS
-- Question: Return item ID, description, category, and current price ordered by i_current_price descending.
SELECT i_item_id, i_item_desc, i_category, i_current_price
FROM item
ORDER BY i_current_price DESC
LIMIT 100;

-- S-062 | order_by | PASS
-- Question: Return store sales ticket number, item key, customer key, and net paid ordered by ss_net_paid descending.
SELECT ss.ss_ticket_number, ss.ss_item_sk, ss.ss_customer_sk, ss.ss_net_paid
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
ORDER BY ss.ss_net_paid DESC;

-- S-063 | order_by | PASS
-- Question: Return customer ID, first name, last name, and birth year ordered by c_birth_year ascending.
SELECT c_customer_id, c_first_name, c_last_name, c_birth_year
FROM customer
ORDER BY c_birth_year ASC
LIMIT 1000;

-- S-064 | order_by | PASS
-- Question: Return store ID, store name, city, and state ordered by s_state, s_city, and s_store_name.
SELECT s_store_id, s_store_name, s_city, s_state FROM store ORDER BY s_state, s_city, s_store_name LIMIT 1;

-- S-065 | order_by | PASS
-- Question: Return warehouse ID, name, square footage, and state ordered by w_warehouse_sq_ft descending.
SELECT w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft, w_state FROM warehouse ORDER BY w_warehouse_sq_ft DESC LIMIT 1;

-- S-066 | top_k_limit | PASS
-- Question: Return the top 10 items ordered by i_current_price descending.
SELECT i_item_sk, i_current_price FROM item ORDER BY i_current_price DESC LIMIT 10;

-- S-067 | top_k_limit | PASS
-- Question: Return the top 20 store_sales rows ordered by ss_net_paid descending.
SELECT ss_sold_date_sk, ss_sold_time_sk, ss_item_sk, ss_customer_sk, ss_cdemo_sk, ss_hdemo_sk, ss_addr_sk, ss_store_sk, ss_promo_sk, ss_ticket_number, ss_quantity, ss_wholesale_cost, ss_list_price, ss_sales_price, ss_ext_discount_amt, ss_ext_sales_price, ss_ext_wholesale_cost, ss_ext_list_price, ss_ext_tax, ss_coupon_amt, ss_net_paid, ss_net_paid_inc_tax, ss_net_profit FROM store_sales ORDER BY ss_net_paid DESC LIMIT 20;

-- S-068 | top_k_limit | PASS
-- Question: Group store_sales by ss_customer_sk, order by SUM of ss_net_paid descending, and return the top 10.
SELECT ss.ss_customer_sk
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
GROUP BY ss.ss_customer_sk
ORDER BY SUM(ss.ss_net_paid) DESC
LIMIT 10;

-- S-069 | top_k_limit | PASS
-- Question: Group web_sales by ws_web_site_sk, order by SUM of ws_net_paid descending, and return the top 15.
SELECT ws_web_site_sk
FROM web_sales
JOIN web_site ON web_sales.ws_web_site_sk = web_site.web_site_sk
GROUP BY ws_web_site_sk
ORDER BY SUM(ws_net_paid) DESC
LIMIT 15;

-- S-070 | top_k_limit | PASS
-- Question: Group inventory by inv_warehouse_sk, order by SUM of inv_quantity_on_hand descending, and return the top 10.
SELECT i.inv_warehouse_sk
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
GROUP BY i.inv_warehouse_sk
ORDER BY SUM(i.inv_quantity_on_hand) DESC
LIMIT 10;

-- S-071 | subquery | PASS
-- Question: Return item rows where i_current_price is greater than a scalar subquery computing AVG i_current_price.
SELECT * FROM item WHERE i_current_price > (SELECT AVG(i_current_price) FROM item);

-- S-072 | subquery | PASS
-- Question: Return store_sales rows where ss_net_paid is greater than a scalar subquery computing AVG ss_net_paid.
SELECT * FROM store_sales WHERE ss_net_paid > (SELECT AVG(ss_net_paid) FROM store_sales);

-- S-073 | subquery | PASS
-- Question: Aggregate store_sales by ss_customer_sk and keep customer totals greater than the average of customer totals.
SELECT ss_customer_sk
FROM store_sales
JOIN customer ON store_sales.ss_customer_sk = customer.c_customer_sk
GROUP BY ss_customer_sk
HAVING SUM(ss_net_paid) > (
    SELECT AVG(customer_total)
    FROM (
        SELECT SUM(ss_net_paid) AS customer_total
        FROM store_sales
        GROUP BY ss_customer_sk
    )
);

-- S-074 | subquery | PASS
-- Question: Aggregate inventory by inv_warehouse_sk and keep warehouse totals greater than the average warehouse total.
SELECT i.inv_warehouse_sk
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
GROUP BY i.inv_warehouse_sk
HAVING SUM(i.inv_quantity_on_hand) > (
    SELECT AVG(warehouse_total)
    FROM (
        SELECT SUM(inv_quantity_on_hand) AS warehouse_total
        FROM inventory
        GROUP BY inv_warehouse_sk
    )
);

-- S-075 | subquery | PASS
-- Question: Return store rows where s_floor_space is greater than a scalar subquery computing AVG s_floor_space.
SELECT * FROM store WHERE s_floor_space > (SELECT AVG(s_floor_space) FROM store);

-- S-076 | exists_not_exists | PASS
-- Question: Return customer rows where an EXISTS subquery finds store_sales with matching c_customer_sk.
SELECT c.c_customer_sk, c.c_customer_id, c.c_first_name, c.c_last_name, c.c_salutation, c.c_preferred_cust_flag, c.c_birth_day, c.c_birth_month, c.c_birth_year, c.c_birth_country, c.c_login, c.c_email_address, c.c_first_shipto_date_sk, c.c_first_sales_date_sk, c.c_current_cdemo_sk, c.c_current_hdemo_sk, c.c_current_addr_sk, c.c_last_review_date_sk
FROM customer c
WHERE EXISTS (
    SELECT 1
    FROM store_sales ss
    WHERE ss.ss_customer_sk = c.c_customer_sk
);

-- S-077 | exists_not_exists | PASS
-- Question: Return item rows where a NOT EXISTS subquery finds no web_sales with matching i_item_sk.
SELECT i.*
FROM item i
WHERE NOT EXISTS (
  SELECT 1
  FROM web_sales ws
  WHERE ws.ws_item_sk = i.i_item_sk
);

-- S-078 | exists_not_exists | PASS
-- Question: Return promotion rows where an EXISTS subquery finds catalog_sales with matching p_promo_sk.
SELECT p.p_promo_sk, p.p_promo_id, p.p_start_date_sk, p.p_end_date_sk, p.p_item_sk, p.p_cost, p.p_response_target, p.p_promo_name, p.p_channel_dmail, p.p_channel_email, p.p_channel_catalog, p.p_channel_tv, p.p_channel_radio, p.p_channel_press, p.p_channel_event, p.p_channel_demo, p.p_channel_details, p.p_purpose, p.p_discount_active
FROM promotion p
WHERE EXISTS (
    SELECT 1
    FROM catalog_sales cs
    WHERE cs.cs_promo_sk = p.p_promo_sk
);

-- S-079 | exists_not_exists | PASS
-- Question: Return store rows where a NOT EXISTS subquery finds no store_sales with matching s_store_sk.
SELECT s.s_store_sk, s.s_store_id, s.s_store_name
FROM store s
WHERE NOT EXISTS (
    SELECT 1
    FROM store_sales ss
    WHERE ss.ss_store_sk = s.s_store_sk
);

-- S-080 | exists_not_exists | PASS
-- Question: Return warehouse rows where an EXISTS or grouped subquery finds more than one distinct inv_item_sk.
SELECT w.w_warehouse_sk, w.w_warehouse_id, w.w_warehouse_name, w.w_warehouse_sq_ft, w.w_street_number, w.w_street_name, w.w_street_type, w.w_suite_number, w.w_city, w.w_county, w.w_state, w.w_zip, w.w_country, w.w_gmt_offset
FROM warehouse w
WHERE EXISTS (
    SELECT 1
    FROM inventory i
    WHERE i.inv_warehouse_sk = w.w_warehouse_sk
    GROUP BY i.inv_warehouse_sk
    HAVING COUNT(DISTINCT i.inv_item_sk) > 1
);

-- S-081 | set_operation | FAIL
-- Question: Use INTERSECT to return customer keys from store_sales and web_sales.
-- No SQL generated.

-- S-082 | set_operation | PASS
-- Question: Use INTERSECT to return item keys from catalog_sales and web_sales.
SELECT cs_item_sk FROM catalog_sales WHERE cs_item_sk IN (SELECT ws_item_sk FROM web_sales)
UNION
SELECT ws_item_sk FROM web_sales WHERE ws_item_sk IN (SELECT cs_item_sk FROM catalog_sales);

-- S-083 | set_operation | PASS
-- Question: Use UNION to combine customer keys from store_sales, catalog_sales, and web_sales.
WITH store_customers AS (
    SELECT ss_customer_sk AS customer_sk FROM store_sales
),
catalog_customers AS (
    SELECT cs_bill_customer_sk AS customer_sk FROM catalog_sales
),
web_customers AS (
    SELECT ws_bill_customer_sk AS customer_sk FROM web_sales
),
combined_customers AS (
    SELECT customer_sk FROM store_customers
    UNION
    SELECT customer_sk FROM catalog_customers
    UNION
    SELECT customer_sk FROM web_customers
)
SELECT 
    (SELECT ss_customer_sk FROM store_sales WHERE ss_customer_sk = cc.customer_sk LIMIT 1) AS store_sales_ss_customer_sk,
    (SELECT cs_bill_customer_sk FROM catalog_sales WHERE cs_bill_customer_sk = cc.customer_sk LIMIT 1) AS catalog_sales_cs_bill_customer_sk,
    (SELECT ws_bill_customer_sk FROM web_sales WHERE ws_bill_customer_sk = cc.customer_sk LIMIT 1) AS web_sales_ws_bill_customer_sk
FROM combined_customers cc
JOIN customer c ON c.c_customer_sk = cc.customer_sk
JOIN store_sales ss ON ss.ss_customer_sk = cc.customer_sk
JOIN catalog_sales cs ON cs.cs_bill_customer_sk = cc.customer_sk
JOIN web_sales ws ON ws.ws_bill_customer_sk = cc.customer_sk
GROUP BY cc.customer_sk;

-- S-084 | set_operation | FAIL
-- Question: Use EXCEPT to return customer keys from store_sales that do not occur in web_sales.
-- No SQL generated.

-- S-085 | set_operation | PASS
-- Question: Use UNION to combine distinct item categories reached through store_sales and catalog_sales.
SELECT DISTINCT i.i_category
FROM store_sales ss, item i
WHERE ss.ss_item_sk = i.i_item_sk
UNION
SELECT DISTINCT i.i_category
FROM catalog_sales cs, item i
WHERE cs.cs_item_sk = i.i_item_sk;

-- S-086 | case_expression | PASS
-- Question: Return item ID, current price, and a CASE expression: low below 20, medium from 20 through 100, high above 100.
SELECT i_item_id, i_current_price, CASE WHEN i_current_price < 20 THEN 'low' WHEN i_current_price <= 100 THEN 'medium' ELSE 'high' END AS price_category FROM item;

-- S-087 | case_expression | PASS
-- Question: Return store sale ticket and net paid with a CASE expression: small below 50, medium from 50 through 500, large above 500.
SELECT ss_ticket_number, ss_net_paid,
       CASE
         WHEN ss_net_paid < 50 THEN 'small'
         WHEN ss_net_paid BETWEEN 50 AND 500 THEN 'medium'
         ELSE 'large'
       END AS net_paid_category
FROM store_sales;

-- S-088 | case_expression | PASS
-- Question: Return inventory keys, quantity on hand, and a CASE expression: out when 0, low below 50, well_stocked otherwise.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand,
CASE
  WHEN inv_quantity_on_hand = 0 THEN 'out'
  WHEN inv_quantity_on_hand < 50 THEN 'low'
  ELSE 'well_stocked'
END AS stock_status
FROM inventory;

-- S-089 | case_expression | PASS
-- Question: Return customer ID, birth year, and a CASE expression that assigns generation bands from c_birth_year.
SELECT "customer"."c_customer_id", "customer"."c_birth_year", "customer"."c_birth_year" AS "generation_band" FROM "customer";

-- S-090 | case_expression | PASS
-- Question: Return store ID, floor space, and a CASE expression: small below 50000, medium through 100000, large above 100000.
SELECT s_store_id, s_floor_space, CASE WHEN s_floor_space < 50000 THEN 'small' WHEN s_floor_space <= 100000 THEN 'medium' ELSE 'large' END AS size_category FROM store;

-- S-091 | derived_metric | PASS
-- Question: From store_sales, return ticket number, quantity, net paid, and ss_net_paid divided by NULLIF ss_quantity as effective_unit_price.
SELECT ss_ticket_number, ss_quantity, ss_net_paid, ss_net_paid / NULLIF(ss_quantity, 0) AS effective_unit_price FROM store_sales;

-- S-092 | derived_metric | PASS
-- Question: From web_sales, return order number, list price, sales price, and one minus ws_sales_price divided by NULLIF ws_list_price as discount_percent.
SELECT ws_order_number, ws_list_price, ws_sales_price, 1.0 - ws_sales_price / NULLIF(ws_list_price, 0) AS discount_percent FROM web_sales;

-- S-093 | derived_metric | PASS
-- Question: From catalog_sales, return order number, net paid, net profit, and cs_net_profit divided by NULLIF cs_net_paid as profit_margin.
SELECT cs_order_number, cs_net_paid, cs_net_profit, cs_net_profit / NULLIF(cs_net_paid, 0) AS profit_margin FROM catalog_sales;

-- S-094 | derived_metric | PASS
-- Question: From store_returns, return ticket number, return quantity, return amount, and sr_return_amt divided by NULLIF sr_return_quantity as return_amount_per_unit.
SELECT sr_ticket_number, sr_return_quantity, sr_return_amt, sr_return_amt / NULLIF(sr_return_quantity, 0) AS return_amount_per_unit FROM store_returns;

-- S-095 | derived_metric | PASS
-- Question: Join inventory to warehouse and return inventory keys, quantity on hand, warehouse square feet, and quantity divided by warehouse square feet times 1000.
SELECT i.inv_date_sk, i.inv_item_sk, i.inv_warehouse_sk, i.inv_quantity_on_hand, w.w_warehouse_sq_ft, (i.inv_quantity_on_hand * 1000.0 / w.w_warehouse_sq_ft) AS quantity_per_sq_ft
FROM inventory i, warehouse w
WHERE i.inv_warehouse_sk = w.w_warehouse_sk;

-- S-096 | window_cte | PASS
-- Question: Aggregate store_sales by item and join item; apply RANK partitioned by i_category ordered by item revenue descending.
WITH item_revenue AS (
  SELECT
    i.i_item_sk,
    i.i_category,
    SUM(ss.ss_sales_price) AS total_revenue
  FROM item i
  JOIN store_sales ss ON i.i_item_sk = ss.ss_item_sk
  GROUP BY i.i_item_sk, i.i_category
)
SELECT
  i_item_sk,
  i_category
FROM (
  SELECT
    i_item_sk,
    i_category,
    RANK() OVER (PARTITION BY i_category ORDER BY total_revenue DESC) AS revenue_rank
  FROM item_revenue
)
WHERE revenue_rank IS NOT NULL;

-- S-097 | window_cte | PASS
-- Question: Aggregate store_sales by sold date and apply cumulative SUM of daily net paid ordered by date.
WITH daily_sales AS (
  SELECT
    ss.ss_sold_date_sk,
    SUM(ss.ss_net_paid) AS daily_net_paid
  FROM store_sales ss
  JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk
  GROUP BY ss.ss_sold_date_sk
)
SELECT
  ss_sold_date_sk,
  SUM(daily_net_paid) OVER (ORDER BY ss_sold_date_sk) AS cumulative_net_paid
FROM daily_sales;

-- S-098 | window_cte | PASS
-- Question: Use ROW_NUMBER partitioned by ws_bill_customer_sk ordered by sold date descending and keep row number 1.
WITH ranked_sales AS (
  SELECT
    ws.ws_bill_customer_sk,
    ws.ws_sold_date_sk,
    ROW_NUMBER() OVER (PARTITION BY ws.ws_bill_customer_sk ORDER BY ws.ws_sold_date_sk DESC) AS rn
  FROM web_sales ws
  JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
)
SELECT ws_bill_customer_sk, ws_sold_date_sk
FROM ranked_sales
WHERE rn = 1;

-- S-099 | window_cte | PASS
-- Question: Aggregate store_sales by store, join store, and use RANK partitioned by s_state ordered by revenue descending.
SELECT s_store_id, s_state
FROM (
  SELECT
    s.s_store_id,
    s.s_state,
    SUM(ss.ss_net_profit) AS total_revenue,
    RANK() OVER (PARTITION BY s.s_state ORDER BY SUM(ss.ss_net_profit) DESC) AS rnk
  FROM store_sales ss
  JOIN store s ON ss.ss_store_sk = s.s_store_sk
  GROUP BY s.s_store_id, s.s_state
)
WHERE rnk = 1;

-- S-100 | window_cte | PASS
-- Question: Build annual catalog sales in a CTE and use LAG to return current-year revenue, previous-year revenue, and year-over-year change.
WITH annual_sales AS (
    SELECT 
        dd.d_year,
        SUM(cs.cs_net_paid) AS current_year_revenue
    FROM catalog_sales cs
    JOIN date_dim dd ON cs.cs_sold_date_sk = dd.d_date_sk
    GROUP BY dd.d_year
)
SELECT 
    d_year,
    current_year_revenue,
    LAG(current_year_revenue) OVER (ORDER BY d_year) AS previous_year_revenue,
    current_year_revenue - LAG(current_year_revenue) OVER (ORDER BY d_year) AS year_over_year_change
FROM annual_sales;
