import java.time.*;
import java.util.*;
import uk.co.jnsystems.nhsbooker.AppointmentPlanner;
import static uk.co.jnsystems.nhsbooker.AppointmentPlanner.*;

public final class PlannerSmokeTest {
    static int assertions = 0;
    static void yes(boolean condition) { assertions++; if (!condition) throw new AssertionError("Test " + assertions + " failed"); }
    static void fails(Runnable f) {
        assertions++;
        try { f.run(); } catch (IllegalArgumentException | IllegalStateException expected) { return; }
        throw new AssertionError("Expected rejection test " + assertions);
    }
    public static void main(String[] args) {
        Instant t = Instant.parse("2026-11-03T09:00:00Z");
        Map<Who,List<Interval>> clear = Map.of(Who.ME, List.of(), Who.JANE, List.of());
        Plan me = makePlan(Who.ME, Who.ME, "Churchtown", t, 10, 0, 20, 20, clear);
        yes(me.appointments.size() == 1);
        yes(me.travelWindow.start.equals(t.minus(Duration.ofMinutes(20))));
        Plan both = makePlan(Who.BOTH, Who.JANE, "Churchtown", t, 10, 0, 20, 20, clear);
        yes(both.appointments.size() == 2);
        yes(both.appointments.get(0).patient == Who.JANE);
        yes(both.appointments.get(1).time.start.equals(t.plus(Duration.ofMinutes(10))));
        yes(both.travelWindow.end.equals(t.plus(Duration.ofMinutes(40))));
        Map<Who,List<Interval>> janeBusy = Map.of(Who.ME, List.of(), Who.JANE,
                List.of(new Interval(t.plusSeconds(1), t.plusSeconds(2))));
        fails(() -> makePlan(Who.BOTH, Who.ME, "Churchtown", t, 10, 0, 20, 20, janeBusy));
        fails(() -> makePlan(Who.BOTH, Who.ME, "Churchtown", t, 10, 0, 20, 20,
                Map.of(Who.ME, List.of())));
        Map<Who,List<Interval>> justBefore = Map.of(Who.ME,
                List.of(new Interval(t.minus(Duration.ofMinutes(45)), t.minus(Duration.ofMinutes(20)))));
        yes(makePlan(Who.ME, Who.ME, "Churchtown", t, 10, 0, 20, 20, justBefore).appointments.size() == 1);
        fails(() -> makePlan(Who.ME, Who.ME, "Churchtown", t, 10, 0, 20, 20,
                Map.of(Who.ME, List.of(new Interval(t.minus(Duration.ofMinutes(25)), t.minus(Duration.ofMinutes(19)))))));
        fails(() -> makePlan(Who.BOTH, Who.BOTH, "Churchtown", t, 10, 0, 20, 20, clear));
        fails(() -> makePlan(Who.ME, Who.ME, "Churchtown", t, 0, 0, 20, 20, clear));
        fails(() -> resolveLocalTime(LocalDateTime.of(2026, 3, 29, 1, 30)));
        fails(() -> resolveLocalTime(LocalDateTime.of(2026, 10, 25, 1, 30)));
        yes(resolveLocalTime(LocalDateTime.of(2026, 11, 3, 9, 0)).equals(t));
        System.out.println("PASS: " + assertions + " appointment planning and DST assertions");
    }
}
