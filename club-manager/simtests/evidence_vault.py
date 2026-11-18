"""Offline, synthetic-only acceptance of encrypted evidence.

CT101 uses *public key only*. Private key remains on Node C.
No HTTP upload or retrieval. No mail. No real insurance documents.
"""
from pathlib import Path
from datetime import date
import os, hashlib, uuid, json, base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization
import psycopg2
from contextlib import closing

PUBLIC_KEY='/opt/jns-club-beta/simtests/gc-evidence-public.pem'
VESSEL='e1000000-0000-4000-8000-000000000001'

def synthetic_pdf(addendum=""):
    text=("FICTIONAL SAMPLE - NOT ACTUAL INSURANCE\n"
          "SYNTH Sea Finch\nSample Marine Insurance\n"
          "SIM-POLICY-VAULT-1\nCover: 09/11/2026 to 09/11/2027\n"
          "No real member or insurer involved." + str(addendum))
    esc=text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)').replace('\n',') Tj 0 -15 Td (')
    content=('BT /F1 11 Tf 30 740 Td ('+esc+') Tj ET').encode()
    objects=[
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    data=b'%PDF-1.4\n'; offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data))
        data+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref=len(data);data+=f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    for pos in offsets[1:]: data+=f'{pos:010d} 00000 n \n'.encode()
    data+=f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return data

def seal(public_pem,plaintext,vessel):
    if not plaintext.startswith(b'%PDF-') or len(plaintext)>512*1024:
        raise ValueError('Invalid synthetic PDF')
    key=serialization.load_pem_public_key(public_pem)
    content_key=os.urandom(32)
    nonce=os.urandom(12)
    digest=hashlib.sha256(plaintext).digest()
    associated_data=uuid.UUID(vessel).bytes+digest
    sealed=nonce+AESGCM(content_key).encrypt(nonce,plaintext,associated_data)
    wrapped=key.encrypt(content_key,padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),label=None))
    return sealed,wrapped,digest

def main():
    plaintext=synthetic_pdf()
    sealed,wrapped,digest=seal(Path(PUBLIC_KEY).read_bytes(),plaintext,VESSEL)
    with closing(psycopg2.connect('dbname=club_manager_simtest user=postgres')) as db:
        with db:
            with db.cursor() as cur:
                cur.execute("""INSERT INTO simtest.vessel_insurance
                (vessel_id,document_sha256,sealed_document,wrapped_key,insurer,
                 policy_ref,cover_from,cover_until,source,validation_state,validation_notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'synthetic_officer','needs_review',%s)
                RETURNING id""",(
                    VESSEL,psycopg2.Binary(digest),psycopg2.Binary(sealed),
                    psycopg2.Binary(wrapped),'Sample Marine Insurance','SIM-POLICY-VAULT-1',
                    '2026-11-09','2027-11-09',
                    'Fictional ciphertext acceptance only; not proof of insurance'))
                insurance_id=cur.fetchone()[0]
                cur.execute("""INSERT INTO simtest.vault_acceptance_events
                    (insurance_id,action,notes) VALUES (%s,'sealed',%s)""",(
                    insurance_id,'RSA-OAEP-3072/AES-256-GCM synthetic acceptance'))
    print(json.dumps({'insurance_id':str(insurance_id),'sha256':digest.hex(),
          'sealed_bytes':len(sealed),'wrapped_bytes':len(wrapped),
          'plaintext_stored':False,'source':'fictional'},sort_keys=True))
if __name__=='__main__':main()
