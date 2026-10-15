-- The source is a Fabric Lakehouse SQL analytics endpoint; reads are permitted.
-- This model MATERIALIZES in a Fabric Warehouse, not in the read-only endpoint.
-- Keep original raw values so invalid events remain inspectable.
with source_events as (
    select * from {{ source('bronze', 'raw_payment_events') }}
)
select
    cast(event_id as varchar(100)) as event_id,
    cast(transaction_id as varchar(100)) as transaction_id,
    try_cast(event_at as datetime2(6)) as event_at,
    try_cast(ingested_at as datetime2(6)) as ingested_at,
    cast(status as varchar(40)) as status,
    cast(currency as varchar(3)) as currency,
    cast(payload_schema_version as varchar(20)) as payload_schema_version,
    case
        when payload_schema_version = '1' then try_cast(amount_cents as bigint)
        when payload_schema_version = '2' then try_cast(gross_amount_cents as bigint)
        else null
    end as amount_cents,
    case when payload_schema_version in ('1', '2') then 1 else 0 end as approved_contract
from source_events
