"""Fail-closed data minimisation for Club Manager outbound reference snapshots.

No network, database, or filesystem access. The authoritative system must sign
the filtered output with the existing Ed25519 snapshot contract before export.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Mapping

SCHEMA_VERSION = 1
# Only public racing reference fields; never infer permission from presence.
ALLOWED_FIELDS = frozenset({
    "vessel_id", "display_name", "sail_number", "boat_class",
    "handicap_scheme", "handicap_value", "club_reference",
})
DENIED_FIELDS = frozenset({
    "email", "phone", "address", "date_of_birth", "dob", "payment",
    "bank", "medical", "emergency_contact", "member_id", "crew_names",
    "membership_status", "subscription_status", "notes",
})

class ExportPolicyError(ValueError):
    pass

def make_reference_record(record: Mapping, *, published: bool, consented: bool) -> dict:
    """Export only deliberately published vessels, not member records.

    Both approval flags are supplied by authoritative officer-controlled
    policy; an internet-facing application must never set them.
    """
    if not isinstance(record, Mapping):
        raise ExportPolicyError("Invalid source record")
    if published is not True or consented is not True:
        raise ExportPolicyError("Record not approved for reference publication")
    required = ("vessel_id", "display_name")
    if any(not isinstance(record.get(k), str) or not record[k].strip() for k in required):
        raise ExportPolicyError("Missing reference identity")
    if any(k not in ALLOWED_FIELDS for k in record):
        # Reject unexpected fields rather than silently leaking through future changes.
        raise ExportPolicyError("Unapproved reference field")
    return {k: record[k] for k in sorted(record) if record[k] is not None}

def make_snapshot(records, *, sequence: int, issued_at: datetime) -> dict:
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ExportPolicyError("Invalid sequence")
    if issued_at.tzinfo is None or issued_at.utcoffset() is None:
        raise ExportPolicyError("Timestamp must be timezone-aware")
    if not isinstance(records, (list, tuple)):
        raise ExportPolicyError("Invalid record collection")
    seen = set()
    output = []
    for record in records:
        if not isinstance(record, Mapping) or set(record) - ALLOWED_FIELDS:
            raise ExportPolicyError("Unapproved record shape")
        vessel_id = record.get("vessel_id")
        if not isinstance(vessel_id, str) or not vessel_id.strip() or vessel_id in seen:
            raise ExportPolicyError("Invalid or duplicate vessel")
        seen.add(vessel_id)
        output.append(dict(record))
    return {
        "schema": SCHEMA_VERSION,
        "sequence": sequence,
        "issued_at": issued_at.astimezone(timezone.utc).isoformat(),
        "vessels": sorted(output, key=lambda x: x["vessel_id"]),
    }
