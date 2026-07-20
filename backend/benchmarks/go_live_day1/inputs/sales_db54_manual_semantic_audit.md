# Sales Database 54 — 500-Query Manual Semantic Audit

## Overall result

- Execution PASS: **496/500 (99.2%)**
- Execution FAIL / no SQL: **4/500 (0.8%)**
- Fully semantically correct SQL: **439/500 (87.8%)**
- Semantically incorrect or incomplete SQL: **61/500 (12.2%)**
- Executed successfully but semantically incorrect/incomplete: **57 queries**

The semantic score is strict: the generated SQL must answer the natural-language request at the requested grain, use the correct relationship role, calculate every requested metric, and avoid unrequested filters.

## Accuracy by category

| Category | Correct | Incorrect | Accuracy |
|---|---:|---:|---:|
| aggregation | 42 | 8 | 84.0% |
| derived_metric | 34 | 16 | 68.0% |
| distinct_count | 47 | 3 | 94.0% |
| group_by | 49 | 1 | 98.0% |
| having | 45 | 5 | 90.0% |
| join | 46 | 4 | 92.0% |
| multi_table_join | 44 | 6 | 88.0% |
| order_limit_topk | 44 | 6 | 88.0% |
| set_operations | 45 | 5 | 90.0% |
| subquery_cte | 43 | 7 | 86.0% |

## Accuracy by difficulty

| Difficulty | Correct | Incorrect | Accuracy |
|---|---:|---:|---:|
| easy | 143 | 7 | 95.3% |
| moderate | 173 | 27 | 86.5% |
| hard | 123 | 27 | 82.0% |

## Trace summary

- Trace entries: **500**
- Mean latency: **15.74s**
- Median latency: **14.83s**
- 95th percentile latency: **23.53s**
- Maximum latency: **29.58s**
- Consensus selections: **58**
- Best-scored-executed selections: **429**

## Four controlled failures

- **Test 044:** Fanout guard rejected every candidate that summed supplier annual revenue after one-to-many joins.
- **Test 081:** Fanout and grain validation rejected every candidate for the supplier-type quotient.
- **Test 379:** Grain validation incorrectly required a comparison predicate for a top-k COUNT(DISTINCT warehouse) ranking.
- **Test 398:** Grain validation incorrectly required a comparison predicate for a top-k COUNT(DISTINCT customer) ranking.

## Incorrect or incomplete tests

### Test 016 — aggregation / moderate

**Query:** What was the total revenue from delivered orders placed in 2025?

**Finding:** Uses summed line-item revenue instead of the sales-order grand total requested at order grain.

**Generated SQL:** `SELECT SUM(soi.line_total) AS total_revenue FROM sales_orders so JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE so.order_status = 'delivered' AND strftime('%Y', so.order_date) = '2025'`

### Test 018 — aggregation / moderate

**Query:** What is the total discount amount given on delivered orders?

**Finding:** Sums line-item discounts rather than the order-level discount amount.

**Generated SQL:** `SELECT SUM(soi.discount_amount) AS total_discount_amount FROM sales_orders so JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE so.order_status = 'delivered' GROUP BY so.order_status HAVING so.order_status = 'delivered'`

### Test 035 — aggregation / moderate

**Query:** What is the average discount percentage on delivered orders, based on discount amount divided by subtotal?

**Finding:** Averages each line discount against the order subtotal, creating the wrong grain and repeated denominators.

**Generated SQL:** `SELECT AVG(CAST(soi.discount_amount AS REAL) / so.subtotal) AS average_discount_percentage FROM sales_orders so JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE so.order_status = 'delivered' AND so.subtotal > 0`

### Test 037 — aggregation / hard

**Query:** What is the total shipped gross profit from products supplied by low-risk suppliers, fulfilled by open warehouses, and sold on delivered orders?

**Finding:** The shipped-profit formula mixes full line revenue with shipped quantity and product standard cost.

**Generated SQL:** `SELECT SUM(soi.line_total - soi.quantity_shipped * p.standard_cost) AS total_shipped_gross_profit FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id JOIN suppliers s ON p.supplier_id = s.supplier_id JOIN sales_orders so ON soi.order_id = so.order_id JOIN warehouses w ON soi.warehouse_id = w.warehouse_id WHERE s.risk_level = 'low' AND w.operating_status = 'open' AND so.order_status = 'delivered'`

### Test 041 — aggregation / hard

**Query:** What is the total delivered order revenue from active enterprise customers whose orders used Northwest warehouses?

**Finding:** Uses line-item revenue instead of delivered sales-order revenue at order grain.

**Generated SQL:** `SELECT SUM(s.line_total) FROM sales_orders o JOIN customers c ON o.customer_id = c.customer_id JOIN sales_order_items s ON o.order_id = s.order_id JOIN warehouses w ON o.warehouse_id = w.warehouse_id WHERE c.account_status = 'active' AND c.customer_segment = 'enterprise' AND w.region = 'Northwest' AND o.order_status = 'delivered'`

