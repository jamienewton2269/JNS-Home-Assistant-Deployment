#!/usr/bin/env python3
"""Transactional HA-General clock persistence + lux priority/weather update."""
import base64, hashlib, json, re, shlex, subprocess, sys, time

NODEB_IP="10.10.110.12"; VMID="905"
BASE="/mnt/data/supervisor/homeassistant"
WEST=BASE+"/packages/ha_general_westminster.yaml"
AUTO=BASE+"/automations.yaml"
PKG=BASE+"/packages/lux_priority_weather.yaml"
DASH=BASE+"/dashboards/testing.yaml"
SSH=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=10","-o","StrictHostKeyChecking=yes","-o",f"HostName={NODEB_IP}","nodeb"]

def ssh(cmd,t=45):
    p=subprocess.run(SSH+[cmd],capture_output=True,text=True,timeout=t)
    if p.returncode: raise RuntimeError(p.stderr[-1200:])
    return p.stdout
def dec(raw):
    i=raw.find("{")
    if i<0: raise RuntimeError("no JSON: "+raw[-500:])
    return json.JSONDecoder().raw_decode(raw[i:])[0]
def guest(cmd,t=240):
    p=subprocess.run(SSH+["qm guest exec %s -- /bin/sh -c %s"%(VMID,shlex.quote(cmd))],capture_output=True,text=True,timeout=35)
    raw=(p.stdout or "")+(p.stderr or "")
    if p.returncode and "returning pid" not in raw: raise RuntimeError(raw[-1200:])
    d=dec(raw)
    if d.get("pid") is not None and not d.get("exited"):
        pid=int(d["pid"]); end=time.time()+t
        while time.time()<end:
            time.sleep(1); d=dec(ssh(f"qm guest exec-status {VMID} {pid}",20))
            if d.get("exited"): break
        else: raise RuntimeError("guest timeout")
    if not d.get("exited"): raise RuntimeError("guest did not exit")
    if int(d.get("exitcode",125)):
        raise RuntimeError((d.get("err-data") or "")+(d.get("out-data") or ""))
    return d.get("out-data") or ""
