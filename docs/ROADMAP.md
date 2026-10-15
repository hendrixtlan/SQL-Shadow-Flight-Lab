# Research roadmap

## v0.1 — Completed in this repository

Local deterministic CDC simulator, governed contract v1/v2 normalization, duplicate/conflict handling, event-time replay, release metric comparison, declared or manifest-driven lineage, standalone HTML/JSON evidence, blocked-release tests, approval-only local pointer, Fabric Bronze notebook and Warehouse dbt SQL skeleton.

## v0.2 — Completed: local SQL shadow execution and Fabric experiment plan

Two truly separate SQLite physical SQL lanes; shared immutable run input; per-lane SQL and table evidence; stable SQL vs Python oracle verification; deterministic metamorphic testing; controlled regression injection; unsigned SHA-256 ledger; verified local gate-aware pointer; run-scoped Fabric CTAS freeze planner and optional real dbt source relation pinning. 21 automated local tests. **No Fabric tenant testing has occurred.**

## v0.3 — Real Fabric execution and parity proof

Implement Fabric metadata bootstrap, upload generator into OneLake Files, run Bronze append notebook, test Warehouse dbt adapter in an actual workspace, add T-SQL result export and compare with reference oracle. Add source Delta version pinning and data egress minimization. **Exit criterion:** live dbt transformations generate identical current-state metrics on a golden dataset, verified in CI or an authenticated deployment run.

## v0.4 — Release-aware dbt build

Generate two isolated candidate/baseline Warehouses from a stable snapshot; run `dbt build` with artifact collection, compute metrics from each actual Gold table; capture pass/fail evidence and identify modified model descendants. Add change-request metadata and manual Fabric deployment approval.

## v0.5 — Lakehouse/Spark research branch

Implement `dbt-fabricspark` and alternative native Materialized Lake Views, separate engines clearly, measure Delta optimization costs, optimize/caching behavior, refresh failure handling, and semantics of replay of late arrivals. Test rather than assume parity.

## v0.6 — Knowledge graph and governed diagnostic assistant

Import dbt lineage + Fabric/Purview item metadata + Power BI semantic model/measure dependencies into a property graph. Use a read-only LangGraph assistant to explain which metric changed, which deployment or upstream contract caused it, and suggest a patch with cited evidence. A deterministic policy evaluator remains the authorization boundary. No LLM writes to production and no agent-issued approval.

## v1.0 — Production-grade controls

Complete transaction-level ledger handling, schema registry, Azure Key Vault / managed identity, tenant-isolated metadata, idempotent ingestion, OpenTelemetry telemetry, policy-controlled CI/CD, Fabric capacity/cost benchmarks, semantic deployment, full audit trace, replay windows, rollback and operator runbooks.
