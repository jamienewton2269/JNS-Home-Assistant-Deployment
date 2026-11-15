"""Offline checks for unsafe GitHub Actions patterns in gateway workflows.

Heuristic guardrail, not a complete YAML parser or security scanner.
"""
from pathlib import Path
import re
import sys

def audit(text):
    findings = []
    if re.search(r"runs-on:\s*\[[^\]]*self-hosted", text):
        if re.search(r"(?m)^\s*pull_request_target\s*:", text):
            findings.append("self_hosted_pull_request_target")
        if re.search(r"(?m)^\s*pull_request\s*:", text):
            findings.append("self_hosted_pull_request")
        if re.search(r"(?m)^\s*push\s*:", text) and re.search(r"(?m)^\s*-\s*audit/", text):
            findings.append("self_hosted_audit_branch_push")
    if re.search(r"(?m)^\s*contents:\s*write\s*$", text) and (
        "sage-result.txt" in text or "gateway/results/" in text
    ):
        findings.append("public_result_commit_risk")
    if "safe.directory=*" in text:
        findings.append("global_git_ownership_bypass")
    return findings

def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: runner_security_audit.py WORKFLOW...")
    found = False
    for path in sys.argv[1:]:
        issues = audit(Path(path).read_text(encoding="utf-8"))
        for issue in issues:
            print(f"{path}: {issue}")
            found = True
    raise SystemExit(1 if found else 0)

if __name__ == "__main__":
    main()
