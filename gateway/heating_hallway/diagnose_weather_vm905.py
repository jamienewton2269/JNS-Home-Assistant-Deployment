#!/usr/bin/env python3
"""Read-only weather provider and hourly forecast health check for VM905.
Uses HAOS app_core_ssh Supervisor token in-process; no credentials or complete
forecast/weather datasets appear in GitHub logs.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

def run_guest(command,timeout=90):
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*command]))
    deadline=time.monotonic()+timeout
    while not r.get("exited"):
        if time.monotonic()>deadline or not isinstance(r.get("pid"),int):
            raise RuntimeError("Weather audit guest command completion uncertain")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
    if r.get("exitcode")!=0:
        msg=(r.get("err-data") or "").splitlines()[-1:]
        raise RuntimeError("Weather audit failed, "+str(msg)[:180])
    return (r.get("out-data") or "").strip()

CONFIG=r'''
import json,pathlib
root=pathlib.Path("/config")
items=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
weather=[{"domain":e.get("domain"),"enabled":not bool(e.get("disabled_by"))}
 for e in items if e.get("domain") in ("open_meteo","met","metoffice","accuweather","pirateweather","weatherkit","tomorrowio")]
heating=[e for e in items if e.get("domain")=="jns_heating_zones"]
result={"weather_providers":weather,"heating_entries":len(heating),
"heating_weather_entity":[(e.get("options") or {}).get("weather_entity",(e.get("data") or {}).get("weather_entity")) for e in heating],
"heating_outdoor_entity":[(e.get("options") or {}).get("outdoor_temperature_entity",(e.get("data") or {}).get("outdoor_temperature_entity")) for e in heating],
"heating_entity_available":len(heating)==1}
print("JNS_HEATING_WEATHER_CONFIG "+json.dumps(result,sort_keys=True))
'''
SHELL=r'''
set -eu
test -n "$SUPERVISOR_TOKEN" || { echo 'JNS_WEATHER_AUTH=missing'; exit 71; }
API=http://supervisor/core/api
AUTH="Authorization: Bearer $SUPERVISOR_TOKEN"
data="$(curl --fail -sS -m 15 -H "$AUTH" "$API/states")" || { echo 'JNS_WEATHER_AUTH=failed'; exit 72; }
printf '%s' "$data" | jq -c '
  {weather_entities:[.[]|select(.entity_id|startswith("weather."))|
     {id:.entity_id,available:(.state!="unknown" and .state!="unavailable"),
     current_outdoor_temp_valid:(.attributes.temperature|numbers|.>-30 and .<50)}],
   outdoor_sensor_state:[.[]|select(.entity_id=="sensor.thermostat_thermostat_outdoor_temperature"
     or .entity_id=="sensor.0xa4c13880bb5cffff_temperature")|
      {id:.entity_id,valid:(.state|tonumber? != null)}],
   heating_state:[.[]|select(.entity_id=="sensor.lyric_home_heating_thermal_learning")|
      {present:true,model_ready:(.attributes.ready==true)}]}' |
 sed 's/^/JNS_WEATHER_STATE /'
ids="$(printf '%s' "$data" | jq -r '[.[]|select(.entity_id|startswith("weather.")
 and .state!="unknown" and .state!="unavailable")|.entity_id]|.[:5]|.[]')"
for id in $ids; do
  case "$id" in weather.*) ;; *) echo 'unexpected weather id';exit 73;; esac
  body="$(jq -nc --arg id "$id" '{entity_id:$id,type:"hourly"}')"
  outfile="$(mktemp)"
  errfile="$(mktemp)"
  httpcode="$(curl -sS -m 18 -o "$outfile" -w '%{http_code}' -X POST -H "$AUTH" \
     -H "Content-Type: application/json" \
     -d "$body" "$API/services/weather/get_forecasts?return_response" 2>"$errfile")" || httpcode="transport_error"
  if [ "$httpcode" = 200 ];then
    jq -c --arg id "$id" '(.service_response[$id].forecast // []) as $f|
      {provider:$id,http_status:200,rows:($f|length),
       hourly_temperatures_valid:([$f[]|.temperature|numbers]|length),
       has_future:([$f[]|select((.datetime|type)=="string")]|length>1),
       forecast_first:($f[0].datetime//null),
       forecast_last:($f[-1].datetime//null)}' "$outfile" | sed 's/^/JNS_WEATHER_FORECAST /'
  else
    printf 'JNS_WEATHER_FORECAST {"provider":"%s","http_status":"%s","rows":0}\n' "$id" "$httpcode"
  fi
  rm -f "$outfile" "$errfile"
done
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("VM905 not running")
    py="exec(__import__('base64').b64decode('"+base64.b64encode(CONFIG.encode()).decode()+"'))"
    cfg=run_guest(["docker","exec","homeassistant","python3","-c",py])
    for line in cfg.splitlines():
        if line.startswith("JNS_HEATING_WEATHER_CONFIG "):print(line,flush=True)
    output=run_guest(["docker","exec","app_core_ssh","sh","-c",SHELL],115)
    for line in output.splitlines():
        if line.startswith(("JNS_WEATHER_STATE ","JNS_WEATHER_FORECAST ","JNS_WEATHER_AUTH=")):
            print(line,flush=True)
if __name__=="__main__":main()
