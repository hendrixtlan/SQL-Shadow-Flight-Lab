-- Validates then deduplicates EVENT identity. The distinct conflicting payload
-- case is guarded by the singular dbt test tests/no_conflicting_event_ids.sql.
with valid_events as (
    select * from {{ ref('stg_payment_events') }}
    where approved_contract = 1
      and event_id is not null
      and transaction_id is not null
      and event_at is not null
      and ingested_at is not null
      and status in ('authorized', 'settled', 'refunded', 'chargeback')
      and currency = 'MXN'
      and amount_cents > 0 and amount_cents <= 1000000000000
),
ranked as (
    select *,
           row_number() over (
               partition by event_id
               order by ingested_at desc, event_at desc, transaction_id desc
           ) as event_rank
    from valid_events
)
select event_id, transaction_id, event_at, ingested_at, status, currency, amount_cents
from ranked
where event_rank = 1