### Test 043 — aggregation / hard

**Query:** What is the total line revenue from order items fulfilled by a warehouse different from the order’s default warehouse?

**Finding:** Compares the order warehouse to a literal parameter instead of comparing it with the item warehouse.

**Generated SQL:** `SELECT SUM("sales_order_items"."line_total") AS "total_line_revenue" FROM "sales_orders" INNER JOIN "sales_order_items" ON "sales_orders"."order_id" = "sales_order_items"."order_id" WHERE "sales_orders"."warehouse_id" != ?`

### Test 044 — aggregation / hard

**Query:** What is the combined annual revenue of suppliers whose products appeared on delivered orders?

**Finding:** No SQL was returned.

**Generated SQL:** `<NO SQL GENERATED>`

### Test 048 — aggregation / hard

**Query:** What is the total gross profit from non-discontinued products sold through online or partner orders?

**Finding:** The gross-profit expression subtracts an adjusted line subtotal instead of the item cost.

**Generated SQL:** `SELECT SUM(soi.line_total - (soi.line_subtotal - soi.line_subtotal * soi.discount_pct / 100.0)) AS total_gross_profit FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id JOIN sales_orders so ON soi.order_id = so.order_id WHERE p.discontinued_flag = '0' AND so.sales_channel IN ('online', 'partner')`

### Test 052 — derived_metric / easy

**Query:** Show each product with the discount amount from list price to sale price.

**Finding:** Returns list and sale prices but never calculates their difference.

**Generated SQL:** `SELECT product_id, product_name, list_price, sale_price FROM products`

### Test 062 — derived_metric / easy

**Query:** Show each warehouse with its estimated used capacity units based on utilization percentage.

**Finding:** Returns SUM(capacity_units), not capacity multiplied by utilization percentage.

**Generated SQL:** `SELECT "warehouses"."warehouse_name", "warehouses"."capacity_units" AS "capacity_units", "warehouses"."current_utilization_pct" AS "current_utilization_pct", SUM("warehouses"."capacity_units") AS "estimated_used_capacity_units" FROM "warehouses" GROUP BY "warehouses"."warehouse_name", "warehouses"."capacity_units", "warehouses"."current_utilization_pct"`

### Test 068 — derived_metric / moderate

**Query:** Calculate the average order discount percentage for each customer segment.

**Finding:** Uses average line-item discount_pct instead of each order's discount amount divided by subtotal.

**Generated SQL:** `SELECT c.customer_segment, AVG(oi.discount_pct) AS average_discount_pct FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id JOIN sales_order_items oi ON so.order_id = oi.order_id GROUP BY c.customer_segment`

### Test 072 — derived_metric / moderate

**Query:** Calculate the average gross profit per unit for each product brand.

**Finding:** Computes (line_total - line_subtotal) / quantity rather than unit_price - unit_cost.

**Generated SQL:** `SELECT p.brand, AVG((soi.line_total - soi.line_subtotal) / soi.quantity_ordered) AS avg_gross_profit_per_unit FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id GROUP BY p.brand`

### Test 078 — derived_metric / moderate

**Query:** Calculate the average customer credit-utilization percentage for each customer segment.

**Finding:** Places credit_limit > 0 in HAVING at group grain instead of filtering customer rows before averaging.

**Generated SQL:** `SELECT customer_segment, AVG((current_balance / credit_limit) * 100) AS avg_credit_utilization FROM customers GROUP BY customer_segment HAVING credit_limit > 0`

### Test 080 — derived_metric / moderate

**Query:** Calculate the average annual operating cost per capacity unit for each warehouse region.

**Finding:** Places capacity_units > 0 in HAVING at region grain instead of filtering warehouse rows before averaging.

**Generated SQL:** `SELECT region, AVG(annual_operating_cost * 1.0 / capacity_units) AS avg_cost_per_unit FROM warehouses GROUP BY region HAVING capacity_units > 0`

### Test 081 — derived_metric / moderate

**Query:** For each supplier type, divide total supplier annual revenue by the number of products those suppliers provide.

**Finding:** No SQL was returned.

**Generated SQL:** `<NO SQL GENERATED>`

### Test 082 — derived_metric / moderate

**Query:** Calculate the average delivered line revenue per distinct order for each sales channel.

**Finding:** Averages individual line totals, not total delivered revenue per distinct order.

**Generated SQL:** `SELECT so.sales_channel, AVG(soi.line_total) AS avg_delivered_line_revenue_per_order FROM sales_orders so JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE so.order_status = 'delivered' GROUP BY so.sales_channel`

### Test 083 — derived_metric / moderate

