/*
Day 4 Coding Assignment - ShopEY Database


Requirements:
1. customer_name: concatenated first_name + ' ' + last_name
2. total_orders: count of distinct orders placed by each customer
3. total_spent: sum of (quantity × unit_price) across all order lines for each customer
4. customer_rank: rank by total_spent descending using RANK() window function
5. Include ONLY customers who have placed at least 1 order
6. Order the result by customer_rank ascending
*/

SELECT
    customer_name,
    total_orders,
    total_spent,
    RANK() OVER (ORDER BY total_spent DESC) AS customer_rank
FROM (
    SELECT
        c.first_name || ' ' || c.last_name AS customer_name,
        COUNT(DISTINCT o.order_id) AS total_orders,
        SUM(ol.quantity * ol.unit_price) AS total_spent
    FROM shopey.customers c
    JOIN shopey.orders o
        ON c.customer_id = o.customer_id
    JOIN shopey.order_lines ol
        ON o.order_id = ol.order_id
    GROUP BY
        c.customer_id,
        c.first_name,
        c.last_name
) customer_summary
ORDER BY customer_rank ASC;
