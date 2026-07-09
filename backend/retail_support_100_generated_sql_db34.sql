SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN support_tickets st ON c.customer_id = st.customer_id
WHERE o.payment_status = 'unpaid'
  AND st.priority = 'high'
  AND st.resolved = 'no'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT CASE WHEN o.payment_status = 'unpaid' THEN o.order_id END) > 0
   AND COUNT(DISTINCT CASE WHEN st.priority = 'high' AND st.resolved = 'no' THEN st.ticket_id END) > 0;

WITH latest_cancelled AS (
    SELECT 
        o.customer_id,
        MAX(o.placed_at) AS latest_cancelled_date
    FROM orders o
    WHERE o.order_status = 'cancelled'
    GROUP BY o.customer_id
),
payment_tickets AS (
    SELECT 
        st.customer_id,
        st.opened_at
    FROM support_tickets st
    WHERE st.issue_type = 'payment'
)
SELECT 
    c.customer_id,
    c.customer_name
FROM customers c
JOIN latest_cancelled lc ON c.customer_id = lc.customer_id
JOIN payment_tickets pt ON c.customer_id = pt.customer_id
WHERE pt.opened_at > lc.latest_cancelled_date;

SELECT DISTINCT p.product_id, p.product_name
FROM products p
JOIN suppliers s ON p.supplier_id = s.supplier_id
JOIN order_items oi ON p.product_id = oi.product_id
WHERE s.preferred = 'yes'
  AND p.discontinued = 'no'
  AND oi.returned = 'yes';

SELECT c.category_id, c.category_name
FROM categories c
JOIN products p ON c.category_id = p.category_id
JOIN order_items oi ON p.product_id = oi.product_id
WHERE p.discontinued = 'no'
GROUP BY c.category_id, c.category_name
HAVING COUNT(DISTINCT p.product_id) = (
    SELECT COUNT(DISTINCT p2.product_id)
    FROM products p2
    WHERE p2.category_id = c.category_id
      AND p2.discontinued = 'no'
);

SELECT s.supplier_id, s.supplier_name
FROM suppliers s
JOIN products p ON s.supplier_id = p.supplier_id
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
JOIN shipments sh ON o.order_id = sh.order_id
JOIN carriers c ON sh.carrier_id = c.carrier_id
GROUP BY s.supplier_id, s.supplier_name
HAVING COUNT(DISTINCT c.service_level) = (SELECT COUNT(DISTINCT service_level) FROM carriers);

SELECT DISTINCT o.order_id
FROM orders o
JOIN shipments s ON o.order_id = s.order_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE s.shipment_status = 'delivered'
  AND oi.returned = 'yes';

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN addresses a ON c.customer_id = a.customer_id
JOIN orders o ON c.customer_id = o.customer_id AND o.shipping_address_id = a.address_id
JOIN support_tickets st ON c.customer_id = st.customer_id AND st.order_id = o.order_id
JOIN employees e ON st.assigned_employee_id = e.employee_id
JOIN departments d ON e.department_id = d.department_id
WHERE a.city != d.region;

SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
WHERE e.manager_id IS NOT NULL
  AND st.resolved = 'no'
  AND st.priority = 'urgent';

SELECT p.product_id, p.product_name
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
GROUP BY p.product_id, p.product_name
HAVING SUM(CASE WHEN oi.returned = 'yes' THEN oi.quantity ELSE 0 END) > SUM(CASE WHEN oi.returned = 'no' THEN oi.quantity ELSE 0 END);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories cat ON p.category_id = cat.category_id
WHERE cat.parent_category_id IS NULL
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT cat.category_id) = (
    SELECT COUNT(*)
    FROM categories
    WHERE parent_category_id IS NULL
);

SELECT o.order_id
FROM orders o
JOIN shipments s ON o.order_id = s.order_id
WHERE s.shipment_status = 'delayed'
  AND o.payment_status = 'paid';

SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
  SELECT 1
  FROM employees e
  WHERE e.department_id = d.department_id
    AND e.active = 'yes'
    AND NOT EXISTS (
      SELECT 1
      FROM support_tickets st
      WHERE st.assigned_employee_id = e.employee_id
    )
);

WITH customer_spending AS (
    SELECT 
        c.customer_id,
        c.customer_name,
        c.loyalty_tier,
        SUM(oi.quantity * oi.unit_price) AS total_spending
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN order_items oi ON o.order_id = oi.order_id
    GROUP BY c.customer_id, c.customer_name, c.loyalty_tier
),
tier_averages AS (
    SELECT 
        loyalty_tier,
        AVG(total_spending) AS avg_spending
    FROM customer_spending
    GROUP BY loyalty_tier
)
SELECT 
    cs.customer_id,
    cs.customer_name
FROM customer_spending cs
JOIN tier_averages ta ON cs.loyalty_tier = ta.loyalty_tier
WHERE cs.total_spending > ta.avg_spending;

