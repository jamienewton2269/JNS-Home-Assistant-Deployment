#!/usr/bin/env python3
"""Issue ONE verified Garden String Lights OFF via local Zigbee2MQTT MQTT client.
Node C -> Node B CT214; no credentials transferred to Node C; no HA configuration edits.
"""
import base64,json,sys,time,subprocess,shlex
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
NODE=r"""
const fs=require('fs');
const yaml=require('/opt/zigbee2mqtt/node_modules/yaml');
const mqtt=require('/opt/zigbee2mqtt/node_modules/mqtt');
const dev=yaml.parse(fs.readFileSync('/opt/zigbee2mqtt/data/devices.yaml','utf8'));
const cfg=yaml.parse(fs.readFileSync('/opt/zigbee2mqtt/data/configuration.yaml','utf8'));
const ieee='0xa4c1388ba234f2e3', desired='Garden String Lights';
const entry=dev[ieee];
if (!entry || entry.friendly_name!==desired) {
 console.log('JNS_STRING_OFF_BLOCKED device_identity_mismatch');
 process.exit(2);
}
if(!cfg.mqtt || typeof cfg.mqtt.server!=='string' || !cfg.mqtt.server.startsWith('mqtt://')){
 console.log('JNS_STRING_OFF_BLOCKED unsupported_broker_config');
 process.exit(2);
}
const base=cfg.mqtt.base_topic || 'zigbee2mqtt';
const topic=base+'/'+desired;
const opts={
 clientId:'jns-garden-off-'+process.pid,
 username:cfg.mqtt.user,
 password:cfg.mqtt.password,
 clean:true,
 reconnectPeriod:0,
 connectTimeout:7500
};
let published=false,verified=false;
const client=mqtt.connect(cfg.mqtt.server,opts);
function finish(code,label){
 console.log(label);
 client.end(true);
 setTimeout(()=>process.exit(code),150);
}
const timer=setTimeout(()=>{
 finish(verified?0:3,published?'JNS_STRING_OFF_SENT_NOT_STATE_CONFIRMED':'JNS_STRING_OFF_NO_BROKER_ACK');
},17000);
client.on('error',e=>{clearTimeout(timer);finish(2,'JNS_STRING_OFF_BROKER_ERROR '+e.code);});
client.on('connect',()=>{
 client.subscribe(topic,{qos:1},(err)=>{
  if(err){clearTimeout(timer);finish(2,'JNS_STRING_OFF_SUBSCRIBE_FAILED');return;}
  client.publish(topic+'/set',JSON.stringify({state:'OFF'}),{qos:1,retain:false},e=>{
   if(e){clearTimeout(timer);finish(2,'JNS_STRING_OFF_PUBLISH_FAILED');return;}
   published=true;
   console.log('JNS_STRING_OFF_MQTT_QOS1_ACCEPTED');
  });
 });
});
client.on('message',(name,message)=>{
 if(name!==topic)return;
 try{
  const state=JSON.parse(message.toString()).state;
  if(state==='OFF' && published && !verified){
   verified=true;
   clearTimeout(timer);
   finish(0,'JNS_STRING_OFF_DEVICE_REPORTED_OFF');
  }
 }catch(e){}
});
"""
def main():
 print("JNS_GARDEN_STRING_SINGLE_DEVICE_OFF_START",flush=True)
 assert 'running' in ssh_host("nodeb",["pct","status","214"]),"CT214 not running"
 assert 'running' in ssh_host("nodeb",["pct","status","212"]),"CT212 not running"
 code=base64.b64encode(NODE.encode()).decode()
 src="eval(Buffer.from('"+code+"','base64').toString('utf8'))"
 command=["pct","exec","214","--","/opt/node22/bin/node","-e",src]
 try:
  assert ssh_host("nodeb",["hostname","-s"]).strip()=="nodeb","Trusted node identity mismatch"
  proc=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","root@nodeb.home.arpa",shlex.join(command)],capture_output=True,text=True,timeout=48)
  result=proc.stdout
  print("JNS_GARDEN_STRING_CONTROL",json.dumps({"rc":proc.returncode,"stdout_tail":result[-1400:],"stderr_tail":proc.stderr[-500:]}),flush=True)
  if proc.returncode:raise RuntimeError("CT214 MQTT action command rejected")
  if "JNS_STRING_OFF_DEVICE_REPORTED_OFF" not in result:
   raise RuntimeError("OFF not confirmed by Zigbee2MQTT state topic")
 except Exception as e:
  print("JNS_GARDEN_STRING_OFF_UNVERIFIED",type(e).__name__,str(e)[:180],flush=True)
  raise SystemExit(2)
if __name__=="__main__":main()
