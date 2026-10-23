#!/usr/bin/env python3
"""JNS VM902: enable the mobile Wi-Fi connection sensor through supported HA WS API.

Executed with Python *inside* the existing Home Assistant Core container.
Credentials remain inside the container; never print supervisor tokens.
Only changes sensor.sm_s721b_wi_fi_connection when disabled_by == integration.
"""
import asyncio
import json
import os
import sys

ENTITY = "sensor.sm_s721b_wi_fi_connection"
APPLY = "--apply" in sys.argv

async def main():
    try:
        import aiohttp
    except ImportError:
        print(json.dumps({"status":"blocked","reason":"missing_core_aiohttp"}))
        return 4
    token=os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        print(json.dumps({"status":"blocked","reason":"supervisor_token_not_available_in_core_container"}))
        return 5
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=100)) as session:
            async with session.ws_connect("ws://supervisor/core/websocket",timeout=12) as ws:
                hello=await ws.receive_json(timeout=12)
                if hello.get("type")!="auth_required":
                    print(json.dumps({"status":"blocked","reason":"unexpected_websocket_handshake"}))
                    return 6
                await ws.send_json({"type":"auth","access_token":token})
                authentication=await ws.receive_json(timeout=12)
                if authentication.get("type")!="auth_ok":
                    print(json.dumps({"status":"blocked","reason":"supervisor_websocket_auth_rejected"}))
                    return 7
                async def command(n,typ,**kwargs):
                    await ws.send_json(dict(id=n,type=typ,**kwargs))
                    while True:
                        d=await ws.receive_json(timeout=30)
                        if d.get("id")==n and d.get("type")=="result":
                            return d
                data=await command(1,"config/entity_registry/get_entries",entity_ids=[ENTITY])
                item=(data.get("result") or {}).get(ENTITY)
                if not data.get("success") or not item:
                    print(json.dumps({"status":"blocked","reason":"target_entity_not_in_live_registry","entity":ENTITY}))
                    return 8
                disabled=item.get("disabled_by")
                if disabled is None:
                    changed=False
                    status="already_enabled"
                    details={}
                elif disabled!="integration":
                    print(json.dumps({"status":"blocked","reason":"disabled_by_unexpected","disabled_by":disabled}))
                    return 9
                elif not APPLY:
                    print(json.dumps({"status":"ready_to_enable","entity":ENTITY,"disabled_by":disabled}))
                    return 0
                else:
                    result=await command(2,"config/entity_registry/update",entity_id=ENTITY,disabled_by=None)
                    if not result.get("success"):
                        print(json.dumps({"status":"blocked","reason":"registry_api_update_failed",
                                          "error_code":(result.get("error") or {}).get("code")}))
                        return 10
                    details=result.get("result") or {}
                    if (details.get("entity_entry") or {}).get("disabled_by") is not None:
                        print(json.dumps({"status":"blocked","reason":"registry_update_not_reflected"}))
                        return 11
                    changed=True
                    status="enabled"
                # The mobile_app integration may reload asynchronously.
                report={"status":status,"entity":ENTITY,"changed":changed,
                        "require_restart":bool(details.get("require_restart",False)),
                        "reload_delay":details.get("reload_delay")}
                print(json.dumps(report))
                return 0
    except Exception as exc:
        # Avoid leaking authentication/session content via exception text.
        print(json.dumps({"status":"blocked","reason":"websocket_transport_or_protocol_error",
                          "error_class":type(exc).__name__}))
        return 12

if __name__=="__main__":
    raise SystemExit(asyncio.run(main()))