SELECT p.product_id, p.product_name, p.unit_price
FROM products p
JOIN categories c ON p.category_id = c.category_id
WHERE p.unit_price > (
    SELECT AVG(p2.unit_price)
    FROM products p2
    WHERE p2.category_id = p.category_id
);

SELECT st.ticket_id, st.order_id, st.issue_type, st.priority
FROM support_tickets st
WHERE EXISTS (
    SELECT 1
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    WHERE o.order_id = st.order_id
      AND p.discontinued = 'yes'
);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN addresses a ON o.shipping_address_id = a.address_id
WHERE a.address_type = 'work'
AND NOT EXISTS (
    SELECT 1
    FROM orders o2
    JOIN addresses a2 ON o2.shipping_address_id = a2.address_id
    WHERE o2.customer_id = c.customer_id
    AND a2.address_type = 'billing'
)
GROUP BY c.customer_id, c.customer_name;

SELECT c.category_id, c.category_name
FROM categories c
JOIN products p ON c.category_id = p.category_id
WHERE c.parent_category_id IS NOT NULL
GROUP BY c.category_id, c.category_name
HAVING COUNT(DISTINCT p.supplier_id) > (
    SELECT COUNT(DISTINCT p2.supplier_id)
    FROM categories pc
    JOIN products p2 ON pc.category_id = p2.category_id
    WHERE pc.category_id = c.parent_category_id
);

SELECT o.order_id
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id
HAVING COUNT(*) = SUM(CASE WHEN oi.returned = 'yes' THEN 1 ELSE 0 END);

SELECT s.supplier_id, s.supplier_name
FROM suppliers s
JOIN products p ON s.supplier_id = p.supplier_id
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
JOIN customers c ON o.customer_id = c.customer_id
JOIN addresses a ON c.customer_id = a.customer_id
GROUP BY s.supplier_id, s.supplier_name
HAVING COUNT(DISTINCT a.state) = (SELECT COUNT(DISTINCT state) FROM addresses);

SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
JOIN employees m ON e.manager_id = m.employee_id
WHERE m.active = 'no'
  AND st.resolved = 'no';

WITH first_orders AS (
    SELECT o.customer_id, o.order_id, o.payment_status,
           ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.placed_at ASC) AS rn
    FROM orders o
),
latest_tickets AS (
    SELECT st.customer_id, st.resolved,
           ROW_NUMBER() OVER (PARTITION BY st.customer_id ORDER BY st.opened_at DESC) AS rn
    FROM support_tickets st
)
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN first_orders fo ON c.customer_id = fo.customer_id AND fo.rn = 1
JOIN latest_tickets lt ON c.customer_id = lt.customer_id AND lt.rn = 1
WHERE fo.payment_status = 'unpaid'
  AND lt.resolved = 'no';

SELECT p.product_id, p.product_name
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
      AND oi.returned = 'yes'
)
AND EXISTS (
    SELECT 1
    FROM order_items oi
    JOIN shipments s ON oi.order_id = s.order_id
    WHERE oi.product_id = p.product_id
      AND s.shipment_status = 'delayed'
);

SELECT c.carrier_name
FROM carriers c
JOIN shipments s ON c.carrier_id = s.carrier_id
JOIN orders o ON s.order_id = o.order_id
JOIN customers cu ON o.customer_id = cu.customer_id
WHERE s.shipment_status = 'delivered'
GROUP BY c.carrier_id, c.carrier_name
HAVING COUNT(DISTINCT cu.loyalty_tier) = (SELECT COUNT(DISTINCT loyalty_tier) FROM customers);

SELECT o.order_id
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE oi.returned = 'yes'
  AND NOT EXISTS (
    SELECT 1
    FROM support_tickets st
    WHERE st.order_id = o.order_id
  )
GROUP BY o.order_id;

SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN support_tickets st ON c.customer_id = st.customer_id
JOIN orders o ON st.order_id = o.order_id
WHERE st.resolved = 'no'
  AND st.issue_type = 'shipping'
  AND o.order_status != 'delivered';

SELECT p.product_id, p.product_name
FROM products p
WHERE EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.product_id = p.product_id
      AND oi.unit_price < p.unit_price
);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN support_tickets st ON c.customer_id = st.customer_id
WHERE oi.returned = 'yes' AND st.resolved = 'yes'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(oi.order_item_id) > COUNT(st.ticket_id);

SELECT DISTINCT "employees"."employee_id", "employees"."employee_name" FROM "employees" INNER JOIN "departments" ON "employees"."department_id" = "departments"."department_id" INNER JOIN "support_tickets" ON "employees"."employee_id" = "support_tickets"."assigned_employee_id" INNER JOIN "customers" ON "support_tickets"."customer_id" = "customers"."customer_id" INNER JOIN "addresses" ON "customers"."customer_id" = "addresses"."customer_id" WHERE "support_tickets"."assigned_employee_id" = ? AND "support_tickets"."customer_id" = ? AND "customers"."customer_id" = ? AND "customers"."customer_id" = ? AND "addresses"."address_id" = ? AND "employees"."department_id" = ? AND "departments"."department_id" = ? AND "departments"."region" != ?;

