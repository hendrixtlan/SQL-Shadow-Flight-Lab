-- Run in the SAME Fabric workspace where both warehouses are readable.
-- dbt default schema concatenation is assumed: <target.schema>_gold.
-- Save result sets with run_id, source identity, commit SHAs and job identifiers.
WITH b AS (
    SELECT COALESCE(SUM(current_settled_amount_cents),0) AS settled,
           COALESCE(SUM(currently_settled_transactions),0) AS settled_n,
           COALESCE(SUM(authorized_exposure_cents),0) AS authorized
    FROM [baseline_wh].[analytics_dev_gold].[mart_daily_payments]
), c AS (
    SELECT COALESCE(SUM(current_settled_amount_cents),0) AS settled,
           COALESCE(SUM(currently_settled_transactions),0) AS settled_n,
           COALESCE(SUM(authorized_exposure_cents),0) AS authorized
    FROM [candidate_wh].[analytics_ci_gold].[mart_daily_payments]
)
SELECT b.settled AS baseline_settled_cents, c.settled AS candidate_settled_cents,
       c.settled - b.settled AS settled_delta_cents,
       b.settled_n AS baseline_settled_transactions,
       c.settled_n AS candidate_settled_transactions,
       c.settled_n - b.settled_n AS settled_transactions_delta,
       b.authorized AS baseline_authorized_cents,
       c.authorized AS candidate_authorized_cents,
       c.authorized - b.authorized AS authorized_delta_cents
FROM b CROSS JOIN c;

-- Row-level state difference, not only aggregate parity.
SELECT COUNT_BIG(*) AS changed_transaction_count
FROM [baseline_wh].[analytics_dev_gold].[fct_payment_current] AS b
FULL OUTER JOIN [candidate_wh].[analytics_ci_gold].[fct_payment_current] AS c
    ON b.transaction_id = c.transaction_id
WHERE b.transaction_id IS NULL OR c.transaction_id IS NULL
   OR b.status <> c.status OR b.amount_cents <> c.amount_cents
   OR b.event_id <> c.event_id;
