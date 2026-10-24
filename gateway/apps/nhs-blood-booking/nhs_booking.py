"""JNS blood-test booking CLI. All NHS appointment submissions are deliberately disabled."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from planner import candidates, parse_slots, LOCAL_TZ

URL = 'https://www.merseycare.nhs.uk/bloodtestsouthportformby'


def inspect() -> int:
    """Inspect public booking page only; do not capture medical fields, state or screenshots."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=False, service_workers='block')
        try:
            page = context.new_page()
            page.goto(URL, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2500)
            from urllib.parse import urlsplit
            frames = sorted({urlsplit(f.url).hostname for f in page.frames if f.url.startswith('https://')})
            print(json.dumps({'source': URL, 'title': page.title(), 'frame_hosts': frames,
                              'status': 'DISCOVERY ONLY: selectors and NHS submission not commissioned'}, indent=2))
        finally:
            context.close()
            browser.close()
    return 0


def select_patients(explicit: str | None) -> str:
    """Ask for the patients on every interactive request; never infer from an earlier booking."""
    if explicit:
        return explicit
    if not sys.stdin.isatty():
        raise RuntimeError('Select --who me, jane or both in non-interactive mode')
    print('Who needs the NHS blood test?')
    print('  1. Just me')
    print('  2. Just Jane')
    print('  3. Both — consecutive appointments')
    selection = input('Choose 1, 2 or 3: ').strip()
    if selection not in {'1','2','3'}:
        raise ValueError('Choose 1, 2 or 3')
    return {'1': 'me', '2': 'jane', '3': 'both'}[selection]


def propose(args) -> int:
    args.who = select_patients(args.who)
    now = datetime.now(timezone.utc).astimezone(LOCAL_TZ)
    slots = parse_slots(Path(args.slots), now=now)
    if not slots:
        raise RuntimeError('No fresh candidate slots from the provider')
    from calendars import fetch_calendar
    people = ('me', 'jane') if args.who == 'both' else (args.who,)
    until = max(s.window.end for s in slots) + timedelta(minutes=args.after + 1)
    start = now - timedelta(days=1)
    busy = {person: fetch_calendar(person, start, until) for person in people}
    plans = candidates(slots, args.who, busy, args.before, args.after, args.max_gap)
    print(json.dumps({'status': 'CANDIDATES ONLY — NOT BOOKED; requires approval and NHS confirmation',
                      'source_observed_at': json.loads(Path(args.slots).read_text())['observed_at'],
                      'patient_selection': args.who, 'candidate_count': len(plans),
                      'top_candidates': plans[:args.limit]}, indent=2))
    return 0 if plans else 2


def main() -> int:
    parser = argparse.ArgumentParser(description='JNS Southport NHS appointment planner — no booking submission')
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('inspect', help='Inspect public website structure using Playwright')
    proposal = subs.add_parser('propose', help='Calendar-safe proposals from fresh, observed NHS slots')
    proposal.add_argument('--who', choices=['me', 'jane', 'both'], help='Omit in a terminal to be asked who needs appointments')
    proposal.add_argument('--slots', required=True)
    proposal.add_argument('--before', type=int, default=20, help='Travel buffer before, minutes')
    proposal.add_argument('--after', type=int, default=20, help='Travel buffer after, minutes')
    proposal.add_argument('--max-gap', type=int, default=0, help='Maximum gap between two appointments, minutes')
    proposal.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    if args.command == 'inspect':
        return inspect()
    if args.limit < 1 or args.limit > 20:
        parser.error('--limit must be 1 to 20')
    return propose(args)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        # Intentionally never log request bodies, iCalendar URLs or patient identifiers.
        print(f'JNS NHS BOOKING STOPPED: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
