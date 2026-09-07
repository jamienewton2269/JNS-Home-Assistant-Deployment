from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
import hashlib, json, os, shutil, stat, tempfile, time, uuid, zipfile
from .const import ALLOWED_ROOTS, MAX_MEMBER_BYTES, MAX_MEMBER_COUNT, MAX_PACKAGE_BYTES, PACKAGE_MANIFEST, TRANSACTION_RECORD

class DeploymentError(Exception):
    """Raised when a JNS package fails validation or deployment."""

@dataclass(frozen=True)
class ValidatedFile:
    source_member: str
    target_rel: str
    sha256: str
    size: int

class DeploymentManager:
    def __init__(self, config_root: Path, inbox_rel: str, staging_rel: str, backups_rel: str) -> None:
        self.config_root=config_root.resolve(); self.inbox=(self.config_root/inbox_rel).resolve(); self.staging=(self.config_root/staging_rel).resolve(); self.backups=(self.config_root/backups_rel).resolve()
        for p in (self.inbox,self.staging,self.backups): p.mkdir(parents=True,exist_ok=True)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h=hashlib.sha256()
        with path.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
        return h.hexdigest()

    @staticmethod
    def _safe_posix_path(value: str) -> str:
        if not isinstance(value,str) or not value.strip(): raise DeploymentError('Empty package path is not allowed.')
        if '\\' in value: raise DeploymentError(f'Backslashes are not allowed in package paths: {value!r}')
        p=PurePosixPath(value)
        if p.is_absolute() or '..' in p.parts or '.' in p.parts: raise DeploymentError(f'Unsafe package path: {value!r}')
        n=str(p)
        if not n or n.startswith('/'): raise DeploymentError(f'Unsafe package path: {value!r}')
        return n

    @staticmethod
    def _allowed_target(target_rel: str) -> bool:
        return any(target_rel.startswith(prefix) for prefix in ALLOWED_ROOTS)

    def _package_path(self, package_name: str) -> Path:
        if Path(package_name).name != package_name: raise DeploymentError('Package must be a filename only, not a path.')
        if not package_name.lower().endswith('.zip'): raise DeploymentError('Only ZIP deployment packages are accepted.')
        package=(self.inbox/package_name).resolve()
        if package.parent != self.inbox: raise DeploymentError('Package path escaped the JNS inbox.')
        if not package.is_file(): raise DeploymentError(f'Package not found in JNS inbox: {package_name}')
        if package.stat().st_size > MAX_PACKAGE_BYTES: raise DeploymentError('Package exceeds the maximum permitted size.')
        return package

    def _read_manifest(self, archive: zipfile.ZipFile) -> dict[str,Any]:
        try: raw=archive.read(PACKAGE_MANIFEST)
        except KeyError as exc: raise DeploymentError(f'Package is missing {PACKAGE_MANIFEST}.') from exc
        try: manifest=json.loads(raw.decode('utf-8'))
        except Exception as exc: raise DeploymentError('Package manifest is not valid UTF-8 JSON.') from exc
        if manifest.get('format') != 1: raise DeploymentError('Unsupported JNS package format.')
        if not isinstance(manifest.get('name'),str) or not manifest['name'].strip(): raise DeploymentError('Manifest requires a package name.')
        if not isinstance(manifest.get('version'),str) or not manifest['version'].strip(): raise DeploymentError('Manifest requires a package version.')
        if not isinstance(manifest.get('files'),list) or not manifest['files']: raise DeploymentError('Manifest requires a non-empty files list.')
        return manifest

    def _validate_zip_metadata(self, archive: zipfile.ZipFile) -> None:
        infos=archive.infolist()
        if len(infos)>MAX_MEMBER_COUNT: raise DeploymentError('Package contains too many archive members.')
        seen=set()
        for info in infos:
            s=info.filename.rstrip('/')
            if not s: continue
            name=self._safe_posix_path(s)
            if name in seen: raise DeploymentError(f'Duplicate ZIP member: {name}')
            seen.add(name)
            mode=(info.external_attr>>16)&0xFFFF
            if mode and stat.S_ISLNK(mode): raise DeploymentError(f'Symbolic links are forbidden: {name}')
            if info.file_size>MAX_MEMBER_BYTES: raise DeploymentError(f'Archive member exceeds maximum size: {name}')

    def validate_package(self, package_name: str) -> dict[str,Any]:
        package=self._package_path(package_name); package_sha256=self._sha256_file(package)
        with zipfile.ZipFile(package,'r') as archive:
            self._validate_zip_metadata(archive); manifest=self._read_manifest(archive); validated=[]; declared=set()
            for entry in manifest['files']:
                if not isinstance(entry,dict): raise DeploymentError('Each manifest files entry must be an object.')
                member=self._safe_posix_path(entry.get('source','')); target=self._safe_posix_path(entry.get('target','')); expected=str(entry.get('sha256','')).lower()
                if not self._allowed_target(target): raise DeploymentError(f'Target is outside JNS allowed roots: {target}')
                if len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected): raise DeploymentError(f'Invalid SHA-256 in manifest for {member}.')
                if member in declared: raise DeploymentError(f'Manifest declares member more than once: {member}')
                declared.add(member)
                try: info=archive.getinfo(member)
                except KeyError as exc: raise DeploymentError(f'Manifest member missing from ZIP: {member}') from exc
                if info.is_dir(): raise DeploymentError(f'Manifest member must be a file: {member}')
                data=archive.read(member); actual=hashlib.sha256(data).hexdigest()
                if actual!=expected: raise DeploymentError(f'SHA-256 mismatch for {member}: expected {expected}, got {actual}')
                validated.append(ValidatedFile(member,target,actual,len(data)))
            allowed=declared|{PACKAGE_MANIFEST}; undeclared=[]
            for info in archive.infolist():
                if info.is_dir(): continue
                n=self._safe_posix_path(info.filename)
                if n not in allowed: undeclared.append(n)
            if undeclared: raise DeploymentError('Package contains undeclared files: '+', '.join(sorted(undeclared)))
        return {'ok':True,'package':package_name,'package_sha256':package_sha256,'name':manifest['name'],'version':manifest['version'],'file_count':len(validated),'files':[v.__dict__ for v in validated]}

    def install_package(self, package_name: str, dry_run: bool=False) -> dict[str,Any]:
        validation=self.validate_package(package_name)
        if dry_run: return {**validation,'dry_run':True,'installed':False}
        package=self._package_path(package_name); txid=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:10]
        stage=(self.staging/txid).resolve(); backup=(self.backups/txid).resolve(); stage.mkdir(parents=True,exist_ok=False); backup.mkdir(parents=True,exist_ok=False)
        tx={'transaction_id':txid,'package':package_name,'package_sha256':validation['package_sha256'],'name':validation['name'],'version':validation['version'],'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'files':[],'status':'staging'}
        try:
            with zipfile.ZipFile(package,'r') as archive:
                manifest=self._read_manifest(archive)
                for entry in manifest['files']:
                    member=self._safe_posix_path(entry['source']); target=self._safe_posix_path(entry['target']); staged=(stage/target).resolve()
                    if stage not in staged.parents: raise DeploymentError(f'Staged path escaped transaction root: {target}')
                    staged.parent.mkdir(parents=True,exist_ok=True)
                    with archive.open(member,'r') as src, staged.open('wb') as dst: shutil.copyfileobj(src,dst)
                    if self._sha256_file(staged)!=entry['sha256'].lower(): raise DeploymentError(f'Staged hash mismatch for {target}')
                tx['status']='committing'
                for entry in manifest['files']:
                    target=self._safe_posix_path(entry['target']); live=(self.config_root/target).resolve(); staged=(stage/target).resolve(); b=(backup/target).resolve()
                    if self.config_root not in live.parents: raise DeploymentError(f'Live path escaped Home Assistant config: {target}')
                    existed=live.exists()
                    if existed:
                        if live.is_symlink(): raise DeploymentError(f'Refusing to overwrite symbolic link: {target}')
                        if live.is_dir(): raise DeploymentError(f'Refusing to overwrite directory with file: {target}')
                        b.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(live,b)
                    item={'target':target,'previously_existed':existed,'installed_sha256':None}; tx['files'].append(item)
                    live.parent.mkdir(parents=True,exist_ok=True); fd,tmpname=tempfile.mkstemp(prefix='.jns-',dir=str(live.parent)); os.close(fd); tmp=Path(tmpname)
                    try: shutil.copy2(staged,tmp); os.replace(tmp,live)
                    finally:
                        if tmp.exists(): tmp.unlink(missing_ok=True)
                    item['installed_sha256']=self._sha256_file(live)
            tx['status']='committed'; (backup/TRANSACTION_RECORD).write_text(json.dumps(tx,indent=2),encoding='utf-8')
            return {'ok':True,'installed':True,'dry_run':False,'transaction_id':txid,'package':package_name,'name':validation['name'],'version':validation['version'],'file_count':len(tx['files'])}
        except Exception:
            try:
                for item in reversed(tx['files']):
                    target=item['target']; live=(self.config_root/target).resolve(); b=(backup/target).resolve()
                    if item['previously_existed'] and b.is_file(): live.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(b,live)
                    elif not item['previously_existed'] and live.is_file(): live.unlink()
                tx['status']='rolled_back_after_failure'; (backup/TRANSACTION_RECORD).write_text(json.dumps(tx,indent=2),encoding='utf-8')
            finally: shutil.rmtree(stage,ignore_errors=True)
            raise
        finally: shutil.rmtree(stage,ignore_errors=True)

    def rollback_transaction(self, transaction_id: str) -> dict[str,Any]:
        if Path(transaction_id).name != transaction_id: raise DeploymentError('Invalid transaction id.')
        txroot=(self.backups/transaction_id).resolve()
        if txroot.parent != self.backups or not txroot.is_dir(): raise DeploymentError('Transaction backup not found.')
        record=txroot/TRANSACTION_RECORD
        if not record.is_file(): raise DeploymentError('Transaction record is missing.')
        data=json.loads(record.read_text(encoding='utf-8')); files=data.get('files',[])
        if not isinstance(files,list): raise DeploymentError('Transaction record is invalid.')
        restored=[]
        for item in reversed(files):
            target=self._safe_posix_path(item['target']); live=(self.config_root/target).resolve(); b=(txroot/target).resolve()
            if self.config_root not in live.parents: raise DeploymentError(f'Rollback target escaped config root: {target}')
            if item.get('previously_existed'):
                if not b.is_file(): raise DeploymentError(f'Required rollback file is missing: {target}')
                live.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(b,live)
            elif live.is_file(): live.unlink()
            restored.append(target)
        data['status']='rolled_back'; data['rolled_back_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()); record.write_text(json.dumps(data,indent=2),encoding='utf-8')
        return {'ok':True,'transaction_id':transaction_id,'restored_count':len(restored),'restored':restored}
