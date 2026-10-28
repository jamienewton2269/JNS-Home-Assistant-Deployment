"""Fail-closed VM905 bathroom v0.3.6 release policy. PURE FUNCTIONS ONLY.

Reviewed, root-installed code may import these functions. GitHub runner may
execute tests; neither this module nor GitHub Actions authorises promotion.
All six candidate digests were independently attested in run 40676574781.
"""
from datetime import datetime, timezone
import re

STAGE="v036-20261028T103734Z-a6babd0e"
VM="905"
HOST="nodeb.home.arpa"
JOB_TYPE="ha_heating_v036_promote"
OPERATION="once_vm905_bathroom_advisory_core_restart"
CANDIDATE={
 "coordinator.py":"6efba63422429a0871784024eff0fb08956b82012d431949c19e700bf6130abc",
 "sensor.py":"4c414892b141308113f08d54a49445dd7e70a7cd61f7f80d8d606dc14aff84d1",
 "thermal.py":"43b0f6ec0229d15dc137bbf3c52cd41b4bb125072fbcc49202e744ba8a19bc6c",
 "bathroom_reference.py":"d227e6f5cc2113b8fd8af9e2958c50a3d408a22156ad671ddee0c9ef2f97389d",
 "bathroom_runtime.py":"786f0a8d938976e5e86945441dbb75d2fdbb6526b486edfa2f1a7de1720567f8",
 "manifest.json":"deabac235df69398d8a9eaff7dfef0ef0ca3977ffb98af4c6ab48b429d903ab9",
}
ORIGINAL={
 "coordinator.py":"9407ac6a9d75b772c4fe833b53cca1c7d565c61ebe40bdc5e6c8f72e609a0b74",
 "sensor.py":"f917e70602765c67fe0ed7597ea3e87cc9920b82ac773b7c2c2f2d5ce4ce9a01",
 "thermal.py":"44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8",
 "manifest.json":"1a31faa9074154b8db44fb3435a146644f664aebc51908de7da3fccf810f077b",
}
THERMOSTAT="climate.thermostat_thermostat"
HEAT_CALL="binary_sensor.lyric_home_heating_heating_call"
HONEYWELL="sensor.thermostat_thermostat_indoor_temperature"
BATHROOM_TEMP="sensor.0xa4c1382471d2ed23_temperature"
BATHROOM_RH="sensor.0xa4c1382471d2ed23_humidity"
LEARNER="sensor.lyric_home_heating_thermal_learning"
PRE_REQUIRED=(THERMOSTAT,HEAT_CALL,HONEYWELL,BATHROOM_TEMP,BATHROOM_RH,LEARNER)
ADVISORY_NAMES=(
 "Bathroom advisory precision temperature",
 "Bathroom advisory projected temperature in 60 minutes",
 "Bathroom advisory learning quality",
)

class Denied(RuntimeError): pass

def require(ok, why):
    if not ok:raise Denied(why)

def stage(metadata):
    require(isinstance(metadata,dict),"private stage missing")
    require(metadata.get("stage_id")==STAGE and metadata.get("version")=="0.3.6",
            "wrong stage or version")
    require(metadata.get("state")=="staged","stage not pre-activation")
    require(metadata.get("candidate")==CANDIDATE,"six-file candidate digest mismatch")
    require(metadata.get("original")==ORIGINAL,"private original digest mismatch")
    require(metadata.get("legacy_store_preserved") is True,"history snapshot missing")
    require(metadata.get("core_restarted") is False,"stage records unexpected restart")
    return True

