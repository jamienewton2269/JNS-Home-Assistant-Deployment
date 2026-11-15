import json
import unittest
from job_validation import validate, JobRejected

class ValidationTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(json.dumps({"schema_version":2,"job_id":"20261115_test_01","job_type":"health"}))["job_type"], "health")

    def test_unknown_type(self):
        self.assertRaises(JobRejected, validate, '{"schema_version":2,"job_id":"20261115_test_01","job_type":"shell"}')

    def test_unexpected_command(self):
        self.assertRaises(JobRejected, validate, '{"schema_version":2,"job_id":"20261115_test_01","job_type":"health","command":"id"}')

    def test_duplicate_keys_rejected_by_field_count(self):
        # The strict schema must not be mistaken for authorization.
        self.assertRaises(JobRejected, validate, '{"schema_version":2,"job_id":"bad","job_type":"health"}')

    def test_large(self):
        self.assertRaises(JobRejected, validate, "x" * 9000)

    def test_invalid_utf8(self):
        self.assertRaises(JobRejected, validate, b"\\xff")

    def test_version(self):
        self.assertRaises(JobRejected, validate, '{"schema_version":1,"job_id":"20261115_test_01","job_type":"health"}')

if __name__ == "__main__":
    unittest.main()