**Query:** Calculate the average quantity ordered per distinct order for each product category.

**Finding:** Averages individual line quantities, not quantity per distinct order and category.

**Generated SQL:** `SELECT p.category, AVG(s.quantity_ordered) AS avg_quantity_per_order FROM products p JOIN sales_order_items s ON p.product_id = s.product_id GROUP BY p.category HAVING COUNT(DISTINCT s.order_id) > 0`

### Test 087 — derived_metric / hard

**Query:** For each supplier, calculate total order-item revenue minus total order-item cost for its products.

**Finding:** Returns separate revenue and subtotal columns, does not subtract cost, and treats line_subtotal as cost.

**Generated SQL:** `SELECT "suppliers"."supplier_name", "suppliers"."supplier_id", SUM("sales_order_items"."line_total") AS "total_revenue", SUM("sales_order_items"."line_subtotal") AS "total_cost" FROM "products" INNER JOIN "sales_order_items" ON "products"."product_id" = "sales_order_items"."product_id" INNER JOIN "suppliers" ON "products"."supplier_id" = "suppliers"."supplier_id" GROUP BY "suppliers"."supplier_id", "suppliers"."supplier_name"`

### Test 090 — derived_metric / hard

**Query:** For each product category, calculate total gross profit divided by total line revenue.

**Finding:** Uses line_total - line_subtotal as profit and divides by line_subtotal rather than line revenue.

**Generated SQL:** `SELECT p.category, SUM(soi.line_total - soi.line_subtotal) * 1.0 / SUM(soi.line_subtotal) AS profit_margin FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id GROUP BY p.category`

### Test 091 — derived_metric / hard

**Query:** For each sales representative, calculate delivered-order revenue per distinct customer served.

**Finding:** Groups by representative and customer but never divides revenue by distinct customers.

**Generated SQL:** `SELECT "sales_orders"."sales_rep_name", "sales_orders"."customer_id", SUM("sales_order_items"."line_total") AS "revenue" FROM "sales_orders" INNER JOIN "sales_order_items" ON "sales_orders"."order_id" = "sales_order_items"."order_id" WHERE "sales_orders"."order_status" = ? GROUP BY "sales_orders"."sales_rep_name", "sales_orders"."customer_id"`

### Test 092 — derived_metric / hard

**Query:** For each supplier, calculate distinct customers reached per non-discontinued product supplied.

**Finding:** Counts distinct customers but never divides by the number of non-discontinued products.

**Generated SQL:** `SELECT "suppliers"."supplier_id", "suppliers"."supplier_name", COUNT(DISTINCT "customers"."customer_id") AS "distinct_customers_reached" FROM "products" INNER JOIN "sales_order_items" ON "products"."product_id" = "sales_order_items"."product_id" INNER JOIN "sales_orders" ON "sales_order_items"."order_id" = "sales_orders"."order_id" INNER JOIN "customers" ON "sales_orders"."customer_id" = "customers"."customer_id" INNER JOIN "suppliers" ON "products"."supplier_id" = "suppliers"."supplier_id" WHERE "products"."discontinued_flag" = ? GROUP BY "suppliers"."supplier_id", "suppliers"."supplier_name"`

### Test 095 — derived_metric / hard

**Query:** For each warehouse region, calculate shipped units divided by total warehouse capacity.

**Finding:** Groups by region and individual capacity value; denominator is not total regional capacity.

**Generated SQL:** `SELECT w.region, SUM(soi.quantity_shipped) * 1.0 / w.capacity_units AS shipped_units_per_capacity FROM sales_order_items soi JOIN warehouses w ON soi.warehouse_id = w.warehouse_id GROUP BY w.region, w.capacity_units`

### Test 099 — derived_metric / hard

**Query:** For each product category, calculate its share of total delivered line revenue and its share of total gross profit.

**Finding:** Uses line_total - line_subtotal as gross profit, so both requested shares use an incorrect profit measure.

**Generated SQL:** `WITH delivered_totals AS ( SELECT SUM(s.line_total) AS total_revenue, SUM(s.line_total - s.line_subtotal) AS total_gross_profit FROM sales_order_items s JOIN sales_orders o ON s.order_id = o.order_id WHERE o.order_status = 'delivered' ), category_stats AS ( SELECT p.category, SUM(s.line_total) AS category_revenue, SUM(s.line_total - s.line_subtotal) AS category_gross_profit FROM products p JOIN sales_order_items s ON p.product_id = s.product_id JOIN sales_orders o ON s.order_id = o.order_id WHERE o.order_status = 'delivered' GROUP BY p.category ) SELECT cs.category, cs.category_revenue / dt.total_revenue AS revenue_share, cs.category_gross_profit / dt.total_gross_profit AS gross_profit_share FROM category_stats cs CROSS JOIN delivered_totals dt`

