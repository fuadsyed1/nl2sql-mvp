-- SpiderSQL containment generated SQL: 30_containment_cases
-- Database: TPC-DS #51

-- CASE 01 | normal | filter_threshold | PASS
-- Q1: Show store sales with quantity above 10.
SELECT * FROM store_sales WHERE ss_quantity > 10;

-- Q2: Show store sales with quantity above 5.
SELECT * FROM store_sales WHERE ss_quantity > 5;

-- Q3: Show store sales with quantity above 1.
SELECT * FROM store_sales WHERE ss_quantity > 1;

-- Q4: Show store sales with quantity above 20.
SELECT * FROM store_sales WHERE ss_quantity > 20;

-- CASE 02 | normal | filter_threshold | PASS
-- Q1: Show store sales with net paid above 1000.
SELECT * FROM store_sales WHERE ss_net_paid > 1000;

-- Q2: Show store sales with net paid above 500.
SELECT * FROM store_sales WHERE ss_net_paid > 500;

-- Q3: Show store sales with net paid above 100.
SELECT * FROM store_sales WHERE ss_net_paid > 100;

-- Q4: Show store sales with net paid above 2000.
SELECT * FROM store_sales WHERE ss_net_paid > 2000;

-- CASE 03 | normal | conjunction | PASS
-- Q1: List married customers born after 1970.
SELECT c.c_customer_sk, c.c_customer_id, c.c_first_name, c.c_last_name, c.c_birth_year
FROM customer c, customer_demographics cd
WHERE c.c_current_cdemo_sk = cd.cd_demo_sk
  AND cd.cd_marital_status = 'M'
  AND c.c_birth_year > 1970;

-- Q2: List married customers.
SELECT c.c_customer_sk, c.c_customer_id, c.c_first_name, c.c_last_name
FROM customer c, customer_demographics cd
WHERE c.c_current_cdemo_sk = cd.cd_demo_sk
AND cd.cd_marital_status = 'M';

-- Q3: List customers born after 1970.
SELECT c_customer_sk, c_customer_id, c_first_name, c_last_name, c_birth_year
FROM customer
WHERE c_birth_year > 1970;

-- Q4: List customers born after 1960 with a recorded marital status.
SELECT "customer"."c_customer_id", "customer"."c_first_name", "customer"."c_last_name" FROM "customer" WHERE "customer"."c_birth_year" > ? AND "customer"."c_salutation" IS NOT NULL;

-- CASE 04 | normal | conjunction | PASS
-- Q1: Show electronics items priced above 100.
SELECT i_item_id, i_item_desc, i_current_price
FROM item
WHERE i_current_price > 100
  AND i_category = 'Electronics';

-- Q2: Show electronics items.
SELECT i_item_sk, i_item_id, i_item_desc, i_category, i_class, i_brand, i_product_name
FROM item
WHERE i_category = 'Electronics';

-- Q3: Show items priced above 100.
SELECT i_item_sk, i_item_id, i_item_desc, i_current_price FROM item WHERE i_current_price > 100;

-- Q4: Show items with a category priced above 50.
SELECT i_item_sk, i_item_id, i_category, i_current_price
FROM item
WHERE i_current_price > 50;

-- CASE 05 | normal | conjunction | PASS
-- Q1: List California stores larger than 80000 square feet.
SELECT s_store_id, s_store_name, s_floor_space FROM store WHERE s_state = 'California' AND s_floor_space > 80000;

-- Q2: List California stores.
SELECT s_store_id, s_store_name, s_city, s_state FROM store WHERE s_state = 'CA';

-- Q3: List stores larger than 80000 square feet.
SELECT s_store_id, s_store_name, s_floor_space FROM store WHERE s_floor_space > 80000;

-- Q4: List United States stores larger than 50000 square feet.
SELECT s_store_id, s_store_name, s_floor_space
FROM store
WHERE s_floor_space > 50000
  AND s_country = 'United States';

-- CASE 06 | normal | conjunction | PASS
-- Q1: Show web sales with shipping cost above 50 and net paid above 500.
SELECT * FROM web_sales WHERE ws_ext_ship_cost > 50 AND ws_net_paid > 500;

-- Q2: Show web sales with shipping cost above 50.
SELECT * FROM web_sales WHERE ws_ext_ship_cost > 50;

-- Q3: Show web sales with net paid above 500.
SELECT * FROM web_sales WHERE ws_net_paid > 500;

-- Q4: Show web sales with shipping cost above 25 and net paid above 250.
SELECT * FROM web_sales WHERE ws_ext_ship_cost > 25 AND ws_net_paid > 250;

-- CASE 07 | normal | conjunction | PASS
-- Q1: Show catalog sales with quantity above 10 and discount amount above 50.
SELECT * FROM catalog_sales WHERE cs_quantity > 10 AND cs_ext_discount_amt > 50;

-- Q2: Show catalog sales with quantity above 10.
SELECT * FROM catalog_sales WHERE cs_quantity > 10;

-- Q3: Show catalog sales with discount amount above 50.
SELECT * FROM catalog_sales WHERE cs_ext_discount_amt > 50;

-- Q4: Show catalog sales with quantity above 5 and discount amount above 25.
SELECT cs_order_number, cs_quantity, cs_ext_discount_amt
FROM catalog_sales
WHERE cs_quantity > 5 AND cs_ext_discount_amt > 25;

