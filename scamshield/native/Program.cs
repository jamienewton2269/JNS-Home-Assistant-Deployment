using Microsoft.Win32;
using System.Diagnostics;
using System.Security.Principal;
using System.Text.Json;

record Policy(string Key, string Name, int Desired);
record OwnedPolicy(string Key, string Name, int Desired);
class Program {
 static readonly string Root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),"JNS","ScamShield");
 static readonly string OwnedFile=Path.Combine(Root,"owned-policies.json");
 static readonly Policy[] Policies={
  new(@"SOFTWARE\Policies\Microsoft\Edge","DefaultNotificationsSetting",2),
  new(@"SOFTWARE\Policies\Microsoft\Edge","DefaultPopupsSetting",2),
  new(@"SOFTWARE\Policies\Microsoft\Edge","SmartScreenEnabled",1),
  new(@"SOFTWARE\Policies\Google\Chrome","DefaultNotificationsSetting",2),
  new(@"SOFTWARE\Policies\Google\Chrome","DefaultPopupsSetting",2)
 };
 static bool Admin()=>new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator);
 static int? Read(Policy p) {
  using var k=Registry.LocalMachine.OpenSubKey(p.Key,false);
  var o=k?.GetValue(p.Name);
  return o is int i?i:null;
 }
 static void Log(string s) {
  Directory.CreateDirectory(Root);
  File.AppendAllText(Path.Combine(Root,"events.log"),$"{DateTimeOffset.UtcNow:O} {s}{Environment.NewLine}");
 }
 static List<OwnedPolicy> Load(){
  try{return JsonSerializer.Deserialize<List<OwnedPolicy>>(File.ReadAllText(OwnedFile))??new();}
  catch(FileNotFoundException){return new();}
 }
 static void Save(List<OwnedPolicy> policies) {
  Directory.CreateDirectory(Root);
  File.WriteAllText(OwnedFile,JsonSerializer.Serialize(policies,new JsonSerializerOptions{WriteIndented=true}));
 }
 static int Audit(){
  Console.WriteLine("JNS ScamShield pilot — Windows protection and browser-policy audit");
  foreach(var p in Policies){
   var value=Read(p);
   Console.WriteLine($"{p.Name} [{p.Key}]: {(value.HasValue?value.ToString():"NOT SET")}; desired {p.Desired}");
  }
  try{
   var psi=new ProcessStartInfo("powershell.exe","-NoProfile -NonInteractive -Command \"Get-MpComputerStatus | Select-Object AMRunningMode,AntivirusEnabled,RealTimeProtectionEnabled,IsTamperProtected,AntivirusSignatureAge | Format-List; Get-MpPreference | Select-Object PUAProtection | Format-List\""){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true,CreateNoWindow=true};
   using var p=Process.Start(psi)??throw new Exception("Defender status process unavailable");
   if(!p.WaitForExit(20000)){p.Kill(true);Console.WriteLine("Defender query timed out");return 2;}
   Console.WriteLine(p.StandardOutput.ReadToEnd());
   if(p.ExitCode!=0)Console.WriteLine("Defender query unavailable; check Windows Security directly.");
  }catch(Exception e){Console.WriteLine($"Defender status unavailable: {e.Message}");}
  Console.WriteLine("Audit only: browser policy keys alone do not prove effective protection.");
  return 0;
 }
 static int Enforce(){
  if(!Admin()){Console.Error.WriteLine("Administrator rights required");return 1;}
  var owned=Load();
  foreach(var p in Policies) {
   var old=Read(p);
   bool ours=owned.Any(x=>x.Key==p.Key&&x.Name==p.Name);
   if(!ours&&old.HasValue) {
    // Existing values, including matching values, belong to another owner.
    Log($"PRESERVE existing policy {p.Key}\\{p.Name}");
    continue;
   }
   if(!ours)owned.Add(new OwnedPolicy(p.Key,p.Name,p.Desired));
   using var k=Registry.LocalMachine.CreateSubKey(p.Key,true);
   k.SetValue(p.Name,p.Desired,RegistryValueKind.DWord);
   Log($"Enforced {p.Key}\\{p.Name}");
  }
  Save(owned);
  return Audit();
 }
 static int Restore(){
  if(!Admin()){Console.Error.WriteLine("Administrator rights required");return 1;}
  var owned=Load();
  foreach(var item in owned){
   var p=new Policy(item.Key,item.Name,item.Desired);
   if(Read(p)!=item.Desired){Log($"SKIP changed external value {item.Key}\\{item.Name}");continue;}
   using var key=Registry.LocalMachine.OpenSubKey(item.Key,true);
   key?.DeleteValue(item.Name,false);
   Log($"Restored {item.Key}\\{item.Name}");
  }
  if(File.Exists(OwnedFile))File.Delete(OwnedFile);
  return 0;
 }
 static int Main(string[] args){
  var mode=args.FirstOrDefault()?.ToLowerInvariant()??"audit";
  try{return mode switch {"audit"=>Audit(),"enforce"=>Enforce(),"restore"=>Restore(),_=>1};}
  catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}
 }
}