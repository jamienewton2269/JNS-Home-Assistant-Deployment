"""JNS heating 0.3.5 root-owned promotion policy.

Pure validation helpers with no I/O; shared by the privileged dispatcher and
offline tests. GitHub queue data is *untrusted*, even on a private network.
"""
from __future__ import annotations
from datetime import datetime, timezone
import re

STAGE_ID="v035-20261024T162546Z-43b0f6ec"
CANDIDATE_SHA="43b0f6ec0229d15dc137bbf3c52cd41b4bb125072fbcc49202e744ba8a19bc6c"
BASELINE_SHA="44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8"
JOB_TYPE="ha_heating_v035_promote"
APPROVAL_OPERATION="one_time_heating_maintenance"

class PolicyDenied(RuntimeError): pass

def approve(job, permit, now=None):
    if not isinstance(job,dict) or set(job)!={"job_id","job_type","stage_id"}:
        raise PolicyDenied("job fields not strictly allowlisted")
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-heating-v035-[0-9a-f]{6}",str(job["job_id"])):
        raise PolicyDenied("invalid immutable heating job identifier")
    if job["job_type"]!=JOB_TYPE or job["stage_id"]!=STAGE_ID:
        raise PolicyDenied("wrong job type or pinned stage")
    if not isinstance(permit,dict) or set(permit)!={
        "operation","stage_id","candidate_sha","expires_utc","heating_outage_approved","job_id"}:
        raise PolicyDenied("local root approval fields invalid")
    if permit["job_id"]!=job["job_id"]:
        raise PolicyDenied("local maintenance permit not bound to exact immutable job")
    if permit["operation"]!=APPROVAL_OPERATION or permit["stage_id"]!=STAGE_ID:
        raise PolicyDenied("local maintenance approval not for this stage")
    if permit["candidate_sha"]!=CANDIDATE_SHA or permit["heating_outage_approved"] is not True:
        raise PolicyDenied("candidate signature or maintenance consent invalid")
    try:
        expiry=datetime.fromisoformat(permit["expires_utc"])
    except (TypeError,ValueError):
        raise PolicyDenied("invalid maintenance expiry") from None
    if expiry.tzinfo is None:
        raise PolicyDenied("approval expiry has no timezone")
    now=now or datetime.now(timezone.utc)
    seconds=(expiry-now).total_seconds()
    if not 0 < seconds <= 900:
        raise PolicyDenied("local maintenance approval not within fifteen minutes")
    return True
