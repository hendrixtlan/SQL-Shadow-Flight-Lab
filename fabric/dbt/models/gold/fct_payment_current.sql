-- Current transaction state, not a settled-cash ledger.
-- Latest business event time wins, irrespective of arrival order.
with ranked as (
    select *,
           row_number() over (
               partition by transaction_id
               order by event_at desc, ingested_at desc, event_id desc
           ) as state_rank
    from {{ ref('silver_payment_events') }}
)
select transaction_id, event_id, event_at, ingested_at, status, currency, amount_cents
from ranked
where state_rank = 1
