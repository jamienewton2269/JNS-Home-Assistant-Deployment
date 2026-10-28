"""Offline v0.3.6 gateway policy tests; no production access."""
import importlib.util,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

spec=importlib.util.spec_from_file_location("v036_release_policy",Path(__file__).with_name("v036_release_policy.py"))
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
NOW=datetime(2026,10,28,12,0,tzinfo=timezone.utc)
JOB={"job_id":"20261028T120000Z-heating-v036-a1b2c3","job_type":P.JOB_TYPE,"stage_id":P.STAGE}
PERMIT={"job_id":JOB["job_id"],"operation":P.OPERATION,"stage_id":P.STAGE,
        "candidate_sha256":P.CANDIDATE["thermal.py"],
        "expires_utc":(NOW+timedelta(minutes=8)).isoformat(),
        "heating_outage_approved":True}
STAGE={"stage_id":P.STAGE,"state":"staged","version":"0.3.6",
       "candidate":P.CANDIDATE.copy(),"original":P.ORIGINAL.copy(),
       "legacy_store_preserved":True,"core_restarted":False}

def live():
    timestamp=NOW.isoformat()
    def item(name,value,attrs=None):
        return {"entity_id":name,"state":value,"attributes":attrs or {},
                "last_reported":timestamp}
    return {
     P.THERMOSTAT:item(P.THERMOSTAT,"heat",{"temperature":21.0,"hvac_action":"idle"}),
     P.HEAT_CALL:item(P.HEAT_CALL,"off"),
     P.HONEYWELL:item(P.HONEYWELL,"21.0"),
     P.BATHROOM_TEMP:item(P.BATHROOM_TEMP,"21.35"),
     P.BATHROOM_RH:item(P.BATHROOM_RH,"45.2"),
     P.LEARNER:item(P.LEARNER,"Learned values outside safe bounds"),
    }

class PolicyTests(unittest.TestCase):
    def test_stage_exact_pinned_six_files(self):
        self.assertTrue(P.stage(STAGE))
        bad={**STAGE,"candidate":{**P.CANDIDATE,"coordinator.py":"0"*64}}
        with self.assertRaises(P.Denied):P.stage(bad)

    def test_wrong_version_or_unpreserved_history_fails(self):
        for change in ({"version":"0.3.5"},{"legacy_store_preserved":False},{"core_restarted":True},{"state":"applied_pending_core_restart"}):
            with self.subTest(change=change),self.assertRaises(P.Denied):
                P.stage({**STAGE,**change})

    def test_signed_local_single_job_approval(self):
        self.assertTrue(P.approve(JOB,PERMIT,NOW))
        for mod in ({"job_id":"wrong"},{"heating_outage_approved":False},
                    {"candidate_sha256":"0"*64},{"expires_utc":(NOW+timedelta(minutes=11)).isoformat()},
                    {"expires_utc":(NOW-timedelta(seconds=1)).isoformat()}):
            with self.subTest(mod=mod),self.assertRaises(P.Denied):
                P.approve(JOB,{**PERMIT,**mod},NOW)

    def test_untrusted_queue_cannot_choose_host_or_command(self):
        for extra in ("vm","shell","host","command","candidate_sha256"):
            with self.subTest(extra=extra),self.assertRaises(P.Denied):
                P.approve({**JOB,extra:"injection"},PERMIT,NOW)
        with self.assertRaises(P.Denied):
            P.approve({**JOB,"job_type":"ha_shell"},PERMIT,NOW)

    def test_live_heating_idle_requires_authenticated_entity_values(self):
        self.assertEqual(P.live_heating(live(),NOW)["target"],21.0)
        for name,state in ((P.HEAT_CALL,"on"),(P.HONEYWELL,"unavailable"),(P.LEARNER,"unknown")):
            a=live();a[name]["state"]=state
            with self.subTest(name=name),self.assertRaises(P.Denied):
                P.live_heating(a,NOW)
        a=live();a[P.THERMOSTAT]["attributes"]["hvac_action"]="heating"
        with self.assertRaises(P.Denied):P.live_heating(a,NOW)

    def test_stale_shower_and_invalid_states_block(self):
        a=live();a[P.BATHROOM_RH]["last_reported"]=(NOW-timedelta(minutes=16)).isoformat()
        with self.assertRaises(P.Denied):P.live_heating(a,NOW)
        a=live();a[P.BATHROOM_TEMP]["state"]="35.73"
        with self.assertRaises(P.Denied):P.live_heating(a,NOW)
        a=live();a[P.THERMOSTAT]["attributes"].pop("temperature")
        with self.assertRaises(P.Denied):P.live_heating(a,NOW)
        a=live();a[P.HONEYWELL]["entity_id"]="sensor.forged"
        with self.assertRaises(P.Denied):P.live_heating(a,NOW)

    def test_post_release_preserves_thermostat_and_accepts_unavailable_forecast(self):
        pre=P.live_heating(live(),NOW)
        advisory=[{"attributes":{"friendly_name":"Lyric home heating "+name,
                                 "advisory_only":True}} for name in P.ADVISORY_NAMES]
        self.assertTrue(P.live_post(pre,live(),advisory,NOW)["target_unchanged"])
        a=live();a[P.THERMOSTAT]["attributes"]["temperature"]=19
        with self.assertRaises(P.Denied):P.live_post(pre,a,advisory,NOW)
        with self.assertRaises(P.Denied):P.live_post(pre,live(),advisory[:2],NOW)
        advisory[-1]["attributes"]["advisory_only"]=False
        with self.assertRaises(P.Denied):P.live_post(pre,live(),advisory,NOW)

if __name__=="__main__":unittest.main()
