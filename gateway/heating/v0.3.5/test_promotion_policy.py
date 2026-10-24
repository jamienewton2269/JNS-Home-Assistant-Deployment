"""Offline policy checks: no calls to SSH, QGA or Home Assistant."""
import importlib.util
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from promotion_policy import approve,PolicyDenied,STAGE_ID,JOB_TYPE,CANDIDATE_SHA

NOW=datetime(2026,10,24,18,40,tzinfo=timezone.utc)

def job():
    return {
        "job_id":"20261024T184000Z-heating-v035-1a2b3c",
        "job_type":JOB_TYPE,"stage_id":STAGE_ID,
    }

def permit():
    return {
        "operation":"one_time_heating_maintenance",
        "job_id":job()["job_id"],
        "stage_id":STAGE_ID,
        "candidate_sha":CANDIDATE_SHA,
        "expires_utc":(NOW+timedelta(minutes=8)).isoformat(),
        "heating_outage_approved":True,
    }

class PromotionPolicyTests(unittest.TestCase):
    def test_only_exact_approved_job_is_admitted(self):
        self.assertTrue(approve(job(),permit(),now=NOW))

    def test_attacker_cannot_send_custom_shell_command_or_argv(self):
        mutated=job()
        mutated["command"]="docker rm -f homeassistant"
        with self.assertRaisesRegex(PolicyDenied,"allowlisted"):
            approve(mutated,permit(),now=NOW)

    def test_cannot_redirect_to_node_a_or_other_vm(self):
        for extra in ("target_vm","host","rollback_path","shell"):
            changed=job();changed[extra]="900"
            with self.assertRaises(PolicyDenied):
                approve(changed,permit(),now=NOW)
        changed=job();changed["stage_id"]="v035-20261024T162546Z-aaaa0000"
        with self.assertRaises(PolicyDenied):
            approve(changed,permit(),now=NOW)

    def test_stale_or_long_lived_approval_is_blocked(self):
        with self.assertRaises(PolicyDenied):
            approve(job(),permit(),now=NOW+timedelta(minutes=9))
        too_far=permit()
        too_far["expires_utc"]=(NOW+timedelta(hours=5)).isoformat()
        with self.assertRaises(PolicyDenied):
            approve(job(),too_far,now=NOW)

    def test_approval_must_be_explicitly_local_and_correct_hash(self):
        for field,value in (("candidate_sha","0"*64),("heating_outage_approved",False),
                            ("operation","read_only"),("stage_id","other"),
                            ("job_id","20261024T185500Z-heating-v035-deadbe")):
            altered=permit();altered[field]=value
            with self.assertRaises(PolicyDenied):
                approve(job(),altered,now=NOW)

    def test_unrecognised_type_and_job_identity_are_blocked(self):
        for field,value in (("job_type","script_exec"),
                            ("job_id","../../tmp/exploit"),
                            ("job_id","not_unique")):
            altered=job();altered[field]=value
            with self.assertRaises(PolicyDenied):
                approve(altered,permit(),now=NOW)

    def test_missing_local_approval_field_is_blocked(self):
        altered=permit();del altered["heating_outage_approved"]
        with self.assertRaises(PolicyDenied):
            approve(job(),altered,now=NOW)

    def test_root_route_uses_existing_runner_identity_not_root_keys(self):
        spec=importlib.util.spec_from_file_location("jns_heating_gateway_route",
                                                  ROOT/"root_owned_promotion.py")
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        calls=[]
        def fake_run(argv,timeout):
            calls.append(argv)
            if argv[-1]=="hostname -s":
                return "nodeb"
            return "status: running"
        with patch.object(module,"run",side_effect=fake_run):
            self.assertIn("running",module.host_command(["qm","status","905"]))
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][:4],
                         ["/usr/sbin/runuser","-u","github-runner","--"])
        self.assertIn("root@nodeb.home.arpa",calls[0])
        self.assertEqual(calls[1][-1],"qm status 905")

    def test_root_recovery_refuses_unverified_checksums(self):
        spec=importlib.util.spec_from_file_location("jns_heating_gateway_recovery",
                                                  ROOT/"root_owned_promotion.py")
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        with patch.object(module,"guest") as guest:
            with self.assertRaisesRegex(module.DeploymentBlocked,"pinned manifest digest"):
                module.host_fallback_rollback("../not-a-hash","0"*64)
            guest.assert_not_called()

    def test_v4_dispatcher_is_exact_v3_plus_one_case(self):
        baseline=(ROOT.parent.parent/"trusted/jns-gateway-exec-wrapper-v3.sh").read_text()
        current=(ROOT/"jns-gateway-exec-wrapper-v4-heating.sh").read_text()
        marker='  *)\n    exec /usr/local/sbin/jns-gateway-exec.base "$REAL"\n    ;;'
        patch_case=('  ha_heating_v035_promote)\n'
                    '    exec /usr/local/libexec/jns-heating-v035/root_owned_promotion.py "$REAL"\n'
                    '    ;;\n')
        self.assertEqual(baseline.count(marker),1)
        self.assertEqual(current,baseline.replace(marker,patch_case+marker))

    def test_dormant_handler_has_no_unsafe_commit_without_permit(self):
        # Guarded handler is importable but cannot send commands absent a
        # privately minted maintenance token. Root permissions are simulated.
        spec=importlib.util.spec_from_file_location("jns_heating_privileged_test",
                                                  ROOT/"root_owned_promotion.py")
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        with patch.object(module,"guard_filesystem"), \
             patch.object(module,"read_permit",side_effect=module.DeploymentBlocked("no permit")), \
             patch.object(module,"guest") as guest:
            with self.assertRaises(module.DeploymentBlocked):
                module.perform(job())
            guest.assert_not_called()

if __name__=="__main__":
    unittest.main()
