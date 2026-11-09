import asyncio,os,json,pathlib,aiohttp,yaml
async def main():
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=35)) as s:
  token_path=pathlib.Path('/config/.jns-steward/ha_general_api.token')
  print('LOCAL_TOKEN_PRESENT',token_path.exists(),flush=True)
  assert token_path.exists(),'Local HA API credential missing'
  token=token_path.read_text().strip()
  async with s.ws_connect('http://127.0.0.1/api/websocket',receive_timeout=15) as ws:
   first=await ws.receive_json()
   if first.get('type')=='auth_required':
    await ws.send_json({'type':'auth','access_token':token})
    first=await ws.receive_json()
   assert first.get('type')=='auth_ok','Core websocket authentication failed'
   print('CORE_WS_AUTH_OK',flush=True)
   for i,cmd in enumerate(['lovelace/resources','lovelace/dashboards/list','lovelace/config'],1):
    await ws.send_json({'id':i,'type':cmd})
    while True:
     r=await ws.receive_json()
     if r.get('id')==i:break
    if not r.get('success'):
     print('API_RESULT',cmd,json.dumps(r.get('error')),flush=True);continue
    d=r.get('result')
    if cmd=='lovelace/resources':print('RESOURCES',json.dumps(d),flush=True)
    elif cmd=='lovelace/dashboards/list':print('DASHBOARDS',json.dumps([{k:x.get(k) for k in ('id','url_path','mode','filename')} for x in d]),flush=True)
    else: print('DEFAULT_CONFIG',json.dumps({'keys':list(d),'views':len(d.get('views',[]))}),flush=True)
  async with s.get('http://127.0.0.1/local/community/Statistics-Graph-Chart-Card/statistics-graph-chart-card.js') as r:
   b=await r.read();print('CARD_HTTP',r.status,'bytes',len(b),flush=True)
asyncio.run(main())
