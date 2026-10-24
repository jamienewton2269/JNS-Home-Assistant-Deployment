package uk.co.jnsystems.nhsbooker;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Pure logic: candidate suggestions only. Never claims NHS slot availability. */
public final class AppointmentPlanner {
    public enum Who { ME, JANE, BOTH }
    public static final ZoneId LONDON = ZoneId.of("Europe/London");

    public static final class Interval {
        public final Instant start, end;
        public Interval(Instant start, Instant end) {
            if (start == null || end == null || !end.isAfter(start)) throw new IllegalArgumentException("Invalid interval");
            this.start = start; this.end = end;
        }
        public boolean intersects(Interval other) {
            return start.isBefore(other.end) && other.start.isBefore(end);
        }
    }
    public static final class Assignment {
        public final Who patient;
        public final Interval time;
        private Assignment(Who patient, Interval time) { this.patient = patient; this.time = time; }
    }
    public static final class Plan {
        public final String clinic;
        public final List<Assignment> appointments;
        public final Interval travelWindow;
        private Plan(String clinic, List<Assignment> appointments, Interval travelWindow) {
            this.clinic = clinic;
            this.appointments = Collections.unmodifiableList(new ArrayList<>(appointments));
            this.travelWindow = travelWindow;
        }
    }
    /** Reject nonexistent DST times and ambiguous clock times. */
    public static Instant resolveLocalTime(LocalDateTime local) {
        List<java.time.ZoneOffset> offsets = LONDON.getRules().getValidOffsets(local);
        if (offsets.size() != 1) throw new IllegalArgumentException("Clock time is ambiguous or does not exist in UK time");
        return local.atOffset(offsets.get(0)).toInstant();
    }
    public static Plan makePlan(Who who, Who firstWhenBoth, String clinic, Instant firstStart,
                                int minutesEach, int gapMinutes, int beforeMinutes, int afterMinutes,
                                Map<Who, List<Interval>> busy) {
        if (who == null || firstStart == null || clinic == null || clinic.trim().isEmpty())
            throw new IllegalArgumentException("Select clinic, patient and time");
        if (minutesEach < 1 || minutesEach > 120 || gapMinutes < 0 || gapMinutes > 30 ||
            beforeMinutes < 0 || beforeMinutes > 240 || afterMinutes < 0 || afterMinutes > 240)
            throw new IllegalArgumentException("Invalid duration, gap, or travel buffer");
        if (who == Who.BOTH && firstWhenBoth != Who.ME && firstWhenBoth != Who.JANE)
            throw new IllegalArgumentException("Select who goes first");

        Interval first = new Interval(firstStart, firstStart.plus(Duration.ofMinutes(minutesEach)));
        List<Assignment> appointments = new ArrayList<>();
        appointments.add(new Assignment(who == Who.BOTH ? firstWhenBoth : who, first));
        Instant lastEnd = first.end;
        if (who == Who.BOTH) {
            Instant secondStart = first.end.plus(Duration.ofMinutes(gapMinutes));
            Interval second = new Interval(secondStart, secondStart.plus(Duration.ofMinutes(minutesEach)));
            Who secondPatient = firstWhenBoth == Who.ME ? Who.JANE : Who.ME;
            appointments.add(new Assignment(secondPatient, second));
            lastEnd = second.end;
        }
        Interval trip = new Interval(first.start.minus(Duration.ofMinutes(beforeMinutes)),
                lastEnd.plus(Duration.ofMinutes(afterMinutes)));
        Set<Who> patients = who == Who.BOTH ? Set.of(Who.ME, Who.JANE) : Set.of(who);
        for (Who patient : patients) {
            if (busy == null || !busy.containsKey(patient) || busy.get(patient) == null)
                throw new IllegalStateException("Missing authorised calendar for " + patient);
            for (Interval event : busy.get(patient)) {
                if (event == null || trip.intersects(event))
                    throw new IllegalStateException("Diary conflict for " + patient);
            }
        }
        return new Plan(clinic, appointments, trip);
    }
    private AppointmentPlanner() { }
}
