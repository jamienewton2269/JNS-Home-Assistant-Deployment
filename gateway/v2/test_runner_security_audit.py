import unittest
from runner_security_audit import audit

class RunnerSecurityTests(unittest.TestCase):
    def test_public_sage_result_commit(self):
        workflow = "permissions:\n  contents: write\nrun: git add gateway/sage-result.txt\n"
        self.assertIn("public_result_commit_risk", audit(workflow))

    def test_audit_branch_self_hosted(self):
        workflow = "push:\n  branches:\n    - audit/test\njobs:\n  x:\n    runs-on: [self-hosted, linux, nodec]\n"
        self.assertIn("self_hosted_audit_branch_push", audit(workflow))

    def test_hosted_ci(self):
        self.assertEqual(audit("jobs:\n  test:\n    runs-on: ubuntu-latest\n"), [])

    def test_global_trust(self):
        self.assertIn("global_git_ownership_bypass", audit("git config --global --add safe.directory=*"))

if __name__ == "__main__":
    unittest.main()
