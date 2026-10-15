import json
import tempfile
from pathlib import Path
import unittest
from medallion_x.cli import main
from medallion_x.generator import make_events
from medallion_x.replay import replay
from medallion_x.gate import assess

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/release_policy.json").read_text())


class GateTests(unittest.TestCase):
    def _assess(self, scenario, candidate=None):
        events = make_events(scenario)
        base = replay(events)
        cand = replay(events, model_version=candidate or "stable")
        return assess(events=events, baseline=base, candidate=cand, policy=POLICY, impact={})

    def test_clean_eligible(self):
        self.assertEqual(self._assess("clean")["gate"]["decision"], "ELIGIBLE_FOR_APPROVAL")

    def test_poisoned_blocked(self):
        result = self._assess("poisoned")
        self.assertEqual(result["gate"]["decision"], "BLOCKED")
        self.assertIn("contract_quarantine_threshold_exceeded", result["gate"]["reasons"])

    def test_regression_blocked_even_with_unchanged_state(self):
        result = self._assess("clean", "buggy-authorized-as-settled")
        self.assertEqual(result["gate"]["decision"], "BLOCKED")
        self.assertEqual(result["changed_transaction_ids"], [])
        self.assertEqual(result["metric_deltas"]["current_settled_amount_cents"], 16000)

    def test_promote_requires_valid_evidence_and_reviewer(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            self.assertEqual(main(["demo", "--scenario", "clean", "--out-dir", str(p / "clean")]), 0)
            good = p / "clean/release_evidence.json"
            ptr = p / "pointer.json"
            self.assertEqual(main(["promote", "--evidence", str(good), "--approved-by", "reviewer", "--pointer", str(ptr)]), 0)
            self.assertTrue(json.loads(ptr.read_text())["simulation_only"])
            self.assertEqual(main(["demo", "--scenario", "poisoned", "--out-dir", str(p / "poison"), "--expect-block"]), 0)
            self.assertEqual(main(["promote", "--evidence", str(p / "poison/release_evidence.json"), "--approved-by", "reviewer", "--pointer", str(ptr)]), 3)