-- CASE 08 | normal | join | PASS
-- Q1: List store returns for damaged items with return amount above 100.
SELECT sr.sr_returned_date_sk, sr.sr_item_sk, sr.sr_return_amt
FROM store_returns sr
JOIN item i ON sr.sr_item_sk = i.i_item_sk
WHERE sr.sr_return_amt > 100
  AND i.i_item_desc LIKE '%damage%';

-- Q2: List store returns for damaged items.
SELECT sr.sr_item_sk, sr.sr_return_quantity, sr.sr_return_amt, sr.sr_reason_sk
FROM store_returns sr, reason r
WHERE sr.sr_reason_sk = r.r_reason_sk
  AND r.r_reason_desc LIKE '%damaged%';

-- Q3: List store returns with return amount above 100.
SELECT * FROM store_returns WHERE sr_return_amt > 100;

-- Q4: List store returns with any reason and return amount above 50.
SELECT * FROM store_returns WHERE sr_return_amt > 50;

-- CASE 09 | normal | filter_threshold | PASS
-- Q1: Show inventory rows with more than 500 units on hand.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
FROM inventory
WHERE inv_quantity_on_hand > 500;

-- Q2: Show inventory rows with more than 250 units on hand.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand FROM inventory WHERE inv_quantity_on_hand > 250;

-- Q3: Show inventory rows with more than 100 units on hand.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand FROM inventory WHERE inv_quantity_on_hand > 100;

-- Q4: Show inventory rows with more than 750 units on hand.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand FROM inventory WHERE inv_quantity_on_hand > 750;

-- CASE 10 | normal | conjunction | PASS
-- Q1: List promotions with discount active and email channel enabled.
SELECT "promotion"."p_promo_id", "promotion"."p_promo_name" FROM "promotion" WHERE "promotion"."p_discount_active" = ? AND "promotion"."p_channel_email" = ?;

-- Q2: List promotions with discount active.
SELECT "promotion"."p_promo_id", "promotion"."p_promo_name" FROM "promotion" WHERE "promotion"."p_discount_active" = ?;

-- Q3: List promotions with email channel enabled.
SELECT p_promo_id, p_promo_name
FROM promotion
WHERE p_channel_email = 'N';

-- Q4: List promotions with any active channel and discount active.
SELECT "promotion"."p_promo_id", "promotion"."p_promo_name" FROM "promotion" WHERE "promotion"."p_discount_active" = ? AND "promotion"."p_channel_dmail" = ? OR "promotion"."p_channel_email" = ? OR "promotion"."p_channel_catalog" = ? OR "promotion"."p_channel_tv" = ? OR "promotion"."p_channel_radio" = ? OR "promotion"."p_channel_press" = ? OR "promotion"."p_channel_event" = ? OR "promotion"."p_channel_demo" = ? OR "promotion"."p_channel_details" = ?;

-- CASE 11 | normal | date_scope | PASS
-- Q1: Show dates in January 2000.
SELECT d_date FROM date_dim WHERE d_year = 2000 AND d_moy = 1;

-- Q2: Show all dates in 2000.
SELECT d_date FROM date_dim WHERE d_year = 2000;

-- Q3: Show all January dates.
SELECT d_date FROM date_dim WHERE d_moy = 1;

-- Q4: Show dates from 1999 through 2000.
SELECT d_date FROM date_dim WHERE d_year BETWEEN 1999 AND 2000;

-- CASE 12 | normal | conjunction | PASS
-- Q1: List California warehouses larger than 100000 square feet.
SELECT w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft FROM warehouse WHERE w_state = 'CA' AND w_warehouse_sq_ft > 100000;

-- Q2: List California warehouses.
SELECT w_warehouse_id, w_warehouse_name, w_city, w_state, w_zip FROM warehouse WHERE w_state = 'CA';

-- Q3: List warehouses larger than 100000 square feet.
SELECT w_warehouse_sk, w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft FROM warehouse WHERE w_warehouse_sq_ft > 100000;

-- Q4: List United States warehouses larger than 50000 square feet.
SELECT w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft FROM warehouse WHERE w_country = 'United States' AND w_warehouse_sq_ft > 50000;

-- CASE 13 | normal | conjunction | PASS
-- Q1: List customers born after 1970 who have an advanced degree.
SELECT c.c_customer_sk, c.c_customer_id, c.c_first_name, c.c_last_name
FROM customer c, customer_demographics cd
WHERE c.c_current_cdemo_sk = cd.cd_demo_sk
  AND c.c_birth_year > 1970
  AND cd.cd_education_status = 'Advanced Degree';

-- Q2: List customers born after 1970.
SELECT c_customer_sk, c_customer_id, c_first_name, c_last_name, c_birth_year
FROM customer
WHERE c_birth_year > 1970;

-- Q3: List customers with an advanced degree.
SELECT c.c_customer_sk, c.c_customer_id, c.c_first_name, c.c_last_name
FROM customer c
JOIN customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
WHERE cd.cd_education_status = 'Advanced Degree';

