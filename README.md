# MEDALLION X
### A replayable, contract-aware, self-defending Fabric + dbt data platform

**Research question:** Can an analytics platform block financially dangerous changes before they reach Power BI, even when SQL execution and row-level state checks succeed?

Medallion X demonstrates an engineering answer through a **two-lane data transformation release gate**: a current baseline and a proposed candidate process an identical immutable event snapshot. Independent controls evaluate data contracts, deterministic event-state reconstruction, aggregate metric parity, downstream dbt lineage and human approval.

It is an experimental architecture, not a claim that it is the world's first. The novelty is in the combination and in measuring observable behavior, not in inventing a new medallion layer.

## v0.2 — What's new

**Real SQL execution, not just an in-memory Python oracle.** The baseline and candidate run separate versioned SQL scripts in **two physical, isolated local SQLite databases**, from the exact same frozen synthetic CDC input. A policy-as-code flight gate compares both Gold metric results and canonical per-transaction state. A Python reference oracle independently checks the stable SQL behavior. This proves the **local** SQL flight gate; it does **not** prove compatibility with Fabric T-SQL or `dbt-fabric`.

**Forensic evidence bundles.** Every `flight-test` writes the frozen raw input, baseline/candidate `.sqlite` databases, copies of both executable SQL files, policy + lineage configuration, JSON/HTML flight reports and an **unsigned SHA-256 integrity ledger**. Run `verify` before local simulated promotion. Tampered evidence blocks the v2 promotion pointer; the ledger is **not a digital signature** and is not authentication.

**Metamorphic experiments.** Seeded permutations and exact duplicate-delivery mutations run against physical SQL, checking invariance of transaction state and financial metrics. An optional Fabric deployment-plan generator creates CTAS freeze scripts for a dedicated Warehouse, dbt `--vars` pinning and cross-Warehouse read-only comparison queries. Those scripts are **not remotely executed or verified** here.

```bash
python -m pip install -e .
medallion-x flight-test --scenario clean --out-dir runs/v2-clean
medallion-x flight-test --scenario regression --expect-block --out-dir runs/v2-regression
medallion-x flight-test --scenario poisoned --expect-block --out-dir runs/v2-poisoned
medallion-x flight-test --scenario late --out-dir runs/v2-late
medallion-x verify --run-dir runs/v2-regression
medallion-x stress-test --rounds 100 --seed 42 --out runs/metamorphic.json
python fabric/experiments/plan.py --run-id lab01 --out-dir runs/fabric-plan-lab01
```

Read [V2 Flight Experiments](docs/V2_FLIGHT_EXPERIMENTS.md) for research design, exact boundaries and Fabric execution instructions.

## What runs today?

| Component | State | Dependencies |
|---|---|---|
| Synthetic CDC payments feed with v1 / v2 schemas and failures | Runnable locally | Python standard library |
| Contract validation, quarantine and exact-duplicate detection | Runnable locally | Python standard library |
| Replay with late events and latest-event-wins state | Runnable locally | Python standard library |
| Baseline vs candidate financial regression detection | Runnable locally | Python standard library |
| Lineage blast radius (dbt manifest or explicit fallback DAG) | Runnable locally | Python standard library |
| JSON evidence + standalone HTML release report | Runnable locally | Python standard library |
| Human-reviewed **local simulation** release pointer | Runnable locally | Python standard library |
| GitHub Actions acceptance/regression tests | Source included, locally tested with unittest | GitHub Actions when published |
| Fabric Bronze Delta Spark notebook | Provided, **not live validated** | Fabric Lakehouse |
| SQL-first Silver/Gold dbt project | Provided, **not live validated** | Fabric Warehouse + dbt-fabric |
| Two isolated SQL execution lanes and physical Gold outputs | Runnable locally | Python SQLite / standard library |
| SQL mutation + reproducible contract/metric parity and SQL artifacts | Runnable locally | Python SQLite / standard library |
| Metamorphic 100-run SQL test suite | Runnable locally | Python standard library |
| SHA-256 local evidence verification and tamper-aware local promotion | Runnable locally | Python standard library |
| Fabric CTAS freeze plan + two-Warehouse SQL comparison | Generated, **not live validated** | Fabric tenant to execute |
| Fabric-native blue/green promotion, Direct Lake semantic model release | **Future research** | Fabric tenant + CI/CD integration |
| LLM root-cause investigator | **Future research** | Governed agent + model endpoint |

## Quick start — works without Fabric

Python 3.10+ is required.

