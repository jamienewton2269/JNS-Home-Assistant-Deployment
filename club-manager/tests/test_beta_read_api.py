"""No real DB credentials, users or services required."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1] / "beta" / "read_api.py"
spec=importlib.util.spec_from_file_location("club_beta_reads",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Cursor:
    def __init__(self, parent):
        self.parent=parent
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,args):
        self.parent.calls.append((sql,args))
    def fetchone(self): return ({"synthetic":True},)
class Conn:
    def __init__(self): self.calls=[];self.closed=False
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def cursor(self): return Cursor(self)
    def close(self): self.closed=True
class Tests(unittest.TestCase):
    def setUp(self):
        self.conns=[]
        def connect():
            c=Conn()
            self.conns.append(c)
            return c
        self.api=module.ReadOnlyBetaAPI(connect)
        self.token="a"*48
    def test_seven_routes_use_fixed_parameterized_sql(self):
        self.assertEqual(len(module.READ_ROUTES),7)
        for route,expected in module.READ_ROUTES.items():
            self.assertEqual(self.api.get(route,self.token),{"synthetic":True})
            c=self.conns[-1]
            self.assertEqual(c.calls,[(expected,(self.token,))])
            self.assertTrue(c.closed)
        self.assertFalse(any("UPDATE " in s or "INSERT " in s for s in module.READ_ROUTES.values()))
    def test_unknown_route_never_connects(self):
        with self.assertRaises(LookupError): self.api.get("/api/v1/delete",self.token)
        with self.assertRaises(LookupError): self.api.get("/api/v1/members?role=admin",self.token)
        self.assertEqual(self.conns,[])
    def test_invalid_token_never_connects(self):
        for value in (None,"","a"*39,"a"*257,"x\ny"*20):
            with self.assertRaises(PermissionError):
                self.api.get("/api/v1/members",value)
        self.assertEqual(self.conns,[])
if __name__=="__main__":unittest.main()
