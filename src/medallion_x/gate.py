"""Deterministic release gate. Fail closed; never triggers a Fabric deployment."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .replay import snapshot_hash

METRIC_LIMITS = {
    "current_settled_amount_cents": "max_metric_delta_cents",
    "currently_settled_transactions": "max_metric_delta_transactions",
    "authorized_exposure_cents": "max_metric_delta_cents",
}


def assess(*, events: list[dict[str, str]], baseline: dict[str, Any], candidate: dict[str, Any], policy: dict[str, Any], impact: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    baseline_quarantine = len(baseline["quarantine"])
    candidate_quarantine = len(candidate["quarantine"])
    if baseline_quarantine > policy["max_quarantined_rows"] or candidate_quarantine > policy["max_quarantined_rows"]:
        reasons.append("contract_quarantine_threshold_exceeded")

    baseline_state, candidate_state = baseline["current_state"], candidate["current_state"]
    state_diffs = sorted(k for k in baseline_state.keys() | candidate_state.keys() if baseline_state.get(k) != candidate_state.get(k))
    if len(state_diffs) > policy["max_state_differences"]:
        reasons.append("state_drift_exceeds_policy")
    metric_deltas = {}
    for metric, limit_key in METRIC_LIMITS.items():
        delta = candidate["metrics"][metric] - baseline["metrics"][metric]
        metric_deltas[metric] = delta
        if abs(delta) > policy[limit_key]:
            reasons.append(f"metric_drift:{metric}")
    return {
        "project": "Medallion X",
        "source_snapshot_sha256": snapshot_hash(events),
        "source_event_rows": len(events),
        "policy": policy,
        "baseline": {k: baseline[k] for k in ["model_version", "metrics", "state_hash", "state_counts", "accepted_count", "duplicate_count", "quarantine"]},
        "candidate": {k: candidate[k] for k in ["model_version", "metrics", "state_hash", "state_counts", "accepted_count", "duplicate_count", "quarantine"]},
        "metric_deltas": metric_deltas,
        "changed_transaction_ids": state_diffs,
        "impact": impact,
        "gate": {"decision": "BLOCKED" if reasons else "ELIGIBLE_FOR_APPROVAL", "reasons": sorted(set(reasons)), "human_approval_required": True, "production_promoted": False},
        "limitations": [
            "Reference Python evaluator; Fabric/dbt SQL parity has not been validated in this run.",
            "A local release pointer is not a Power BI or Fabric deployment.",
            "A production comparison must pin source Delta table versions or a consistent source snapshot."
        ],
    }


def html_report(report: dict[str, Any]) -> str:
    """Fully standalone report: no JS, no external assets, escaped dynamic content."""
    from html import escape
    def h(obj: Any) -> str:
        return escape(str(obj), quote=True)
    rows = "".join(
        f"<tr><td>{h(metric)}</td><td>{h(report['baseline']['metrics'][metric])}</td>"
        f"<td>{h(report['candidate']['metrics'][metric])}</td><td>{h(delta)}</td></tr>"
        for metric, delta in report["metric_deltas"].items()
    )
    issues = "".join(f"<li>{h(r)}</li>" for r in report["gate"]["reasons"]) or "<li>No policy violations detected</li>"
    affected = "".join(f"<li>{h(n)}</li>" for n in report["impact"]["affected_nodes"])
    state = report["gate"]["decision"]
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Medallion X - {h(state)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:980px;margin:40px auto;padding:0 20px;color:#182034;background:#fafbfc}}
header{{padding:25px;background:#152340;color:white;border-radius:13px}}h1{{margin:0}}.panel{{border:1px solid #dbe2ec;border-radius:12px;padding:22px;background:white;margin-top:18px}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #e5e9f0}}th{{background:#f3f6fa}}.blocked{{color:#bd2434}}.eligible{{color:#047857}}
code{{overflow-wrap:anywhere}}li{{margin:7px 0}}</style>
<header><h1>MEDALLION X | Release Flight Recorder</h1><p>Candidate vs baseline on identical synthetic CDC input</p></header>
<div class="panel"><h2 class="{'blocked' if state == 'BLOCKED' else 'eligible'}">{h(state)}</h2><p>No production publication was performed. Human approval is required.</p><p>Snapshot: <code>{h(report['source_snapshot_sha256'])}</code></p></div>
<div class="panel"><h2>Metric parity</h2><table><thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Delta</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="panel"><h2>Policy findings</h2><ul>{issues}</ul><p>Changed transaction IDs: {h(len(report['changed_transaction_ids']))}</p></div>
<div class="panel"><h2>Downstream impact</h2><p>Lineage provenance: {h(report['impact']['graph_provenance'])}</p><ul>{affected}</ul></div>
<div class="panel"><h2>Run limitations</h2><ul>{''.join('<li>'+h(x)+'</li>' for x in report['limitations'])}</ul></div>
</html>"""