SELECT c.category_id, c.category_name
FROM categories c
JOIN products p ON c.category_id = p.category_id
JOIN suppliers s ON p.supplier_id = s.supplier_id
GROUP BY c.category_id, c.category_name
HAVING COUNT(*) = SUM(CASE WHEN s.preferred = 'yes' THEN 1 ELSE 0 END);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN suppliers s ON p.supplier_id = s.supplier_id
GROUP BY c.customer_id, c.customer_name
HAVING SUM(CASE WHEN s.preferred = 'yes' THEN 1 ELSE 0 END) > 0
   AND SUM(CASE WHEN s.preferred = 'no' THEN 1 ELSE 0 END) > 0;

SELECT st.ticket_id, st.customer_id, st.order_id, st.assigned_employee_id, st.opened_at, st.issue_type, st.priority, st.resolved
FROM support_tickets st
JOIN employees e ON st.assigned_employee_id = e.employee_id
JOIN departments d ON e.department_id = d.department_id
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e2
    WHERE e2.department_id = d.department_id
      AND e2.role = 'manager'
      AND e2.active = 'yes'
)
AND e.manager_id IS NOT NULL;

WITH latest_shipments AS (
  SELECT
    order_id,
    shipment_status,
    shipped_at,
    ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY shipped_at DESC) AS rn
  FROM shipments
)
SELECT o.order_id
FROM orders o
JOIN latest_shipments ls ON o.order_id = ls.order_id
WHERE ls.rn = 1 AND ls.shipment_status = 'delayed';

SELECT DISTINCT p.product_id, p.product_name
FROM products p
JOIN categories c ON p.category_id = c.category_id
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
JOIN customers cu ON o.customer_id = cu.customer_id
WHERE c.parent_category_id IS NOT NULL
  AND cu.loyalty_tier = 'platinum';

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN addresses a ON o.shipping_address_id = a.address_id
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT a.city) >= 3;

SELECT d.department_id, d.department_name
FROM departments d
JOIN employees e ON d.department_id = e.department_id
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(DISTINCT st.issue_type) = (SELECT COUNT(DISTINCT issue_type) FROM support_tickets);

SELECT p.product_id, p.product_name
FROM products p
WHERE EXISTS (
  SELECT 1
  FROM order_items oi
  JOIN orders o ON oi.order_id = o.order_id
  WHERE oi.product_id = p.product_id
    AND o.payment_status = 'unpaid'
)
AND NOT EXISTS (
  SELECT 1
  FROM order_items oi
  JOIN orders o ON oi.order_id = o.order_id
  WHERE oi.product_id = p.product_id
    AND o.payment_status = 'paid'
);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories cat ON p.category_id = cat.category_id
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT cat.category_id) > (
    SELECT AVG(cat_count)
    FROM (
        SELECT COUNT(DISTINCT cat2.category_id) AS cat_count
        FROM customers c2
        JOIN orders o2 ON c2.customer_id = o2.customer_id
        JOIN order_items oi2 ON o2.order_id = oi2.order_id
        JOIN products p2 ON oi2.product_id = p2.product_id
        JOIN categories cat2 ON p2.category_id = cat2.category_id
        GROUP BY c2.customer_id
    )
);

SELECT s.supplier_id, s.supplier_name
FROM suppliers s
WHERE NOT EXISTS (
    SELECT 1
    FROM products p
    JOIN order_items oi ON p.product_id = oi.product_id
    WHERE p.supplier_id = s.supplier_id
      AND p.discontinued = 'yes'
);

SELECT o.order_id
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id
HAVING SUM(oi.quantity * oi.unit_price) > (
    SELECT AVG(customer_order_total)
    FROM (
        SELECT SUM(oi2.quantity * oi2.unit_price) AS customer_order_total
        FROM orders o2
        JOIN order_items oi2 ON o2.order_id = oi2.order_id
        WHERE o2.customer_id = o.customer_id
        GROUP BY o2.order_id
    )
);

SELECT e.employee_id, e.employee_name
FROM employees e
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
JOIN employees m ON e.manager_id = m.employee_id
WHERE st.resolved = 'no'
GROUP BY e.employee_id, e.employee_name, m.employee_id
HAVING COUNT(st.ticket_id) > (
    SELECT COUNT(*)
    FROM support_tickets st2
    WHERE st2.assigned_employee_id = m.employee_id
      AND st2.resolved = 'no'
);

SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN support_tickets st ON c.customer_id = st.customer_id
JOIN orders o ON st.order_id = o.order_id
JOIN shipments s ON o.order_id = s.order_id
JOIN carriers car ON s.carrier_id = car.carrier_id
WHERE car.service_level = 'international';