### Test 100 — derived_metric / hard

**Query:** For each customer, calculate the average number of days from order date to shipped date for orders that were shipped or delivered.

**Finding:** Returns only customer_id; the requested average number of shipping days is missing.

**Generated SQL:** `SELECT c.customer_id FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id WHERE so.order_status IN ('shipped', 'delivered') GROUP BY c.customer_id HAVING AVG(julianday(so.shipped_date) - julianday(so.order_date)) IS NOT NULL`

### Test 129 — distinct_count / moderate

**Query:** How many distinct warehouses fulfilled items on delivered orders?

**Finding:** Counts the order's default warehouse instead of the line item's fulfillment warehouse.

**Generated SQL:** `SELECT COUNT(DISTINCT so.warehouse_id) FROM sales_orders so JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE so.order_status = 'delivered'`

### Test 140 — distinct_count / hard

**Query:** How many distinct warehouses fulfilled order items for gold customers during 2025?

**Finding:** Counts the order's default warehouse instead of the warehouse that fulfilled the item.

**Generated SQL:** `SELECT COUNT(DISTINCT so.warehouse_id) FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id JOIN sales_order_items soi ON so.order_id = soi.order_id JOIN warehouses w ON so.warehouse_id = w.warehouse_id WHERE c.loyalty_tier = 'gold' AND so.order_date LIKE '2025%' AND soi.fulfillment_status = 'fulfilled'`

### Test 141 — distinct_count / hard

**Query:** How many distinct products were ordered through at least three different sales channels?

**Finding:** Groups by product and returns multiple count rows instead of one count of qualifying products.

**Generated SQL:** `SELECT COUNT(DISTINCT p.product_id) FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id JOIN sales_orders so ON soi.order_id = so.order_id GROUP BY p.product_id HAVING COUNT(DISTINCT so.sales_channel) >= 3`

### Test 191 — group_by / hard

**Query:** Show order count and average days from order date to shipped date by warehouse region.

**Finding:** The unnecessary line-item join duplicates orders, inflating order count and weighting the average by item count.

**Generated SQL:** `SELECT w.region, COUNT(*) AS order_count, AVG(julianday(so.shipped_date) - julianday(so.order_date)) AS avg_days_to_ship FROM sales_orders so JOIN sales_order_items soi ON so.order_id = soi.order_id JOIN warehouses w ON so.warehouse_id = w.warehouse_id GROUP BY w.region`

### Test 211 — having / easy

**Query:** List product categories with an average markup percentage above 40 percent.

**Finding:** Checks only average unit price > average unit cost; it never calculates or tests a 40% markup.

**Generated SQL:** `SELECT "products"."category", AVG("sales_order_items"."unit_price") AS "avg_price", AVG("sales_order_items"."unit_cost") AS "avg_cost" FROM "products" INNER JOIN "sales_order_items" ON "products"."product_id" = "sales_order_items"."product_id" GROUP BY "products"."category" HAVING "avg_price" > "avg_cost"`

### Test 221 — having / moderate

**Query:** List customer segments whose delivered-order revenue exceeds 20,000 dollars.

**Finding:** Uses summed line-item revenue instead of delivered order revenue at order grain.

**Generated SQL:** `SELECT c.customer_segment FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE so.order_status = 'delivered' GROUP BY c.customer_segment HAVING SUM(soi.line_total) > 20000`

### Test 224 — having / moderate

**Query:** List warehouse regions that fulfilled more than 15 order items.

**Finding:** Counts every item assigned to a region without requiring the item to be fulfilled.

**Generated SQL:** `SELECT w.region FROM sales_order_items soi JOIN sales_orders so ON soi.order_id = so.order_id JOIN warehouses w ON soi.warehouse_id = w.warehouse_id GROUP BY w.region HAVING COUNT(soi.order_item_id) > 15`

### Test 225 — having / moderate

**Query:** List loyalty tiers whose settled-payment-status order revenue exceeds 20,000 dollars.

**Finding:** Uses summed line-item revenue instead of order revenue for settled orders.

**Generated SQL:** `SELECT c.loyalty_tier FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE so.payment_status = 'settled' GROUP BY c.loyalty_tier HAVING SUM(soi.line_total) > 20000`

### Test 234 — having / moderate

**Query:** List warehouse regions that fulfilled orders for more than 10 distinct customers.

**Finding:** Uses the order's default warehouse and does not identify the line-item fulfillment warehouse.

**Generated SQL:** `SELECT "warehouses"."region", COUNT(DISTINCT "customers"."customer_id") AS "distinct_customer_count" FROM "sales_orders" INNER JOIN "customers" ON "sales_orders"."customer_id" = "customers"."customer_id" INNER JOIN "warehouses" ON "sales_orders"."warehouse_id" = "warehouses"."warehouse_id" GROUP BY "warehouses"."region" HAVING "distinct_customer_count" > ?`

