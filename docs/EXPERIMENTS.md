# Testable research experiments

## Hypothesis H1 — Aggregate financial regressions survive ordinary quality checks

Inject a candidate bug (`authorized` counted as `settled`). The accepted CDC events and final transaction states remain equal. The financial metric changes by **16,000 cents** and the policy blocks candidate publication. This proves *only* that the prototype gate detects this injected class of failure; more coverage is required.

**Measure:** metric absolute delta, changed-row count, gate decision and contract errors.

## Hypothesis H2 — A strict schema contract prevents silent coercion

Introduce unapproved schema v3, negative cents and conflicting `event_id`. Records are quarantined and the gate blocks publication even when baseline and candidate metrics are equal.

**Measure:** contract violation types, quarantine rate and false-approval count.

## Hypothesis H3 — Replay is invariant to delivery order

Reverse/shuffle raw events without changing their multiset. Final state fingerprint remains identical. A late event with older business timestamp doesn't revive a refunded transaction. A new correction with a genuinely later business timestamp does update the state.

**Measure:** state SHA-256 and current-exposure metrics, not just row count.

## Hypothesis H4 — Lineage-based analysis bounds the review blast radius

Use dbt `target/manifest.json` to follow downstream dependencies from the Bronze source, then map named Power BI consumers from an externally maintained catalog. Current static fallback illustrates logic but is *not* authoritative lineage.

**Measure:** impacted nodes, detected vs known dependent consumers, audit completeness.

## Next benchmarks (NOT implemented)

- Scale from 100K to 100M events, report candidate reprocessing time/cost and capacity units.
- Compare warehouse SQL dbt models to lakehouse Spark SQL/dbt-fabricspark using identical Delta snapshots.
- Compare full replay with incremental stateful reprocessing, including late-arrival windows.
- Use workload-specific blast radius to select modified dbt models via state-aware CI.
- Test intentional fraud-like chargebacks, refunds, tombstones, schema evolution and reconciliation.
- Evaluate end-to-end Power BI semantic model correctness after governed publication.