-- Q4: List customers born after 1960 with a recorded education status.
SELECT c.c_customer_sk, c.c_first_name, c.c_last_name, c.c_birth_year
FROM customer c
JOIN customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
WHERE c.c_birth_year > 1960
  AND cd.cd_education_status IS NOT NULL;

-- CASE 14 | normal | multi_join | PASS
-- Q1: List store sales for electronics items with quantity above 5.
SELECT ss.*
FROM store_sales ss
JOIN inventory i ON ss.ss_item_sk = i.inv_item_sk
WHERE ss.ss_quantity > 5;

-- Q2: List store sales for electronics items.
SELECT ss.ss_sold_date_sk, ss.ss_item_sk, ss.ss_quantity, ss.ss_sales_price, ss.ss_net_profit
FROM store_sales ss
JOIN item i ON ss.ss_item_sk = i.i_item_sk
WHERE i.i_category = 'Electronics';

-- Q3: List store sales with quantity above 5.
SELECT ss_sold_date_sk, ss_sold_time_sk, ss_item_sk, ss_customer_sk, ss_cdemo_sk, ss_hdemo_sk, ss_addr_sk, ss_store_sk, ss_promo_sk, ss_ticket_number, ss_quantity, ss_wholesale_cost, ss_list_price, ss_sales_price, ss_ext_discount_amt, ss_ext_sales_price, ss_ext_wholesale_cost, ss_ext_list_price, ss_ext_tax, ss_coupon_amt, ss_net_paid, ss_net_paid_inc_tax, ss_net_profit FROM store_sales WHERE ss_quantity > 5;

-- Q4: List store sales for categorized items with quantity above 2.
SELECT ss.ss_sold_date_sk, ss.ss_item_sk, ss.ss_quantity, ss.ss_sales_price
FROM store_sales ss
JOIN item i ON ss.ss_item_sk = i.i_item_sk
WHERE ss.ss_quantity > 2;

-- CASE 15 | normal | multi_join | PASS
-- Q1: List web sales billed to California customers with net paid above 500.
SELECT ws.ws_order_number, ws.ws_bill_customer_sk, ws.ws_net_paid
FROM web_sales ws
JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
WHERE ca.ca_state = 'California'
  AND ws.ws_net_paid > 500;

-- Q2: List web sales billed to California customers.
SELECT ws.ws_order_number, ws.ws_bill_customer_sk, ws.ws_sales_price
FROM web_sales ws
JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
WHERE ca.ca_state = 'CA';

-- Q3: List web sales with net paid above 500.
SELECT * FROM web_sales WHERE ws_net_paid > 500;

-- Q4: List web sales billed to United States customers with net paid above 250.
SELECT ws.ws_order_number, ws.ws_bill_customer_sk, ws.ws_net_paid
FROM web_sales ws
JOIN customer_address ca ON ws.ws_bill_addr_sk = ca.ca_address_sk
WHERE ca.ca_country = 'United States'
  AND ws.ws_net_paid > 250;

-- CASE 16 | structured | filter_threshold | PASS
-- Q1: Return ss_ticket_number, ss_item_sk, ss_customer_sk, and ss_quantity from store_sales where ss_quantity is greater than 10.
SELECT ss.ss_ticket_number, ss.ss_item_sk, ss.ss_customer_sk, ss.ss_quantity
FROM store_sales ss
JOIN customer c ON ss.ss_customer_sk = c.c_customer_sk
WHERE ss.ss_quantity > 10;

-- Q2: Return the same columns where ss_quantity is greater than 5.
SELECT * FROM store_sales WHERE ss_quantity > 5;

-- Q3: Return the same columns where ss_quantity is greater than 1.
SELECT ss_sold_date_sk, ss_sold_time_sk, ss_item_sk, ss_customer_sk, ss_cdemo_sk, ss_hdemo_sk, ss_addr_sk, ss_store_sk, ss_promo_sk, ss_ticket_number, ss_quantity, ss_wholesale_cost, ss_list_price, ss_sales_price, ss_ext_discount_amt, ss_ext_sales_price, ss_ext_wholesale_cost, ss_ext_list_price, ss_ext_tax, ss_coupon_amt, ss_net_paid, ss_net_paid_inc_tax, ss_net_profit
FROM store_sales
WHERE ss_quantity > 1;

-- Q4: Return the same columns where ss_quantity is greater than 20.
SELECT * FROM store_sales WHERE ss_quantity > 20;

-- CASE 17 | structured | filter_threshold | PASS
-- Q1: Return ss_ticket_number, ss_item_sk, ss_customer_sk, and ss_net_paid from store_sales where ss_net_paid is greater than 1000.
SELECT ss_ticket_number, ss_item_sk, ss_customer_sk, ss_net_paid
FROM store_sales
JOIN customer ON store_sales.ss_customer_sk = customer.c_customer_sk
WHERE ss_net_paid > 1000;

-- Q2: Return the same columns where ss_net_paid is greater than 500.
SELECT * FROM store_sales WHERE ss_net_paid > 500;

