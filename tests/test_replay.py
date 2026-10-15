import unittest
from medallion_x.generator import make_events
from medallion_x.replay import replay, snapshot_hash


class ReplayTests(unittest.TestCase):
    def test_settlement_and_latest_event_time(self):
        result = replay(make_events())
        self.assertEqual(result["metrics"]["current_settled_amount_cents"], 39500)
        self.assertEqual(result["metrics"]["currently_settled_transactions"], 3)
        self.assertEqual(result["metrics"]["authorized_exposure_cents"], 16000)
        self.assertEqual(result["current_state"]["tx-007"]["status"], "refunded")
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(result["quarantine"], [])

    def test_deterministic_under_input_permutation(self):
        events = make_events()
        self.assertEqual(snapshot_hash(events), snapshot_hash(list(reversed(events))))
        self.assertEqual(replay(events)["state_hash"], replay(list(reversed(events)))["state_hash"])

    def test_late_real_correction_updates_state(self):
        value = replay(make_events("late"))
        self.assertEqual(value["metrics"]["current_settled_amount_cents"], 22000)
        self.assertEqual(value["current_state"]["tx-002"]["status"], "refunded")

    def test_reject_bad_schemas_and_conflicts(self):
        output = replay(make_events("poisoned"))
        self.assertEqual(len(output["quarantine"]), 3)
        self.assertEqual({q["reason"] for q in output["quarantine"]},
                         {"unapproved_schema_version", "amount_out_of_range", "conflicting_event_id"})

    def test_semantic_regression_injects_difference(self):
        events = make_events()
        good, bad = replay(events), replay(events, model_version="buggy-authorized-as-settled")
        self.assertEqual(good["state_hash"], bad["state_hash"])
        self.assertEqual(bad["metrics"]["current_settled_amount_cents"], 55500)