### Test 260 — join / easy

**Query:** Show each order item with its order number and product name.

**Finding:** Returns product_name_snapshot instead of the current products.product_name.

**Generated SQL:** `SELECT soi.order_item_id, so.order_number, soi.product_name_snapshot FROM sales_order_items soi JOIN sales_orders so ON soi.order_id = so.order_id`

### Test 275 — join / moderate

**Query:** List order items fulfilled by a warehouse different from the order’s default warehouse, showing both warehouse names.

**Finding:** Returns the fulfillment warehouse name but not the default warehouse name requested.

**Generated SQL:** `SELECT soi.order_item_id, soi.order_id, soi.product_id, soi.quantity_ordered, soi.fulfillment_status, so.warehouse_id AS order_warehouse_id, soi.warehouse_id AS item_warehouse_id, w.warehouse_name FROM sales_order_items soi JOIN sales_orders so ON soi.order_id = so.order_id JOIN warehouses w ON soi.warehouse_id = w.warehouse_id WHERE soi.warehouse_id != so.warehouse_id`

### Test 289 — join / hard

**Query:** List products whose supplier state matches the state of a warehouse that fulfilled the product.

**Finding:** Uses order-level fulfillment status and an overcomplicated EXISTS path instead of the item's fulfillment warehouse relationship.

**Generated SQL:** `SELECT DISTINCT p.product_id, p.product_name FROM products p JOIN suppliers s ON p.supplier_id = s.supplier_id JOIN sales_order_items soi ON p.product_id = soi.product_id JOIN sales_orders so ON soi.order_id = so.order_id JOIN customers c ON so.customer_id = c.customer_id JOIN warehouses w ON soi.warehouse_id = w.warehouse_id WHERE EXISTS ( SELECT 1 FROM suppliers s2 JOIN warehouses w2 ON s2.state_code = w2.state_code JOIN sales_order_items soi2 ON w2.warehouse_id = soi2.warehouse_id JOIN sales_orders so2 ON soi2.order_id = so2.order_id WHERE s2.supplier_id = p.supplier_id AND soi2.product_id = p.product_id AND so2.fulfillment_status = 'fulfilled' AND s2.state_code = w2.state_code )`

### Test 291 — join / hard

**Query:** List order items whose unit price is lower than the product’s current sale price.

**Finding:** Adds an unrequested discontinued_flag = 0 restriction.

**Generated SQL:** `SELECT soi.order_item_id, soi.order_id, soi.product_id, soi.unit_price, p.sale_price FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id WHERE soi.unit_price < p.sale_price AND p.discontinued_flag = '0'`

### Test 330 — multi_table_join / moderate

**Query:** List enterprise customers with order numbers, default warehouse state, and item warehouse state.

**Finding:** Returns the item warehouse ID instead of the requested item warehouse state.

**Generated SQL:** `SELECT c.customer_id, so.order_number, w.state_code, soi.warehouse_id FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id JOIN sales_order_items soi ON so.order_id = soi.order_id JOIN warehouses w ON so.warehouse_id = w.warehouse_id WHERE c.customer_segment = 'enterprise'`

### Test 333 — multi_table_join / moderate

**Query:** List sales representatives with customers and products on the orders they handled.

**Finding:** Returns customer and product IDs instead of the requested customer and product names.

**Generated SQL:** `SELECT DISTINCT s.sales_rep_name, c.customer_id, p.product_id FROM sales_orders s JOIN customers c ON s.customer_id = c.customer_id JOIN sales_order_items soi ON s.order_id = soi.order_id JOIN products p ON soi.product_id = p.product_id`

### Test 335 — multi_table_join / moderate

**Query:** List preferred suppliers with products sold through the partner channel.

**Finding:** Returns only supplier information; the products sold through the partner channel are missing.

**Generated SQL:** `SELECT s.supplier_id, s.supplier_name, s.preferred_flag FROM suppliers s JOIN products p ON s.supplier_id = p.supplier_id JOIN sales_order_items soi ON p.product_id = soi.product_id JOIN sales_orders so ON soi.order_id = so.order_id WHERE s.preferred_flag = '1' AND so.sales_channel = 'partner' GROUP BY s.supplier_id, s.supplier_name, s.preferred_flag`

### Test 338 — multi_table_join / hard

**Query:** List orders whose item warehouse matches the default warehouse, with customer, product, and supplier.

**Finding:** Compares the item warehouse with the first open warehouse rather than the order's default warehouse.