-- Q3: Return the same columns where ss_net_paid is greater than 100.
SELECT ss_sold_date_sk, ss_sold_time_sk, ss_item_sk, ss_customer_sk, ss_cdemo_sk, ss_hdemo_sk, ss_addr_sk, ss_store_sk, ss_promo_sk, ss_ticket_number, ss_quantity, ss_wholesale_cost, ss_list_price, ss_sales_price, ss_ext_discount_amt, ss_ext_sales_price, ss_ext_wholesale_cost, ss_ext_list_price, ss_ext_tax, ss_coupon_amt, ss_net_paid, ss_net_paid_inc_tax, ss_net_profit FROM store_sales WHERE ss_net_paid > 100;

-- Q4: Return the same columns where ss_net_paid is greater than 2000.
SELECT * FROM store_sales WHERE ss_net_paid > 2000;

-- CASE 18 | structured | conjunction | PASS
-- Q1: Return customer ID, name, birth year, and marital status from customer where c_marital_status indicates married and c_birth_year is greater than 1970.
SELECT c.c_customer_id, c.c_first_name, c.c_last_name, c.c_birth_year, cd.cd_marital_status
FROM customer c
JOIN customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
WHERE cd.cd_marital_status = 'M'
  AND c.c_birth_year > 1970;

-- Q2: Return the same columns where c_marital_status indicates married.
SELECT "customer_demographics"."cd_marital_status" FROM "customer_demographics" WHERE "customer_demographics"."cd_marital_status" = ?;

-- Q3: Return the same columns where c_birth_year is greater than 1970.
SELECT c_customer_sk, c_customer_id, c_current_cdemo_sk, c_current_hdemo_sk, c_current_addr_sk, c_first_shipto_date_sk, c_first_sales_date_sk, c_salutation, c_first_name, c_last_name, c_preferred_cust_flag, c_birth_day, c_birth_month, c_birth_year, c_birth_country, c_login, c_email_address, c_last_review_date_sk FROM customer WHERE c_birth_year > 1970;

-- Q4: Return the same columns where c_birth_year is greater than 1960 and c_marital_status is not null.
SELECT c.c_customer_sk, c.c_customer_id, c.c_current_cdemo_sk, c.c_current_hdemo_sk, c.c_current_addr_sk, c.c_first_shipto_date_sk, c.c_first_sales_date_sk, c.c_salutation, c.c_first_name, c.c_last_name, c.c_preferred_cust_flag, c.c_birth_day, c.c_birth_month, c.c_birth_year, c.c_birth_country, c.c_login, c.c_email_address, c.c_last_review_date_sk
FROM customer c
JOIN customer_demographics cd ON c.c_current_cdemo_sk = cd.cd_demo_sk
WHERE c.c_birth_year > 1960
  AND cd.cd_marital_status IS NOT NULL;

-- CASE 19 | structured | conjunction | PASS
-- Q1: Return item ID, description, category, and current price from item where i_category equals Electronics and i_current_price is greater than 100.
SELECT i_item_id, i_item_desc, i_category, i_current_price
FROM item
WHERE i_category = 'Electronics' AND i_current_price > 100;

-- Q2: Return the same columns where i_category equals Electronics.
SELECT i_item_sk, i_item_id, i_rec_start_date, i_rec_end_date, i_item_desc, i_current_price, i_wholesale_cost, i_brand_id, i_brand, i_class_id, i_class, i_category_id, i_category, i_manufact_id, i_manufact, i_size, i_formulation, i_color, i_units, i_container, i_manager_id, i_product_name FROM item WHERE i_category = 'Electronics';

-- Q3: Return the same columns where i_current_price is greater than 100.
SELECT * FROM item WHERE i_current_price > 100;

-- Q4: Return the same columns where i_category is not null and i_current_price is greater than 50.
SELECT i_item_sk, i_item_id, i_rec_start_date, i_rec_end_date, i_item_desc, i_current_price, i_wholesale_cost, i_brand_id, i_brand, i_class_id, i_class, i_category_id, i_category, i_manufact_id, i_manufact, i_size, i_formulation, i_color, i_units, i_container, i_manager_id, i_product_name
FROM item
WHERE i_category IS NOT NULL AND i_current_price > 50;

-- CASE 20 | structured | conjunction | PASS
-- Q1: Return store ID, name, state, country, and floor space from store where s_state equals CA and s_floor_space is greater than 80000.
SELECT s_store_id, s_store_name, s_state, s_country, s_floor_space FROM store WHERE s_state = 'CA' AND s_floor_space > 80000;

-- Q2: Return the same columns where s_state equals CA.
SELECT s_store_sk, s_store_id, s_rec_start_date, s_rec_end_date, s_closed_date_sk, s_store_name, s_number_employees, s_floor_space, s_hours, s_manager, s_market_id, s_geography_class, s_market_desc, s_market_manager, s_division_id, s_division_name, s_company_id, s_company_name, s_street_number, s_street_name, s_street_type, s_suite_number, s_city, s_county, s_state, s_zip, s_country, s_gmt_offset, s_tax_percentage
FROM store
WHERE s_state = 'CA';

-- Q3: Return the same columns where s_floor_space is greater than 80000.
SELECT s_store_sk, s_store_id, s_rec_start_date, s_rec_end_date, s_closed_date_sk, s_store_name, s_number_employees, s_floor_space, s_hours, s_manager, s_market_id, s_geography_class, s_market_desc, s_market_manager, s_division_id, s_division_name, s_company_id, s_company_name, s_street_number, s_street_name, s_street_type, s_suite_number, s_city, s_county, s_state, s_zip, s_country, s_gmt_offset, s_tax_percentage FROM store WHERE s_floor_space > 80000;

