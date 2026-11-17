import unittest
from batch_plan import plan, BatchRejected

class BatchPlanTests(unittest.TestCase):
    def test_order(self):
        items = [
            {"id":"build","kind":"build","after":["test"]},
            {"id":"test","kind":"test","after":["health"]},
            {"id":"health","kind":"health","after":[]},
        ]
        self.assertEqual([x["id"] for x in plan(items)], ["health","test","build"])

    def test_cycle(self):
        self.assertRaises(BatchRejected, plan, [
            {"id":"a","kind":"test","after":["b"]},
            {"id":"b","kind":"build","after":["a"]},
        ])

    def test_shell_not_allowed(self):
        self.assertRaises(BatchRejected, plan, [{"id":"x","kind":"shell","after":[]}])

    def test_unknown_dependency(self):
        self.assertRaises(BatchRejected, plan, [{"id":"x","kind":"health","after":["missing"]}])

    def test_duplicate(self):
        self.assertRaises(BatchRejected, plan, [
            {"id":"x","kind":"health","after":[]},
            {"id":"x","kind":"test","after":[]},
        ])

    def test_malformed_dependency_rejected(self):
        self.assertRaises(BatchRejected, plan, [{"id":"x","kind":"health","after":[{}]}])

    def test_malformed_kind_rejected(self):
        self.assertRaises(BatchRejected, plan, [{"id":"x","kind":[],"after":[]}])

    def test_empty(self):
        self.assertRaises(BatchRejected, plan, [])

if __name__ == "__main__":
    unittest.main()
