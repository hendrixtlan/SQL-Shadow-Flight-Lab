# Medallion X v0.2 — SQL Shadow Flight Lab

## Core research claim, narrowly stated

The project detects **silent semantic regressions**: both versions of SQL execute successfully and can generate exactly the same physical current-state records, while a Gold business metric changes. All local acceptance tests use executable SQL and test results are machine-readable. This repository does **not** claim to be the first such system or to have run successfully on a tenant we don't control.

## Experimental design

1. Materialize one fixed synthetic payment CDC input (`frozen_bronze.csv`), record its SHA-256 and a duplicate-sensitive canonical source ID.
2. Independently execute `inputs/baseline.sql` and `inputs/candidate.sql` in separate physical SQLite databases. Each lane creates its own `valid_events`, `current_state` and `gold_metrics` tables. The source contract normalizer is shared, intentionally limiting the independence of ingestion validation.
3. Independently calculate reference metrics in Python. Compare stable SQL to the oracle; automatically fail closed on mismatches. The intentionally broken candidate is supposed to diverge.
4. Compare three financial/state metrics under `config/release_policy.json`. Any unapproved deviation blocks release. The financial amounts are **MXN cents**, not dollars or Mexican pesos.
5. Preserve replayable forensic artifacts and hash them into an **unsigned** ledger; refuse local v2 simulated promotion on corrupt bundles. Local promotion **never** changes Fabric or Power BI.
6. Run seeded randomized metamorphic tests over input permutation and exact duplicate deliveries: invariance is expected in final business state and aggregates, **not** in raw source row multiplicity or source hash.

## Research questions and expected observations

| Experiment | Invariant / counterfactual | Expected outcome |
|---|---|---|
| Clean | Candidate and baseline use equivalent SQL | Eligible, zero drift |
| SQL Gold semantic mutation | Candidate counts `authorized` as `settled` | **BLOCKED**: +16,000 cents, +2 settled transactions, **zero state drift** |
| Schema poison | Unapproved v3, negative amount, conflicting event-id | BLOCKED by zero-quarantine policy |
| Late refund | Latest event-time governs, even if ingestion is delayed | Eligible; current settlement exposure 22,000 cents |
| Metamorphic runs | Permuting raw event delivery and injecting exact duplicates | Stable current state & metrics across 100 seeded trials |
| Integrity attack | Modify an input, executable SQL, SQLite database or release evidence | `verify` rejects affected bundle; local v2 promotion rejects it |

## Local reproduction

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
medallion-x flight-test --scenario clean --out-dir runs/v2-clean
medallion-x flight-test --scenario regression --expect-block --out-dir runs/v2-regression
medallion-x flight-test --scenario poisoned --expect-block --out-dir runs/v2-poisoned
medallion-x flight-test --scenario late --out-dir runs/v2-late
medallion-x stress-test --rounds 100 --seed 42 --out runs/metamorphic.json
medallion-x verify --run-dir runs/v2-regression
```

`--expect-block` causes the command to fail when a deliberately wrong candidate unexpectedly passes. The local `promote` command only advances a pointer after an eligible report and an explicit reviewer string; this is **not a trusted approval identity**.

## Fabric deployment design — prepared but unvalidated

The Lakehouse SQL analytics endpoint is **read-only** and cannot receive dbt transformations through `dbt-fabric`. Instead use a Fabric Warehouse for writes. Microsoft documents Fabric Warehouse `CREATE TABLE AS SELECT` from Lakehouse SQL endpoint sources using three-part names. Its Warehouse zero-copy clone feature **does not work on the Lakehouse SQL endpoint**. This project therefore creates a **physical frozen copy** of the source in a dedicated freeze Warehouse and uses it for both dbt executions. This creates storage and compute cost.

1. Create same-workspace `bronze_lh`, `freeze_wh`, `baseline_wh`, `candidate_wh` Fabric items. Load `frozen_bronze.csv` into Bronze as a Delta table, using the included notebook.
2. Generate statements with `python fabric/experiments/plan.py --run-id lab01`. Execute generated `01_create_schema.sql`, then `02_freeze_snapshot.sql` on `freeze_wh`. Ensure the schema is mutation-restricted after CTAS, record row count and a trustworthy job ID.
3. Prepare **two Git worktrees from different commits**: production baseline and candidate change. Configure `fabric/dbt/profiles.yml.example` to point `dev` to baseline and `ci` to candidate warehouses. Do not put secrets into the repository.
4. Execute the `dbt build` commands in the generated `execution_plan.json` from each respective worktree, pinning `source_database`, `source_schema`, `source_table` to the **same** frozen Warehouse table. For deliberate fault injection, copy `fabric/experiments/mutations/mart_daily_payments.REGRESSION.sql` into the candidate checkout's `models/gold/mart_daily_payments.sql`.
5. Capture the commit SHA, actual Fabric job and query IDs, `dbt target/manifest.json` and `target/run_results.json`; review dbt tests and query-generated schemas. Then execute generated `03_compare_outputs.sql` to compare both Gold outputs and changed transaction count.
6. At this stage, review evidence manually and **do not run production publication**. Full parity automation, semantic-model dependency impact, tenant CI authentication and deployment/rollback are deliberately gated milestones.

**Critical caveats:** A CTAS freezes the selected rows at execution time, but does not certify cross-source transactional consistency. The Fabric SQL/dbt components are unvalidated in a live capacity. The local SQLite SQL is not automatically identical to T-SQL generated by dbt. Integrity checks do not provide cryptographic signer authenticity. Warehouse zero-copy clone retention and Delta `VACUUM` retention are separate concerns. If future work uses Delta time travel rather than CTAS, pin versions and retain all underlying data files and logs.

## Product references

- https://docs.getdbt.com/docs/local/connect-data-platform/fabric-setup
- https://learn.microsoft.com/en-us/fabric/data-warehouse/ingest-data-tsql
- https://learn.microsoft.com/en-us/fabric/data-warehouse/clone-table
- https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-sql-analytics-endpoint
- https://learn.microsoft.com/en-us/fabric/data-engineering/delta-lake-time-travel