```bash
python -m pip install -e .
python -m unittest discover -s tests -v

medallion-x demo --scenario clean --out-dir runs/clean
medallion-x demo --scenario regression --expect-block --out-dir runs/regression
medallion-x demo --scenario poisoned --expect-block --out-dir runs/poisoned
medallion-x demo --scenario late --out-dir runs/late
medallion-x impact
```

Open `runs/regression/release_report.html` locally in any browser; inspect `release_evidence.json` for machine-readable proof. Each run includes `bronze_payment_events.csv` ready to upload into OneLake.

The `--expect-block` flag returns success only if the safety gate **correctly blocks** the experiment. If it unexpectedly approves a regression, the CI check fails.

If you have **no** Fabric capacity, the simulator, reports and unit tests still run. You will not be exercising dbt or OneLake until the tenant-dependent steps are completed.

## Experiments

| Experiment | Input perturbation / candidate change | Expected result |
|---|---|---|
| `clean` | Explicit contract v1/v2, duplicate deliveries, one late older event | ELIGIBLE_FOR_APPROVAL |
| `regression` | Candidate accidentally counts `authorized` as `settled` | BLOCKED — financial delta +16,000 cents |
| `poisoned` | Unapproved v3, negative amount, conflicting event identity | BLOCKED — quarantine policy failure |
| `late` | A late arriving **newer business-time** refund corrects a prior settlement | ELIGIBLE_FOR_APPROVAL and settled current amount falls from 39,500 to 22,000 cents |

Amounts are synthetic **MXN cents**. The Gold metric is *current settled transaction exposure*, not a booked revenue or cash-ledger measure. A refunded or charged-back transaction no longer contributes to current-settled exposure.

## Architecture

```text
                           SYNTHETIC PAYMENT CDC
                       v1/v2 / out-of-order / poison
                                      |
                            Fabric Data Factory
                                      |
                 OneLake / Bronze Lakehouse [DELTA]
                  immutable-ish append-only raw events
                                      |
                    SQL analytics endpoint (READ ONLY)
                                      |
         Fabric Warehouse + dbt-fabric (SQL/T-SQL)
                 staging -> silver -> gold
                       /              \
         Candidate warehouse       Production baseline
         (change under test)      (approved model version)
                       \              /
                      REPLAY / QUALITY GATE
                  contract, duplicates, metric diff
                         + dbt manifest lineage
                                 |
                     APPROVAL + RELEASE CONTROL
                                 |
                   APPROVED PHYSICAL GOLD TABLES
                                 |
                       Power BI Direct Lake
```

**Why Warehouse for the first Fabric implementation?** It gives a clear supported SQL transformation boundary. Microsoft documents this exact Lakehouse Bronze → Warehouse Silver/Gold pattern, with cross-database reads from Lakehouse Delta tables. The SQL analytics endpoint itself is read-only; dbt writes into the Warehouse, never the Lakehouse endpoint.

A Lakehouse-only research variant using `dbt-fabricspark` and Materialized Lake Views is described under `docs/ROADMAP.md`.

## Deterministic experiment design

- Same raw multiset of CDC events in both lanes. SHA-256 source identity is insensitive to input ordering but sensitive to duplicate multiplicity.
- A strict, versioned schema contract permits only reviewed revisions; v2 renames `amount_cents` to `gross_amount_cents`.
- Event identity duplicates are ignored if byte-equivalent after normalization; conflicting records are quarantined.
- Business ordering uses `(event_at, ingested_at, event_id)` rather than arrival order; **event time** determines the current state, with deterministic tie breaks.
- Policy requires zero unreviewed contract violations and zero unapproved critical business-metric changes.
- A valid candidate is **eligible for human approval**, not silently published.
- Fallback lineage is explicitly marked. When a dbt `target/manifest.json` is supplied, dbt dependencies are used instead.

## Local-only explicit approval

```bash
medallion-x promote \
  --evidence runs/clean/release_evidence.json \
  --approved-by reviewer@example.test \
  --pointer runs/current_release.json
```

This command atomically updates a **local simulation pointer only**. It cannot push changes to Fabric or Power BI. A blocked report is rejected. A production release must implement actual Fabric deployment steps with tenant roles, dataset version pinning, a baseline comparison query, controlled publication, monitoring and rollback.

## Where the repo is designed to go

Read `docs/ARCHITECTURE.md` (design decisions), `docs/EXPERIMENTS.md` (research method), `docs/ROADMAP.md` (milestones) and `fabric/dbt/README.md` (tenant deployment).

References: [Microsoft Fabric medallion / dbt patterns](https://learn.microsoft.com/en-us/fabric/data-factory/common-dbt-job-patterns), [dbt-fabric setup](https://docs.getdbt.com/docs/local/connect-data-platform/fabric-setup), [Direct Lake overview](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-overview).
