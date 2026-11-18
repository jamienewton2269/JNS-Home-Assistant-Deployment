"""Transient, synthetic insurance-PDF malware checks. No evidence persistence.

Fail closed on missing/stale signatures, ClamAV errors, PDF parser failures,
or suspicious active-content indicators. Clean does NOT validate insurance.
"""
from pathlib import Path
import subprocess, datetime, os
from insurance_preflight import extract_pdf
DB=Path('/var/lib/clamav')
MAX_SIZE=512*1024
def reject_active_pdf(pdf):
 """Validate and normalise PDF structure before rejecting active-content names."""
 import re
 checks=('/JavaScript','/JS','/Launch','/EmbeddedFiles','/EmbeddedFile',
  '/OpenAction','/RichMedia','/XFA','/AcroForm','/AA','/SubmitForm','/GoToR')
 fd=os.memfd_create('jns-insurance-inspection',flags=0)
 try:
  os.write(fd,pdf)
  path='/proc/self/fd/'+str(fd)
  try:
   os.lseek(fd,0,os.SEEK_SET)
   checked=subprocess.run(['/usr/bin/qpdf','--check',path],pass_fds=(fd,),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=6,check=False)
   os.lseek(fd,0,os.SEEK_SET)
   normalised=subprocess.run(['/usr/bin/qpdf','--qdf','--object-streams=disable',path,'-'],
        pass_fds=(fd,),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8,check=False)
  except (OSError,subprocess.TimeoutExpired):
   raise ValueError('PDF structure verification did not complete')
 finally:
  os.close(fd)
 if checked.returncode!=0 or normalised.returncode!=0 or len(normalised.stdout)>3*1024*1024:
  raise ValueError('Malformed or unsupported PDF structure')
 # PDF names are token-level; reject conservatively rather than risk active content.
 for token in checks:
  if re.search(rb'(?<![A-Za-z0-9])'+re.escape(token.encode())+rb'(?![A-Za-z0-9])',normalised.stdout):
   raise ValueError('PDF contains prohibited active or embedded content')
 return True

def malware_scan(pdf):
 if not isinstance(pdf,bytes) or not 100<=len(pdf)<=MAX_SIZE or not pdf.startswith(b'%PDF-'):
  raise ValueError('PDF required, max 512 KiB')
 if not any((DB/name).exists() for name in ('daily.cvd','daily.cld')):
  raise RuntimeError('Signature database unavailable; intake closed')
 # Staleness is enforced by ClamAV as well as check exit status.
 # A single ClamAV scan avoids repeatedly loading 100+ MB of signatures.
 command=['/usr/bin/clamscan','--stdout','--no-summary','--scan-pdf=yes',
      '--max-filesize=1M','--max-scansize=3M','--max-files=100',
      '--fail-if-cvd-older-than=3','-']
 try:
  result=subprocess.run(command,input=pdf,stdout=subprocess.PIPE,
       stderr=subprocess.PIPE,timeout=40,check=False)
 except (OSError,subprocess.TimeoutExpired):
  raise RuntimeError('Malware scanner unavailable; intake closed')
 if result.returncode==1:
  return {'malware':'detected','accepted':False}
 if result.returncode!=0 or b'OK' not in result.stdout:
  raise RuntimeError('Malware scanner unavailable, outdated or inconclusive; intake closed')
 reject_active_pdf(pdf)
 # Consistency parser is a second independent hurdle. It does not certify insurance.
 extract_pdf(pdf)
 return {'malware':'not_detected','accepted':False,
         'next_stage':'manual_review_only','evidence_retained':False}
