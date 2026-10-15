select event_id from {{ ref('stg_payment_events') }}
where event_id is null or transaction_id is null
   or event_at is null or ingested_at is null
   or status not in ('authorized', 'settled', 'refunded', 'chargeback') or status is null
   or currency <> 'MXN' or currency is null
   or amount_cents <= 0 or amount_cents > 1000000000000 or amount_cents is null
