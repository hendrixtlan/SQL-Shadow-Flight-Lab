"""Deterministic metamorphic testing of SQL transformations; standard library only."""
from __future__ import annotations
import json
from pathlib import Path
import random
import tempfile
from typing import Any
from .generator import make_events
from .sqlflight import _execute_lane


def stress(*, root: Path, rounds: int, seed: int, out: Path) -> dict[str, Any]:
    if not 1 <= rounds <= 1000:
        raise ValueError('rounds must be between 1 and 1000')
    randomizer = random.Random(seed)
    sql = root / 'local_sql/stable.sql'
    base = make_events('clean')
    failures: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp) / 'test.sqlite'
        original = _execute_lane(events=base, sql_file=sql, database=db, version='stable')
        for i in range(rounds):
            shuffled = [dict(x) for x in base]
            randomizer.shuffle(shuffled)
            mutation = i % 3
            if mutation == 1:  # duplicate delivery does not change business-state metrics
                shuffled.append(dict(randomizer.choice(shuffled)))
            elif mutation == 2:  # arbitrary arrival order + duplicated messages
                shuffled.extend(dict(randomizer.choice(base)) for _ in range(3))
                randomizer.shuffle(shuffled)
            observed = _execute_lane(events=shuffled, sql_file=sql, database=db, version='stable')
            if observed['metrics'] != original['metrics'] or observed['state_hash'] != original['state_hash']:
                failures.append({'trial': i, 'mutation': mutation, 'metrics': observed['metrics'], 'state_hash': observed['state_hash']})
    result = {
        'schema': 'medallion-x.metamorphic-test.v1',
        'seed': seed, 'rounds': rounds,
        'invariants': ['permutation_invariant_business_state', 'idempotent_exact_duplicate_deliveries'],
        'failures': failures,
        'passed': not failures,
        'engine': 'SQLite local SQL and normalized contract source',
        'fabric_executed': False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return result
