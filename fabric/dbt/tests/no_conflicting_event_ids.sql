-- Allows exact repeats, rejects the same event_id carrying inconsistent data.
-- A normalized comparison avoids treating physical ingestion duplicates as incidents.
select event_id
from {{ ref('stg_payment_events') }}
group by event_id
having count(distinct concat(
      coalesce(transaction_id, '<null>'), '|',
      coalesce(convert(varchar(33), event_at, 126), '<null>'), '|',
      coalesce(convert(varchar(33), ingested_at, 126), '<null>'), '|',
      coalesce(status, '<null>'), '|',
      coalesce(currency, '<null>'), '|',
      coalesce(convert(varchar(30), amount_cents), '<null>')
    )) > 1
