#!/usr/bin/env python3
"""Club Manager controlled handover gate.

Preflight fails closed until both temporary accounts are gone.
--dry-run performs the *real* cleanup SQL in one rollback-only transaction.
--execute performs the same cleanup transaction only with a deliberate
commissioning confirmation. No CASCADE and no audit-history bypass.
"""
import argparse
import sys
import psycopg2
from psycopg2 import sql

EMAILS=('itadmin1@beta.invalid','itadmin2@beta.invalid')
DELETE_ORDER=(
    'officer_api_sessions',
    'officer_webauthn_challenges',
    'officer_webauthn_credentials',
    'officer_authenticator_registry',
    'committee_permission_grants',
    'committee_role_grants',
    'officer_mfa_sessions',
    'committee_accounts',
)

def remaining(c):
    c.execute("""SELECT id::text,display_name,account_state
                   FROM club.committee_accounts
                  WHERE lower(email)=ANY(%s)
               ORDER BY display_name""",(list(EMAILS),))
    return c.fetchall()

def clean(c):
    # Explicit account-scoped deletion only. FK errors leave the transaction
    # unchanged and signal that legal/audit retention needs review.
    c.execute("SELECT id FROM club.committee_accounts WHERE lower(email)=ANY(%s) FOR UPDATE",(list(EMAILS),))
    ids=[r[0] for r in c.fetchall()]
    if not ids: return []
    for table in DELETE_ORDER:
        if table=='committee_accounts':
            c.execute("DELETE FROM club.committee_accounts WHERE id=ANY(%s::uuid[])",(ids,))
        else:
            c.execute(sql.SQL("DELETE FROM club.{} WHERE account_id=ANY(%s::uuid[])").format(sql.Identifier(table)),(ids,))
    if remaining(c):
        raise RuntimeError('Temporary officer rows still exist')
    return ids

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',default='club_manager',choices=['club_manager','club_manager_simtest'])
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--check',action='store_true')
    choice.add_argument('--dry-run',action='store_true')
    choice.add_argument('--execute',action='store_true')
    parser.add_argument('--confirm',default='')
    args=parser.parse_args()
    if args.execute and args.confirm!='REMOVE-TEMP-ITADMINS-AT-CLUB-HANDOVER':
        parser.error('Explicit club handover confirmation is required')
    with psycopg2.connect(dbname=args.database,user='postgres') as conn:
        try:
            with conn.cursor() as c:
                before=remaining(c)
                print('database:',args.database,'temporary accounts:',len(before))
                for _,label,state in before:print('  ',label,state)
                if args.check:
                    if before:
                        print('HANDOVER BLOCKED: temporary officers still present')
                        return 2
                    print('PASS: temporary officer identities absent')
                    return 0
                deleted=clean(c)
                print('cleanup SQL succeeded; accounts targeted:',len(deleted))
                if args.dry_run:
                    conn.rollback()
                    print('DRY RUN: full transaction rolled back, no committed change')
                    return 0
                conn.commit()
                print('COMMITTED: temporary officer identities removed')
                return 0
        except Exception as exc:
            conn.rollback()
            print('HANDOVER BLOCKED; full cleanup rolled back:',type(exc).__name__,str(exc).splitlines()[0],file=sys.stderr)
            return 3

if __name__=='__main__':
    sys.exit(main())