SELECT c.category_id, c.category_name
FROM categories c
WHERE EXISTS (
    SELECT 1
    FROM products p
    JOIN order_items oi ON p.product_id = oi.product_id
    JOIN orders o ON oi.order_id = o.order_id
    WHERE p.category_id = c.category_id
      AND p.unit_price = (
          SELECT MAX(p2.unit_price)
          FROM products p2
          WHERE p2.category_id = c.category_id
      )
      AND NOT EXISTS (
          SELECT 1
          FROM order_items oi2
          WHERE oi2.product_id = p.product_id
      )
)
AND EXISTS (
    SELECT 1
    FROM products p3
    JOIN order_items oi3 ON p3.product_id = oi3.product_id
    JOIN orders o3 ON oi3.order_id = o3.order_id
    WHERE p3.category_id = c.category_id
      AND p3.unit_price < (
          SELECT MAX(p4.unit_price)
          FROM products p4
          WHERE p4.category_id = c.category_id
      )
);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN suppliers s ON p.supplier_id = s.supplier_id
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT CASE WHEN s.supplier_name = 'BookHub' THEN p.product_id END) = (SELECT COUNT(*) FROM products WHERE supplier_id = (SELECT supplier_id FROM suppliers WHERE supplier_name = 'BookHub'))
   OR COUNT(DISTINCT CASE WHEN s.supplier_name = 'GlobalTech' THEN p.product_id END) = (SELECT COUNT(*) FROM products WHERE supplier_id = (SELECT supplier_id FROM suppliers WHERE supplier_name = 'GlobalTech'))
   OR COUNT(DISTINCT CASE WHEN s.supplier_name = 'HomePro' THEN p.product_id END) = (SELECT COUNT(*) FROM products WHERE supplier_id = (SELECT supplier_id FROM suppliers WHERE supplier_name = 'HomePro'))
   OR COUNT(DISTINCT CASE WHEN s.supplier_name = 'Northwest Supply' THEN p.product_id END) = (SELECT COUNT(*) FROM products WHERE supplier_id = (SELECT supplier_id FROM suppliers WHERE supplier_name = 'Northwest Supply'))
   OR COUNT(DISTINCT CASE WHEN s.supplier_name = 'Pacific Traders' THEN p.product_id END) = (SELECT COUNT(*) FROM products WHERE supplier_id = (SELECT supplier_id FROM suppliers WHERE supplier_name = 'Pacific Traders'));

SELECT s.shipment_id, s.order_id, s.shipped_at, s.delivered_at, st.ticket_id, st.opened_at
FROM shipments s
JOIN orders o ON s.order_id = o.order_id
JOIN support_tickets st ON o.order_id = st.order_id
WHERE s.delivered_at < st.opened_at;

SELECT p.product_id, p.product_name
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
JOIN customers c ON o.customer_id = c.customer_id
GROUP BY p.product_id, p.product_name
HAVING COUNT(DISTINCT c.loyalty_tier) = (SELECT COUNT(DISTINCT loyalty_tier) FROM customers);

SELECT e.employee_id, e.employee_name
FROM employees e
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
GROUP BY e.employee_id, e.employee_name
HAVING COUNT(*) = SUM(CASE WHEN st.resolved = 'yes' THEN 1 ELSE 0 END);

SELECT o.order_id
FROM orders o
WHERE o.payment_status = 'refunded'
  AND NOT EXISTS (
    SELECT 1
    FROM order_items oi
    WHERE oi.order_id = o.order_id
      AND oi.returned = 'yes'
  );

SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM support_tickets st
    WHERE st.customer_id = c.customer_id
)
AND EXISTS (
    SELECT 1
    FROM orders o
    JOIN shipments s ON s.order_id = o.order_id
    WHERE o.customer_id = c.customer_id
    AND s.shipment_status = 'delayed'
);

SELECT s.supplier_id, s.supplier_name
FROM suppliers s
JOIN products p ON s.supplier_id = p.supplier_id
JOIN order_items oi ON p.product_id = oi.product_id
GROUP BY s.supplier_id, s.supplier_name
HAVING SUM(oi.quantity * oi.unit_price) > (
    SELECT AVG(supplier_total_sales)
    FROM (
        SELECT SUM(oi2.quantity * oi2.unit_price) AS supplier_total_sales
        FROM suppliers s2
        JOIN products p2 ON s2.supplier_id = p2.supplier_id
        JOIN order_items oi2 ON p2.product_id = oi2.product_id
        GROUP BY s2.supplier_id
    )
);

