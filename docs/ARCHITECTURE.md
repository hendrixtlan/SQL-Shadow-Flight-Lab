# Architecture decision record — Medallion X 0.1

## Decision 001 — Split data lake landing and SQL transformation

**Selected:** OneLake Bronze Lakehouse (Delta) → read-only Lakehouse SQL analytics endpoint → Fabric Warehouse Silver/Gold materializations with dbt-fabric → approved physical Gold tables → Power BI Direct Lake.

**Why:** Standard, supported SQL-first transformation and serving model, with good testing and manifest lineage. The Warehouse can query Lakehouse tables in the same workspace with three-part names. The Lakehouse SQL endpoint cannot execute dbt writes.

**Alternative:** dbt-fabricspark can write Delta Silver/Gold into the Lakehouse through Spark/Livy. Choose it for Spark-native logic or a lakehouse-only footprint. Fabric Materialized Lake Views could refresh certain derived aggregates automatically, but these have separate behavior and limitations for time travel and supported SQL constructs.

## Decision 002 — A medallion tier is not a dbt model tier

Bronze/Silver/Gold describe **data maturity and trust**. `staging`/`intermediate`/`marts` describe **dbt modularization**. Mapping them one-to-one is sometimes convenient but is not an invariant. In Medallion X: Bronze=source Delta, Staging=Warehouse views, Silver=valid deduplicated events, Gold=current state and serving mart.

## Decision 003 — Fail closed on schema drift

Accepted schema v1 has `amount_cents`; v2 has `gross_amount_cents`. Version 3 and malformed/negative values are quarantined and cause release failure. The local reference engine collects quarantine reasons; the Fabric dbt project uses singular data tests to block invalid source records. **The dbt models do not themselves quarantine rows into a physical audit table yet.** That is a separate production milestone.

## Decision 004 — Semantically compare two versions, not just successful runs

Tests like `not_null`, `unique`, and SQL correctness cannot determine whether the financial KPI has changed unexpectedly. We compare named business metrics under an explicit policy. Example: including `authorized` in `settled` produces correct SQL and consistent row state, but violates expected financial semantics. The local gate identifies it.

## Decision 005 — Replay uses event time, not ingest time

An old settlement arriving after a refund should not revive the transaction as settled. Later business-time corrections *should* update the state. This is only a basic CDC ordering model, not an exhaustive ledger for multiple independent processors. A serious payments implementation must handle tombstones, version/sequence numbers, chargeback lifecycle, financial reconciliation, currency conversion and immutable postings.

## Decision 006 — No implicit promotion to semantic models

A local pointer is an engineering simulation. SQL views may force DirectQuery fallback for some Direct Lake models; therefore a Fabric prod cutover needs an explicitly designed process using physical Delta-backed tables, semantic-model validation, permission checks and rollback. A clean candidate must not auto-promote without approval.

## Design risks and work needed

1. **Source pinning**: A production replay must bind baseline and candidate to identical Delta table versions / stable materialized snapshots. The local SHA-256 of source data is not a Fabric Delta transaction-version guarantee.
2. **Cross-runtime parity**: Local Python replay must be checked against actual dbt/T-SQL output at least on a golden test dataset. The included unit tests validate the local oracle only.
3. **Deployment isolation**: Separate prod / candidate Fabric Warehouses and roles; optional two-workspace architecture needs shortcuts for cross-workspace sources.
4. **Storage and compute overhead**: Parallel execution has a cost. Evaluate impact-based selective builds and bounded replay windows.
5. **Lineage accuracy**: dbt manifest is transformation lineage; Purview/Fabric lineage and Power BI metadata must also be integrated. The fallback graph explicitly identifies itself as manually declared.
6. **Drift budgets**: Some metrics legitimately change when business rules evolve; the gate must support risk-based approved tolerances and explicit change requests in a later version.
7. **Security**: This example uses synthetic customer IDs only. Production customer identifiers require minimization, PII controls, tenant separation, credential management, audit logging and least privilege.
