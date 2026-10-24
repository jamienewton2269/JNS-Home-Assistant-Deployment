package uk.co.jnsystems.nhsbooker;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.provider.CalendarContract;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Only reads locally synced, visible Google calendars. No event metadata leaves this class. */
public final class PhoneCalendars {
    public static final class GoogleCalendar {
        public final long id;
        public final String display;
        public GoogleCalendar(long id, String display) { this.id = id; this.display = display; }
    }
    private static void requirePermission(Context context) {
        if (context.checkSelfPermission(Manifest.permission.READ_CALENDAR) != PackageManager.PERMISSION_GRANTED)
            throw new SecurityException("Calendar reading permission is required");
    }
    public static List<GoogleCalendar> available(Context context) {
        requirePermission(context);
        List<GoogleCalendar> calendars = new ArrayList<>();
        String[] columns = {
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
            CalendarContract.Calendars.ACCOUNT_NAME,
            CalendarContract.Calendars.ACCOUNT_TYPE,
            CalendarContract.Calendars.VISIBLE,
            CalendarContract.Calendars.SYNC_EVENTS
        };
        try (Cursor cursor = context.getContentResolver().query(
                CalendarContract.Calendars.CONTENT_URI, columns,
                CalendarContract.Calendars.ACCOUNT_TYPE + "=? AND " +
                        CalendarContract.Calendars.VISIBLE + "=1 AND " +
                        CalendarContract.Calendars.SYNC_EVENTS + "=1",
                new String[] {"com.google"}, null)) {
            if (cursor == null) throw new IllegalStateException("Google calendar provider unavailable");
            while (cursor.moveToNext()) {
                long id = cursor.getLong(0);
                String name = cursor.getString(1);
                String account = cursor.getString(2);
                calendars.add(new GoogleCalendar(id, (name == null ? "Calendar" : name) + "  ·  " +
                        (account == null ? "Google account" : account)));
            }
        }
        return calendars;
    }
    public static List<AppointmentPlanner.Interval> busy(Context context, Set<Long> chosen,
                      AppointmentPlanner.Interval window) {
        requirePermission(context);
        if (chosen == null || chosen.isEmpty())
            throw new IllegalStateException("Choose at least one Google calendar for this person");
        Set<Long> accessible = new HashSet<>();
        for (GoogleCalendar cal : available(context)) accessible.add(cal.id);
        if (!accessible.containsAll(chosen))
            throw new IllegalStateException("A selected Google calendar is not synced, visible or accessible");
        List<AppointmentPlanner.Interval> busy = new ArrayList<>();
        String[] projection = {
            CalendarContract.Instances.BEGIN,
            CalendarContract.Instances.END,
            CalendarContract.Instances.CALENDAR_ID,
            CalendarContract.Instances.AVAILABILITY,
            CalendarContract.Instances.STATUS
        };
        // Instances expands recurrent appointments within range; unlike Events it doesn't miss recurrences.
        try (Cursor cursor = CalendarContract.Instances.query(context.getContentResolver(), projection,
                window.start.toEpochMilli(), window.end.toEpochMilli())) {
            if (cursor == null) throw new IllegalStateException("Calendar busy periods unavailable");
            while (cursor.moveToNext()) {
                long id = cursor.getLong(2);
                if (!chosen.contains(id)) continue;
                if (cursor.isNull(0) || cursor.isNull(1) || cursor.isNull(3))
                    throw new IllegalStateException("Incomplete synced calendar event");
                int availability = cursor.getInt(3);
                if (!cursor.isNull(4) && cursor.getInt(4) == CalendarContract.Events.STATUS_CANCELED) continue;
                if (availability == CalendarContract.Events.AVAILABILITY_FREE) continue;
                Instant start = Instant.ofEpochMilli(cursor.getLong(0));
                Instant end = Instant.ofEpochMilli(cursor.getLong(1));
                if (end.isAfter(start)) busy.add(new AppointmentPlanner.Interval(start, end));
                else throw new IllegalStateException("Invalid synced calendar event");
            }
        }
        return busy;
    }
    private PhoneCalendars() { }
}