**Generated SQL:** `SELECT so.order_id, so.order_number, c.customer_id, c.first_name, c.last_name, p.product_id, p.product_name, s.supplier_id, s.supplier_name FROM sales_orders so JOIN customers c ON so.customer_id = c.customer_id JOIN sales_order_items soi ON so.order_id = soi.order_id JOIN products p ON soi.product_id = p.product_id JOIN suppliers s ON p.supplier_id = s.supplier_id WHERE soi.warehouse_id = (SELECT warehouse_id FROM warehouses WHERE operating_status = 'open' ORDER BY warehouse_id LIMIT 1)`

### Test 340 — multi_table_join / hard

**Query:** List products with more than 20 total ordered units, together with supplier and fulfillment warehouses.

**Finding:** Applies the quantity threshold separately per product and warehouse instead of using the product's total ordered quantity.

**Generated SQL:** `SELECT p.product_id, p.product_name, s.supplier_name, w.warehouse_name FROM products p JOIN suppliers s ON p.supplier_id = s.supplier_id JOIN sales_order_items soi ON p.product_id = soi.product_id JOIN warehouses w ON soi.warehouse_id = w.warehouse_id GROUP BY p.product_id, s.supplier_id, w.warehouse_id HAVING SUM(soi.quantity_ordered) > 20`

### Test 343 — multi_table_join / hard

**Query:** List products from rating-1 suppliers that generated delivered line revenue in 2025, summarized by warehouse.

**Finding:** Does not enforce delivered order status, omits the product grain, and has conflicting raw and aggregated revenue outputs.

**Generated SQL:** `SELECT "sales_order_items"."warehouse_id", "warehouses"."warehouse_id", "sales_order_items"."line_total" AS "total_revenue", SUM("sales_order_items"."line_total") AS "total_revenue" FROM "sales_order_items" INNER JOIN "products" ON "sales_order_items"."product_id" = "products"."product_id" INNER JOIN "sales_orders" ON "sales_order_items"."order_id" = "sales_orders"."order_id" INNER JOIN "suppliers" ON "products"."supplier_id" = "suppliers"."supplier_id" INNER JOIN "warehouses" ON "sales_order_items"."warehouse_id" = "warehouses"."warehouse_id" WHERE "suppliers"."rating" = ? AND "sales_orders"."order_date" >= ? AND "sales_orders"."order_date" < ? AND "sales_order_items"."fulfillment_status" = ? GROUP BY "sales_order_items"."warehouse_id"`

### Test 369 — order_limit_topk / moderate

**Query:** Show the top 5 warehouses by total fulfilled line revenue.

**Finding:** Ranks the order's default warehouse rather than the line item's fulfillment warehouse.

**Generated SQL:** `SELECT w.warehouse_id, w.warehouse_name FROM warehouses w JOIN sales_orders so ON w.warehouse_id = so.warehouse_id JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE soi.fulfillment_status = 'fulfilled' GROUP BY w.warehouse_id, w.warehouse_name ORDER BY SUM(soi.line_total) DESC LIMIT 5`

### Test 375 — order_limit_topk / moderate

**Query:** Show the top 10 products by total gross profit.

**Finding:** Ranks by total revenue and never calculates gross profit.

**Generated SQL:** `SELECT "products"."product_name", "products"."product_id", SUM("sales_order_items"."line_total") AS "total_revenue", SUM("sales_order_items"."line_subtotal") AS "total_subtotal" FROM "sales_order_items" INNER JOIN "products" ON "sales_order_items"."product_id" = "products"."product_id" GROUP BY "products"."product_name", "products"."product_id" ORDER BY "total_revenue" DESC LIMIT 10`

### Test 379 — order_limit_topk / moderate

**Query:** Show the top 10 products by number of distinct warehouses that fulfilled them.

**Finding:** No SQL was returned.

**Generated SQL:** `<NO SQL GENERATED>`

### Test 393 — order_limit_topk / hard

**Query:** Show the 5 customers with the highest delivered revenue per delivered order.

**Finding:** Counts line items, does not calculate revenue per distinct delivered order, and ranks by total revenue.

**Generated SQL:** `SELECT "customers"."customer_id", "customers"."customer_number", "customers"."first_name", "customers"."last_name", SUM("sales_order_items"."line_total") AS "total_revenue", COUNT(*) AS "order_count" FROM "sales_orders" INNER JOIN "customers" ON "sales_orders"."customer_id" = "customers"."customer_id" INNER JOIN "sales_order_items" ON "sales_orders"."order_id" = "sales_order_items"."order_id" WHERE "sales_orders"."order_status" = ? GROUP BY "customers"."customer_id", "customers"."customer_number", "customers"."first_name", "customers"."last_name" ORDER BY "total_revenue" DESC LIMIT 5`

### Test 398 — order_limit_topk / hard

**Query:** Show the top 5 suppliers by number of distinct customers who bought their products.

**Finding:** No SQL was returned.

**Generated SQL:** `<NO SQL GENERATED>`

