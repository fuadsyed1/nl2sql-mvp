#!/usr/bin/env python3
"""Natural-language benchmark catalog for TPC-DS #51."""

from __future__ import annotations

from typing import Any

DATABASE_ID = 51
DATABASE_NAME = 'TPC-DS'
EXPECTED_TABLES = 24
EXPECTED_RELATIONSHIPS = 0

QUERY_CATEGORIES: dict[str, dict[str, list[str]]] = {'select_projection': {'normal': ['Show customer IDs, first names, last names, and birth years.',
                                  'List item IDs, descriptions, current prices, and categories.',
                                  'Show store IDs, store names, cities, and states.',
                                  'List web site IDs, names, and classes.',
                                  'Show warehouse IDs, names, square footage, and states.'],
                       'structured': ['From customer, return c_customer_sk, c_customer_id, c_first_name, c_last_name, '
                                      'and c_birth_year.',
                                      'From item, return i_item_sk, i_item_id, i_item_desc, i_current_price, and '
                                      'i_category.',
                                      'From store, return s_store_sk, s_store_id, s_store_name, s_city, and s_state.',
                                      'From web_site, return web_site_sk, web_site_id, web_name, and web_class.',
                                      'From warehouse, return w_warehouse_sk, w_warehouse_id, w_warehouse_name, '
                                      'w_warehouse_sq_ft, and w_state.']},
 'filter_comparison': {'normal': ['Which items have a current price greater than 100?',
                                  'Show store sales rows with quantity greater than 5.',
                                  'List web sales where net paid is above 500.',
                                  'Show catalog sales with discount amount above 50.',
                                  'List store returns where return amount is above 100.'],
                       'structured': ['From item, return i_item_sk, i_item_id, i_item_desc, and i_current_price where '
                                      'i_current_price is greater than 100.',
                                      'From store_sales, return ss_ticket_number, ss_item_sk, ss_customer_sk, and '
                                      'ss_quantity where ss_quantity is greater than 5.',
                                      'From web_sales, return ws_order_number, ws_item_sk, ws_bill_customer_sk, and '
                                      'ws_net_paid where ws_net_paid is greater than 500.',
                                      'From catalog_sales, return cs_order_number, cs_item_sk, cs_bill_customer_sk, '
                                      'and cs_ext_discount_amt where cs_ext_discount_amt is greater than 50.',
                                      'From store_returns, return sr_ticket_number, sr_item_sk, sr_customer_sk, and '
                                      'sr_return_amt where sr_return_amt is greater than 100.']},
 'range_between': {'normal': ['Show calendar dates from January 1, 1999 through December 31, 2000.',
                              'List items priced between 20 and 80.',
                              'Find customers born between 1940 and 1960.',
                              'Show inventory rows with quantity between 100 and 500.',
                              'List stores with floor space between 50000 and 100000 square feet.'],
                   'structured': ['From date_dim, return d_date_sk, d_date, d_year, and d_moy where d_date is between '
                                  '1999-01-01 and 2000-12-31.',
                                  'From item, return i_item_sk, i_item_id, and i_current_price where i_current_price '
                                  'is between 20 and 80.',
                                  'From customer, return c_customer_sk, c_first_name, c_last_name, and c_birth_year '
                                  'where c_birth_year is between 1940 and 1960.',
                                  'From inventory, return inv_date_sk, inv_item_sk, inv_warehouse_sk, and '
                                  'inv_quantity_on_hand where inv_quantity_on_hand is between 100 and 500.',
                                  'From store, return s_store_sk, s_store_name, and s_floor_space where s_floor_space '
                                  'is between 50000 and 100000.']},
 'pattern_text': {'normal': ['Find items whose description contains cotton.',
                             'Show customers whose last name starts with A.',
                             'List customer addresses in cities beginning with New.',
                             'Find web pages whose URL contains catalog.',
                             'Show promotions whose name contains holiday.'],
                  'structured': ['From item, return i_item_sk, i_item_id, and i_item_desc where i_item_desc contains '
                                 'cotton.',
                                 'From customer, return c_customer_sk, c_first_name, and c_last_name where c_last_name '
                                 'starts with A.',
                                 'From customer_address, return ca_address_sk, ca_city, ca_state, and ca_zip where '
                                 'ca_city starts with New.',
                                 'From web_page, return wp_web_page_sk, wp_web_page_id, and wp_url where wp_url '
                                 'contains catalog.',
                                 'From promotion, return p_promo_sk, p_promo_id, and p_promo_name where p_promo_name '
                                 'contains holiday.']},
 'null_boolean': {'normal': ['Show customers that do not have a current address key.',
                             'List items with no brand recorded.',
                             'Show web sales that do not have a ship date.',
                             'List stores that do not have a closed date.',
                             'Show promotions where the email channel flag is present.'],
                  'structured': ['From customer, return c_customer_sk and c_current_addr_sk where c_current_addr_sk is '
                                 'null.',
                                 'From item, return i_item_sk, i_item_id, and i_brand where i_brand is null.',
                                 'From web_sales, return ws_order_number, ws_item_sk, and ws_ship_date_sk where '
                                 'ws_ship_date_sk is null.',
                                 'From store, return s_store_sk, s_store_name, and s_closed_date_sk where '
                                 's_closed_date_sk is null.',
                                 'From promotion, return p_promo_sk, p_promo_name, and p_channel_email where '
                                 'p_channel_email is not null.']},
 'join': {'normal': ['Show store sales with the item description and category.',
                     "List store sales with the customer's name.",
                     'Show web sales with the web site name.',
                     'List catalog sales with the catalog page description.',
                     'Show store returns with the return reason description.'],
          'structured': ['Join store_sales to item on ss_item_sk and return ss_ticket_number, i_item_id, i_item_desc, '
                         'i_category, ss_quantity, and ss_net_paid.',
                         'Join store_sales to customer on ss_customer_sk and return ss_ticket_number, c_customer_id, '
                         'customer name, ss_quantity, and ss_net_paid.',
                         'Join web_sales to web_site on ws_web_site_sk and return ws_order_number, web_site_id, '
                         'web_name, ws_quantity, and ws_net_paid.',
                         'Join catalog_sales to catalog_page on cs_catalog_page_sk and return cs_order_number, '
                         'cp_catalog_page_id, cp_description, cs_quantity, and cs_net_paid.',
                         'Join store_returns to reason on sr_reason_sk and return sr_ticket_number, r_reason_id, '
                         'r_reason_desc, sr_return_quantity, and sr_return_amt.']},
 'multi_join': {'normal': ['List store sales with customer name, item description, store name, sales date, quantity, '
                           'and net paid.',
                           'Show web sales with customer, item, web site, sold date, quantity, and net paid.',
                           'List catalog sales with customer, item, catalog page, sold date, quantity, and net paid.',
                           'Show store returns with customer, item, store, reason, return date, and return amount.',
                           'List inventory with item, warehouse, inventory date, and quantity on hand.'],
                'structured': ['Join store_sales, customer, item, store, and date_dim; return ticket number, customer '
                               'ID, item ID, store ID, date, quantity, and net paid.',
                               'Join web_sales, customer, item, web_site, and date_dim; return order number, customer '
                               'ID, item ID, web site ID, date, quantity, and net paid.',
                               'Join catalog_sales, customer, item, catalog_page, and date_dim; return order number, '
                               'customer ID, item ID, catalog page ID, date, quantity, and net paid.',
                               'Join store_returns, customer, item, store, reason, and date_dim; return ticket number, '
                               'customer ID, item ID, store ID, reason description, return date, and return amount.',
                               'Join inventory, item, warehouse, and date_dim; return inventory date, item ID, '
                               'warehouse ID, and quantity on hand.']},
 'aggregation': {'normal': ['How many customers are in the customer table?',
                            'What is the average current price of all items?',
                            'What is the total net paid across store sales?',
                            'What is the largest extended sales price in web sales?',
                            'What is the total quantity sold through catalog sales?'],
                 'structured': ['Return COUNT of all rows in customer as customer_count.',
                                'Return AVG of i_current_price from item as average_item_price.',
                                'Return SUM of ss_net_paid from store_sales as total_store_net_paid.',
                                'Return MAX of ws_ext_sales_price from web_sales as maximum_web_extended_price.',
                                'Return SUM of cs_quantity from catalog_sales as total_catalog_quantity.']},
 'group_by': {'normal': ['Show store sales revenue by item category.',
                         'Show store sales revenue by customer state.',
                         'Show store sales revenue by calendar year.',
                         'Show web sales revenue by web site.',
                         'Show inventory quantity by warehouse.'],
              'structured': ['Join store_sales to item, group by i_category, and return category, COUNT of rows, and '
                             'SUM of ss_net_paid.',
                             'Join store_sales to customer and customer_address, group by ca_state, and return state, '
                             'order count, and SUM of ss_net_paid.',
                             'Join store_sales to date_dim, group by d_year, and return year, sales count, and SUM of '
                             'ss_net_paid.',
                             'Join web_sales to web_site, group by web_site_sk and web_name, and return order count '
                             'and SUM of ws_net_paid.',
                             'Join inventory to warehouse, group by warehouse ID and name, and return SUM of '
                             'inv_quantity_on_hand.']},
 'having': {'normal': ['Find item categories with more than 100000 in store sales revenue.',
                       'Show customer states with more than 1000 store sales rows.',
                       'Find customers with more than 10 web orders.',
                       'Show promotions responsible for more than 50000 in catalog discount amount.',
                       'Find warehouses holding more than 1000000 total units.'],
            'structured': ['Join store_sales to item, group by i_category, and keep categories where SUM of '
                           'ss_net_paid is greater than 100000.',
                           'Join store_sales to customer and customer_address, group by ca_state, and keep states '
                           'where COUNT of sales rows is greater than 1000.',
                           'Group web_sales by ws_bill_customer_sk and keep customers where COUNT DISTINCT '
                           'ws_order_number is greater than 10.',
                           'Group catalog_sales by cs_promo_sk and keep promotions where SUM of cs_ext_discount_amt is '
                           'greater than 50000.',
                           'Group inventory by inv_warehouse_sk and keep warehouses where SUM of inv_quantity_on_hand '
                           'is greater than 1000000.']},
 'distinct': {'normal': ['List the distinct customer states.',
                         'Show all distinct item categories.',
                         'List distinct item brands.',
                         'Show distinct shipping mode types.',
                         'List distinct store return reasons.'],
              'structured': ['Return DISTINCT ca_state from customer_address where ca_state is not null.',
                             'Return DISTINCT i_category from item where i_category is not null.',
                             'Return DISTINCT i_brand from item where i_brand is not null.',
                             'Return DISTINCT sm_type from ship_mode.',
                             'Join store_returns to reason and return DISTINCT r_reason_desc.']},
 'count_distinct': {'normal': ['How many distinct customers made store purchases?',
                               'How many distinct items were sold through the web channel?',
                               'How many different stores have store sales?',
                               'How many distinct promotions were used in catalog sales?',
                               'How many distinct warehouses have inventory records?'],
                    'structured': ['Return COUNT DISTINCT ss_customer_sk from store_sales.',
                                   'Return COUNT DISTINCT ws_item_sk from web_sales.',
                                   'Return COUNT DISTINCT ss_store_sk from store_sales.',
                                   'Return COUNT DISTINCT cs_promo_sk from catalog_sales where cs_promo_sk is not '
                                   'null.',
                                   'Return COUNT DISTINCT inv_warehouse_sk from inventory.']},
 'order_by': {'normal': ['List items from highest to lowest current price.',
                         'Show store sales from highest to lowest net paid.',
                         'List customers from oldest to youngest birth year.',
                         'Show stores ordered by state, city, and store name.',
                         'List warehouses from largest to smallest square footage.'],
              'structured': ['Return item ID, description, category, and current price ordered by i_current_price '
                             'descending.',
                             'Return store sales ticket number, item key, customer key, and net paid ordered by '
                             'ss_net_paid descending.',
                             'Return customer ID, first name, last name, and birth year ordered by c_birth_year '
                             'ascending.',
                             'Return store ID, store name, city, and state ordered by s_state, s_city, and '
                             's_store_name.',
                             'Return warehouse ID, name, square footage, and state ordered by w_warehouse_sq_ft '
                             'descending.']},
 'top_k_limit': {'normal': ['Show the 10 most expensive items.',
                            'List the 20 store sales rows with the highest net paid.',
                            'Which 10 customers spent the most in store sales?',
                            'Show the 15 web sites with the greatest total web sales.',
                            'List the 10 warehouses with the most inventory units.'],
                 'structured': ['Return the top 10 items ordered by i_current_price descending.',
                                'Return the top 20 store_sales rows ordered by ss_net_paid descending.',
                                'Group store_sales by ss_customer_sk, order by SUM of ss_net_paid descending, and '
                                'return the top 10.',
                                'Group web_sales by ws_web_site_sk, order by SUM of ws_net_paid descending, and return '
                                'the top 15.',
                                'Group inventory by inv_warehouse_sk, order by SUM of inv_quantity_on_hand descending, '
                                'and return the top 10.']},
 'subquery': {'normal': ['Find items priced above the average current item price.',
                         'Show store sales with net paid above the average store sale.',
                         'List customers whose total store spending is above average customer spending.',
                         'Find warehouses with inventory above the average warehouse inventory.',
                         'Show stores whose floor space is above the average store floor space.'],
              'structured': ['Return item rows where i_current_price is greater than a scalar subquery computing AVG '
                             'i_current_price.',
                             'Return store_sales rows where ss_net_paid is greater than a scalar subquery computing '
                             'AVG ss_net_paid.',
                             'Aggregate store_sales by ss_customer_sk and keep customer totals greater than the '
                             'average of customer totals.',
                             'Aggregate inventory by inv_warehouse_sk and keep warehouse totals greater than the '
                             'average warehouse total.',
                             'Return store rows where s_floor_space is greater than a scalar subquery computing AVG '
                             's_floor_space.']},
 'exists_not_exists': {'normal': ['List customers who have at least one store purchase.',
                                  'Find items that have never been sold through the web channel.',
                                  'Show promotions that were used in at least one catalog sale.',
                                  'Find stores with no store sales.',
                                  'List warehouses that have inventory for more than one item.'],
                       'structured': ['Return customer rows where an EXISTS subquery finds store_sales with matching '
                                      'c_customer_sk.',
                                      'Return item rows where a NOT EXISTS subquery finds no web_sales with matching '
                                      'i_item_sk.',
                                      'Return promotion rows where an EXISTS subquery finds catalog_sales with '
                                      'matching p_promo_sk.',
                                      'Return store rows where a NOT EXISTS subquery finds no store_sales with '
                                      'matching s_store_sk.',
                                      'Return warehouse rows where an EXISTS or grouped subquery finds more than one '
                                      'distinct inv_item_sk.']},
 'set_operation': {'normal': ['List customer IDs that appear in both store sales and web sales.',
                              'Find item IDs sold through both catalog and web channels.',
                              'Combine all customer IDs from store, catalog, and web sales without duplicates.',
                              'Find customers with store purchases but no web purchases.',
                              'List item categories that appear in store sales or catalog sales.'],
                   'structured': ['Use INTERSECT to return customer keys from store_sales and web_sales.',
                                  'Use INTERSECT to return item keys from catalog_sales and web_sales.',
                                  'Use UNION to combine customer keys from store_sales, catalog_sales, and web_sales.',
                                  'Use EXCEPT to return customer keys from store_sales that do not occur in web_sales.',
                                  'Use UNION to combine distinct item categories reached through store_sales and '
                                  'catalog_sales.']},
 'case_expression': {'normal': ['Label items as low, medium, or high price.',
                                'Classify store sales as small, medium, or large by net paid.',
                                'Label inventory as out, low, or well stocked.',
                                'Group customers into birth-year generations.',
                                'Classify stores as small, medium, or large by floor space.'],
                     'structured': ['Return item ID, current price, and a CASE expression: low below 20, medium from '
                                    '20 through 100, high above 100.',
                                    'Return store sale ticket and net paid with a CASE expression: small below 50, '
                                    'medium from 50 through 500, large above 500.',
                                    'Return inventory keys, quantity on hand, and a CASE expression: out when 0, low '
                                    'below 50, well_stocked otherwise.',
                                    'Return customer ID, birth year, and a CASE expression that assigns generation '
                                    'bands from c_birth_year.',
                                    'Return store ID, floor space, and a CASE expression: small below 50000, medium '
                                    'through 100000, large above 100000.']},
 'derived_metric': {'normal': ['For each store sale, calculate the effective unit price using net paid divided by '
                               'quantity.',
                               'For each web sale, calculate discount percentage from list price and sales price.',
                               'For each catalog sale, calculate profit margin as net profit divided by net paid.',
                               'For each store return, calculate return amount per returned unit.',
                               'For each inventory row, calculate units per thousand square feet of warehouse space.'],
                    'structured': ['From store_sales, return ticket number, quantity, net paid, and ss_net_paid '
                                   'divided by NULLIF ss_quantity as effective_unit_price.',
                                   'From web_sales, return order number, list price, sales price, and one minus '
                                   'ws_sales_price divided by NULLIF ws_list_price as discount_percent.',
                                   'From catalog_sales, return order number, net paid, net profit, and cs_net_profit '
                                   'divided by NULLIF cs_net_paid as profit_margin.',
                                   'From store_returns, return ticket number, return quantity, return amount, and '
                                   'sr_return_amt divided by NULLIF sr_return_quantity as return_amount_per_unit.',
                                   'Join inventory to warehouse and return inventory keys, quantity on hand, warehouse '
                                   'square feet, and quantity divided by warehouse square feet times 1000.']},
 'window_cte': {'normal': ['Rank items by store sales revenue within each item category.',
                           'Show a running total of daily store sales revenue.',
                           'Return the latest web order for each customer.',
                           'Find the highest-revenue store in each state.',
                           "Compare each year's catalog sales with the previous year's catalog sales."],
                'structured': ['Aggregate store_sales by item and join item; apply RANK partitioned by i_category '
                               'ordered by item revenue descending.',
                               'Aggregate store_sales by sold date and apply cumulative SUM of daily net paid ordered '
                               'by date.',
                               'Use ROW_NUMBER partitioned by ws_bill_customer_sk ordered by sold date descending and '
                               'keep row number 1.',
                               'Aggregate store_sales by store, join store, and use RANK partitioned by s_state '
                               'ordered by revenue descending.',
                               'Build annual catalog sales in a CTE and use LAG to return current-year revenue, '
                               'previous-year revenue, and year-over-year change.']}}

