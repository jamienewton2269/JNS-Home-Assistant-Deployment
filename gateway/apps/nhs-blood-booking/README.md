# JNS NHS Blood Test Booking — staged v0.1

A **non-submitting** browser discovery and calendar-safe appointment planner for the official Mersey Care Southport and Formby blood test service.

Official page: https://www.merseycare.nhs.uk/bloodtestsouthportformby

## Status and limitations

- **Implemented**: `me` / `jane` / `both` choices; find adjacent pairs at same clinic; check both diaries over the entire shared trip with before/after travel buffers; reject unavailable calendars, unknown clinics, ambiguous timestamps and stale availability; NHS public page inspection with Playwright; tests.
- **Not implemented, deliberately disabled**: verified live slot extraction from NHS/SimplyBook, entering patient details, submitting or cancelling appointments, parsing confirmation email/SMS, or writing calendar events. No site-specific selectors or booking endpoint have been validated. This package **cannot yet book an NHS appointment**.
- A pair of slots is a **proposal only**. Mersey Care may require separate submissions; two consecutive bookings cannot be atomic. If booking one succeeds and the other fails, the correct future behaviour is to stop, show the confirmed one, and obtain fresh approval before changes.
- Appointment availability feeds must come from authorised live inspection of the real NHS page. Never fabricate a candidate record and present it as real availability.

## Safe commissioning checklist

1. Provision an isolated, resource-limited JNS service container on an approved host (prefer Node B if capacity allows); do not install Playwright on HA-Primary VM902 or HA-General VM905. No fixed IP or DHCP reservation; DNS-first policy.
2. Commission through the **existing JNS GitHub signed/guarded deployment pathway**. Inventory the actual package schema, target container and root-owned deploy wrapper, then pin source hash, run dry-run, backup, stage, verify and enable rollback. This repository folder is source material, **not** an authorised deployment action.
3. Install `requirements.txt` inside a dedicated unprivileged environment; install Playwright Chromium after confirming available storage. Allow outbound HTTPS only to the official booking provider and read-only calendar servers. Do not publish a browser debugging port to the Internet.
4. Set the secret, read-only calendar URLs as environment variables `JNS_NHS_ICAL_ME_URL` and (with Jane's permission) `JNS_NHS_ICAL_JANE_URL`. Store in root-readable secret store, **not** in GitHub or the command line; enforce `0600` for credentials and avoid backups containing patient data. An unavailable diary prevents a proposal.
5. `python nhs_booking.py inspect` inspects only public NHS browser structure; no patient entry or website submission.
6. Independently verify the actual NHS booking widget and provider authorisation before writing a site adapter. Use a local approval screen and explicit consent per patient. Respect rate limits; never bypass CAPTCHA, access controls or confirmation steps.
7. Only after approved live booking validation: extract authoritative slots, recheck calendar immediately before submission, stop on any discrepancy, store confirmation ID locally encrypted, then create private calendar events. For two people confirm each appointment separately and never roll back a valid first appointment automatically.

## Usage

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python nhs_booking.py inspect
PYTHONPATH=. python -m unittest discover -s tests -v
python nhs_booking.py propose --slots /secure/nhs-observed-slots.json  # asks me/Jane/both
python nhs_booking.py propose --who both --slots /secure/nhs-observed-slots.json --before 20 --after 20
```

The `--slots` input is a short-lived internal handoff format for the future verified provider adapter, **not** a user-maintained file. It must identify genuine slot IDs and include UTC offsets:

```json
{
  "provider": "merseycare-southport-formby",
  "observed_at": "2026-11-03T09:00:00Z",
  "slots": [
    {"id": "provider-id-1", "clinic": "Churchtown Clinic", "start": "2026-11-05T09:00:00+00:00", "end": "2026-11-05T09:10:00+00:00"},
    {"id": "provider-id-2", "clinic": "Churchtown Clinic", "start": "2026-11-05T09:10:00+00:00", "end": "2026-11-05T09:20:00+00:00"}
  ]
}
```

Example data above is illustrative **only**. `observed_at` must be within ten minutes of the current clock or the program stops.

All displayed candidate times use Europe/London with DST-aware timestamps. Existing diaries must expose all-day, recurring and time-zoned commitments via read-only HTTPS ICS feeds. No event titles or health details are printed. Free/busy URL credentials must be treated as secrets. The planner does not guarantee two bookings will remain available when NHS submissions begin.

## Public reference

NHS guidance says confirmation email/SMS is required to demonstrate a successful request and patients should bring the blood test request form. Urgent bookings must be arranged via the referring GP. Phone alternative: 0151 285 4548.
