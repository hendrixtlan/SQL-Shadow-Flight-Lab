"""CLI for reproducible data-change experiments and explicit local release approval."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from .generator import make_events, write_csv
from .replay import replay
from .gate import assess, html_report
from .impact import compute_impact
from .sqlflight import flight_test
from .mutation_lab import stress
from .integrity import verify_ledger


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def to_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_demo(args: argparse.Namespace) -> int:
    root = repo_root()
    output = Path(args.out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    events = make_events(args.scenario)
    write_csv(events, output / "bronze_payment_events.csv")
    baseline = replay(events, model_version="stable")
    candidate_version = "buggy-authorized-as-settled" if args.scenario == "regression" else "stable"
    candidate = replay(events, model_version=candidate_version)
    impact = compute_impact(graph_file=root / "config/impact_graph.json", manifest_file=Path(args.manifest) if args.manifest else None)
    policy = json.loads((root / "config/release_policy.json").read_text())
    report = assess(events=events, baseline=baseline, candidate=candidate, policy=policy, impact=impact)
    report["scenario"] = args.scenario
    to_json(output / "release_evidence.json", report)
    (output / "release_report.html").write_text(html_report(report), encoding="utf-8")
    print(f"scenario={args.scenario} decision={report['gate']['decision']} metrics={baseline['metrics']} deltas={report['metric_deltas']}")
    print(f"Evidence: {output / 'release_evidence.json'}")
    print(f"Report:   {output / 'release_report.html'}")
    blocked = report["gate"]["decision"] == "BLOCKED"
    return 0 if blocked == args.expect_block else 2


def run_promote(args: argparse.Namespace) -> int:
    """Advance a *local simulation* pointer; this never changes Fabric artifacts."""
    evidence_path = Path(args.evidence)
    report = json.loads(evidence_path.read_text(encoding="utf-8"))
    if report.get('schema') == 'medallion-x.flight-evidence.v2':
        errors = verify_ledger(evidence_path.parent)
        if errors:
            print(f"Rejected: evidence bundle failed integrity check: {errors}", file=sys.stderr)
            return 3
    if report["gate"]["decision"] != "ELIGIBLE_FOR_APPROVAL":
        print("Rejected: safety gate has not passed.", file=sys.stderr)
        return 3
    if not args.approved_by.strip():
        print("Rejected: reviewer identity must be supplied.", file=sys.stderr)
        return 3
    pointer = Path(args.pointer)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    release = {
        "simulation_only": True,
        "candidate_version": report["candidate"]["model_version"],
        "source_snapshot_sha256": report["source_snapshot_sha256"],
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "approved_by": args.approved_by,
        "approved_at_utc": datetime.now(timezone.utc).isoformat(),
        "fabric_deployment_executed": False,
    }
    staged = pointer.with_name(pointer.name + ".tmp")
    to_json(staged, release)
    os.replace(staged, pointer)
    print(f"Approved in LOCAL SIMULATION ONLY: {pointer}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="medallion-x")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo", help="Generate data and compare two transformations")
    d.add_argument("--scenario", choices=["clean", "poisoned", "regression", "late"], default="clean")
    d.add_argument("--out-dir", default="runs/clean")
    d.add_argument("--expect-block", action="store_true", help="Assert the release is blocked")
    d.add_argument("--manifest", help="Real dbt target/manifest.json for lineage; otherwise use declared fallback")
    p = sub.add_parser("promote", help="Approve an eligible release in a local pointer ONLY")
    p.add_argument("--evidence", required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--pointer", default="runs/current_release.json")
    f = sub.add_parser("flight-test", help="Run actual SQL baseline/candidate in isolated local SQLite databases")
    f.add_argument("--scenario", choices=["clean", "regression", "poisoned", "late"], default="clean")
    f.add_argument("--out-dir", default="runs/flight")
    f.add_argument("--candidate-model", choices=["stable", "buggy-authorized-as-settled"])
    f.add_argument("--expect-block", action="store_true")
    m = sub.add_parser("stress-test", help="Run SQL metamorphic permutation + duplicate-delivery experiments")
    m.add_argument("--rounds", type=int, default=100)
    m.add_argument("--seed", type=int, default=42)
    m.add_argument("--out", default="runs/metamorphic.json")
    v = sub.add_parser("verify", help="Verify SHA-256 ledger for one flight-test directory")
    v.add_argument("--run-dir", required=True)
    i = sub.add_parser("impact", help="Print lineage blast radius")
    i.add_argument("--manifest")
    args = parser.parse_args(argv)
    if args.command == "demo":
        return run_demo(args)
    if args.command == "promote":
        return run_promote(args)
    if args.command == "flight-test":
        r = flight_test(scenario=args.scenario, directory=Path(args.out_dir), root=repo_root(), candidate_model=args.candidate_model)
        print(f"SQL flight: {args.scenario} -> {r['gate']['decision']}; metric deltas: {r['metric_deltas']}")
        print(f"Evidence, SQL databases and integrity ledger: {Path(args.out_dir).resolve()}")
        return 0 if (r['gate']['decision'] == 'BLOCKED') == args.expect_block else 2
    if args.command == "stress-test":
        r = stress(root=repo_root(), rounds=args.rounds, seed=args.seed, out=Path(args.out))
        print(f"SQL metamorphic: {r['rounds']} rounds, failures={len(r['failures'])}, seed={r['seed']}")
        return 0 if r['passed'] else 5
    if args.command == "verify":
        errors = verify_ledger(Path(args.run_dir))
        print(json.dumps({'verification': 'FAILED' if errors else 'PASSED', 'errors': errors}, indent=2))
        return 4 if errors else 0
    if args.command == "impact":
        print(json.dumps(compute_impact(graph_file=repo_root() / "config/impact_graph.json", manifest_file=Path(args.manifest) if args.manifest else None), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
