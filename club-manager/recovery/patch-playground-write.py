from pathlib import Path
import ast
p=Path('/opt/beta/server.py')
s=p.read_text()
if 'from write_api import write_seniority' not in s:
    old='from read_api import ReadOnlyBetaAPI, READ_ROUTES'
    assert s.count(old)==1
    s=s.replace(old,old+'\nfrom write_api import write_seniority')
    old='"/auth/logout"):'
    assert s.count(old)==1
    s=s.replace(old,'"/auth/logout", "/api/v1/seniority/write"):')
    old='            if self.path == "/auth/logout":'
    assert s.count(old)==1
    s=s.replace(old,'''            if self.path == "/api/v1/seniority/write":
                try:
                    result = write_seniority(self.controller.read_api.connect, self.headers.get("Cookie",""), body)
                    return self.send_body(200, result)
                except PermissionError:
                    return self.deny(401, "Named officer session required")
                except ValueError:
                    return self.deny(400, "Invalid write request")
                except Exception as exc:
                    if getattr(exc, "pgcode", None) == "42501":
                        return self.deny(403, "Permission denied")
                    if str(getattr(exc, "pgcode", "")).startswith(("22", "23")):
                        return self.deny(400, "Invalid or conflicting data")
                    return self.deny(503, "Write unavailable")
'''+old)
ast.parse(s)
tmp=p.with_suffix('.new')
tmp.write_text(s)
tmp.chmod(p.stat().st_mode & 0o777)
tmp.replace(p)
