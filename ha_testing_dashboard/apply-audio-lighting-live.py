#!/usr/bin/env python3
import base64, hashlib, json, re, shlex, subprocess, sys, time

NODEB_IP="10.10.110.12"
VMID="905"
BASE="/mnt/data/supervisor/homeassistant"
DASH=BASE+"/dashboards/testing.yaml"
HOUSE_CLOCK=BASE+"/packages/house_clock.yaml"
WESTMINSTER=BASE+"/packages/ha_general_westminster.yaml"
SSH=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=10","-o","StrictHostKeyChecking=yes","-o",f"HostName={NODEB_IP}","nodeb"]

def run_ssh(command,timeout=45):
    p=subprocess.run(SSH+[command],capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"SSH command failed rc={p.returncode}: {p.stderr[-1200:]}")
    return p.stdout

def decode_json(raw):
    pos=raw.find("{")
    if pos<0:
        raise RuntimeError("No JSON from qm guest exec: "+raw[-1000:])
    return json.JSONDecoder().raw_decode(raw[pos:])[0]

def guest(command,timeout=240):
    remote="qm guest exec %s -- /bin/sh -c %s"%(VMID,shlex.quote(command))
    p=subprocess.run(SSH+[remote],capture_output=True,text=True,timeout=35)
    raw=(p.stdout or "")+(p.stderr or "")
    if p.returncode and "returning pid" not in raw:
        raise RuntimeError(f"guest exec failed rc={p.returncode}: {raw[-1200:]}")
    d=decode_json(raw)
    if d.get("pid") is not None and not d.get("exited"):
        pid=int(d["pid"])
        deadline=time.time()+timeout
        while time.time()<deadline:
            time.sleep(1)
            d=decode_json(run_ssh(f"qm guest exec-status {VMID} {pid}",timeout=20))
            if d.get("exited"):
                break
        else:
            raise RuntimeError(f"guest timeout pid={pid}")
    if not d.get("exited"):
        raise RuntimeError("guest command did not exit")
    rc=int(d.get("exitcode",125))
    out=d.get("out-data") or ""
    err=d.get("err-data") or ""
    if rc:
        raise RuntimeError(f"guest command rc={rc}: {err[-1200:]} {out[-500:]}")
    return out