### Test 400 — order_limit_topk / hard

**Query:** Show the top 5 warehouse regions by gross profit per shipped unit.

**Finding:** Mixes full line revenue with shipped-unit cost, so the gross profit per shipped unit is incorrect for partial shipments.

**Generated SQL:** `SELECT region FROM ( SELECT w.region, (SUM(soi.line_total) - SUM(soi.unit_cost * soi.quantity_shipped)) * 1.0 / SUM(soi.quantity_shipped) AS gross_profit_per_shipped_unit FROM sales_order_items soi JOIN sales_orders so ON soi.order_id = so.order_id JOIN warehouses w ON soi.warehouse_id = w.warehouse_id WHERE soi.quantity_shipped > 0 GROUP BY w.region ) ORDER BY gross_profit_per_shipped_unit DESC LIMIT 5`

### Test 419 — set_operations / moderate

**Query:** List warehouses used both as an order’s default warehouse and as an item fulfillment warehouse.

**Finding:** Does not compute the intersection of warehouse IDs used in both roles; it groups one role while displaying another.

**Generated SQL:** `SELECT DISTINCT "sales_orders"."warehouse_id", "warehouses"."warehouse_id", "warehouses"."warehouse_name" FROM "sales_order_items" INNER JOIN "sales_orders" ON "sales_order_items"."order_id" = "sales_orders"."order_id" INNER JOIN "warehouses" ON "sales_order_items"."warehouse_id" = "warehouses"."warehouse_id" GROUP BY "sales_orders"."warehouse_id"`

### Test 433 — set_operations / moderate

**Query:** List warehouse regions that fulfilled delivered items but never handled a backordered item.

**Finding:** Uses default warehouses rather than item warehouses and evaluates the no-backorder condition per warehouse, not per region.

**Generated SQL:** `SELECT w.region FROM warehouses w JOIN sales_orders so ON w.warehouse_id = so.warehouse_id JOIN sales_order_items soi ON so.order_id = soi.order_id WHERE w.region IN ( SELECT w2.region FROM warehouses w2 JOIN sales_orders so2 ON w2.warehouse_id = so2.warehouse_id JOIN sales_order_items soi2 ON so2.order_id = soi2.order_id WHERE so2.order_status = 'delivered' AND soi2.fulfillment_status = 'fulfilled' AND soi2.quantity_backordered = 0 ) AND NOT EXISTS ( SELECT 1 FROM sales_orders so3 JOIN sales_order_items soi3 ON so3.order_id = soi3.order_id WHERE so3.warehouse_id = w.warehouse_id AND soi3.quantity_backordered > 0 ) GROUP BY w.region`

### Test 434 — set_operations / moderate

**Query:** List product categories sold in 2025 but not in 2024.

**Finding:** Excludes products sold in 2024 rather than excluding categories that were sold in 2024.

**Generated SQL:** `SELECT DISTINCT p.category FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id JOIN sales_orders so ON soi.order_id = so.order_id WHERE strftime('%Y', so.order_date) = '2025' AND NOT EXISTS ( SELECT 1 FROM sales_order_items soi2 JOIN sales_orders so2 ON soi2.order_id = so2.order_id WHERE soi2.product_id = p.product_id AND strftime('%Y', so2.order_date) = '2024' ) GROUP BY p.category`

### Test 439 — set_operations / hard

**Query:** List warehouses that fulfilled items for both gold and platinum customers but never for bronze customers.

**Finding:** Uses default order warehouses and never joins the fulfilled line items requested.

**Generated SQL:** `SELECT w.warehouse_id, w.warehouse_name FROM warehouses w JOIN sales_orders so ON w.warehouse_id = so.warehouse_id JOIN customers c ON so.customer_id = c.customer_id WHERE c.loyalty_tier IN ('gold', 'platinum') AND NOT EXISTS ( SELECT 1 FROM sales_orders so2 JOIN customers c2 ON so2.customer_id = c2.customer_id WHERE so2.warehouse_id = w.warehouse_id AND c2.loyalty_tier = 'bronze' ) GROUP BY w.warehouse_id, w.warehouse_name HAVING COUNT(DISTINCT CASE WHEN c.loyalty_tier = 'gold' THEN 1 END) > 0 AND COUNT(DISTINCT CASE WHEN c.loyalty_tier = 'platinum' THEN 1 END) > 0`

### Test 445 — set_operations / hard

**Query:** List product categories supplied by both high-risk and low-risk suppliers but not by medium-risk suppliers.

**Finding:** Only excludes medium-risk suppliers; it never requires each category to have both high- and low-risk suppliers.

**Generated SQL:** `SELECT DISTINCT "products"."category" FROM "products" INNER JOIN "suppliers" ON "products"."supplier_id" = "suppliers"."supplier_id" WHERE NOT EXISTS (SELECT 1 FROM "suppliers" WHERE "products"."supplier_id" = "suppliers"."supplier_id" AND "suppliers"."risk_level" = ?)`

