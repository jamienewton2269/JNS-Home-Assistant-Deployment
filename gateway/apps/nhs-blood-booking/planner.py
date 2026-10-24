"""Safe local planning for Mersey Care blood-test booking; no NHS submissions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo('Europe/London')
CLINICS = frozenset({
    'Ainsdale Centre for Health and Wellbeing',
    'Churchtown Clinic',
    'Formby Clinic',
    'Southport Centre for Health and Wellbeing',
})
PEOPLE = frozenset({'me', 'jane'})


def date_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError('Appointment/event timestamps must specify a UTC offset')
    return dt.astimezone(LOCAL_TZ)


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or self.end <= self.start:
            raise ValueError('Invalid time interval')

    def collides(self, other: 'Interval') -> bool:
        return self.start < other.end and other.start < self.end

    def padded(self, before: int, after: int) -> 'Interval':
        return Interval(self.start - timedelta(minutes=before), self.end + timedelta(minutes=after))


@dataclass(frozen=True)
class Slot:
    slot_id: str
    clinic: str
    window: Interval


def parse_slots(path: Path, *, now: datetime | None = None, max_age_minutes: int = 10) -> list[Slot]:
    """Only accept recently observed candidates. They remain UNCONFIRMED until NHS receipt."""
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('provider') != 'merseycare-southport-formby':
        raise ValueError('Unexpected booking provider')
    observed = date_time(data['observed_at'])
    now = (now or datetime.now(timezone.utc)).astimezone(LOCAL_TZ)
    if observed > now + timedelta(seconds=30) or now - observed > timedelta(minutes=max_age_minutes):
        raise ValueError('Availability observation is stale or dated in the future')
    slots = []
    seen = set()
    for item in data['slots']:
        key = item['id']
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('Missing or duplicate booking slot ID')
        seen.add(key)
        clinic = item['clinic']
        if clinic not in CLINICS:
            raise ValueError('Unknown clinic: ' + str(clinic))
        window = Interval(date_time(item['start']), date_time(item['end']))
        if window.start <= now:
            continue
        if window.start.date() != window.end.date():
            raise ValueError('Appointment spans calendar days')
        slots.append(Slot(key, clinic, window))
    return sorted(slots, key=lambda s: (s.window.start, s.clinic, s.slot_id))


def candidates(slots: Iterable[Slot], who: str, busy: dict[str, list[Interval]],
               before: int = 20, after: int = 20, max_gap: int = 0) -> list[dict]:
    """Require all relevant calendars to be present. For 'both', shared trip covers both slots."""
    if who not in {'me', 'jane', 'both'}:
        raise ValueError('who must be me, jane or both')
    if min(before, after, max_gap) < 0 or max_gap > 30:
        raise ValueError('Invalid travel buffer or appointment gap')
    attendees = ['me', 'jane'] if who == 'both' else [who]
    for person in attendees:
        if person not in busy:
            raise ValueError('Calendar for ' + person + ' unavailable; refuse to guess availability')
    slots = list(slots)
    results = []
    def free(window: Interval) -> bool:
        trip = window.padded(before, after)
        return all(not trip.collides(ev) for person in attendees for ev in busy[person])
    if who != 'both':
        for s in slots:
            if free(s.window):
                results.append({'clinic': s.clinic, 'slots': [{'person': who, 'slot_id': s.slot_id,
                    'start': s.window.start.isoformat(), 'end': s.window.end.isoformat()}]})
    else:
        for i, first in enumerate(slots):
            for second in slots[i+1:]:
                if first.clinic != second.clinic or first.window.start.date() != second.window.start.date():
                    continue
                gap = (second.window.start - first.window.end).total_seconds() / 60
                if gap < 0 or gap > max_gap:
                    continue
                journey = Interval(first.window.start, second.window.end)
                if not free(journey):
                    continue
                for a, b in (('me', 'jane'), ('jane', 'me')):
                    results.append({'clinic': first.clinic, 'slots': [
                        {'person': a, 'slot_id': first.slot_id, 'start': first.window.start.isoformat(), 'end': first.window.end.isoformat()},
                        {'person': b, 'slot_id': second.slot_id, 'start': second.window.start.isoformat(), 'end': second.window.end.isoformat()}]})
    return results
