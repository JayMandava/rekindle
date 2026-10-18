-- ReKindle segmentation. One query, two engines:
--   * BigQuery in production (Standard SQL, DATE columns, @named params)
--   * SQLite in local mode (ISO-text dates, same query via a 2-macro dialect shim)
-- Macros: {days_between(a, b)} = whole days from b to a; {orders}/{customers} = table references.
-- Params: @as_of DATE, @dormant_days INT64, @lost_days INT64
WITH order_agg AS (
  SELECT customer_id,
         MAX(order_date) AS last_order_date,
         COUNT(*)        AS frequency,
         SUM(amount)     AS monetary
  FROM {orders}
  GROUP BY customer_id
),
last_product AS (
  SELECT o.customer_id, MIN(o.product) AS last_product
  FROM {orders} o
  JOIN order_agg a ON a.customer_id = o.customer_id AND a.last_order_date = o.order_date
  GROUP BY o.customer_id
),
base AS (
  SELECT c.customer_id, c.name, c.phone, c.email, c.language,
         c.consent_whatsapp, c.consent_email,
         c.anchor_name, c.anchor_date,
         a.last_order_date, a.frequency, a.monetary, p.last_product,
         {days_between(@as_of, a.last_order_date)} AS recency_days
  FROM {customers} c
  JOIN order_agg a ON a.customer_id = c.customer_id
  JOIN last_product p ON p.customer_id = c.customer_id
),
scored AS (
  SELECT base.*,
         NTILE(5) OVER (ORDER BY recency_days DESC, customer_id) AS r_score,
         CASE WHEN frequency >= 5 THEN 5 WHEN frequency = 4 THEN 4 WHEN frequency = 3 THEN 3
              WHEN frequency = 2 THEN 2 ELSE 1 END                AS f_score,
         NTILE(5) OVER (ORDER BY monetary, customer_id)          AS m_score
  FROM base
)
SELECT scored.*,
       CASE
         WHEN recency_days < @dormant_days THEN 'active'
         WHEN recency_days > @lost_days THEN 'lost'
         WHEN f_score >= 4 AND m_score >= 4 THEN 'champion_dormant'
         WHEN frequency = 1 THEN 'one_time_lapsed'
         ELSE 'at_risk'
       END AS segment
FROM scored
