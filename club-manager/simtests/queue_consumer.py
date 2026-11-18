"""Synthetic-only one-at-a-time insurance queue consumer; no upload endpoint.
Holds one PostgreSQL session advisory lock across scanner processing.
"""
import json, sys
from contextlib import closing
import psycopg2
from evidence_vault import synthetic_pdf
from synthetic_admission import intake

def main():
    with closing(psycopg2.connect('dbname=club_manager_simtest user=clubintake')) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute('SELECT simtest.claim_synthetic_intake()')
                job=cur.fetchone()[0]
        if job.get('empty') or job.get('busy'):
            print(json.dumps(job,sort_keys=True),flush=True)
            return
        # The producer can select only a known FICTIONAL fixture tag.
        tag=job['fixture_tag']
        if not tag.startswith('SIM-QUEUE-'):
            raise RuntimeError('Non-synthetic queue item')
        decision='failed'
        outcome={'stored':False}
        try:
            pdf=synthetic_pdf(' Restricted queue fixture '+tag)
            outcome=intake(pdf)
            decision=outcome['decision']
        except Exception as exc:
            print(json.dumps({'job_id':job['job_id'],
                'failure_type':type(exc).__name__,'status':'failed'},sort_keys=True),flush=True)
        with conn:
            with conn.cursor() as cur:
                cur.execute('SELECT simtest.finish_synthetic_intake(%s::uuid,%s,%s::jsonb)',
                    (job['job_id'],decision,json.dumps({'stored':outcome.get('stored',False)})))
                assert cur.fetchone()[0] is True
        print(json.dumps({'job_id':job['job_id'],'decision':decision,
            'stored':bool(outcome.get('stored')),'fixture_only':True},sort_keys=True),flush=True)

if __name__=='__main__':
    main()
