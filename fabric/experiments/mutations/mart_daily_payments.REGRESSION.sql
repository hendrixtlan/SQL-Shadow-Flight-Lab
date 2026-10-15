-- INTENTIONALLY BUGGY Fabric/dbt Gold model for candidate-worktree experiments.
-- Copy ONLY into the candidate Git worktree as models/gold/mart_daily_payments.sql.
-- Baseline checkout MUST retain the original. Release policy should block it.
select
    cast(event_at as date) as latest_event_date,
    currency,
    count_big(*) as current_transactions,
    sum(case when status in ('settled', 'authorized') then amount_cents
             else cast(0 as bigint) end) as current_settled_amount_cents,
    sum(case when status in ('settled', 'authorized') then cast(1 as bigint)
             else cast(0 as bigint) end) as currently_settled_transactions,
    sum(case when status = 'authorized' then amount_cents
             else cast(0 as bigint) end) as authorized_exposure_cents
from {{ ref('fct_payment_current') }}
group by cast(event_at as date), currency