def fetch(path):
    size=int(guest("wc -c < "+shlex.quote(path)).strip())
    if not (200<size<250000):
        raise RuntimeError(f"Unexpected file size {path}: {size}")
    parts=[]
    for i in range((size+2047)//2048):
        raw=guest("dd if=%s bs=2048 skip=%d count=1 2>/dev/null | base64"%(shlex.quote(path),i))
        parts.append(base64.b64decode("".join(raw.split())))
    data=b"".join(parts)
    if len(data)!=size:
        raise RuntimeError(f"Incomplete transfer {path}")
    return data

def stage(path,data):
    staged=path+".jns-audio-lighting-stage"
    guest(": > "+shlex.quote(staged))
    for i in range(0,len(data),1800):
        b64=base64.b64encode(data[i:i+1800]).decode()
        guest("printf '%s' %s | base64 -d >> %s"%(shlex.quote(b64),shlex.quote(staged)))
    expected=hashlib.sha256(data).hexdigest()
    actual=guest("sha256sum %s | cut -d ' ' -f1"%shlex.quote(staged)).strip()
    if actual!=expected:
        raise RuntimeError(f"Checksum mismatch staging {path}")
    return staged,expected

def patch_dashboard(text):
    marker="- title: Lighting Settings\n  path: lighting-settings"
    if marker not in text:
        raise RuntimeError("Lighting Settings view not found")
    if "JNS_LUX_LIVE_STATUS_V1" not in text:
        start=text.index(marker)
        cards=text.index("  cards:\n",start)+len("  cards:\n")
        lux_card=r"""  # JNS_LUX_LIVE_STATUS_V1
  - type: markdown
    title: Live Outdoor Lux Status
    content: |
      {% set raw_e = 'sensor.0xa4c1383917c90309_illuminance' %}
      {% set avg_e = 'sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average' %}
      {% set s = states.sensor['0xa4c1383917c90309_illuminance'] %}
      {% set age = ((as_timestamp(now()) - as_timestamp(s.last_updated, 0)) / 60) | round(1) %}
      {% set on_lux = states('input_number.general_outdoor_lighting_on_lux') | float(2500) %}
      **Current lux:** {{ states(raw_e) }} lx

      **10-minute average:** {{ states(avg_e) }} lx

      **Last sensor update:** {{ as_local(s.last_updated).strftime('%H:%M:%S') }}
      ({{ relative_time(s.last_updated) }} ago)

      **Update age:** {{ age }} minutes

      {% if not has_value(raw_e) %}
      **Sensor status:** 🔴 UNAVAILABLE
      {% elif age <= 5 %}
      **Sensor status:** 🟢 LIVE
      {% elif age <= 30 %}
      **Sensor status:** 🟠 DELAYED
      {% else %}
      **Sensor status:** 🔴 STALE
      {% endif %}

      {% if has_value(raw_e) %}
      {% if states(raw_e) | float < on_lux %}
      **Lighting threshold:** 🟢 BELOW the {{ on_lux | round(0) }} lx ON threshold
      {% else %}
      **Lighting threshold:** ⚪ ABOVE the {{ on_lux | round(0) }} lx ON threshold
      {% endif %}
      {% endif %}
"""
        text=text[:cards]+lux_card+text[cards:]
    if "path: audio-clock" not in text:
        audio_view=r"""
- title: Audio / Clock
  path: audio-clock
  icon: mdi:music-circle
  cards:
  - type: markdown
    content: |
      ## House Audio & Clock
      Native Home Assistant controls for the house clock and shared audio.
      Westminster is installed now. Bird Calls and Custom use matching MPD
      playlists when those media sets are added; until then playback safely
      falls back to Westminster.

  - type: entities
    title: House Clock
    show_header_toggle: false
    entities:
    - entity: input_boolean.jns_westminster_enabled
      name: Chimes enabled
      icon: mdi:bell-ring
    - entity: input_select.general_clock_sound
      name: Sound scheme
      icon: mdi:music-box-multiple
    - entity: input_datetime.jns_westminster_quiet_from
      name: Quiet from
    - entity: input_datetime.jns_westminster_quiet_until
      name: Quiet until
    - entity: input_number.jns_westminster_volume
      name: Chime volume
    - entity: input_boolean.general_clock_half_hour_enabled
      name: Half-hour chime
    - entity: input_select.general_clock_mode
      name: Clock mode

  - type: grid
    columns: 2
    square: false
    cards:
    - type: button
      entity: script.jns_clock_test_selected_half
      name: Test half-hour
      icon: mdi:bell
      tap_action:
        action: toggle
    - type: button
      entity: script.jns_clock_test_selected_hour
      name: Test current hour
      icon: mdi:clock-outline
      tap_action:
        action: toggle

  - type: entities
    title: Audio Status
    show_header_toggle: false
    entities:
    - entity: media_player.music_player_daemon
      name: House audio player
    - entity: automation.westminster_chimes_half_and_hour
      name: Clock schedule
    - entity: input_text.general_clock_last_event
      name: Last clock event

  - type: markdown
    title: Selected Scheme Status
    content: |
      {% set scheme = states('input_select.general_clock_sound') %}
      **Selected:** {{ scheme }}

      **Audio player:** {{ states('media_player.music_player_daemon') }}

      {% if scheme == 'Bird Calls' %}
      Expected playlists: jns_birds_half and jns_birds_hour_01 through jns_birds_hour_12.
      {% elif scheme == 'Custom' %}
      Expected playlists: jns_custom_half and jns_custom_hour_01 through jns_custom_hour_12.
      {% elif scheme == 'Silent' %}
      Clock audio is muted by the sound-scheme selector.
      {% else %}
      Westminster playlists are installed.
      {% endif %}

      If Bird Calls or Custom media is not installed yet, playback automatically
      falls back to Westminster rather than breaking the clock.
"""
        text=text.rstrip()+"\n"+audio_view
    return text

def patch_house_clock(text):
    old="""  general_clock_sound:
    name: House clock sound
    options:
      - Westminster
      - Silent
    initial: Westminster
"""
    new="""  general_clock_sound:
    name: House clock sound
    options:
      - Westminster
      - Bird Calls
      - Custom
      - Silent
    initial: Westminster
"""
    if "      - Bird Calls\n" not in text:
        if old not in text:
            raise RuntimeError("Unexpected house_clock selector layout")
        text=text.replace(old,new,1)
    return text

def patch_westminster(text):
    if "jns_clock_test_selected_half:" not in text:
        marker="\nautomation:\n"
        if marker not in text:
            raise RuntimeError("Westminster automation marker missing")
        scripts=r"""
  jns_clock_test_selected_half:
    alias: "House Clock - Test Selected Half-hour"
    mode: single
    sequence:
      - variables:
          sound_scheme: "{{ states('input_select.general_clock_sound') }}"
          requested_playlist: >-
            {% if sound_scheme == 'Bird Calls' %}
              jns_birds_half
            {% elif sound_scheme == 'Custom' %}
              jns_custom_half
            {% else %}
              jns_westminster_half
            {% endif %}
          playlist_name: >-
            {% set available = state_attr('media_player.music_player_daemon', 'source_list') or [] %}
            {{ requested_playlist | trim if requested_playlist | trim in available else 'jns_westminster_half' }}
      - condition: template
        value_template: "{{ sound_scheme != 'Silent' }}"
      - action: media_player.volume_set
        target:
          entity_id: media_player.music_player_daemon
        data:
          volume_level: "{{ states('input_number.jns_westminster_volume') | float(100) / 100 }}"
      - action: media_player.play_media
        target:
          entity_id: media_player.music_player_daemon
        data:
          media_content_type: playlist
          media_content_id: "{{ playlist_name | trim }}"

  jns_clock_test_selected_hour:
    alias: "House Clock - Test Selected Current Hour"
    mode: single
    sequence:
      - variables:
          sound_scheme: "{{ states('input_select.general_clock_sound') }}"
          hour_number: "{{ '%02d' | format(((now().hour - 1) % 12) + 1) }}"
          requested_playlist: >-
            {% if sound_scheme == 'Bird Calls' %}
              jns_birds_hour_{{ hour_number }}
            {% elif sound_scheme == 'Custom' %}
              jns_custom_hour_{{ hour_number }}
            {% else %}
              jns_westminster_hour_{{ hour_number }}
            {% endif %}
          fallback_playlist: "jns_westminster_hour_{{ hour_number }}"
          playlist_name: >-
            {% set available = state_attr('media_player.music_player_daemon', 'source_list') or [] %}
            {{ requested_playlist | trim if requested_playlist | trim in available else fallback_playlist | trim }}
      - condition: template
        value_template: "{{ sound_scheme != 'Silent' }}"
      - action: media_player.volume_set
        target:
          entity_id: media_player.music_player_daemon
        data:
          volume_level: "{{ states('input_number.jns_westminster_volume') | float(100) / 100 }}"
      - action: media_player.play_media
        target:
          entity_id: media_player.music_player_daemon
        data:
          media_content_type: playlist
          media_content_id: "{{ playlist_name | trim }}"
"""
        text=text.replace(marker,scripts+marker,1)

    if "states('input_select.general_clock_sound') != 'Silent'" not in text:
        anchor="""      - condition: state
        entity_id: input_boolean.jns_westminster_enabled
        state: 'on'
"""
        addition=anchor+"""      - condition: template
        value_template: "{{ states('input_select.general_clock_sound') != 'Silent' }}"
"""
        if anchor not in text:
            raise RuntimeError("Westminster enabled condition not found")
        text=text.replace(anchor,addition,1)

    automation_text=text[text.find("automation:"):]
    if "requested_playlist:" not in automation_text:
        pat=re.compile(r"""      - variables:\n          playlist_name: >-\n.*?(?=      - action: media_player\.volume_set)""",re.S)
        replacement=r"""      - variables:
          sound_scheme: "{{ states('input_select.general_clock_sound') }}"
          hour_number: "{{ '%02d' | format(((now().hour - 1) % 12) + 1) }}"
          requested_playlist: >-
            {% if trigger.id == 'half' %}
              {% if sound_scheme == 'Bird Calls' %}
                jns_birds_half
              {% elif sound_scheme == 'Custom' %}
                jns_custom_half
              {% else %}
                jns_westminster_half
              {% endif %}
            {% else %}
              {% if sound_scheme == 'Bird Calls' %}
                jns_birds_hour_{{ hour_number }}
              {% elif sound_scheme == 'Custom' %}
                jns_custom_hour_{{ hour_number }}
              {% else %}
                jns_westminster_hour_{{ hour_number }}
              {% endif %}
            {% endif %}
          fallback_playlist: >-
            {% if trigger.id == 'half' %}
              jns_westminster_half
            {% else %}
              jns_westminster_hour_{{ hour_number }}
            {% endif %}
          playlist_name: >-
            {% set available = state_attr('media_player.music_player_daemon', 'source_list') or [] %}
            {{ requested_playlist | trim if requested_playlist | trim in available else fallback_playlist | trim }}
"""
        text,n=pat.subn(replacement,text,count=1)
        if n!=1:
            raise RuntimeError("Could not patch Westminster scheduled selector")
    return text

print("[1/8] Verify VM905 and QGA",flush=True)
run_ssh(f"qm status {VMID} | grep -q 'status: running'")
run_ssh(f"timeout 8 qm agent {VMID} ping")

print("[2/8] Fetch current live files",flush=True)
original={DASH:fetch(DASH),HOUSE_CLOCK:fetch(HOUSE_CLOCK),WESTMINSTER:fetch(WESTMINSTER)}
texts={p:b.decode("utf-8") for p,b in original.items()}

print("[3/8] Build native Home Assistant changes",flush=True)
new={
    DASH:patch_dashboard(texts[DASH]).encode(),
    HOUSE_CLOCK:patch_house_clock(texts[HOUSE_CLOCK]).encode(),
    WESTMINSTER:patch_westminster(texts[WESTMINSTER]).encode(),
}

stamp=time.strftime("%Y%m%dT%H%M%S")
backups={p:p+f".jns-audio-lighting-{stamp}.bak" for p in original}
staged={}
installed=False
try:
    print("[4/8] Backup and stage with SHA256",flush=True)
    for p in original:
        guest("cp -p %s %s"%(shlex.quote(p),shlex.quote(backups[p])))
        staged[p],sha=stage(p,new[p])
        print(f"  {p}: {sha}",flush=True)

    print("[5/8] Atomic install",flush=True)
    for p in original:
        guest("mv %s %s"%(shlex.quote(staged[p]),shlex.quote(p)))
    installed=True

    print("[6/8] HA configuration check",flush=True)
    print(guest("ha core check",timeout=240)[-4000:],flush=True)

    print("[7/8] Restart and health verification",flush=True)
    guest("ha core restart",timeout=240)
    healthy=False
    for n in range(1,61):
        try:
            info=guest("ha core info",timeout=30)
            if "version:" in info:
                print(f"  Core healthy attempt={n}",flush=True)
                healthy=True
                break
        except Exception:
            pass
        time.sleep(2)
    if not healthy:
        raise RuntimeError("HA Core did not return healthy")

    print("[8/8] Verify deployed markers",flush=True)
    for p,token in [
        (DASH,"JNS_LUX_LIVE_STATUS_V1"),
        (DASH,"path: audio-clock"),
        (HOUSE_CLOCK,"- Bird Calls"),
        (HOUSE_CLOCK,"- Custom"),
        (WESTMINSTER,"jns_clock_test_selected_half"),
        (WESTMINSTER,"jns_clock_test_selected_hour"),
        (WESTMINSTER,"requested_playlist"),
    ]:
        guest("grep -Fq -- %s %s"%(shlex.quote(token),shlex.quote(p)))
        print("  verified "+token,flush=True)
except Exception:
    if installed:
        print("ROLLBACK: restoring previous files",file=sys.stderr,flush=True)
        for p in original:
            try:
                guest("cp -p %s %s"%(shlex.quote(backups[p]),shlex.quote(p)))
            except Exception as e:
                print("rollback error",p,e,file=sys.stderr)
        try:
            guest("ha core check",timeout=240)
            guest("ha core restart",timeout=240)
        except Exception as e:
            print("rollback check/restart error",e,file=sys.stderr)
    raise

print("DEPLOYMENT_OK",flush=True)
for p in original:
    print("backup="+backups[p],flush=True)
print("lighting=/testing-dashboard/lighting-settings",flush=True)
print("audio_clock=/testing-dashboard/audio-clock",flush=True)
print("westminster_master_state_preserved=true",flush=True)