WITH carrier_counts AS (
    SELECT 
        c.category_id,
        c.category_name,
        COUNT(DISTINCT sh.carrier_id) AS carrier_count
    FROM categories c
    JOIN products p ON c.category_id = p.category_id
    JOIN order_items oi ON p.product_id = oi.product_id
    JOIN orders o ON oi.order_id = o.order_id
    JOIN shipments sh ON o.order_id = sh.order_id
    GROUP BY c.category_id, c.category_name
),
avg_carrier_count AS (
    SELECT AVG(carrier_count) AS avg_count
    FROM carrier_counts
)
SELECT 
    cc.category_id,
    cc.category_name
FROM carrier_counts cc
CROSS JOIN avg_carrier_count ac
WHERE cc.carrier_count > ac.avg_count;

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.customer_name
HAVING SUM(CASE WHEN o.order_status = 'cancelled' THEN 1 ELSE 0 END) > 0
   AND SUM(CASE WHEN o.order_status = 'delivered' THEN 1 ELSE 0 END) > 0;

SELECT "o"."order_id" AS "order_id" FROM "orders" AS "o" INNER JOIN "addresses" AS "a" ON "o"."shipping_address_id" = "a"."address_id" INNER JOIN "customers" AS "c_order" ON "o"."customer_id" = "c_order"."customer_id" INNER JOIN "customers" AS "c_addr" ON "a"."customer_id" = "c_addr"."customer_id" WHERE "c_order"."customer_id" != "c_addr"."customer_id";

SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
JOIN employees te ON e.employee_id = te.manager_id
JOIN support_tickets st ON te.employee_id = st.assigned_employee_id
WHERE e.role = 'manager'
  AND st.resolved = 'no'
  AND st.priority = 'urgent';

SELECT DISTINCT p.product_id, p.product_name
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
JOIN customers c ON o.customer_id = c.customer_id
JOIN shipments s ON o.order_id = s.order_id
WHERE c.signup_date < o.placed_at
  AND s.shipment_status = 'delayed';

SELECT st.ticket_id, st.customer_id, st.order_id, st.assigned_employee_id, st.opened_at, st.issue_type, st.priority, st.resolved
FROM support_tickets st
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = st.customer_id
      AND o.payment_status = 'paid'
);

SELECT c.carrier_name
FROM carriers c
JOIN shipments s ON c.carrier_id = s.carrier_id
JOIN orders o ON s.order_id = o.order_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE s.shipment_status IN ('delivered', 'delayed')
GROUP BY c.carrier_id, c.carrier_name
HAVING AVG(CASE WHEN s.shipment_status = 'delivered' THEN oi.unit_price * oi.quantity END) >
       AVG(CASE WHEN s.shipment_status = 'delayed' THEN oi.unit_price * oi.quantity END);

SELECT c.category_id, c.category_name
FROM categories c
WHERE NOT EXISTS (
    SELECT 1
    FROM categories child
    WHERE child.parent_category_id = c.category_id
      AND NOT EXISTS (
        SELECT 1
        FROM products p
        WHERE p.category_id = child.category_id
          AND p.discontinued = 'no'
      )
)
GROUP BY c.category_id, c.category_name
HAVING COUNT(*) > 0;

WITH latest_orders AS (
  SELECT o.customer_id, o.order_id,
         ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.placed_at DESC) AS rn
  FROM orders o
)
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN latest_orders lo ON c.customer_id = lo.customer_id
JOIN order_items oi ON lo.order_id = oi.order_id
WHERE lo.rn = 1
  AND oi.returned = 'yes';

SELECT p.product_id, p.product_name
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
JOIN suppliers s ON p.supplier_id = s.supplier_id
WHERE s.preferred = 'no'
GROUP BY p.product_id, p.product_name
HAVING SUM(CASE WHEN oi.returned = 'yes' THEN oi.quantity ELSE 0 END) > 5;

SELECT d.department_id, d.department_name
FROM departments d
JOIN employees e ON d.department_id = e.department_id
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
WHERE st.resolved = 'no'
GROUP BY d.department_id, d.department_name
HAVING COUNT(st.ticket_id) > (
    SELECT AVG(ticket_count)
    FROM (
        SELECT COUNT(st2.ticket_id) AS ticket_count
        FROM employees e2
        JOIN support_tickets st2 ON e2.employee_id = st2.assigned_employee_id
        WHERE st2.resolved = 'no'
        GROUP BY e2.department_id
    )
);

SELECT o.order_id
FROM orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM shipments s
    WHERE s.order_id = o.order_id
      AND s.shipment_status != 'delivered'
)
AND NOT EXISTS (
    SELECT 1
    FROM support_tickets st
    WHERE st.order_id = o.order_id
      AND st.resolved = 'no'
);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN suppliers s ON p.supplier_id = s.supplier_id
WHERE s.preferred = 'yes'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT s.supplier_id) = (
    SELECT COUNT(*)
    FROM suppliers
    WHERE preferred = 'yes'
);

