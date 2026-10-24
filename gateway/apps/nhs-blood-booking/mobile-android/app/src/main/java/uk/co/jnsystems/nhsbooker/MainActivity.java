package uk.co.jnsystems.nhsbooker;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.app.TimePickerDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.provider.CalendarContract;
import android.net.Uri;
import android.view.View;
import android.widget.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

/** JNS mobile companion: checks local Google calendars; bookings remain on the real NHS website. */
public class MainActivity extends Activity {
    private static final String NHS = "https://www.merseycare.nhs.uk/bloodtestsouthportformby";
    private static final String[] CLINICS = {
        "Ainsdale Centre for Health and Wellbeing", "Churchtown Clinic",
        "Formby Clinic", "Southport Centre for Health and Wellbeing"
    };
    private static final int PERMISSION = 401;
    private final int COLOR = Color.rgb(106, 225, 212);
    private SharedPreferences saved;
    private AppointmentPlanner.Who pending;
    private Spinner who, first, clinic;
    private EditText duration, gap, before, after;
    private CheckBox confirmMe, confirmJane;
    private TextView result, myCalendars, janeCalendars;
    private Button dateButton, timeButton;
    private LocalDate date = LocalDate.now(AppointmentPlanner.LONDON).plusDays(1);
    private LocalTime time = LocalTime.of(9,0);
    private AppointmentPlanner.Plan checked;
    private int generation = 0;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        saved = getSharedPreferences("calendar-selection", MODE_PRIVATE);
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.rgb(10,22,38));
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(1);
        root.setPadding(25,30,25,40);
        scroll.addView(root); setContentView(scroll);
        text(root,"JNS / HEALTH",16, COLOR);
        text(root,"NHS blood test booking",26,Color.WHITE);
        text(root,"Southport & Formby · NHS confirmation required",14,Color.LTGRAY);

        text(root,"1. Who needs an appointment?",19,Color.WHITE);
        who = spinner(root,new String[]{"Just me","Just Jane","Both · consecutive appointments"});
        first = spinner(root,new String[]{"Me first","Jane first"});
        text(root,"2. Which Google calendars count as busy?",19,Color.WHITE);
        button(root,"Select my Google calendars", ()->pick(AppointmentPlanner.Who.ME));
        myCalendars=text(root,"My calendars: none selected",13,Color.LTGRAY);
        button(root,"Select Jane's authorised Google calendars",()->pick(AppointmentPlanner.Who.JANE));
        janeCalendars=text(root,"Jane's calendars: none selected",13,Color.LTGRAY);

        text(root,"3. Enter actual times shown on the NHS booking page",19,Color.WHITE);
        clinic = spinner(root, CLINICS);
        dateButton=button(root,"Date", ()->new DatePickerDialog(this,(v,y,m,d)->{
            date=LocalDate.of(y,m+1,d); dates(); invalidate();
        },date.getYear(),date.getMonthValue()-1,date.getDayOfMonth()).show());
        timeButton=button(root,"Time", ()->new TimePickerDialog(this,(v,h,m)->{
            time=LocalTime.of(h,m); dates(); invalidate();
        },time.getHour(),time.getMinute(),true).show());
        dates();
        duration=num(root,"Appointment length (minutes)",10);
        gap=num(root,"Minutes between appointments (0 for consecutive)",0);
        before=num(root,"Travel/preparation before (minutes)",20);
        after=num(root,"Travel afterwards (minutes)",20);
        button(root,"Open official NHS booking website",()->{
            try { startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(NHS))); }
            catch(ActivityNotFoundException e) { alert("A browser is required"); }
        });

        text(root,"4. Check diary conflicts",19,Color.WHITE);
        button(root,"Check these proposed times",this::check);
        result=text(root,"NHS slot availability has not been checked.",15,Color.LTGRAY);
        text(root,"A clear calendar does not mean NHS slots are available. Check both NHS slots and confirmations yourself.",13,Color.LTGRAY);

        text(root,"5. Add an appointment only after NHS confirmation",19,Color.WHITE);
        confirmMe=new CheckBox(this); confirmMe.setText("I received my NHS confirmation");
        root.addView(confirmMe);
        confirmJane=new CheckBox(this); confirmJane.setText("Jane received NHS confirmation");
        root.addView(confirmJane);
        button(root,"Add my confirmed appointment",()->add(AppointmentPlanner.Who.ME));
        button(root,"Add Jane's confirmed appointment",()->add(AppointmentPlanner.Who.JANE));
        text(root,"This opens a calendar draft, which you must review and save in the correct Google calendar.",13,Color.LTGRAY);
        updateSelection();
        who.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
            public void onNothingSelected(AdapterView<?> p) {}
            public void onItemSelected(AdapterView<?> p, View v,int i,long id){invalidate();}
        });
        for(Spinner spinner : new Spinner[]{first,clinic}) {
            spinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
                public void onNothingSelected(AdapterView<?> p) {}
                public void onItemSelected(AdapterView<?> p,View v,int i,long id){invalidate();}
            });
        }
    }
    private TextView text(LinearLayout parent,String value,int size,int color){
        TextView v=new TextView(this);v.setText(value);v.setTextSize(size);v.setTextColor(color);
        v.setPadding(0,12,0,13);parent.addView(v);return v;
    }
    private Button button(LinearLayout parent,String value,Runnable cb){
        Button b=new Button(this);b.setAllCaps(false);b.setText(value);parent.addView(b);
        b.setOnClickListener(v->cb.run());return b;
    }
    private Spinner spinner(LinearLayout parent,String[] options){
        Spinner s=new Spinner(this);
        s.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,options));
        parent.addView(s);return s;
    }
    private EditText num(LinearLayout parent,String label,int initial){
        text(parent,label,13,Color.LTGRAY);
        EditText e=new EditText(this);
        e.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);
        e.setSingleLine(true);e.setText(String.valueOf(initial));parent.addView(e);
        e.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence s,int st,int c,int a){}
            public void onTextChanged(CharSequence s,int st,int b,int c){invalidate();}
            public void afterTextChanged(android.text.Editable e){}
        });
        return e;
    }
    private void dates(){
        dateButton.setText("Appointment date: "+date);
        timeButton.setText("First NHS slot: "+time.format(DateTimeFormatter.ofPattern("HH:mm")));
    }
    private AppointmentPlanner.Who patient(){
        int i=who.getSelectedItemPosition();
        return i==0?AppointmentPlanner.Who.ME:i==1?AppointmentPlanner.Who.JANE:AppointmentPlanner.Who.BOTH;
    }
    private void invalidate(){
        checked=null;generation++;
        if(result!=null)result.setText("Not checked — repeat the calendar check before proceeding.");
        if(confirmMe!=null)confirmMe.setChecked(false);
        if(confirmJane!=null)confirmJane.setChecked(false);
        updateSelection();
    }
    private void updateSelection(){
        if(myCalendars!=null) myCalendars.setText("My calendars selected: "+selected(AppointmentPlanner.Who.ME).size());
        if(janeCalendars!=null) janeCalendars.setText("Jane's calendars selected: "+selected(AppointmentPlanner.Who.JANE).size());
    }
    private Set<Long> selected(AppointmentPlanner.Who w){
        Set<Long> ids=new HashSet<>();
        for(String x:saved.getStringSet("calendars."+w.name(),Collections.emptySet())){
            try{ids.add(Long.parseLong(x));}catch(NumberFormatException ignored){}
        }
        return ids;
    }
    private void pick(AppointmentPlanner.Who w){
        if(checkSelfPermission(Manifest.permission.READ_CALENDAR)!=PackageManager.PERMISSION_GRANTED){
            pending=w;requestPermissions(new String[]{Manifest.permission.READ_CALENDAR},PERMISSION);return;
        }
        try{
            List<PhoneCalendars.GoogleCalendar> all=PhoneCalendars.available(this);
            if(all.isEmpty()){alert("No visible, synced Google calendars found. Enable Google Calendar sync.");return;}
            String[] titles=new String[all.size()];boolean[] checked=new boolean[all.size()];
            Set<Long> old=selected(w);
            for(int i=0;i<all.size();i++){titles[i]=all.get(i).display;checked[i]=old.contains(all.get(i).id);}
            new AlertDialog.Builder(this).setTitle(w==AppointmentPlanner.Who.ME?"My calendars":"Jane's authorised calendars")
                .setMultiChoiceItems(titles,checked,(dlg,index,state)->checked[index]=state)
                .setNegativeButton("Cancel",null).setPositiveButton("Save",(dlg,which)->{
                    Set<String> ids=new HashSet<>();
                    for(int i=0;i<all.size();i++)if(checked[i])ids.add(Long.toString(all.get(i).id));
                    saved.edit().putStringSet("calendars."+w.name(),ids).apply();invalidate();
                }).show();
        }catch(Exception e){alert("Google Calendar access unavailable.");}
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] grantResults){
        super.onRequestPermissionsResult(request,permissions,grantResults);
        if(request==PERMISSION){
            if(grantResults.length>0&&grantResults[0]==PackageManager.PERMISSION_GRANTED&&pending!=null)pick(pending);
            else alert("Calendar permission is required for collision checks.");
            pending=null;
        }
    }
    private int number(EditText e,int max){
        try {int n=Integer.parseInt(e.getText().toString().trim());if(n>=0&&n<=max)return n;}
        catch(NumberFormatException ignored){}
        throw new IllegalArgumentException("A timing field must be between 0 and "+max+" minutes.");
    }
    private void check(){
        try{
            if(checkSelfPermission(Manifest.permission.READ_CALENDAR)!=PackageManager.PERMISSION_GRANTED)
                throw new IllegalStateException("Allow calendar access and choose Google calendars first");
            AppointmentPlanner.Who w=patient();
            int dur=number(duration,120),g=number(gap,30),bef=number(before,240),aft=number(after,240);
            if(dur==0)throw new IllegalArgumentException("Appointment duration must be positive");
            Instant start=AppointmentPlanner.resolveLocalTime(LocalDateTime.of(date,time));
            if(!start.isAfter(Instant.now()))throw new IllegalArgumentException("Choose a future time");
            Set<Long> myIds=selected(AppointmentPlanner.Who.ME),janeIds=selected(AppointmentPlanner.Who.JANE);
            if(w!=AppointmentPlanner.Who.JANE&&myIds.isEmpty())throw new IllegalStateException("Select my calendar first");
            if(w!=AppointmentPlanner.Who.ME&&janeIds.isEmpty())throw new IllegalStateException("Select Jane's calendar first");
            String site=CLINICS[clinic.getSelectedItemPosition()];
            AppointmentPlanner.Who firstPerson=first.getSelectedItemPosition()==0?AppointmentPlanner.Who.ME:AppointmentPlanner.Who.JANE;
            long id=++generation;result.setText("Checking Google calendars…");
            new Thread(()->{
                try{
                    int count=w==AppointmentPlanner.Who.BOTH?2:1;
                    Instant end=start.plus(Duration.ofMinutes(dur*count+(count==2?g:0)));
                    AppointmentPlanner.Interval trip=new AppointmentPlanner.Interval(start.minus(Duration.ofMinutes(bef)),end.plus(Duration.ofMinutes(aft)));
                    Map<AppointmentPlanner.Who,List<AppointmentPlanner.Interval>> busy=new HashMap<>();
                    if(w!=AppointmentPlanner.Who.JANE)busy.put(AppointmentPlanner.Who.ME,PhoneCalendars.busy(this,myIds,trip));
                    if(w!=AppointmentPlanner.Who.ME)busy.put(AppointmentPlanner.Who.JANE,PhoneCalendars.busy(this,janeIds,trip));
                    AppointmentPlanner.Plan plan=AppointmentPlanner.makePlan(w,firstPerson,site,start,dur,g,bef,aft,busy);
                    runOnUiThread(()->{
                        if(id!=generation)return;
                        checked=plan;StringBuilder msg=new StringBuilder("No diary collisions in selected synced calendars:\n");
                        for(AppointmentPlanner.Assignment a:plan.appointments)
                            msg.append(a.patient==AppointmentPlanner.Who.ME?"You":"Jane").append("  ")
                               .append(a.time.start.atZone(AppointmentPlanner.LONDON).toLocalTime())
                               .append("–").append(a.time.end.atZone(AppointmentPlanner.LONDON).toLocalTime()).append("\n");
                        msg.append("These are NOT confirmed NHS slots.");
                        result.setText(msg.toString());result.setTextColor(COLOR);
                    });
                }catch(Exception e){runOnUiThread(()->{
                    if(id!=generation)return;
                    checked=null;result.setText("Blocked: diary conflict, inaccessible calendar or invalid slot. Select another time.");
                    result.setTextColor(Color.rgb(255,180,135));
                });}
            },"jns-google-calendar-check").start();
        }catch(IllegalArgumentException|IllegalStateException e){alert(e.getMessage());}
    }
    private void add(AppointmentPlanner.Who person){
        if(checked==null){alert("Check the proposed appointment against your diary first.");return;}
        boolean attested=(person==AppointmentPlanner.Who.ME?confirmMe:confirmJane).isChecked();
        if(!attested){alert("Only proceed after receiving this person's NHS booking confirmation.");return;}
        AppointmentPlanner.Assignment target=null;
        for(AppointmentPlanner.Assignment a:checked.appointments)if(a.patient==person)target=a;
        if(target==null){alert("This patient was not selected.");return;}
        try{
            Intent intent=new Intent(Intent.ACTION_INSERT).setData(CalendarContract.Events.CONTENT_URI)
                .putExtra(CalendarContract.Events.TITLE,"NHS blood test (confirmed)")
                .putExtra(CalendarContract.Events.EVENT_LOCATION,checked.clinic)
                .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME,target.time.start.toEpochMilli())
                .putExtra(CalendarContract.EXTRA_EVENT_END_TIME,target.time.end.toEpochMilli());
            startActivity(intent);
        }catch(ActivityNotFoundException e){alert("Install or enable a calendar app first.");}
    }
    private void alert(String message){
        new AlertDialog.Builder(this).setTitle("Action required").setMessage(message)
            .setPositiveButton("OK",null).show();
    }
}