CONTAINMENT_SCENARIOS: list[dict[str, Any]] = [{'category': 'filter_threshold',
  'name': 'Store-sales quantity threshold chain',
  'normal_queries': ['Show store sales with quantity above 10.',
                     'Show store sales with quantity above 5.',
                     'Show store sales with quantity above 1.',
                     'Show store sales with quantity above 20.'],
  'structured_queries': ['Return ss_ticket_number, ss_item_sk, ss_customer_sk, and ss_quantity from store_sales where '
                         'ss_quantity is greater than 10.',
                         'Return the same columns where ss_quantity is greater than 5.',
                         'Return the same columns where ss_quantity is greater than 1.',
                         'Return the same columns where ss_quantity is greater than 20.'],
  'expected_note': 'Larger quantity thresholds should be contained in smaller thresholds.'},
 {'category': 'filter_threshold',
  'name': 'Store-sales net-paid threshold chain',
  'normal_queries': ['Show store sales with net paid above 1000.',
                     'Show store sales with net paid above 500.',
                     'Show store sales with net paid above 100.',
                     'Show store sales with net paid above 2000.'],
  'structured_queries': ['Return ss_ticket_number, ss_item_sk, ss_customer_sk, and ss_net_paid from store_sales where '
                         'ss_net_paid is greater than 1000.',
                         'Return the same columns where ss_net_paid is greater than 500.',
                         'Return the same columns where ss_net_paid is greater than 100.',
                         'Return the same columns where ss_net_paid is greater than 2000.'],
  'expected_note': 'Higher net-paid thresholds should be narrower.'},
 {'category': 'conjunction',
  'name': 'Customer birth-year and marital-status narrowing',
  'normal_queries': ['List married customers born after 1970.',
                     'List married customers.',
                     'List customers born after 1970.',
                     'List customers born after 1960 with a recorded marital status.'],
  'structured_queries': ['Return customer ID, name, birth year, and marital status from customer where '
                         'c_marital_status indicates married and c_birth_year is greater than 1970.',
                         'Return the same columns where c_marital_status indicates married.',
                         'Return the same columns where c_birth_year is greater than 1970.',
                         'Return the same columns where c_birth_year is greater than 1960 and c_marital_status is not '
                         'null.'],
  'expected_note': 'Married recent-birth customers should be contained in both single-condition sets.'},
 {'category': 'conjunction',
  'name': 'Item category and price narrowing',
  'normal_queries': ['Show electronics items priced above 100.',
                     'Show electronics items.',
                     'Show items priced above 100.',
                     'Show items with a category priced above 50.'],
  'structured_queries': ['Return item ID, description, category, and current price from item where i_category equals '
                         'Electronics and i_current_price is greater than 100.',
                         'Return the same columns where i_category equals Electronics.',
                         'Return the same columns where i_current_price is greater than 100.',
                         'Return the same columns where i_category is not null and i_current_price is greater than '
                         '50.'],
  'expected_note': 'Expensive electronics should be narrower than category-only and price-only sets.'},
 {'category': 'conjunction',
  'name': 'Store state and size narrowing',
  'normal_queries': ['List California stores larger than 80000 square feet.',
                     'List California stores.',
                     'List stores larger than 80000 square feet.',
                     'List United States stores larger than 50000 square feet.'],
  'structured_queries': ['Return store ID, name, state, country, and floor space from store where s_state equals CA '
                         'and s_floor_space is greater than 80000.',
                         'Return the same columns where s_state equals CA.',
                         'Return the same columns where s_floor_space is greater than 80000.',
                         'Return the same columns where s_country equals United States and s_floor_space is greater '
                         'than 50000.'],
  'expected_note': 'Large California stores should be contained in the broader store sets.'},
 {'category': 'conjunction',
  'name': 'Web-sales shipping-cost and net-paid containment',
  'normal_queries': ['Show web sales with shipping cost above 50 and net paid above 500.',
                     'Show web sales with shipping cost above 50.',
                     'Show web sales with net paid above 500.',
                     'Show web sales with shipping cost above 25 and net paid above 250.'],
  'structured_queries': ['Return web order number, item key, customer key, ship cost, and net paid from web_sales '
                         'where ws_ext_ship_cost is greater than 50 and ws_net_paid is greater than 500.',
                         'Return the same columns where ws_ext_ship_cost is greater than 50.',
                         'Return the same columns where ws_net_paid is greater than 500.',
                         'Return the same columns where ws_ext_ship_cost is greater than 25 and ws_net_paid is greater '
                         'than 250.'],
  'expected_note': 'The strong two-condition web-sales query should be narrower.'},
 {'category': 'conjunction',
  'name': 'Catalog-sales quantity and discount containment',
  'normal_queries': ['Show catalog sales with quantity above 10 and discount amount above 50.',
                     'Show catalog sales with quantity above 10.',
                     'Show catalog sales with discount amount above 50.',
                     'Show catalog sales with quantity above 5 and discount amount above 25.'],
  'structured_queries': ['Return catalog order number, item key, customer key, quantity, and extended discount amount '
                         'where cs_quantity is greater than 10 and cs_ext_discount_amt is greater than 50.',
                         'Return the same columns where cs_quantity is greater than 10.',
                         'Return the same columns where cs_ext_discount_amt is greater than 50.',
                         'Return the same columns where cs_quantity is greater than 5 and cs_ext_discount_amt is '
                         'greater than 25.'],
  'expected_note': 'The strong catalog-sales conjunction should be narrower than all broader variants.'},
 {'category': 'join',
  'name': 'Store-return reason and amount containment',
  'normal_queries': ['List store returns for damaged items with return amount above 100.',
                     'List store returns for damaged items.',
                     'List store returns with return amount above 100.',
                     'List store returns with any reason and return amount above 50.'],
  'structured_queries': ['Join store_returns to reason and return ticket number, item key, reason description, and '
                         'return amount where reason describes damaged and sr_return_amt is greater than 100.',
                         'Return the same joined columns where reason describes damaged.',
                         'Return the same joined columns where sr_return_amt is greater than 100.',
                         'Return the same joined columns where reason key is not null and sr_return_amt is greater '
                         'than 50.'],
  'expected_note': 'Damaged high-value returns should be contained in reason-only and amount-only sets.'},
 {'category': 'filter_threshold',
  'name': 'Inventory quantity threshold containment',
  'normal_queries': ['Show inventory rows with more than 500 units on hand.',
                     'Show inventory rows with more than 250 units on hand.',
                     'Show inventory rows with more than 100 units on hand.',
                     'Show inventory rows with more than 750 units on hand.'],
  'structured_queries': ['Return inv_date_sk, inv_item_sk, inv_warehouse_sk, and inv_quantity_on_hand where quantity '
                         'on hand is greater than 500.',
                         'Return the same columns where quantity on hand is greater than 250.',
                         'Return the same columns where quantity on hand is greater than 100.',
                         'Return the same columns where quantity on hand is greater than 750.'],
  'expected_note': 'Higher inventory thresholds should be subsets of lower thresholds.'},
 {'category': 'conjunction',
  'name': 'Promotion discount and channel containment',
  'normal_queries': ['List promotions with discount active and email channel enabled.',
                     'List promotions with discount active.',
                     'List promotions with email channel enabled.',
                     'List promotions with any active channel and discount active.'],
  'structured_queries': ['Return promotion ID, name, discount-active flag, and email-channel flag where '
                         'p_discount_active is true and p_channel_email is true.',
                         'Return the same columns where p_discount_active is true.',
                         'Return the same columns where p_channel_email is true.',
                         'Return the same columns where p_discount_active is true and at least one promotion channel '
                         'flag is true.'],
  'expected_note': 'Discount-active email promotions should be contained in both parent sets.'},
 {'category': 'date_scope',
  'name': 'Date year and month containment',
  'normal_queries': ['Show dates in January 2000.',
                     'Show all dates in 2000.',
                     'Show all January dates.',
                     'Show dates from 1999 through 2000.'],
  'structured_queries': ['Return date key, date, year, month number, and month sequence from date_dim where d_year '
                         'equals 2000 and d_moy equals 1.',
                         'Return the same columns where d_year equals 2000.',
                         'Return the same columns where d_moy equals 1.',
                         'Return the same columns where d_year is between 1999 and 2000.'],
  'expected_note': 'January 2000 should be contained in year-only, month-only, and wider-year sets.'},
 {'category': 'conjunction',
  'name': 'Warehouse state and size containment',
  'normal_queries': ['List California warehouses larger than 100000 square feet.',
                     'List California warehouses.',
                     'List warehouses larger than 100000 square feet.',
                     'List United States warehouses larger than 50000 square feet.'],
  'structured_queries': ['Return warehouse ID, name, state, country, and square feet where w_state equals CA and '
                         'w_warehouse_sq_ft is greater than 100000.',
                         'Return the same columns where w_state equals CA.',
                         'Return the same columns where w_warehouse_sq_ft is greater than 100000.',
                         'Return the same columns where w_country equals United States and w_warehouse_sq_ft is '
                         'greater than 50000.'],
  'expected_note': 'Large California warehouses should be narrower than the broader sets.'},
 {'category': 'conjunction',
  'name': 'Customer birth-year and education containment',
  'normal_queries': ['List customers born after 1970 who have an advanced degree.',
                     'List customers born after 1970.',
                     'List customers with an advanced degree.',
                     'List customers born after 1960 with a recorded education status.'],
  'structured_queries': ['Join customer to customer_demographics and return customer ID, birth year, and education '
                         'status where birth year is greater than 1970 and education status indicates an advanced '
                         'degree.',
                         'Return the same joined columns where birth year is greater than 1970.',
                         'Return the same joined columns where education status indicates an advanced degree.',
                         'Return the same joined columns where birth year is greater than 1960 and education status is '
                         'not null.'],
  'expected_note': 'Recent-birth advanced-degree customers should be contained in both parent sets.'},
 {'category': 'multi_join',
  'name': 'Store-sales item-category containment',
  'normal_queries': ['List store sales for electronics items with quantity above 5.',
                     'List store sales for electronics items.',
                     'List store sales with quantity above 5.',
                     'List store sales for categorized items with quantity above 2.'],
  'structured_queries': ['Join store_sales to item and return ticket number, item ID, category, quantity, and net paid '
                         'where category equals Electronics and quantity is greater than 5.',
                         'Return the same joined columns where category equals Electronics.',
                         'Return the same joined columns where quantity is greater than 5.',
                         'Return the same joined columns where category is not null and quantity is greater than 2.'],
  'expected_note': 'High-quantity electronics sales should be narrower than each broader set.'},
 {'category': 'multi_join',
  'name': 'Web-sales customer-state containment',
  'normal_queries': ['List web sales billed to California customers with net paid above 500.',
                     'List web sales billed to California customers.',
                     'List web sales with net paid above 500.',
                     'List web sales billed to United States customers with net paid above 250.'],
  'structured_queries': ['Join web_sales, customer, and customer_address; return order number, customer ID, state, '
                         'country, and net paid where state equals CA and net paid is greater than 500.',
                         'Return the same joined columns where state equals CA.',
                         'Return the same joined columns where net paid is greater than 500.',
                         'Return the same joined columns where country equals United States and net paid is greater '
                         'than 250.'],
  'expected_note': 'High-value California web sales should be narrower than the broader sets.'}]


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