SELECT e.employee_id, e.employee_name
FROM employees e
WHERE EXISTS (
    SELECT 1
    FROM support_tickets st
    JOIN orders o ON st.order_id = o.order_id
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    JOIN customers c ON o.customer_id = c.customer_id
    WHERE st.assigned_employee_id = e.employee_id
      AND c.customer_id = (
          SELECT c2.customer_id
          FROM customers c2
          JOIN employees e2 ON e2.manager_id = e.employee_id
          WHERE c2.customer_id = c.customer_id
      )
);

SELECT p.product_id, p.product_name
FROM products p
WHERE (
    SELECT SUM(oi.quantity)
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    JOIN customers c ON o.customer_id = c.customer_id
    WHERE oi.product_id = p.product_id AND c.loyalty_tier = 'gold'
) > (
    SELECT SUM(oi.quantity)
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.order_id
    JOIN customers c ON o.customer_id = c.customer_id
    WHERE oi.product_id = p.product_id AND c.loyalty_tier = 'bronze'
);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY c.customer_id, c.customer_name
HAVING SUM(CASE WHEN o.payment_status = 'unpaid' THEN oi.unit_price * oi.quantity ELSE 0 END) >
       SUM(CASE WHEN o.payment_status = 'paid' THEN oi.unit_price * oi.quantity ELSE 0 END);

SELECT c.category_id, c.category_name
FROM categories c
WHERE EXISTS (
    SELECT 1
    FROM products p
    WHERE p.category_id = c.category_id
    AND NOT EXISTS (
        SELECT 1
        FROM order_items oi
        WHERE oi.product_id = p.product_id
    )
);

SELECT st.ticket_id, st.customer_id, st.order_id, st.opened_at
FROM support_tickets st
JOIN orders o ON st.order_id = o.order_id
JOIN shipments s ON o.order_id = s.order_id
WHERE st.opened_at > s.shipped_at AND st.opened_at < s.delivered_at;

SELECT o.order_id
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id
HAVING COUNT(DISTINCT oi.product_id) > (
    SELECT AVG(product_count)
    FROM (
        SELECT COUNT(DISTINCT oi2.product_id) AS product_count
        FROM orders o2
        JOIN order_items oi2 ON o2.order_id = oi2.order_id
        GROUP BY o2.order_id
    )
);

SELECT s.supplier_id, s.supplier_name
FROM suppliers s
JOIN products p ON s.supplier_id = p.supplier_id
JOIN order_items oi ON p.product_id = oi.product_id
JOIN categories c ON p.category_id = c.category_id
GROUP BY s.supplier_id, s.supplier_name
HAVING COUNT(DISTINCT c.category_id) = (SELECT COUNT(DISTINCT category_id) FROM order_items oi2 JOIN products p2 ON oi2.product_id = p2.product_id);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN addresses a_home ON c.customer_id = a_home.customer_id
JOIN addresses a_work ON c.customer_id = a_work.customer_id
WHERE a_home.address_type = 'home'
  AND a_work.address_type = 'work'
  AND a_home.state != a_work.state;

SELECT e.employee_id, e.employee_name
FROM employees e
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
JOIN orders o ON st.order_id = o.order_id
JOIN shipments s ON o.order_id = s.order_id
JOIN carriers c ON s.carrier_id = c.carrier_id
GROUP BY e.employee_id, e.employee_name
HAVING COUNT(DISTINCT c.carrier_id) = (SELECT COUNT(DISTINCT carrier_id) FROM carriers);

SELECT p.product_id, p.product_name
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE p.discontinued = 'yes'
  AND o.order_status = 'new';

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories cat ON p.category_id = cat.category_id
WHERE oi.returned = 'yes'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT cat.category_id) > 1;

SELECT "departments"."department_id", "departments"."department_name" FROM "employees" INNER JOIN "departments" ON "employees"."department_id" = "departments"."department_id" INNER JOIN "support_tickets" ON "employees"."employee_id" = "support_tickets"."assigned_employee_id" WHERE NOT EXISTS (SELECT 1 FROM "support_tickets" WHERE "employees"."employee_id" = "support_tickets"."assigned_employee_id" AND "employees"."department_id" = "departments"."department_id" AND "support_tickets"."resolved" = ? AND "support_tickets"."priority" = ?) GROUP BY "departments"."department_id", "departments"."department_name";

SELECT o.order_id
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id
HAVING SUM(CASE WHEN oi.returned = 'yes' THEN oi.unit_price * oi.quantity ELSE 0 END) >
       SUM(CASE WHEN oi.returned = 'no' THEN oi.unit_price * oi.quantity ELSE 0 END);

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN support_tickets st ON c.customer_id = st.customer_id
JOIN employees e ON st.assigned_employee_id = e.employee_id
JOIN departments d ON e.department_id = d.department_id
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT d.department_id) > 1;

SELECT c.category_id, c.category_name
FROM categories c
JOIN products p ON c.category_id = p.category_id
WHERE c.parent_category_id IS NOT NULL
GROUP BY c.category_id, c.category_name
HAVING AVG(p.unit_price) > (
    SELECT AVG(p2.unit_price)
    FROM products p2
    JOIN categories c2 ON p2.category_id = c2.category_id
    WHERE c2.category_id = c.parent_category_id
);

