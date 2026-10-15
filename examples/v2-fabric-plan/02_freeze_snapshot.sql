-- Run in freeze_wh AFTER executing 01_create_schema.sql.
-- Materialize ONE frozen source; dbt baselines and candidates must read this exact table.
-- Record SQL statement execution id, UTC time and COUNT_BIG(*) manually.
-- A schema-only Git deployment does not freeze or move any lakehouse data.
CREATE TABLE [flight_lab01].[raw_payment_events] AS
SELECT event_id, transaction_id, event_at, ingested_at, status,
       amount_cents, gross_amount_cents, currency,
       payload_schema_version, customer_id
FROM [bronze_lh].[dbo].[raw_payment_events];

SELECT COUNT_BIG(*) AS frozen_input_rows FROM [flight_lab01].[raw_payment_events];
