import json
import tempfile
from pathlib import Path
import unittest
from medallion_x.impact import compute_impact, SOURCE

ROOT = Path(__file__).resolve().parents[1]


class ImpactTests(unittest.TestCase):
    def test_fallback_dag(self):
        result = compute_impact(graph_file=ROOT / "config/impact_graph.json")
        self.assertEqual(len(result["affected_nodes"]), 5)
        self.assertIn("consumer.powerbi.payment_exposure", result["affected_nodes"])

    def test_dbt_manifest_is_used_when_provided(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = Path(d) / "manifest.json"
            manifest.write_text(json.dumps({"child_map": {
                SOURCE: ["model.medallion_x.stg_payment_events"],
                "model.medallion_x.stg_payment_events": ["model.medallion_x.silver_payment_events"]
            }}))
            result = compute_impact(graph_file=ROOT / "config/impact_graph.json", manifest_file=manifest)
            self.assertEqual(result["graph_provenance"], "dbt_manifest_plus_declared_consumers")
            self.assertIn("model.medallion_x.silver_payment_events", result["affected_nodes"])
