"""Google Calendar FreeBusy adapter: no event titles, attendees or descriptions are requested.

Each person must explicitly authorise a read-only Google Calendar credential or
share the relevant calendars with an already authorised account. No calendar
details are persisted, and any API/permission failure blocks a proposal.
"""
from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials

from planner import Interval, PEOPLE, date_time, LOCAL_TZ

FREEBUSY_SCOPE = 'https://www.googleapis.com/auth/calendar.events.freebusy'
GOOGLE_ENDPOINT = 'https://www.googleapis.com/calendar/v3/freeBusy'
MAX_CALENDARS = 20


def _secret_path(person: str) -> Path:
    key = f'JNS_NHS_GOOGLE_TOKEN_{person.upper()}_FILE'
    raw = os.environ.get(key, '')
    if not raw or not Path(raw).is_absolute():
        raise RuntimeError(f'{person} Google calendar authorisation is not configured')
    path = Path(raw)
    try:
        mode = path.lstat()
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077:
            raise ValueError('credential file must be regular and readable only by its owner')
        if mode.st_uid not in (os.geteuid(), 0):
            raise ValueError('credential file owner is untrusted')
    except (OSError, ValueError):
        raise RuntimeError(f'Unsafe or missing {person} calendar credential') from None
    return path


def _calendar_ids(person: str) -> list[str]:
    raw = os.environ.get(f'JNS_NHS_GOOGLE_CALENDAR_IDS_{person.upper()}', '')
    ids = [part.strip() for part in raw.split(',') if part.strip()]
    if not ids or len(ids) > MAX_CALENDARS or len(set(ids)) != len(ids):
        raise RuntimeError(f'{person} Google calendar IDs must be configured uniquely (1–20)')
    if any(any(c in cal for c in '\r\n\t') or len(cal) > 254 for cal in ids):
        raise RuntimeError(f'{person} Google calendar ID is invalid')
    return ids


def parse_freebusy(body: dict, ids: list[str]) -> list[Interval]:
    """Fail closed on partial Google responses, calendar errors or invalid periods."""
    if not isinstance(body, dict) or body.get('groups'):
        raise RuntimeError('Unexpected Google free/busy response')
    calendars = body.get('calendars')
    if not isinstance(calendars, dict):
        raise RuntimeError('Google free/busy did not return calendars')
    busy = []
    for cal in ids:
        result = calendars.get(cal)
        if not isinstance(result, dict) or result.get('errors'):
            raise RuntimeError('Missing or inaccessible Google calendar')
        if not isinstance(result.get('busy'), list):
            raise RuntimeError('Malformed Google calendar busy periods')
        for period in result['busy']:
            if not isinstance(period, dict):
                raise RuntimeError('Malformed Google calendar busy period')
            try:
                busy.append(Interval(date_time(period['start']), date_time(period['end'])))
            except (ValueError, TypeError, KeyError):
                raise RuntimeError('Invalid Google calendar busy period') from None
    return busy


def fetch_calendar(person: str, range_start: datetime, range_end: datetime) -> list[Interval]:
    if person not in PEOPLE:
        raise ValueError('Unknown patient')
    if (range_start.tzinfo is None or range_end.tzinfo is None or
            range_end <= range_start or (range_end-range_start).days > 62):
        raise ValueError('Invalid Google calendar query range')
    token_file = _secret_path(person)
    ids = _calendar_ids(person)
    try:
        credentials = Credentials.from_authorized_user_file(str(token_file), scopes=[FREEBUSY_SCOPE])
        if not credentials.valid:
            if not credentials.refresh_token:
                raise RuntimeError('Offline calendar authorisation missing')
            credentials.refresh(GoogleAuthRequest())
        if not credentials.valid or FREEBUSY_SCOPE not in (credentials.scopes or []):
            raise RuntimeError('Google calendar authorisation is not valid')
        response = requests.post(
            GOOGLE_ENDPOINT,
            json={'timeMin': range_start.isoformat(), 'timeMax': range_end.isoformat(),
                  'timeZone': 'Europe/London', 'items': [{'id': x} for x in ids]},
            headers={'Authorization': f'Bearer {credentials.token}',
                     'Content-Type': 'application/json'},
            timeout=(5, 12), allow_redirects=False,
        )
        if response.status_code != 200:
            raise RuntimeError('Google calendar request failed')
        return parse_freebusy(response.json(), ids)
    except Exception:
        # Never log the token, response body, calendar IDs or Google account details.
        raise RuntimeError(f'Google calendar free/busy check failed for {person}') from None
