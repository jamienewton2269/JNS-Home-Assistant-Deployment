"""Fail-closed, dependency-free validation for proposed gateway v2 jobs.

This module is not wired into the production runner.
"""
import json
import re

JOB_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,95}$")
ALLOWED = frozenset({"capabilities", "health", "git_status", "test", "build"})
MAX_BYTES = 8192

class JobRejected(ValueError):
    pass

def validate(payload):
    if isinstance(payload, bytes):
        if len(payload) > MAX_BYTES:
            raise JobRejected("payload_too_large")
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            raise JobRejected("invalid_encoding") from None
    if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_BYTES:
        raise JobRejected("invalid_payload")
    try:
        job = json.loads(payload)
    except (ValueError, TypeError):
        raise JobRejected("invalid_json") from None
    if not isinstance(job, dict) or set(job) != {"schema_version", "job_id", "job_type"}:
        raise JobRejected("invalid_fields")
    if type(job["schema_version"]) is not int or job["schema_version"] != 2:
        raise JobRejected("unsupported_schema")
    if not isinstance(job["job_id"], str) or not JOB_ID.fullmatch(job["job_id"]):
        raise JobRejected("invalid_job_id")
    if not isinstance(job["job_type"], str) or job["job_type"] not in ALLOWED:
        raise JobRejected("job_type_not_allowed")
    return job