-- Q4: Return the same columns where s_country equals United States and s_floor_space is greater than 50000.
SELECT s_store_sk, s_store_id, s_rec_start_date, s_rec_end_date, s_closed_date_sk, s_store_name, s_number_employees, s_floor_space, s_hours, s_manager, s_market_id, s_geography_class, s_market_desc, s_market_manager, s_division_id, s_division_name, s_company_id, s_company_name, s_street_number, s_street_name, s_street_type, s_suite_number, s_city, s_county, s_state, s_zip, s_country, s_gmt_offset, s_tax_percentage
FROM store
WHERE s_country = 'United States' AND s_floor_space > 50000;

-- CASE 21 | structured | conjunction | PASS
-- Q1: Return web order number, item key, customer key, ship cost, and net paid from web_sales where ws_ext_ship_cost is greater than 50 and ws_net_paid is greater than 500.
SELECT ws.ws_order_number, ws.ws_item_sk, ws.ws_bill_customer_sk, ws.ws_ext_ship_cost, ws.ws_net_paid
FROM web_sales ws
JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
WHERE ws.ws_ext_ship_cost > 50 AND ws.ws_net_paid > 500;

-- Q2: Return the same columns where ws_ext_ship_cost is greater than 50.
SELECT ws_sold_date_sk, ws_sold_time_sk, ws_ship_date_sk, ws_item_sk, ws_bill_customer_sk, ws_bill_cdemo_sk, ws_bill_hdemo_sk, ws_bill_addr_sk, ws_ship_customer_sk, ws_ship_cdemo_sk, ws_ship_hdemo_sk, ws_ship_addr_sk, ws_web_page_sk, ws_web_site_sk, ws_ship_mode_sk, ws_warehouse_sk, ws_promo_sk, ws_order_number, ws_quantity, ws_wholesale_cost, ws_list_price, ws_sales_price, ws_ext_discount_amt, ws_ext_sales_price, ws_ext_wholesale_cost, ws_ext_list_price, ws_ext_tax, ws_coupon_amt, ws_ext_ship_cost, ws_net_paid, ws_net_paid_inc_tax, ws_net_paid_inc_ship, ws_net_paid_inc_ship_tax, ws_net_profit
FROM web_sales
WHERE ws_ext_ship_cost > 50;

-- Q3: Return the same columns where ws_net_paid is greater than 500.
SELECT ws_sold_date_sk, ws_sold_time_sk, ws_ship_date_sk, ws_item_sk, ws_bill_customer_sk, ws_bill_cdemo_sk, ws_bill_hdemo_sk, ws_bill_addr_sk, ws_ship_customer_sk, ws_ship_cdemo_sk, ws_ship_hdemo_sk, ws_ship_addr_sk, ws_web_page_sk, ws_web_site_sk, ws_ship_mode_sk, ws_warehouse_sk, ws_promo_sk, ws_order_number, ws_quantity, ws_wholesale_cost, ws_list_price, ws_sales_price, ws_ext_discount_amt, ws_ext_sales_price, ws_ext_wholesale_cost, ws_ext_list_price, ws_ext_tax, ws_coupon_amt, ws_ext_ship_cost, ws_net_paid, ws_net_paid_inc_tax, ws_net_paid_inc_ship, ws_net_paid_inc_ship_tax, ws_net_profit
FROM web_sales
WHERE ws_net_paid > 500;

-- Q4: Return the same columns where ws_ext_ship_cost is greater than 25 and ws_net_paid is greater than 250.
SELECT ws_sold_date_sk, ws_sold_time_sk, ws_ship_date_sk, ws_item_sk, ws_bill_customer_sk, ws_bill_cdemo_sk, ws_bill_hdemo_sk, ws_bill_addr_sk, ws_ship_customer_sk, ws_ship_cdemo_sk, ws_ship_hdemo_sk, ws_ship_addr_sk, ws_web_page_sk, ws_web_site_sk, ws_ship_mode_sk, ws_warehouse_sk, ws_promo_sk, ws_order_number, ws_quantity, ws_wholesale_cost, ws_list_price, ws_sales_price, ws_ext_discount_amt, ws_ext_sales_price, ws_ext_wholesale_cost, ws_ext_list_price, ws_ext_tax, ws_coupon_amt, ws_ext_ship_cost, ws_net_paid, ws_net_paid_inc_tax, ws_net_paid_inc_ship, ws_net_paid_inc_ship_tax, ws_net_profit
FROM web_sales
WHERE ws_ext_ship_cost > 25 AND ws_net_paid > 250;

-- CASE 22 | structured | conjunction | PASS
-- Q1: Return catalog order number, item key, customer key, quantity, and extended discount amount where cs_quantity is greater than 10 and cs_ext_discount_amt is greater than 50.
SELECT cs_order_number, cs_item_sk, cs_bill_customer_sk, cs_quantity, cs_ext_discount_amt
FROM catalog_sales
JOIN customer ON catalog_sales.cs_bill_customer_sk = customer.c_customer_sk
WHERE cs_quantity > 10 AND cs_ext_discount_amt > 50;

