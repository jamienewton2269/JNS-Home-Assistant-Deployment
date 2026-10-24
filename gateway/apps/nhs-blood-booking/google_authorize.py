"""One-time Google Calendar consent on an approved admin workstation with a browser.

This utility must NOT run on an exposed server, and must never commit or
print the OAuth client JSON or generated token. Copies to the JNS host must
use the separately approved private credential transport.
"""
from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from calendars import FREEBUSY_SCOPE


def main():
    parser = argparse.ArgumentParser(description='Authorise read-only Google Calendar free/busy access')
    parser.add_argument('--person', choices=['me', 'jane'], required=True)
    parser.add_argument('--client', type=Path, required=True, help='Local Google OAuth Desktop client JSON')
    parser.add_argument('--output', type=Path, required=True, help='New token JSON path outside any repository')
    args = parser.parse_args()

    target = args.output.expanduser().absolute()
    if not target.parent.is_dir() or target.exists() or target.is_symlink():
        parser.error('Output folder must exist and token filename must be unused')
    if target.parent.stat().st_mode & 0o077:
        parser.error('Credential directory must have permissions 0700')
    if not args.client.is_file():
        parser.error('OAuth client file does not exist')
    if any((parent / '.git').exists() for parent in [target.parent, *target.parents]):
        parser.error('Never store credentials inside a Git repository')
    print('Google will ask for consent to read only calendar free/busy times.')
    print(f'Confirm you are signing into the authorised {args.person} account.')
    flow = InstalledAppFlow.from_client_secrets_file(str(args.client), [FREEBUSY_SCOPE])
    creds = flow.run_local_server(
        host='127.0.0.1', port=0, open_browser=True,
        access_type='offline', prompt='consent',
    )
    if not creds.refresh_token:
        raise RuntimeError('Google did not issue an offline refresh token; credentials not saved')
    if FREEBUSY_SCOPE not in (creds.scopes or []):
        raise RuntimeError('Google did not grant the required FreeBusy permission')
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(creds.to_json())
            stream.write('\n')
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    print(f'Consent saved for {args.person}. Transfer credential by the approved private JNS path.')
    print('Do not send it through chat, GitHub, email, or deploy logs.')


if __name__ == '__main__':
    main()