def approve(job,permit,now=None):
    require(isinstance(job,dict) and set(job)=={"job_id","job_type","stage_id"},
            "queue keys not strictly allowlisted")
    require(isinstance(job["job_id"],str) and
            re.fullmatch(r"\d{8}T\d{6}Z-heating-v036-[a-f0-9]{6}",job["job_id"]),
            "immutable job ID malformed")
    require(job["job_type"]==JOB_TYPE and job["stage_id"]==STAGE,"wrong job/stage")
    require(isinstance(permit,dict) and set(permit)=={
      "job_id","operation","stage_id","candidate_sha256","expires_utc","heating_outage_approved"},
      "local root permit schema mismatch")
    require(permit["job_id"]==job["job_id"] and permit["stage_id"]==STAGE,
            "permit not tied to immutable job")
    require(permit["operation"]==OPERATION and
            permit["candidate_sha256"]==CANDIDATE["thermal.py"] and
            permit["heating_outage_approved"] is True,"maintenance permit not authorised")
    try:
        expiry=datetime.fromisoformat(permit["expires_utc"].replace("Z","+00:00"))
        require(expiry.tzinfo is not None,"permit timezone missing")
        lifetime=(expiry-(now or datetime.now(timezone.utc))).total_seconds()
        require(0<lifetime<=600,"permit expired or longer than 10 minutes")
    except (ValueError,TypeError,AttributeError) as exc:
        raise Denied("permit date invalid") from exc
    return True

def _age_minutes(entity,now):
    text=entity.get("last_reported") or entity.get("last_updated")
    require(isinstance(text,str),"state report time missing")
    try:stamp=datetime.fromisoformat(text.replace("Z","+00:00"))
    except ValueError as exc:raise Denied("state report time malformed") from exc
    require(stamp.tzinfo is not None,"timestamp timezone missing")
    return (now-stamp).total_seconds()/60

def live_heating(snapshot,now=None,require_idle=True):
    """Validate authenticated Home Assistant GET /api/states response map.

    All entries MUST come from live admin-token GET requests, never Recorder.
    Read-only; no thermostat or setpoint commands. Does not infer heat-idle
    from a last-changed database timestamp.
    """
    now=now or datetime.now(timezone.utc)
    require(isinstance(snapshot,dict) and set(PRE_REQUIRED)<=set(snapshot),
            "required live heating entities missing")
    for name in PRE_REQUIRED:
        item=snapshot[name]
        require(isinstance(item,dict) and item.get("entity_id")==name,
                "live HA entity identity mismatch")
        require(item.get("state") not in (None,"unknown","unavailable",""),
                "live heating entity unavailable")
        age=_age_minutes(item,now)
        require(-2<=age<=60,"essential live state stale or clock drift")
    for name in (BATHROOM_TEMP,BATHROOM_RH):
        require(_age_minutes(snapshot[name],now)<=15,"bathroom sensor report stale")
    try:
        indoor=float(snapshot[HONEYWELL]["state"])
        bathroom=float(snapshot[BATHROOM_TEMP]["state"])
        humidity=float(snapshot[BATHROOM_RH]["state"])
    except (ValueError,TypeError) as exc:raise Denied("non-numeric temperature or humidity") from exc
    require(5<=indoor<=35 and 5<=bathroom<=35 and 10<=humidity<=95,
            "implausible live thermal measurement")
    climate=snapshot[THERMOSTAT]
    attrs=climate.get("attributes") or {}
    try:target=float(attrs["temperature"])
    except (ValueError,KeyError,TypeError) as exc:raise Denied("thermostat target unavailable") from exc
    require(5<=target<=35,"implausible thermostat target")
    if require_idle:
        require(snapshot[HEAT_CALL]["state"]=="off","live heating call active")
        require(attrs.get("hvac_action") not in ("heating","cooling"),
                "thermostat actively heating/cooling")
    return {"temperature":indoor,"target":target,"hvac_mode":climate["state"]}

def live_post(pre,post,advisories,now=None):
    live=live_heating(post,now,require_idle=False)
    require(abs(live["target"]-pre["target"])<0.01,
            "thermostat target changed during Core release")
    require(live["hvac_mode"]==pre["hvac_mode"],
            "thermostat mode changed during Core release")
    require(isinstance(advisories,list),"new entities absent")
    names={x.get("attributes",{}).get("friendly_name","").split(": ")[-1]:x
           for x in advisories if isinstance(x,dict)}
    for label in ADVISORY_NAMES:
        require(any(label in k for k in names),"missing advisory entity: "+label)
    quality=next(x for x in advisories
                 if "Bathroom advisory learning quality" in
                 (x.get("attributes",{}).get("friendly_name") or ""))
    require(quality.get("attributes",{}).get("advisory_only") is True,
            "bathroom learner not identified as advisory")
    # Numeric forecasts are NEVER required immediately after activation.
    return {"advisory_entities_found":3,"target_unchanged":True,"predictions_required":False}
