import unittest
from queue_metrics import summarize

class QueueMetricsTests(unittest.TestCase):
    def test_summary_and_deduplication(self):
        s = ("job_id\\tstate\\texit_code\\tstarted\\tfinished\n"
             "one\\tdone\\t0\\ta\\tb\n"
             "two\\tfailed\\t64\\ta\\tb\n"
             "two\\tfailed\\t64\\ta\\tb\n")
        report = summarize(s)
        self.assertEqual(report["total_unique_jobs"], 2)
        self.assertEqual(report["states"], {"done": 1, "failed": 1})
        self.assertEqual(report["duplicate_job_ids"], 1)
        self.assertEqual(report["failed_exit_codes"], {"64": 1})

    def test_malformed_rows(self):
        self.assertEqual(summarize("bad\n")["invalid_rows"], 1)

    def test_real_tabs(self):
        self.assertEqual(summarize("a\tdone\t0\tx\ty\n")["states"]["done"], 1)

if __name__ == "__main__":
    unittest.main()
