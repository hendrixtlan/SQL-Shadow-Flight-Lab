"""True SQL-vs-SQL dual execution, on isolated local SQLite databases.

This verifies transformation behavior and policy without Fabric credentials. SQL here is
SQLite SQL, and cannot establish Fabric T-SQL / dbt adapter compatibility.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import shutil
from pathlib import Path
import sqlite3
from typing import Any
from .replay import normalize, replay, snapshot_hash
from .generator import make_events, write_csv
from .impact import compute_impact
from .gate import assess, html_report
from .integrity import create_ledger

VERSIONS = {'stable': 'stable.sql', 'buggy-authorized-as-settled': 'buggy-authorized-as-settled.sql'}


def _accepted_rows(events: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Contract validation is shared; transformation/metrics are independent SQL.

    Retains v1 oracle's first accepted event-id rule. Conflicts are quarantined.
    A future version should reject entire conflicting identity groups instead.
    """
    unique: dict[str, dict[str, Any]] = {}
    quarantine: list[dict[str, Any]] = []
    duplicates = 0
    for i, raw in enumerate(events):
        try:
            row = normalize(raw)
        except ValueError as e:
            quarantine.append({'source_index': i, 'event_id': raw.get('event_id', ''), 'reason': str(e)})
            continue
        previous = unique.get(row['event_id'])
        if previous is None:
            unique[row['event_id']] = row
        elif previous == row:
            duplicates += 1
        else:
            quarantine.append({'source_index': i, 'event_id': row['event_id'], 'reason': 'conflicting_event_id'})
    quarantine.sort(key=lambda x: (x['event_id'], x['reason'], x['source_index']))
    return list(unique.values()), quarantine, duplicates


def _execute_lane(*, events: list[dict[str, str]], sql_file: Path, database: Path, version: str) -> dict[str, Any]:
    accepted, quarantine, duplicates = _accepted_rows(events)
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(str(database))
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('CREATE TABLE valid_events (event_id TEXT NOT NULL PRIMARY KEY, transaction_id TEXT NOT NULL, event_at TEXT NOT NULL, ingested_at TEXT NOT NULL, status TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK (amount_cents > 0), currency TEXT NOT NULL)')
        connection.executemany(
            'INSERT INTO valid_events VALUES (:event_id,:transaction_id,:event_at,:ingested_at,:status,:amount_cents,:currency)',
            accepted,
        )
        connection.commit()
        connection.executescript(sql_file.read_text(encoding='utf-8'))
        connection.commit()
        state_rows = [dict(r) for r in connection.execute('SELECT * FROM current_state ORDER BY transaction_id')]
        metrics = dict(connection.execute('SELECT * FROM gold_metrics').fetchone())
        count_rows = connection.execute('SELECT COUNT(*) FROM valid_events').fetchone()[0]
        if count_rows != len(accepted) or len(state_rows) != len({r['transaction_id'] for r in accepted}):
            raise RuntimeError('physical_state_row_count_invariant_failed')
    finally:
        connection.close()
    state = {r['transaction_id']: {'status': r['status'], 'amount_cents': r['amount_cents'], 'event_id': r['event_id']} for r in state_rows}
    canonical = json.dumps(state, sort_keys=True, separators=(',', ':'))
    return {
        'model_version': version,
        'accepted_count': len(accepted), 'duplicate_count': duplicates,
        'quarantine': quarantine,
        'current_state': state,
        'state_hash': hashlib.sha256(canonical.encode()).hexdigest(),
        'state_counts': dict(sorted(Counter(r['status'] for r in state_rows).items())),
        'metrics': metrics,
        'physical_db': database.name,
        'source_snapshot_sha256': snapshot_hash(events),
        'sql_sha256': hashlib.sha256(sql_file.read_bytes()).hexdigest(),
    }


def _parity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(left[k] == right[k] for k in (
        'metrics', 'current_state', 'state_hash', 'accepted_count', 'duplicate_count', 'quarantine'
    ))


