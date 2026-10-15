"""Generate (never execute) a safe, run-scoped Fabric freeze and dbt flight plan.

No fabricated remote provenance: a human must execute SQL/dbt and capture result sets.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

NAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
RUN = re.compile(r'^[a-z][a-z0-9_]{1,30}$')


def name(value: str) -> str:
    if not NAME.fullmatch(value):
        raise ValueError(f'unsafe SQL identifier: {value!r}')
    return f'[{value}]'


def generate(*, run_id: str, bronze_lakehouse: str, freeze_warehouse: str,
             baseline_warehouse: str, candidate_warehouse: str,
             baseline_schema: str, candidate_schema: str, out_dir: Path) -> dict:
    if not RUN.fullmatch(run_id):
        raise ValueError('run-id must be lowercase [a-z][a-z0-9_]{1,30}')
    b, f, base, cand = map(name, (bronze_lakehouse, freeze_warehouse, baseline_warehouse, candidate_warehouse))
    for value in (baseline_schema, candidate_schema):
        name(value)
    if len({bronze_lakehouse.lower(), freeze_warehouse.lower(), baseline_warehouse.lower(), candidate_warehouse.lower()}) < 4:
        raise ValueError('each Lakehouse/Warehouse must have a distinct name')
    freeze_schema = f'flight_{run_id}'
    schema_name = name(freeze_schema)
    out_dir.mkdir(parents=True, exist_ok=True)
    schema_sql = f'-- Run in {freeze_warehouse}; fail if run already exists.\nCREATE SCHEMA {schema_name};\n'
    freeze_sql = f'''-- Run in {freeze_warehouse} AFTER executing 01_create_schema.sql.
-- Materialize ONE frozen source; dbt baselines and candidates must read this exact table.
-- Record SQL statement execution id, UTC time and COUNT_BIG(*) manually.
-- A schema-only Git deployment does not freeze or move any lakehouse data.
CREATE TABLE {schema_name}.[raw_payment_events] AS
SELECT event_id, transaction_id, event_at, ingested_at, status,
       amount_cents, gross_amount_cents, currency,
       payload_schema_version, customer_id
FROM {b}.[dbo].[raw_payment_events];

SELECT COUNT_BIG(*) AS frozen_input_rows FROM {schema_name}.[raw_payment_events];
'''
    bs, cs = name(baseline_schema + '_gold'), name(candidate_schema + '_gold')
    compare_sql = f'''-- Run in the SAME Fabric workspace where both warehouses are readable.
-- dbt default schema concatenation is assumed: <target.schema>_gold.
-- Save result sets with run_id, source identity, commit SHAs and job identifiers.
WITH b AS (
    SELECT COALESCE(SUM(current_settled_amount_cents),0) AS settled,
           COALESCE(SUM(currently_settled_transactions),0) AS settled_n,
           COALESCE(SUM(authorized_exposure_cents),0) AS authorized
    FROM {base}.{bs}.[mart_daily_payments]
), c AS (
    SELECT COALESCE(SUM(current_settled_amount_cents),0) AS settled,
           COALESCE(SUM(currently_settled_transactions),0) AS settled_n,
           COALESCE(SUM(authorized_exposure_cents),0) AS authorized
    FROM {cand}.{cs}.[mart_daily_payments]
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
FROM {base}.{bs}.[fct_payment_current] AS b
FULL OUTER JOIN {cand}.{cs}.[fct_payment_current] AS c
    ON b.transaction_id = c.transaction_id
WHERE b.transaction_id IS NULL OR c.transaction_id IS NULL
   OR b.status <> c.status OR b.amount_cents <> c.amount_cents
   OR b.event_id <> c.event_id;
'''
    files = {
        '01_create_schema.sql': schema_sql,
        '02_freeze_snapshot.sql': freeze_sql,
        '03_compare_outputs.sql': compare_sql,
    }
    for filename, content in files.items():
        (out_dir / filename).write_text(content, encoding='utf-8')
    variables = {'source_database': freeze_warehouse, 'source_schema': freeze_schema, 'source_table': 'raw_payment_events'}
    plan = {
        'schema': 'medallion-x.fabric-experiment-plan.v1',
        'mode': 'PLAN_ONLY_NOT_EXECUTED',
        'run_id': run_id,
        'workspace_constraint': 'The Bronze Lakehouse and all three Warehouses must be accessible within the same Fabric workspace.',
        'source_relation': f'{freeze_warehouse}.{freeze_schema}.raw_payment_events',
        'baseline_warehouse': baseline_warehouse,
        'candidate_warehouse': candidate_warehouse,
        'expected_gold_relations': [f'{baseline_warehouse}.{baseline_schema}_gold.mart_daily_payments', f'{candidate_warehouse}.{candidate_schema}_gold.mart_daily_payments'],
        'dbt_vars': variables,
        'dbt_commands': {
            'baseline': f"dbt build --target dev --vars '{json.dumps(variables, separators=(',', ':'))}'",
            'candidate': f"dbt build --target ci --vars '{json.dumps(variables, separators=(',', ':'))}'",
        },
        'assumptions': [
            'Execute baseline and candidate from separate Git worktrees/commits.',
            'Profiles dev/ci Warehouse environment variables must match the chosen names.',
            'Run-scoped freeze table must be immutable after CTAS; restrict mutation permissions.',
            'Manifest/job evidence and actual T-SQL results must be collected before promotion.',
            'Reference SQL not yet run against a live Fabric tenant.',
        ],
        'fabric_executed': False,
        'dbt_executed': False,
        'production_promoted': False,
    }
    (out_dir / 'execution_plan.json').write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--bronze-lakehouse', default='bronze_lh')
    parser.add_argument('--freeze-warehouse', default='freeze_wh')
    parser.add_argument('--baseline-warehouse', default='baseline_wh')
    parser.add_argument('--candidate-warehouse', default='candidate_wh')
    parser.add_argument('--baseline-schema', default='analytics_dev')
    parser.add_argument('--candidate-schema', default='analytics_ci')
    parser.add_argument('--out-dir', default='runs/fabric-plan')
    args = parser.parse_args()
    try:
        result = generate(run_id=args.run_id, bronze_lakehouse=args.bronze_lakehouse,
                          freeze_warehouse=args.freeze_warehouse, baseline_warehouse=args.baseline_warehouse,
                          candidate_warehouse=args.candidate_warehouse,
                          baseline_schema=args.baseline_schema, candidate_schema=args.candidate_schema,
                          out_dir=Path(args.out_dir))
    except ValueError as err:
        parser.error(str(err))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
