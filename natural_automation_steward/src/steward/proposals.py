from __future__ import annotations

from dataclasses import dataclass, asdict
import re
import time
import threading
import uuid
from typing import Any


@dataclass(slots=True)
class AutomationProposal:
    proposal_id: str
    request: str
    target_entity_id: str
    summary: str
    automation: dict[str, Any]
    unresolved: list[str]
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProposalStore:
    def __init__(self, ttl_seconds: float = 900.0):
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, AutomationProposal] = {}
        self._lock = threading.RLock()

    def put(self, proposal: AutomationProposal) -> AutomationProposal:
        with self._lock:
            self._prune_locked()
            self._items[proposal.proposal_id] = proposal
            return proposal

    def get(self, proposal_id: str) -> AutomationProposal | None:
        with self._lock:
            self._prune_locked()
            return self._items.get(proposal_id)

    def remove(self, proposal_id: str) -> None:
        with self._lock:
            self._items.pop(proposal_id, None)

    def _prune_locked(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for key, value in list(self._items.items()):
            if value.created_at < cutoff:
                self._items.pop(key, None)

    def prune(self) -> None:
        with self._lock:
            self._prune_locked()


def _time_24h(text: str) -> tuple[int, int] | None:
    m = re.search(r"\bat\s+([01]?\d|2[0-3]):([0-5]\d)\b", text, flags=re.I)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.search(
        r"\bat\s+(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b",
        text,
        flags=re.I,
    )
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3).lower() == "pm":
        hour += 12
    return hour, minute


def _duration(text: str) -> tuple[dict[str, int], str] | None:
    m = re.search(
        r"\bfor\s+(\d+)\s*(min|mins|minute|minutes|hr|hrs|hour|hours)\b",
        text,
        flags=re.I,
    )
    if not m:
        return None
    amount = int(m.group(1))
    if amount < 1:
        return None
    unit = m.group(2).lower()
    if unit in {"hr", "hrs", "hour", "hours"}:
        if amount > 24:
            return None
        return {"hours": amount}, f"{amount} hour" + ("" if amount == 1 else "s")
    if amount > 1440:
        return None
    return {"minutes": amount}, f"{amount} minute" + ("" if amount == 1 else "s")


def build_automation_proposal(
    request: str,
    target_entity_id: str,
    display_name: str | None = None,
) -> AutomationProposal | None:
    """Build only patterns that can be translated without assumptions.

    v1 deliberately supports the proven test shape:
      "turn on <target> at HH:MM for N minutes/hours"
    and equivalent 12-hour clock forms.
    """

    parsed_time = _time_24h(request)
    parsed_duration = _duration(request)
    if not parsed_time or not parsed_duration:
        return None

    domain = target_entity_id.split(".", 1)[0] if "." in target_entity_id else ""
    if domain not in {"light", "switch", "fan", "input_boolean"}:
        return None

    hour, minute = parsed_time
    delay, duration_text = parsed_duration
    at = f"{hour:02d}:{minute:02d}:00"
    name = display_name or target_entity_id
    alias = f"Natural Automation - {name} - {hour:02d}:{minute:02d} for {duration_text}"

    automation = {
        "alias": alias,
        "description": f"Created by Natural Automation from request: {request}",
        "trigger": [{"platform": "time", "at": at}],
        "condition": [],
        "action": [
            {"service": f"{domain}.turn_on", "target": {"entity_id": target_entity_id}},
            {"delay": delay},
            {"service": f"{domain}.turn_off", "target": {"entity_id": target_entity_id}},
        ],
        "mode": "single",
    }

    return AutomationProposal(
        proposal_id=uuid.uuid4().hex,
        request=request,
        target_entity_id=target_entity_id,
        summary=(
            f"At {hour:02d}:{minute:02d}, turn on {target_entity_id} "
            f"for {duration_text}, then turn it off."
        ),
        automation=automation,
        unresolved=[],
        created_at=time.time(),
    )
