"""v2 SQL release flight: physical SQL, parity, integrity and fail-closed promotion."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from medallion_x.cli import repo_root, run_promote
from medallion_x.integrity import verify_ledger
from medallion_x.mutation_lab import stress
from medallion_x.sqlflight import flight_test


class FlightV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = repo_root()
        self.destination = Path(self.temp.name) / 'run'

    def run_case(self, scenario):
        return flight_test(scenario=scenario, directory=self.destination, root=self.root)

    def test_clean_executes_isolated_sql_and_matches_oracle(self):
        r = self.run_case('clean')
        self.assertEqual(r['gate']['decision'], 'ELIGIBLE_FOR_APPROVAL')
        self.assertTrue(r['reference_parity']['baseline_matches_python'])
        self.assertTrue(r['reference_parity']['candidate_matches_python'])
        self.assertEqual(r['metric_deltas']['current_settled_amount_cents'], 0)
        self.assertFalse(r['platform_execution']['fabric'])
        self.assertEqual(verify_ledger(self.destination), [])
        with sqlite3.connect(self.destination / 'baseline.sqlite') as db:
            self.assertEqual(db.execute('select current_settled_amount_cents from gold_metrics').fetchone()[0], 39500)
        with sqlite3.connect(self.destination / 'candidate.sqlite') as db:
            self.assertEqual(db.execute('select count(*) from current_state').fetchone()[0], 8)

    def test_regression_blocks_even_though_state_is_identical(self):
        r = self.run_case('regression')
        self.assertEqual(r['gate']['decision'], 'BLOCKED')
        self.assertIn('metric_drift:current_settled_amount_cents', r['gate']['reasons'])
        self.assertEqual(r['baseline']['state_hash'], r['candidate']['state_hash'])
        self.assertEqual(r['metric_deltas']['current_settled_amount_cents'], 16000)
        self.assertEqual(verify_ledger(self.destination), [])

    def test_contract_poison_is_blocked(self):
        r = self.run_case('poisoned')
        self.assertEqual(r['gate']['decision'], 'BLOCKED')
        self.assertIn('contract_quarantine_threshold_exceeded', r['gate']['reasons'])
        self.assertTrue(r['reference_parity']['baseline_matches_python'])

    def test_late_event_is_valid_and_replayed(self):
        r = self.run_case('late')
        self.assertEqual(r['gate']['decision'], 'ELIGIBLE_FOR_APPROVAL')
        self.assertEqual(r['baseline']['metrics']['current_settled_amount_cents'], 22000)

    def test_ledger_catches_tampered_sql_database(self):
        self.run_case('clean')
        with sqlite3.connect(self.destination / 'candidate.sqlite') as db:
            db.execute('update gold_metrics set current_settled_amount_cents = 9')
        self.assertIn('hash_mismatch:candidate.sqlite', verify_ledger(self.destination))

    def test_ledger_catches_modified_source(self):
        self.run_case('clean')
        with (self.destination / 'frozen_bronze.csv').open('a') as fh:
            fh.write('TAMPERED\n')
        self.assertIn('hash_mismatch:frozen_bronze.csv', verify_ledger(self.destination))

    def test_promotion_rejects_modified_v2_evidence(self):
        self.run_case('clean')
        evidence = self.destination / 'release_evidence.json'
        r = json.loads(evidence.read_text())
        r['source_event_rows'] = 1
        evidence.write_text(json.dumps(r))
        rc = run_promote(argparse.Namespace(evidence=str(evidence), approved_by='test@example.test', pointer=str(self.destination / 'pointer.json')))
        self.assertEqual(rc, 3)
        self.assertFalse((self.destination / 'pointer.json').exists())

    def test_metamorphic_randomized_invariants(self):
        report = stress(root=self.root, rounds=30, seed=1001, out=Path(self.temp.name) / 'stress.json')
        self.assertTrue(report['passed'])
        self.assertEqual(report['failures'], [])


class FabricPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        file = repo_root() / 'fabric' / 'experiments' / 'plan.py'
        spec = importlib.util.spec_from_file_location('flight_plan', file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.module = module

    def run_plan(self, directory, **kwargs):
        arguments = {'run_id': 'run01', 'bronze_lakehouse': 'bronze_lh', 'freeze_warehouse': 'freeze_wh',
                     'baseline_warehouse': 'baseline_wh', 'candidate_warehouse': 'candidate_wh',
                     'baseline_schema': 'analytics_dev', 'candidate_schema': 'analytics_ci', 'out_dir': directory}
        arguments.update(kwargs)
        return self.module.generate(**arguments)

    def test_plan_targets_one_frozen_warehouse_relation(self):
        with tempfile.TemporaryDirectory() as temp:
            plan = self.run_plan(Path(temp))
            self.assertEqual(plan['mode'], 'PLAN_ONLY_NOT_EXECUTED')
            self.assertIn('flight_run01', plan['dbt_commands']['baseline'])
            self.assertEqual(plan['dbt_vars']['source_schema'], 'flight_run01')
            freeze = (Path(temp) / '02_freeze_snapshot.sql').read_text()
            compare = (Path(temp) / '03_compare_outputs.sql').read_text()
            self.assertIn('FROM [bronze_lh].[dbo].[raw_payment_events]', freeze)
            self.assertIn('[baseline_wh].[analytics_dev_gold].[mart_daily_payments]', compare)
            self.assertIn('FULL OUTER JOIN', compare)

    def test_unsafe_names_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                self.run_plan(Path(temp), freeze_warehouse='freeze_wh]; DROP TABLE x;--')
            with self.assertRaises(ValueError):
                self.run_plan(Path(temp), run_id='../abc')
            with self.assertRaises(ValueError):
                self.run_plan(Path(temp), baseline_warehouse='freeze_wh')


if __name__ == '__main__':
    unittest.main()