def fetch(path,optional=False):
    try: size=int(guest("wc -c < "+shlex.quote(path)).strip())
    except Exception:
        if optional:return None
        raise
    out=[]
    for i in range((size+2047)//2048):
        b=guest("dd if=%s bs=2048 skip=%d count=1 2>/dev/null | base64"%(shlex.quote(path),i))
        out.append(base64.b64decode("".join(b.split())))
    data=b"".join(out)
    if len(data)!=size: raise RuntimeError("incomplete fetch "+path)
    return data
def put_stage(path,data):
    st=path+".jns-priority-stage"; guest(": > "+shlex.quote(st))
    for i in range(0,len(data),1800):
        b64=base64.b64encode(data[i:i+1800]).decode()
        guest("printf '%s' "+shlex.quote(b64)+" | base64 -d >> "+shlex.quote(st))
    e=hashlib.sha256(data).hexdigest()
    a=guest("sha256sum %s | cut -d ' ' -f1"%shlex.quote(st)).strip()
    if e!=a: raise RuntimeError("sha mismatch "+path)
    return st,e

def patch_west(text):
    text=text.replace("    initial: false\n    icon: mdi:bell-ring\n","    initial: true\n    icon: mdi:bell-ring\n",1)
    return text

NEW_AUTOMATION=r"""- id: '1791918795028'
  alias: General - Shared Lux Progressive Control
  description: >-
    Priority-aware lux control. High-priority lights come on earlier; rain uses
    the immediate raw lux reading and raises the turn-on threshold. Turning off
    is deliberately conservative and requires the safe-off helper to remain on.
  triggers:
  - trigger: time_pattern
    minutes: /2
  - trigger: state
    entity_id:
    - sensor.0xa4c1383917c90309_illuminance
    - sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average
    - binary_sensor.outdoor_raining
    - input_number.general_outdoor_lighting_on_lux
    - input_number.general_lighting_lux_hysteresis
    - input_number.general_lux_full_brightness_at
    - input_number.general_lux_fixed_switch_percent
    - input_number.general_lux_priority_boost
    - input_number.general_lux_rain_boost
    - input_boolean.general_bedtime_mode
  conditions:
  - condition: state
    entity_id: input_boolean.general_bedtime_mode
    state: 'off'
  - condition: template
    value_template: >-
      {{ has_value('sensor.0xa4c1383917c90309_illuminance')
         and (as_timestamp(now()) -
              as_timestamp(states.sensor['0xa4c1383917c90309_illuminance'].last_updated,0)) < 600 }}
  actions:
  - variables:
      raw_lux: "{{ states('sensor.0xa4c1383917c90309_illuminance') | float(99999) }}"
      avg_lux: "{{ states('sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average') | float(raw_lux) }}"
      raining: "{{ is_state('binary_sensor.outdoor_raining','on') }}"
      decision_lux: "{{ [raw_lux|float, avg_lux|float] | min if raining|bool else avg_lux|float }}"
      base_start_lux: "{{ states('input_number.general_outdoor_lighting_on_lux') | float(2500) }}"
      rain_boost: "{{ states('input_number.general_lux_rain_boost') | float(1500) if raining|bool else 0 }}"
      normal_start_lux: "{{ base_start_lux|float + rain_boost|float }}"
      priority_start_lux: >-
        {{ normal_start_lux|float +
           states('input_number.general_lux_priority_boost') | float(1000) }}
      full_lux: "{{ states('input_number.general_lux_full_brightness_at') | float(100) }}"
      fixed_percent: "{{ states('input_number.general_lux_fixed_switch_percent') | float(50) }}"
      safe_off: "{{ is_state('binary_sensor.general_lux_safe_to_switch_off','on') }}"
      high_priority: >-
        {% set ids = label_entities('lighting_high_priority') | list %}
        {{ (ids + ['switch.general_kitchen_worktop_light']) | unique | list }}
      all_eligible: >-
        {% set ns = namespace(ids=[]) %}
        {% for e in label_entities('lighting_lux_controlled') %}
          {% set d = device_id(e) %}
          {% set assigned = labels(e) | list + (labels(d) | list if d else []) %}
          {% if 'commissioned' in assigned and 'purpose_standard_light' in assigned
                and 'purpose_protected_it' not in assigned
                and 'purpose_fan' not in assigned
                and 'purpose_grow_light' not in assigned
                and e != 'switch.0xa4c13837e231806e'
                and e.startswith(('light.','switch.')) and states(e) in ['on','off'] %}
            {% set ns.ids = ns.ids + [e] %}
          {% endif %}
        {% endfor %}
        {{ (ns.ids +
            ['switch.general_kitchen_worktop_light',
             'switch.general_kitchen_radiator_light']) | unique | list }}
  - repeat:
      for_each: "{{ all_eligible }}"
      sequence:
      - variables:
          e: "{{ repeat.item }}"
          priority: "{{ e in high_priority }}"
          start_lux: "{{ priority_start_lux|float if priority|bool else normal_start_lux|float }}"
          dimmable: >-
            {{ e.startswith('light.') and
               ((state_attr(e,'supported_color_modes') | default([],true) | list)
                | select('in',['brightness','color_temp','hs','xy','rgb','rgbw','rgbww','white'])
                | list | count > 0) }}
          level: >-
            {% set span = [start_lux|float - full_lux|float,1] | max %}
            {% set pct = 5 + 95 * (start_lux|float - decision_lux|float) / span %}
            {{ [100,[5,pct]|max]|min|round(0)|int }}
      - choose:
        - conditions:
          - condition: template
            value_template: "{{ safe_off|bool }}"
          sequence:
          - action: homeassistant.turn_off
            target:
              entity_id: "{{ e }}"
        - conditions:
          - condition: template
            value_template: "{{ priority|bool and decision_lux|float < start_lux|float and dimmable }}"
          sequence:
          - action: light.turn_on
            target:
              entity_id: "{{ e }}"
            data:
              brightness_pct: "{{ level|int }}"
        - conditions:
          - condition: template
            value_template: "{{ priority|bool and decision_lux|float < start_lux|float and not dimmable }}"
          sequence:
          - action: homeassistant.turn_on
            target:
              entity_id: "{{ e }}"
        - conditions:
          - condition: template
            value_template: "{{ not priority|bool and decision_lux|float < start_lux|float and dimmable }}"
          sequence:
          - action: light.turn_on
            target:
              entity_id: "{{ e }}"
            data:
              brightness_pct: "{{ level|int }}"
        - conditions:
          - condition: template
            value_template: >-
              {{ not priority|bool and decision_lux|float < start_lux|float
                 and not dimmable and level|float >= fixed_percent|float }}
          sequence:
          - action: homeassistant.turn_on
            target:
              entity_id: "{{ e }}"
  mode: restart
"""

def patch_auto(text):
    pat=re.compile(r"(?ms)^- id: '1791918795028'\n.*?(?=^- id: )")
    new,n=pat.subn(NEW_AUTOMATION,text,count=1)
    if n!=1: raise RuntimeError("progressive automation block not found")
    return new

PACKAGE=r"""# Native Home Assistant helpers for lux priority/weather behaviour.
input_number:
  general_lux_priority_boost:
    name: General Lux - High Priority Early Start
    min: 0
    max: 5000
    step: 100
    initial: 1000
    unit_of_measurement: lx
    mode: slider
    icon: mdi:lightning-bolt-circle
  general_lux_rain_boost:
    name: General Lux - Rain Early Start
    min: 0
    max: 5000
    step: 100
    initial: 1500
    unit_of_measurement: lx
    mode: slider
    icon: mdi:weather-rainy

template:
  - binary_sensor:
      - name: General Lux Safe to Switch Off
        unique_id: general_lux_safe_to_switch_off
        icon: mdi:weather-sunny-alert
        delay_on: "00:20:00"
        delay_off: "00:00:00"
        state: >-
          {% set avg = states('sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average') %}
          {% set off_lux =
             states('input_number.general_outdoor_lighting_on_lux')|float(2500) +
             states('input_number.general_lighting_lux_hysteresis')|float(400) %}
          {{ not is_state('binary_sensor.outdoor_raining','on')
             and is_number(avg)
             and avg|float >= off_lux }}
"""

def patch_dash(text):
    if "JNS_LUX_PRIORITY_WEATHER_V1" in text:return text
    marker="  - type: entities\n    title: Daylight Lighting Controls\n"
    i=text.find(marker)
    if i<0: raise RuntimeError("daylight controls card not found")
    # add two control rows inside existing card after hysteresis row
    target="""    - entity: input_number.general_lighting_lux_hysteresis
      name: Hysteresis width (lux)
"""
    repl=target+"""    - entity: input_number.general_lux_priority_boost
      name: High-priority early start (+lux)
    - entity: input_number.general_lux_rain_boost
      name: Rain early start (+lux)
"""
    if target not in text: raise RuntimeError("hysteresis row not found")
    text=text.replace(target,repl,1)
    # add status/instructions before Outdoor Daylight
    marker2="  - type: entities\n    title: Outdoor Daylight\n"
    card=r"""  # JNS_LUX_PRIORITY_WEATHER_V1
  - type: entities
    title: Priority / Weather Status
    show_header_toggle: false
    entities:
    - entity: binary_sensor.outdoor_raining
      name: Rain detected
    - entity: binary_sensor.general_lux_safe_to_switch_off
      name: Safe to turn lights off
    - entity: switch.general_kitchen_worktop_light
      name: Kitchen Worktop - High Priority
    - entity: switch.general_kitchen_radiator_light
      name: Kitchen Radiator - Normal Priority
  - type: markdown
    title: High Priority Lighting
    content: |
      **Kitchen Worktop** is currently high priority and comes on before normal
      lux-controlled lighting.

      To make any other light high priority, assign the normal Home Assistant
      label **Lighting: High Priority** to that entity/device. High-priority
      lights use the **High-priority early start** boost above.

      When **Rain detected** is ON, the controller reacts to the immediate raw
      lux reading and adds the **Rain early start** boost. Lights only turn off
      after conditions have been bright and dry continuously for 20 minutes.
"""
    if marker2 not in text: raise RuntimeError("Outdoor Daylight marker missing")
    text=text.replace(marker2,card+marker2,1)
    return text

print("[1/9] precheck",flush=True)
ssh(f"qm status {VMID} | grep -q 'status: running'"); ssh(f"timeout 8 qm agent {VMID} ping")
orig={WEST:fetch(WEST),AUTO:fetch(AUTO),DASH:fetch(DASH),PKG:fetch(PKG,True)}
new={
 WEST:patch_west(orig[WEST].decode()).encode(),
 AUTO:patch_auto(orig[AUTO].decode()).encode(),
 DASH:patch_dash(orig[DASH].decode()).encode(),
 PKG:PACKAGE.encode(),
}
stamp=time.strftime("%Y%m%dT%H%M%S"); backups={}; staged={}; installed=False
try:
    print("[2/9] backup",flush=True)
    for p,b in orig.items():
        if b is not None:
            bp=p+f".jns-priority-{stamp}.bak"; backups[p]=bp
            guest("cp -p %s %s"%(shlex.quote(p),shlex.quote(bp)))
    print("[3/9] stage/checksum",flush=True)
    for p,b in new.items():
        staged[p],sha=put_stage(p,b); print(p,sha,flush=True)
    print("[4/9] install",flush=True)
    for p in new: guest("mv %s %s"%(shlex.quote(staged[p]),shlex.quote(p)))
    installed=True
    print("[5/9] config check",flush=True); print(guest("ha core check",300)[-3000:],flush=True)
    print("[6/9] restart",flush=True); guest("ha core restart",300)
    print("[7/9] health",flush=True)
    ok=False
    for n in range(60):
        try:
            if "version:" in guest("ha core info",30): ok=True; break
        except Exception: pass
        time.sleep(2)
    if not ok: raise RuntimeError("Core did not become healthy")
    print("[8/9] verify files",flush=True)
    for p,tok in [(WEST,"initial: true"),(AUTO,"general_lux_priority_boost"),(PKG,"General Lux Safe to Switch Off"),(DASH,"JNS_LUX_PRIORITY_WEATHER_V1")]:
        guest("grep -Fq -- %s %s"%(shlex.quote(tok),shlex.quote(p)))
        print("verified",tok,flush=True)
    print("[9/9] live state snapshot",flush=True)
    print(guest("grep -nE 'input_boolean.jns_westminster_enabled|binary_sensor.outdoor_raining|binary_sensor.general_lux_safe_to_switch_off|sensor.0xa4c1383917c90309_illuminance' %s/.storage/core.restore_state | tail -20"%BASE)[-5000:],flush=True)
except Exception:
    if installed:
        print("ROLLBACK",file=sys.stderr,flush=True)
        for p in new:
            try:
                if p in backups: guest("cp -p %s %s"%(shlex.quote(backups[p]),shlex.quote(p)))
                else: guest("rm -f "+shlex.quote(p))
            except Exception as e: print("rollback",p,e,file=sys.stderr)
        try: guest("ha core check",300); guest("ha core restart",300)
        except Exception as e: print("rollback restart",e,file=sys.stderr)
    raise
print("DEPLOYMENT_OK",flush=True)
print("default_high_priority=switch.general_kitchen_worktop_light",flush=True)
print("normal_priority=switch.general_kitchen_radiator_light",flush=True)
print("rain=binary_sensor.outdoor_raining",flush=True)
