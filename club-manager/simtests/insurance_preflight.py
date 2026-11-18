"""Synthetic-only transient PDF checks. NEVER retains, encrypts or uploads policies.
This is a document metadata consistency check, not proof of insurance.
"""
import base64, binascii, re, subprocess, resource, hashlib
from datetime import datetime, date
MAX_SIZE=512*1024
def limits():
 resource.setrlimit(resource.RLIMIT_CPU,(3,3))
 resource.setrlimit(resource.RLIMIT_AS,(192*1024*1024,192*1024*1024))
 resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
def extract_pdf(pdf):
 if not pdf.startswith(b'%PDF-') or len(pdf)>MAX_SIZE or len(pdf)<100:
  raise ValueError('PDF required, maximum 512 KiB')
 command=['/usr/bin/pdftotext','-layout','-enc','UTF-8','-','-']
 try:
  r=subprocess.run(command,input=pdf,capture_output=True,timeout=5,check=False,
                   preexec_fn=limits)
 except (OSError,subprocess.TimeoutExpired):
  raise ValueError('PDF parser did not complete')
 if r.returncode!=0:
  raise ValueError('Invalid, encrypted or unreadable PDF')
 text=r.stdout[:32768].decode('utf-8','replace')
 if len(text.strip())<40:
  raise ValueError('No usable PDF text; a scanned policy needs human review')
 return text
def parse_date(s):
 s=s.strip()
 for fmt in ('%d/%m/%Y','%d-%m-%Y','%Y-%m-%d'):
  try:return datetime.strptime(s,fmt).date()
  except ValueError:pass
 return None
def preflight(payload):
 if not isinstance(payload,dict) or set(payload)!={'filename','pdf_base64','vessel_name','insurer','policy_ref','cover_from','cover_until'}:
  raise ValueError('All policy fields required')
 for name in ('filename','vessel_name','insurer','policy_ref','cover_from','cover_until'):
  if not isinstance(payload[name],str) or len(payload[name])>120:raise ValueError('Invalid field')
 if not payload['filename'].lower().endswith('.pdf'):raise ValueError('PDF filename required')
 encoded=payload['pdf_base64']
 if not isinstance(encoded,str) or len(encoded)>((MAX_SIZE+2)//3)*4+8:raise ValueError('PDF too large')
 try:pdf=base64.b64decode(encoded,validate=True)
 except (ValueError,binascii.Error):raise ValueError('Invalid PDF encoding')
 start,end=parse_date(payload['cover_from']),parse_date(payload['cover_until'])
 if not start or not end or end<start or (end-start).days>1096:
  raise ValueError('Invalid coverage dates')
 from insurance_scan import malware_scan
 scan=malware_scan(pdf)
 if scan['malware']!='not_detected':raise ValueError('File failed malware scan')
 text=extract_pdf(pdf)
 normalized=re.sub(r'[^a-z0-9]+','',text.casefold())
 checks={}
 for name in ('vessel_name','insurer','policy_ref'):
  claimed=re.sub(r'[^a-z0-9]+','',payload[name].casefold())
  checks[name]=len(claimed)>=3 and claimed in normalized
 def date_present(d):
  options=(d.strftime('%d/%m/%Y'),d.strftime('%d-%m-%Y'),d.strftime('%Y-%m-%d'))
  return any(x in text for x in options)
 checks['cover_from']=date_present(start)
 checks['cover_until']=date_present(end)
 return {
   'document_sha256':hashlib.sha256(pdf).hexdigest(),
   'size_bytes':len(pdf),
   'checks':checks,
   'matched_fields':sum(checks.values()),
   'required_fields':len(checks),
   'review_state':'needs_review',
   'action':'Evidence NOT retained. A human must verify insurer, policy terms and coverage before any validated status.',
   'malware_scan':'no_known_threat_detected',
   'staging_only':True,
 }
