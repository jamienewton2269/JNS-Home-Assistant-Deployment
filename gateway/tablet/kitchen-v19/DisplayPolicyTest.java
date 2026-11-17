import uk.jns.hikvisiontalk.DisplayPolicy;

public final class DisplayPolicyTest {
  static class Display implements DisplayPolicy.View {
    boolean video=false, audio=false, guest=false, pin=false, locked=true;
    int sounds=0;
    public void hideAndStopCamera(){video=false;}
    public void showFrontCamera(){video=true;guest=false;locked=false;}
    public void showGuestQrOnly(){guest=true;video=false;locked=false;}
    public void showPrivacyLock(){locked=true;guest=false;video=false;}
    public void stopIncomingAudio(){audio=false;}
    public void listenToFrontDoor(int ms){if(ms!=45000)throw new AssertionError();audio=true;sounds++;}
    public void showLocalPinEntry(){pin=true;}
    public void hideLocalPinEntry(){pin=false;}
  }
  static void ok(boolean p) {if(!p)throw new AssertionError();}
  public static void main(String[] args){
    final long now=1770000000000L;
    Display d=new Display();DisplayPolicy p=new DisplayPolicy(d);
    ok(!d.video && !d.audio && d.locked);
    p.onDoorbellPress(false,"pressed",now);ok(!d.audio);
    p.onConnected();ok(d.locked && !d.video);
    p.onAlarmState("disarmed",now,now);ok(d.video);
    p.onDoorbellPress(false,"pressed",now);ok(d.audio && d.sounds==1);
    p.onDoorbellPress(false,"pressed",now+500);ok(d.sounds==1);
    p.onAlarmState("armed_away",now+800,now+800);ok(!d.video && !d.audio && d.guest);
    p.onDoorbellPress(false,"pressed",now+4000);ok(!d.audio);
    p.onSecretCornerTap(now+5000);p.onSecretCornerTap(now+5300);ok(!d.pin);
    p.onSecretCornerTap(now+5500);ok(d.pin);
    p.checkExpiry(now+37000);ok(!d.pin);
    p.onAlarmState("disarmed",now-999000,now+38000);ok(d.locked && !d.video);
    p.onAlarmState("armed_home",now+40000,now+40000);ok(d.video);
    p.onDoorbellPress(true,"pressed",now+42000);ok(!d.audio);
    p.onDoorbellPress(false,"pressed",now+42500);ok(d.audio);
    p.onDisconnected();ok(!d.video && !d.audio && d.locked);
    p.onConnected();p.onAlarmState("disarmed",now+60000,now+60000);ok(d.video);
    p.checkExpiry(now+110000);ok(!d.video && !d.audio && d.locked);
    p.onAlarmState("arming",now+111000,now+111000);ok(d.locked && !d.video);
    System.out.println("PASS: 19 kitchen privacy/listening assertions");
  }
}