def flight_test(*, scenario: str, directory: Path, root: Path,
                candidate_model: str | None = None) -> dict[str, Any]:
    """Materialize two physical SQL outputs then gate, never publish to Fabric."""
    if scenario not in {'clean', 'regression', 'poisoned', 'late'}:
        raise ValueError('unrecognized_scenario')
    version = candidate_model or ('buggy-authorized-as-settled' if scenario == 'regression' else 'stable')
    if version not in VERSIONS:
        raise ValueError('unrecognized_model')
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    events = make_events(scenario)
    csv_file = directory / 'frozen_bronze.csv'
    write_csv(events, csv_file)
    # Snapshot executable SQL and control inputs INSIDE the evidence bundle.
    inputs_dir = directory / 'inputs'
    inputs_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = inputs_dir / 'baseline.sql'
    candidate_path = inputs_dir / 'candidate.sql'
    policy_path = inputs_dir / 'release_policy.json'
    graph_path = inputs_dir / 'impact_graph.json'
    shutil.copyfile(root / 'local_sql' / VERSIONS['stable'], baseline_path)
    shutil.copyfile(root / 'local_sql' / VERSIONS[version], candidate_path)
    shutil.copyfile(root / 'config' / 'release_policy.json', policy_path)
    shutil.copyfile(root / 'config' / 'impact_graph.json', graph_path)
    baseline_db = directory / 'baseline.sqlite'
    candidate_db = directory / 'candidate.sqlite'
    baseline = _execute_lane(events=events, sql_file=baseline_path, database=baseline_db, version='stable')
    candidate = _execute_lane(events=events, sql_file=candidate_path, database=candidate_db, version=version)
    graph = compute_impact(graph_file=graph_path, manifest_file=None)
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    report = assess(events=events, baseline=baseline, candidate=candidate, policy=policy, impact=graph)
    reference = replay(events, model_version='stable')
    oracle_matches = _parity(baseline, reference)
    same_source = baseline['source_snapshot_sha256'] == candidate['source_snapshot_sha256'] == snapshot_hash(events)
    if not oracle_matches:
        report['gate']['reasons'].append('baseline_sql_python_reference_mismatch')
    if not same_source:
        report['gate']['reasons'].append('source_snapshot_mismatch')
    if version == 'stable' and not _parity(candidate, reference):
        report['gate']['reasons'].append('candidate_sql_python_reference_mismatch')
    if report['gate']['reasons']:
        report['gate']['reasons'] = sorted(set(report['gate']['reasons']))
        report['gate']['decision'] = 'BLOCKED'
    report.update({
        'schema': 'medallion-x.flight-evidence.v2',
        'scenario': scenario,
        'execution_engine': 'SQLite 3 (local; SQL executed physically)',
        'source_csv_sha256': hashlib.sha256(csv_file.read_bytes()).hexdigest(),
        'lanes': {
            'baseline': {'db': baseline_db.name, 'sql': 'inputs/baseline.sql', 'sql_sha256': baseline['sql_sha256']},
            'candidate': {'db': candidate_db.name, 'sql': 'inputs/candidate.sql', 'sql_sha256': candidate['sql_sha256']},
        },
        'reference_parity': {'baseline_matches_python': oracle_matches, 'candidate_matches_python': _parity(candidate, reference) if version == 'stable' else None},
        'source_identity_enforced': same_source,
        'platform_execution': {'fabric': False, 'dbt': False, 'power_bi_published': False},
        'limitations': [
            'Two separate physical SQLite databases execute SQL; this is NOT dbt-fabric/T-SQL runtime validation.',
            'The contract normalizer is shared by both lanes, so its own bugs are common-mode risks.',
            'The source is frozen as a local CSV; Fabric Delta snapshots require separate runtime validation.',
            'The integrity ledger is unsigned and cannot prove release authorization or author identity.',
            'No remote release was performed.',
        ],
    })
    evidence_path = directory / 'release_evidence.json'
    evidence_path.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    html_path = directory / 'release_report.html'
    extra = f'<section class="panel"><h2>v2 SQL flight test</h2><p>Two independent SQLite databases physically ran the versioned transformation SQL.</p><p>Baseline / Python parity: {oracle_matches} · Identical source: {same_source}</p><p>Fabric run: NO · dbt run: NO · Publication: NO</p></section>'
    html_path.write_text(html_report(report).replace('</html>', extra + '</html>'), encoding='utf-8')
    ledger = create_ledger(directory, [csv_file, baseline_db, candidate_db, evidence_path, html_path, baseline_path, candidate_path, policy_path, graph_path])
    (directory / 'integrity_ledger.json').write_text(json.dumps(ledger, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return report