-- Q2: Return the same columns where cs_quantity is greater than 10.
SELECT * FROM catalog_sales WHERE cs_quantity > 10;

-- Q3: Return the same columns where cs_ext_discount_amt is greater than 50.
SELECT p_promo_sk, p_promo_id, p_start_date_sk, p_end_date_sk, p_item_sk, p_cost, p_response_target, p_promo_name, p_channel_dmail, p_channel_email, p_channel_catalog, p_channel_tv, p_channel_radio, p_channel_press, p_channel_event, p_channel_demo, p_channel_details, p_purpose, p_discount_active
FROM promotion
WHERE p_promo_sk IN (SELECT cs_promo_sk FROM catalog_sales WHERE cs_ext_discount_amt > 50);

-- Q4: Return the same columns where cs_quantity is greater than 5 and cs_ext_discount_amt is greater than 25.
SELECT * FROM catalog_sales WHERE cs_quantity > 5 AND cs_ext_discount_amt > 25;

-- CASE 23 | structured | join | PASS
-- Q1: Join store_returns to reason and return ticket number, item key, reason description, and return amount where reason describes damaged and sr_return_amt is greater than 100.
SELECT sr.sr_ticket_number, sr.sr_item_sk, r.r_reason_desc, sr.sr_return_amt
FROM store_returns sr, reason r
WHERE sr.sr_reason_sk = r.r_reason_sk
  AND r.r_reason_desc LIKE '%damaged%'
  AND sr.sr_return_amt > 100;

-- Q2: Return the same joined columns where reason describes damaged.
SELECT r_reason_sk, r_reason_id, r_reason_desc
FROM reason
WHERE r_reason_desc LIKE '%damaged%';

-- Q3: Return the same joined columns where sr_return_amt is greater than 100.
SELECT sr_returned_date_sk, sr_return_time_sk, sr_item_sk, sr_customer_sk, sr_cdemo_sk, sr_hdemo_sk, sr_addr_sk, sr_store_sk, sr_reason_sk, sr_ticket_number, sr_return_quantity, sr_return_amt, sr_return_tax, sr_return_amt_inc_tax, sr_fee, sr_return_ship_cost, sr_refunded_cash, sr_reversed_charge, sr_store_credit, sr_net_loss FROM store_returns WHERE sr_return_amt > 100;

-- Q4: Return the same joined columns where reason key is not null and sr_return_amt is greater than 50.
SELECT sr_returned_date_sk, sr_return_time_sk, sr_item_sk, sr_customer_sk, sr_cdemo_sk, sr_hdemo_sk, sr_addr_sk, sr_store_sk, sr_reason_sk, sr_ticket_number, sr_return_quantity, sr_return_amt, sr_return_tax, sr_return_amt_inc_tax, sr_fee, sr_return_ship_cost, sr_refunded_cash, sr_reversed_charge, sr_store_credit, sr_net_loss
FROM store_returns
WHERE sr_reason_sk IS NOT NULL AND sr_return_amt > 50;

-- CASE 24 | structured | filter_threshold | PASS
-- Q1: Return inv_date_sk, inv_item_sk, inv_warehouse_sk, and inv_quantity_on_hand where quantity on hand is greater than 500.
SELECT i.inv_date_sk, i.inv_item_sk, i.inv_warehouse_sk, i.inv_quantity_on_hand
FROM inventory i
JOIN warehouse w ON i.inv_warehouse_sk = w.w_warehouse_sk
WHERE i.inv_quantity_on_hand > 500;

-- Q2: Return the same columns where quantity on hand is greater than 250.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand FROM inventory WHERE inv_quantity_on_hand > 250;

-- Q3: Return the same columns where quantity on hand is greater than 100.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
FROM inventory
WHERE inv_quantity_on_hand > 100;

-- Q4: Return the same columns where quantity on hand is greater than 750.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
FROM inventory
WHERE inv_quantity_on_hand > 750;

-- CASE 25 | structured | conjunction | PASS
-- Q1: Return promotion ID, name, discount-active flag, and email-channel flag where p_discount_active is true and p_channel_email is true.
SELECT "promotion"."p_promo_id", "promotion"."p_promo_name", "promotion"."p_discount_active", "promotion"."p_channel_email" FROM "promotion" WHERE "promotion"."p_discount_active" = ? AND "promotion"."p_channel_email" = ?;

-- Q2: Return the same columns where p_discount_active is true.
SELECT "promotion"."p_promo_sk", "promotion"."p_promo_id", "promotion"."p_start_date_sk", "promotion"."p_end_date_sk", "promotion"."p_item_sk", "promotion"."p_cost", "promotion"."p_response_target", "promotion"."p_promo_name", "promotion"."p_channel_dmail", "promotion"."p_channel_email", "promotion"."p_channel_catalog", "promotion"."p_channel_tv", "promotion"."p_channel_radio", "promotion"."p_channel_press", "promotion"."p_channel_event", "promotion"."p_channel_demo", "promotion"."p_channel_details", "promotion"."p_purpose", "promotion"."p_discount_active" FROM "promotion" WHERE "promotion"."p_discount_active" = ?;

