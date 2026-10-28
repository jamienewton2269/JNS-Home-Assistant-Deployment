"""Offline dormant root-operator safety tests. No host or Core operations."""
import ast,importlib.util,sys,unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location("v036_root_operator",HERE/"v036_root_operator.py")
O=importlib.util.module_from_spec(spec)
spec.loader.exec_module(O)

class RootOperatorTest(unittest.TestCase):
    def test_syntax_for_both_root_only_sources(self):
        for file in ("v036_root_operator.py","v036_local_approval.py"):
            ast.parse((HERE/file).read_text(),filename=file)

    def test_non_root_checkout_always_denied(self):
        with patch.object(O.os,"geteuid",return_value=1000):
            with self.assertRaisesRegex(O.Blocked,"local root"):
                O.gate()

    def test_arbitrary_transaction_not_allowed_even_before_file_read(self):
        for action in ("commit","shell","shutdown","activate","preflight"):
            with self.subTest(action=action),self.assertRaisesRegex(O.Blocked,"not fixed-purpose"):
                O.transaction(action)

    def test_host_recovery_covers_all_six_and_never_touches_storage(self):
        commands=[]
        def fake_guest(command,**kw):
            commands.append(command)
            return "JNS_V036_ORIGINAL_FILES_RESTORED"
        with patch.object(O,"guest",side_effect=fake_guest):
            O.host_restore()
        self.assertEqual(len(commands),1)
        shell=commands[0][-1]
        self.assertTrue(commands[0][0:2]==["/bin/sh","-c"])
        for name in O.ORIGINAL:
            self.assertIn("original/"+name,shell)
            self.assertIn(O.ORIGINAL[name],shell)
        for name in O.CANDIDATE:
            self.assertIn(O.CANDIDATE[name],shell)
        self.assertIn("rm -f",shell)
        self.assertNotIn(".storage",shell)
        self.assertNotIn("set_temperature",shell)
        self.assertNotIn("qm stop",shell)

    def test_release_never_uses_runner_supplied_host(self):
        args=[]
        def fake_run(argv,timeout):
            args.append(argv)
            return "nodeb" if argv[-1]=="hostname -s" else "OK"
        with patch.object(O,"run",side_effect=fake_run):
            self.assertEqual(O.on_nodeb(["qm","status","905"]),"OK")
        self.assertEqual(len(args),2)
        self.assertIn("root@nodeb.home.arpa",args[0])
        self.assertIn("qm status 905",args[1][-1])

    def test_host_identity_mismatch_blocks_other_proxmox(self):
        with patch.object(O,"run",return_value="nodea"):
            with self.assertRaisesRegex(O.Blocked,"wrong Proxmox host"):
                O.on_nodeb(["qm","status","905"])

    def test_core_restart_not_reported_without_new_process_and_auth(self):
        # An ambiguous restart/disconnect is NOT evidence of live source.
        calls=[]
        with patch.object(O,"guest",side_effect=lambda *a,**k: (_ for _ in ()).throw(O.Blocked("disconnect"))), \
             patch.object(O,"core_stamp",return_value="old-stamp"), \
             patch.object(O.time,"monotonic",side_effect=[0,300]), \
             patch.object(O.time,"sleep"):
            with self.assertRaisesRegex(O.Blocked,"not proven"):
                O.restart_and_verify("old-stamp")

    def test_install_requires_root_owned_fixed_location_and_read_only_policy(self):
        src=(HERE/"v036_root_operator.py").read_text()
        self.assertIn('root@"+HOST',src)
        self.assertIn('Path(__file__).resolve()==INSTALL/"v036_root_operator.py"',src)
        self.assertIn('approve(job,permit)',src)
        self.assertIn('live_heating(authenticated()["states"])',src)
        self.assertIn('live_post(baseline,post["states"],post["advisories"])',src)

if __name__=="__main__":
    unittest.main()