SELECT c.carrier_id, c.carrier_name
FROM carriers c
JOIN shipments s ON c.carrier_id = s.carrier_id
GROUP BY c.carrier_id, c.carrier_name
HAVING SUM(CASE WHEN s.shipment_status = 'delayed' THEN 1 ELSE 0 END) = 0
   AND SUM(CASE WHEN s.shipment_status = 'in_transit' THEN 1 ELSE 0 END) > 0;

SELECT DISTINCT p.product_id, p.product_name
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE NOT EXISTS (
    SELECT 1
    FROM support_tickets st
    WHERE st.customer_id = o.customer_id
      AND st.issue_type = 'account'
      AND st.resolved = 'no'
);

SELECT s.supplier_id, s.supplier_name
FROM suppliers s
WHERE NOT EXISTS (
    SELECT 1
    FROM products p
    JOIN order_items oi ON p.product_id = oi.product_id
    JOIN orders o ON oi.order_id = o.order_id
    JOIN customers c ON o.customer_id = c.customer_id
    WHERE p.supplier_id = s.supplier_id
      AND c.loyalty_tier NOT IN ('platinum', 'gold')
);

SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
WHERE NOT EXISTS (
    SELECT 1
    FROM support_tickets st
    WHERE st.assigned_employee_id = e.employee_id
)
AND EXISTS (
    SELECT 1
    FROM employees sub
    JOIN support_tickets st ON st.assigned_employee_id = sub.employee_id
    WHERE sub.manager_id = e.employee_id
);

WITH latest_tickets AS (
  SELECT customer_id, resolved
  FROM support_tickets st1
  WHERE ticket_id = (
    SELECT ticket_id
    FROM support_tickets st2
    WHERE st2.customer_id = st1.customer_id
    ORDER BY opened_at DESC
    LIMIT 1
  )
),
latest_orders AS (
  SELECT customer_id, payment_status
  FROM orders o1
  WHERE order_id = (
    SELECT order_id
    FROM orders o2
    WHERE o2.customer_id = o1.customer_id
    ORDER BY placed_at DESC
    LIMIT 1
  )
)
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN latest_tickets lt ON c.customer_id = lt.customer_id
JOIN latest_orders lo ON c.customer_id = lo.customer_id
WHERE lt.resolved = 'yes'
  AND lo.payment_status = 'unpaid';

SELECT o.order_id
FROM orders o
WHERE EXISTS (
    SELECT 1
    FROM support_tickets st
    WHERE st.order_id = o.order_id
    AND NOT EXISTS (
        SELECT 1
        FROM shipments s
        WHERE s.order_id = o.order_id
        AND s.shipped_at <= st.opened_at
    )
);

SELECT p.product_id, p.product_name
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
GROUP BY p.product_id, p.product_name
HAVING MAX(oi.unit_price) < p.unit_price;

SELECT c.category_name
FROM categories c
JOIN products p ON c.category_id = p.category_id
JOIN order_items oi ON p.product_id = oi.product_id
JOIN orders o ON oi.order_id = o.order_id
JOIN addresses a ON o.shipping_address_id = a.address_id
GROUP BY c.category_id, c.category_name
HAVING COUNT(DISTINCT a.state) = (SELECT COUNT(DISTINCT state) FROM addresses);

WITH customer_totals AS (
  SELECT 
    c.customer_id,
    c.customer_name,
    c.loyalty_tier,
    SUM(oi.quantity) AS total_quantity
  FROM customers c
  JOIN orders o ON c.customer_id = o.customer_id
  JOIN order_items oi ON o.order_id = oi.order_id
  GROUP BY c.customer_id, c.customer_name, c.loyalty_tier
),
tier_averages AS (
  SELECT 
    loyalty_tier,
    AVG(total_quantity) AS avg_quantity
  FROM customer_totals
  GROUP BY loyalty_tier
)
SELECT 
  ct.customer_id,
  ct.customer_name,
  ct.loyalty_tier
FROM customer_totals ct
JOIN tier_averages ta ON ct.loyalty_tier = ta.loyalty_tier
WHERE ct.total_quantity > ta.avg_quantity;

SELECT st.ticket_id, st.order_id, st.issue_type, st.priority
FROM support_tickets st
WHERE st.order_id IN (
    SELECT o.order_id
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    JOIN categories c ON p.category_id = c.category_id
    WHERE c.parent_category_id IS NOT NULL
);