-- Q3: Return the same columns where p_channel_email is true.
SELECT "promotion"."p_promo_sk", "promotion"."p_promo_id", "promotion"."p_start_date_sk", "promotion"."p_end_date_sk", "promotion"."p_item_sk", "promotion"."p_cost", "promotion"."p_response_target", "promotion"."p_promo_name", "promotion"."p_channel_dmail", "promotion"."p_channel_email", "promotion"."p_channel_catalog", "promotion"."p_channel_tv", "promotion"."p_channel_radio", "promotion"."p_channel_press", "promotion"."p_channel_event", "promotion"."p_channel_demo", "promotion"."p_channel_details", "promotion"."p_purpose", "promotion"."p_discount_active" FROM "promotion" WHERE "promotion"."p_channel_email" = ?;

-- Q4: Return the same columns where p_discount_active is true and at least one promotion channel flag is true.
SELECT "promotion"."p_promo_sk", "promotion"."p_promo_id", "promotion"."p_start_date_sk", "promotion"."p_end_date_sk", "promotion"."p_item_sk", "promotion"."p_cost", "promotion"."p_response_target", "promotion"."p_promo_name", "promotion"."p_channel_dmail", "promotion"."p_channel_email", "promotion"."p_channel_catalog", "promotion"."p_channel_tv", "promotion"."p_channel_radio", "promotion"."p_channel_press", "promotion"."p_channel_event", "promotion"."p_channel_demo", "promotion"."p_channel_details", "promotion"."p_purpose", "promotion"."p_discount_active" FROM "promotion" WHERE "promotion"."p_discount_active" = ? AND "promotion"."p_channel_dmail" = ? AND "promotion"."p_channel_email" = ? AND "promotion"."p_channel_catalog" = ? AND "promotion"."p_channel_tv" = ? AND "promotion"."p_channel_radio" = ? AND "promotion"."p_channel_press" = ? AND "promotion"."p_channel_event" = ? AND "promotion"."p_channel_demo" = ? AND "promotion"."p_channel_details" = ?;

-- CASE 26 | structured | date_scope | PASS
-- Q1: Return date key, date, year, month number, and month sequence from date_dim where d_year equals 2000 and d_moy equals 1.
SELECT d_date_sk, d_date, d_year, d_moy, d_month_seq FROM date_dim WHERE d_year = 2000 AND d_moy = 1;

-- Q2: Return the same columns where d_year equals 2000.
SELECT d_date_sk, d_date_id, d_date, d_month_seq, d_week_seq, d_quarter_seq, d_year, d_dow, d_moy, d_dom, d_qoy, d_fy_year, d_fy_quarter_seq, d_fy_week_seq, d_day_name, d_quarter_name, d_holiday, d_weekend, d_following_holiday, d_first_dom, d_last_dom, d_same_day_ly, d_same_day_lq, d_current_day, d_current_week, d_current_month, d_current_quarter, d_current_year
FROM date_dim
WHERE d_year = 2000
AND EXISTS (SELECT 1 FROM catalog_returns WHERE cr_returned_date_sk = date_dim.d_date_sk)
AND EXISTS (SELECT 1 FROM store_returns WHERE sr_returned_date_sk = date_dim.d_date_sk)
AND EXISTS (SELECT 1 FROM web_returns WHERE wr_returned_date_sk = date_dim.d_date_sk);

-- Q3: Return the same columns where d_moy equals 1.
SELECT d_date_sk, d_date_id, d_date, d_month_seq, d_week_seq, d_quarter_seq, d_year, d_dow, d_moy, d_dom, d_qoy, d_fy_year, d_fy_quarter_seq, d_fy_week_seq, d_day_name, d_quarter_name, d_holiday, d_weekend, d_following_holiday, d_first_dom, d_last_dom, d_same_day_ly, d_same_day_lq, d_current_day, d_current_week, d_current_month, d_current_quarter, d_current_year FROM date_dim WHERE d_moy = 1;

-- Q4: Return the same columns where d_year is between 1999 and 2000.
SELECT * FROM "date_dim";

-- CASE 27 | structured | conjunction | PASS
-- Q1: Return warehouse ID, name, state, country, and square feet where w_state equals CA and w_warehouse_sq_ft is greater than 100000.
SELECT w_warehouse_id, w_warehouse_name, w_state, w_country, w_warehouse_sq_ft FROM warehouse WHERE w_state = 'CA' AND w_warehouse_sq_ft > 100000;

-- Q2: Return the same columns where w_state equals CA.
SELECT w_warehouse_sk, w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft, w_street_number, w_street_name, w_street_type, w_suite_number, w_city, w_county, w_state, w_zip, w_country, w_gmt_offset
FROM warehouse
WHERE w_state = 'CA';

-- Q3: Return the same columns where w_warehouse_sq_ft is greater than 100000.
SELECT w_warehouse_sk, w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft, w_street_number, w_street_name, w_street_type, w_suite_number, w_city, w_county, w_state, w_zip, w_country, w_gmt_offset FROM warehouse WHERE w_warehouse_sq_ft > 100000;

-- Q4: Return the same columns where w_country equals United States and w_warehouse_sq_ft is greater than 50000.
SELECT w_warehouse_sk, w_warehouse_id, w_warehouse_name, w_warehouse_sq_ft, w_street_number, w_street_name, w_street_type, w_suite_number, w_city, w_county, w_state, w_zip, w_country, w_gmt_offset FROM warehouse WHERE w_country = 'United States' AND w_warehouse_sq_ft > 50000;

