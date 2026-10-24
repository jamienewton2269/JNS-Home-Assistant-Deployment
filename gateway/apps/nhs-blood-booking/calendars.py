"""HTTPS-only read-only iCalendar free/busy adapter (titles never retained)."""
from __future__ import annotations
import os
import ssl
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from planner import Interval, PEOPLE, LOCAL_TZ

MAX_ICS = 4 * 1024 * 1024


def fetch_calendar(person: str, range_start: datetime, range_end: datetime) -> list[Interval]:
    if person not in PEOPLE:
        raise ValueError('Unknown calendar owner')
    url = os.environ.get('JNS_NHS_ICAL_' + person.upper() + '_URL', '')
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise RuntimeError(f'Missing or invalid HTTPS iCalendar URL for {person}')
    # No redirects: avoid leaking bearer-in-URL credentials to a different host.
    from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    try:
        with opener.open(Request(url, headers={'User-Agent': 'JNS-NHS-Booking/0.1'}), timeout=12) as response:
            if response.status != 200:
                raise RuntimeError('Calendar HTTP failure')
            payload = response.read(MAX_ICS + 1)
    except Exception as exc:
        # Do not include URLs or their embedded tokens in error output.
        raise RuntimeError(f'Unable to read {person} calendar: {type(exc).__name__}') from None
    if len(payload) > MAX_ICS:
        raise RuntimeError('Calendar exceeds size limit')
    from icalendar import Calendar
    import recurring_ical_events
    try:
        calendar = Calendar.from_ical(payload)
        events = recurring_ical_events.of(calendar).between(range_start, range_end)
    except Exception:
        raise RuntimeError('Calendar parse failure') from None
    intervals = []
    def to_datetime(raw):
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                raise ValueError('Naive calendar event time; cannot safely compare')
            return raw.astimezone(LOCAL_TZ)
        if isinstance(raw, date):
            return datetime.combine(raw, time.min, LOCAL_TZ)
        raise ValueError('Invalid calendar date')
    for event in events:
        if str(event.get('STATUS', '')).upper() == 'CANCELLED':
            continue
        if str(event.get('TRANSP', '')).upper() == 'TRANSPARENT':
            continue
        ds = event.get('DTSTART')
        if not ds:
            raise RuntimeError('Calendar event without start')
        start = to_datetime(ds.dt)
        de = event.get('DTEND')
        if de:
            end = to_datetime(de.dt)
        elif event.get('DURATION'):
            end = start + event['DURATION'].dt
        else:
            end = start + (timedelta(days=1) if isinstance(ds.dt, date) and not isinstance(ds.dt, datetime) else timedelta(0))
        if end <= start:
            raise RuntimeError('Calendar event with invalid duration')
        intervals.append(Interval(start, end))
    return intervals