SELECT e.employee_id, e.employee_name
FROM employees e
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
JOIN departments d ON e.department_id = d.department_id
WHERE st.resolved = 'no'
GROUP BY e.employee_id, e.employee_name, e.department_id
HAVING COUNT(st.ticket_id) > (
    SELECT AVG(unresolved_count)
    FROM (
        SELECT e2.department_id, COUNT(st2.ticket_id) AS unresolved_count
        FROM employees e2
        JOIN support_tickets st2 ON e2.employee_id = st2.assigned_employee_id
        WHERE st2.resolved = 'no'
        GROUP BY e2.employee_id
    ) AS dept_avg
    WHERE dept_avg.department_id = e.department_id
);

SELECT s.supplier_id, s.supplier_name
FROM suppliers s
WHERE s.preferred = 'yes'
AND NOT EXISTS (
    SELECT 1
    FROM products p
    JOIN order_items oi ON p.product_id = oi.product_id
    WHERE p.supplier_id = s.supplier_id
    AND oi.returned = 'yes'
);

SELECT o.order_id
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories c ON p.category_id = c.category_id
GROUP BY o.order_id
HAVING COUNT(DISTINCT c.category_id) >= 3;

SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
  SELECT 1
  FROM orders o
  JOIN shipments s ON o.order_id = s.order_id
  WHERE o.customer_id = c.customer_id
    AND s.shipment_status = 'delayed'
)
AND NOT EXISTS (
  SELECT 1
  FROM support_tickets st
  WHERE st.customer_id = c.customer_id
    AND st.resolved = 'no'
);

SELECT p.product_id, p.product_name
FROM products p
JOIN order_items oi ON p.product_id = oi.product_id
JOIN categories c ON p.category_id = c.category_id
WHERE oi.returned = 'yes'
GROUP BY p.product_id, p.product_name, p.category_id
HAVING COUNT(*) > (
    SELECT AVG(cat_return_count)
    FROM (
        SELECT p2.category_id, COUNT(*) AS cat_return_count
        FROM order_items oi2
        JOIN products p2 ON oi2.product_id = p2.product_id
        WHERE oi2.returned = 'yes'
        GROUP BY p2.category_id
    )
);

SELECT d.department_name
FROM departments d
JOIN employees e ON d.department_id = e.department_id
JOIN support_tickets t ON e.employee_id = t.assigned_employee_id
WHERE e.active = 'yes'
GROUP BY d.department_id, d.department_name
HAVING COUNT(DISTINCT t.priority) = (SELECT COUNT(DISTINCT priority) FROM support_tickets);

WITH customer_first_ticket AS (
    SELECT customer_id, MIN(opened_at) AS first_ticket_date
    FROM support_tickets
    GROUP BY customer_id
),
customer_first_order AS (
    SELECT customer_id, MIN(placed_at) AS first_order_date
    FROM orders
    GROUP BY customer_id
)
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN customer_first_ticket t ON c.customer_id = t.customer_id
JOIN customer_first_order o ON c.customer_id = o.customer_id
WHERE t.first_ticket_date < o.first_order_date;

SELECT DISTINCT c.carrier_name
FROM carriers c
JOIN shipments s ON c.carrier_id = s.carrier_id
JOIN orders o ON s.order_id = o.order_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE p.discontinued = 'yes'
  AND s.shipment_status != 'delayed'
  AND NOT EXISTS (
    SELECT 1
    FROM shipments s2
    WHERE s2.order_id = o.order_id
      AND s2.shipment_status = 'delayed'
  );

SELECT c.category_id, c.category_name
FROM categories c
JOIN products p ON c.category_id = p.category_id
JOIN order_items oi ON p.product_id = oi.product_id
GROUP BY c.category_id, c.category_name
HAVING SUM(oi.quantity * oi.unit_price) > (
    SELECT SUM(oi2.quantity * oi2.unit_price)
    FROM categories c2
    JOIN products p2 ON c2.category_id = p2.category_id
    JOIN order_items oi2 ON p2.product_id = oi2.product_id
    WHERE c2.parent_category_id = c.parent_category_id
    AND c2.category_id != c.category_id
);

SELECT DISTINCT e.employee_id, e.employee_name
FROM employees e
JOIN support_tickets st ON e.employee_id = st.assigned_employee_id
JOIN customers c ON st.customer_id = c.customer_id
JOIN orders o ON c.customer_id = o.customer_id
GROUP BY e.employee_id, e.employee_name
HAVING COUNT(o.order_id) > 5;

SELECT o.order_id
FROM orders o
JOIN shipments s ON o.order_id = s.order_id
JOIN carriers c ON s.carrier_id = c.carrier_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE c.service_level = 'express'
GROUP BY o.order_id
HAVING SUM(CASE WHEN oi.returned = 'yes' THEN 1 ELSE 0 END) = 0;

SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories cat ON p.category_id = cat.category_id
WHERE cat.category_name IN ('Electronics', 'Home')
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(DISTINCT cat.category_name) = 2;

SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM addresses a
    WHERE a.customer_id = c.customer_id
      AND a.address_type = 'billing'
)
AND EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'delivered'
      AND o.payment_status = 'paid'
);