-- CASE 28 | structured | conjunction | PASS
-- Q1: Join customer to customer_demographics and return customer ID, birth year, and education status where birth year is greater than 1970 and education status indicates an advanced degree.
SELECT c.c_customer_id, c.c_birth_year, cd.cd_education_status
FROM customer c, customer_demographics cd
WHERE c.c_current_cdemo_sk = cd.cd_demo_sk
  AND c.c_birth_year > 1970
  AND cd.cd_education_status IN ('Advanced Degree', 'College Degree', 'Masters Degree', 'PhD Degree');

-- Q2: Return the same joined columns where birth year is greater than 1970.
SELECT c.c_customer_sk, c.c_customer_id, c.c_first_name, c.c_last_name, c.c_birth_year
FROM customer c
WHERE c.c_birth_year > 1970;

-- Q3: Return the same joined columns where education status indicates an advanced degree.
SELECT cd_demo_sk, cd_gender, cd_marital_status, cd_education_status, cd_purchase_estimate, cd_credit_rating, cd_dep_count, cd_dep_employed_count, cd_dep_college_count
FROM customer_demographics
WHERE cd_education_status IN ('Advanced Degree', 'Masters Degree', 'PhD', 'Doctorate Degree', 'Professional Degree');

-- Q4: Return the same joined columns where birth year is greater than 1960 and education status is not null.
SELECT c.c_customer_sk, c.c_customer_id, c.c_first_name, c.c_last_name, c.c_birth_year, cd.cd_education_status
FROM customer c, customer_demographics cd
WHERE c.c_current_cdemo_sk = cd.cd_demo_sk
  AND c.c_birth_year > 1960
  AND cd.cd_education_status IS NOT NULL;

-- CASE 29 | structured | multi_join | PASS
-- Q1: Join store_sales to item and return ticket number, item ID, category, quantity, and net paid where category equals Electronics and quantity is greater than 5.
SELECT ss.ss_ticket_number, i.i_item_id, i.i_category, ss.ss_quantity, ss.ss_net_paid
FROM store_sales ss
JOIN item i ON ss.ss_item_sk = i.i_item_sk
WHERE i.i_category = 'Electronics'
  AND ss.ss_quantity > 5;

-- Q2: Return the same joined columns where category equals Electronics.
SELECT i_item_sk, i_item_id, i_item_desc, i_current_price, i_wholesale_cost, i_brand_id, i_brand, i_class_id, i_class, i_category_id, i_category, i_manufact_id, i_manufact, i_size, i_formulation, i_color, i_units, i_container, i_manager_id, i_product_name
FROM item
WHERE i_category = 'Electronics';

-- Q3: Return the same joined columns where quantity is greater than 5.
SELECT inv_date_sk, inv_item_sk, inv_warehouse_sk, inv_quantity_on_hand
FROM inventory
WHERE inv_quantity_on_hand > 5;

-- Q4: Return the same joined columns where category is not null and quantity is greater than 2.
SELECT item.i_item_sk, item.i_item_id, item.i_item_desc, item.i_current_price, item.i_wholesale_cost, item.i_brand_id, item.i_brand, item.i_class_id, item.i_class, item.i_category_id, item.i_category, item.i_manufact_id, item.i_manufact, item.i_size, item.i_formulation, item.i_color, item.i_units, item.i_container, item.i_manager_id, item.i_product_name, catalog_sales.cs_quantity
FROM catalog_sales
JOIN item ON catalog_sales.cs_item_sk = item.i_item_sk
WHERE item.i_category IS NOT NULL AND catalog_sales.cs_quantity > 2;

-- CASE 30 | structured | multi_join | PASS
-- Q1: Join web_sales, customer, and customer_address; return order number, customer ID, state, country, and net paid where state equals CA and net paid is greater than 500.
SELECT ws.ws_order_number, c.c_customer_id, ca.ca_state, ca.ca_country, ws.ws_net_paid
FROM web_sales ws
JOIN customer c ON ws.ws_bill_customer_sk = c.c_customer_sk
JOIN customer_address ca ON c.c_current_addr_sk = ca.ca_address_sk
WHERE ca.ca_state = 'CA' AND ws.ws_net_paid > 500;

-- Q2: Return the same joined columns where state equals CA.
SELECT ca_address_sk, ca_address_id, ca_street_number, ca_street_name, ca_street_type, ca_suite_number, ca_city, ca_county, ca_state, ca_zip, ca_country, ca_gmt_offset, ca_location_type FROM customer_address WHERE ca_state = 'CA';

-- Q3: Return the same joined columns where net paid is greater than 500.
SELECT cs.*
FROM catalog_sales cs
WHERE cs.cs_net_paid > 500;

-- Q4: Return the same joined columns where country equals United States and net paid is greater than 250.
SELECT cs.*
FROM catalog_sales cs
JOIN catalog_returns cr ON cs.cs_order_number = cr.cr_order_number
JOIN call_center cc ON cr.cr_call_center_sk = cc.cc_call_center_sk
WHERE cc.cc_country = 'United States'
  AND cs.cs_net_paid > 250;
