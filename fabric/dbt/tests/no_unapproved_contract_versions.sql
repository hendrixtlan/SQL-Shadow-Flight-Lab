-- Returns invalid rows => dbt test fails. A release MUST fail closed.
select event_id from {{ ref('stg_payment_events') }}
where approved_contract <> 1 or approved_contract is null
