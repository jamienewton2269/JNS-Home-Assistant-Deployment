"""CT101 synthetic-only offline PDF intake acceptance.
No HTTP route, real member documents, email or decrypt API.
Plaintext exists only in caller memory; no uploaded PDF is saved to disk.
"""
from pathlib import Path
from contextlib import closing
from uuid import UUID
import hashlib, json
import psycopg2
from psycopg2 import Binary
from insurance_preflight import preflight, extract_pdf
from insurance_scan import malware_scan, reject_active_pdf
from evidence_vault import seal, PUBLIC_KEY

SYNTHETIC_VESSEL='e1000000-0000-4000-8000-000000000001'
FIELDS={'filename':'fictional-policy.pdf','vessel_name':'SYNTH Sea Finch',
        'insurer':'Sample Marine Insurance','policy_ref':'SIM-POLICY-VAULT-1',
        'cover_from':'2026-11-09','cover_until':'2027-11-09'}
def audit(db,vessel,decision,reason,content_hash=None,insurance_id=None):
    with db.cursor() as cur:
        cur.execute("SELECT simtest.record_synthetic_intake_event(%s,%s,%s,%s)",
            (vessel,decision,reason,Binary(content_hash)))
def intake(pdf,fields=None,vessel=SYNTHETIC_VESSEL):
    # Explicit synthetic-only gate. No function in the web simulation calls this.
    fields=FIELDS if fields is None else fields
    if str(vessel)!=SYNTHETIC_VESSEL:raise ValueError('Synthetic vessel only')
    if b'FICTIONAL SAMPLE - NOT ACTUAL INSURANCE' not in pdf:
        raise ValueError('Synthetic evidence marker required')
    digest=hashlib.sha256(pdf).digest()
    with closing(psycopg2.connect('dbname=club_manager_simtest user=clubintake')) as db:
        with db:
            audit(db,vessel,'quarantined','memory_only_pending_checks',digest)
        try:
            # Reject obvious unsafe features before invoking the signature scanner.
            reject_active_pdf(pdf)
            import base64
            payload=dict(fields,pdf_base64=base64.b64encode(pdf).decode())
            result=preflight(payload)
            if result['matched_fields']!=result['required_fields']:
                raise ValueError('policy_fields_mismatch')
            if result['review_state']!='needs_review':
                raise AssertionError('No document may be automatically validated')
        except Exception as exc:
            reason='malware_or_structure_rejected' if 'policy_fields_mismatch' not in str(exc) else 'policy_fields_mismatch'
            with db:
                audit(db,vessel,'rejected',reason,digest)
            return {'decision':'rejected','reason':reason,'stored':False}
        sealed,wrapped,sealed_digest=seal(Path(PUBLIC_KEY).read_bytes(),pdf,vessel)
        assert sealed_digest==digest
        with db:
            with db.cursor() as cur:
                cur.execute("""SELECT simtest.admit_synthetic_encrypted_evidence(
                  %s,%s,%s,%s,%s,%s,%s,%s)""",
                  (vessel,Binary(digest),Binary(sealed),Binary(wrapped),
                   fields['insurer'],fields['policy_ref'],
                   fields['cover_from'],fields['cover_until']))
                return cur.fetchone()[0]

def acceptance():
    from evidence_vault import synthetic_pdf
    valid=synthetic_pdf(" Quarantine acceptance 2026-11-09 case C restricted worker")
    first=intake(valid)
    second=intake(valid)
    assert first['decision'] in ('needs_review','duplicate'),first
    assert second['decision']=='duplicate',second
    assert not second['stored']
    bad=valid.replace(b'/Type /Catalog',b'/Type /Catalog /OpenAction << /S /JavaScript /JS (x) >>',1)
    unsafe=intake(bad)
    assert unsafe['decision']=='rejected',unsafe
    print(json.dumps({'initial':first['decision'],'resubmission':second['decision'],
      'active_pdf':unsafe['decision'],'no_plaintext_persisted':True,
      'automatic_insurance_verification':False,'real_upload_endpoint':False},sort_keys=True))
if __name__=='__main__':
    acceptance()
