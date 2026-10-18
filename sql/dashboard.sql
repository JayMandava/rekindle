-- Looker Studio data source: connect to rekindle.v_campaign_performance.
CREATE OR REPLACE VIEW rekindle.v_campaign_performance AS
WITH sent AS (
  SELECT draft_id, customer_id, segment, channel, route, risk_tier, confidence, MIN(ts) AS sent_ts
  FROM rekindle.events WHERE kind = 'sent' GROUP BY 1,2,3,4,5,6,7
),
orders_after AS (
  SELECT s.draft_id, SUM(e.amount) AS recovered
  FROM sent s
  JOIN rekindle.events e
    ON e.customer_id = s.customer_id AND e.kind = 'order'
   AND e.ts BETWEEN s.sent_ts AND TIMESTAMP_ADD(s.sent_ts, INTERVAL 30 DAY)
  GROUP BY 1
)
SELECT DATE(s.sent_ts) AS day, s.segment, s.channel, s.route, s.risk_tier, s.confidence,
       s.draft_id, COALESCE(o.recovered, 0) AS recovered_revenue
FROM sent s LEFT JOIN orders_after o USING (draft_id);
