-- INTENTIONALLY FAULTY. Tests should BLOCK this candidate on the same input.
CREATE TABLE current_state AS
WITH ranked AS (
    SELECT event_id, transaction_id, event_at, ingested_at, status,
           amount_cents, currency,
           ROW_NUMBER() OVER (
               PARTITION BY transaction_id
               ORDER BY event_at DESC, ingested_at DESC, event_id DESC
           ) AS rn
    FROM valid_events
)
SELECT event_id, transaction_id, event_at, ingested_at, status,
       amount_cents, currency
FROM ranked WHERE rn = 1;

CREATE TABLE gold_metrics AS
SELECT
  COALESCE(SUM(CASE WHEN status IN ('settled', 'authorized')
                    THEN amount_cents ELSE 0 END), 0)
    AS current_settled_amount_cents,
  COALESCE(SUM(CASE WHEN status IN ('settled', 'authorized') THEN 1 ELSE 0 END), 0)
    AS currently_settled_transactions,
  COALESCE(SUM(CASE WHEN status = 'authorized' THEN amount_cents ELSE 0 END), 0)
    AS authorized_exposure_cents
FROM current_state;