### Test 452 — subquery_cte / easy

**Query:** List suppliers whose annual revenue is above the overall supplier average.

**Finding:** Aggregates the entire supplier table with HAVING and does not compare each supplier's revenue with the overall average.

**Generated SQL:** `SELECT "suppliers"."supplier_name", "suppliers"."annual_revenue", AVG("suppliers"."annual_revenue") AS "avg_revenue" FROM "suppliers" HAVING "avg_revenue" < ?`

### Test 460 — subquery_cte / easy

**Query:** List warehouses that have never fulfilled an order item.

**Finding:** Treats any assigned order item as a fulfillment and does not check fulfillment_status.

**Generated SQL:** `SELECT w.warehouse_id, w.warehouse_name FROM warehouses w WHERE NOT EXISTS ( SELECT 1 FROM sales_order_items soi WHERE soi.warehouse_id = w.warehouse_id )`

### Test 462 — subquery_cte / easy

**Query:** List customers who have never placed a delivered order.

**Finding:** The inner join excludes customers with no orders, although they also have never placed a delivered order.

**Generated SQL:** `SELECT c.customer_id, c.first_name, c.last_name FROM customers c JOIN sales_orders so ON c.customer_id = so.customer_id WHERE NOT EXISTS ( SELECT 1 FROM sales_orders so2 WHERE so2.customer_id = c.customer_id AND so2.order_status = 'delivered' ) GROUP BY c.customer_id, c.first_name, c.last_name`

### Test 466 — subquery_cte / moderate

**Query:** List products priced above the average sale price for their category.

**Finding:** Compares product sale_price with average order-item unit_price instead of average product sale_price by category.

**Generated SQL:** `SELECT p.product_id, p.product_name, p.category, p.sale_price FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id WHERE p.sale_price > ( SELECT AVG(soi2.unit_price) FROM sales_order_items soi2 JOIN products p2 ON soi2.product_id = p2.product_id WHERE p2.category = p.category ) GROUP BY p.product_id, p.product_name, p.category, p.sale_price HAVING p.sale_price > ( SELECT AVG(soi3.unit_price) FROM sales_order_items soi3 JOIN products p3 ON soi3.product_id = p3.product_id WHERE p3.category = p.category )`

### Test 485 — subquery_cte / moderate

**Query:** List products whose latest order date is later than the average latest-order date across products.

**Finding:** Applies AVG directly to text dates instead of averaging a numeric date representation such as julianday.

**Generated SQL:** `WITH product_latest_orders AS ( SELECT p.product_id, p.product_name, MAX(so.order_date) AS latest_order_date FROM products p JOIN sales_order_items soi ON p.product_id = soi.product_id JOIN sales_orders so ON soi.order_id = so.order_id GROUP BY p.product_id, p.product_name ) SELECT product_id, product_name FROM product_latest_orders WHERE latest_order_date > ( SELECT AVG(latest_order_date) FROM product_latest_orders )`

### Test 492 — subquery_cte / hard

**Query:** List warehouses whose backordered-item count is above the average for warehouses in the same region.

**Finding:** Sums backordered units, while the query asks for the count of backordered items.

**Generated SQL:** `WITH warehouse_backorders AS ( SELECT w.warehouse_id, w.warehouse_name, w.region, SUM(soi.quantity_backordered) AS total_backordered FROM warehouses w JOIN sales_order_items soi ON w.warehouse_id = soi.warehouse_id GROUP BY w.warehouse_id, w.warehouse_name, w.region ), region_averages AS ( SELECT region, AVG(total_backordered) AS avg_backordered FROM warehouse_backorders GROUP BY region ) SELECT wb.warehouse_id, wb.warehouse_name, wb.region FROM warehouse_backorders wb JOIN region_averages ra ON wb.region = ra.region WHERE wb.total_backordered > ra.avg_backordered`

### Test 497 — subquery_cte / hard

**Query:** List warehouses that fulfilled at least one item from every product category.

**Finding:** Counts every item category assigned to a warehouse without requiring a fulfilled item.

**Generated SQL:** `WITH warehouse_categories AS ( SELECT soi.warehouse_id, COUNT(DISTINCT p.category) AS cat_count FROM sales_order_items soi JOIN products p ON soi.product_id = p.product_id GROUP BY soi.warehouse_id ), total_categories AS ( SELECT COUNT(DISTINCT category) AS total_cat_count FROM products ) SELECT w.warehouse_id, w.warehouse_name FROM warehouses w JOIN warehouse_categories wc ON w.warehouse_id = wc.warehouse_id CROSS JOIN total_categories tc WHERE wc.cat_count = tc.total_cat_count`
