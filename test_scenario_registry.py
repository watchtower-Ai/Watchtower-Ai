import copy
import json
import tempfile
import unittest
from pathlib import Path
import scenario_registry as registry

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.records = registry.load(Path(__file__).with_name("scenarios.json"))
        self.record = copy.deepcopy(self.records[0])

    def test_seed_records_are_hypotheses_not_incidents(self):
        self.assertTrue(all(r["evidence_status"] == "hypothetical" for r in self.records))

    def test_drafts_never_enter_retrieval(self):
        self.assertEqual(registry.retrieve(self.records, "operator stop action"), [])

    def test_approved_fixture_is_retrievable(self):
        self.record.update(review_status="approved", reviewer="TEST FIXTURE ONLY")
        self.assertEqual(registry.retrieve([self.record], "operator stop")[0]["scenario"]["id"], self.record["id"])

    def test_approval_requires_reviewer(self):
        self.record["review_status"] = "approved"
        with self.assertRaises(ValueError): registry.validate(self.record)

    def test_observed_claim_requires_sources(self):
        self.record["evidence_status"] = "observed"
        with self.assertRaises(ValueError): registry.validate(self.record)

    def test_no_fabricated_probability_field(self):
        self.record["catastrophe_probability"] = 0.99
        with self.assertRaises(ValueError): registry.validate(self.record)

    def test_benign_examples_required(self):
        self.record["false_positive_examples"] = []
        with self.assertRaises(ValueError): registry.validate(self.record)

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            path.write_text(json.dumps([self.record, self.record]))
            with self.assertRaises(ValueError): registry.load(path)

    def test_bad_limit_rejected(self):
        with self.assertRaises(ValueError): registry.retrieve(self.records, "stop", 0)

    def test_retrieval_does_not_mutate_source(self):
        self.record.update(review_status="approved", reviewer="TEST FIXTURE ONLY")
        result = registry.retrieve([self.record], "operator stop")
        result[0]["scenario"]["title"] = "changed"
        self.assertNotEqual(self.record["title"], "changed")

if __name__ == "__main__":
    unittest.main()
