# JNS NHS Blood Tests — Android mobile companion v0.1

Native Java Android application with **zero backend required** for the initial patient selection and calendar-checking workflow.

## Feature status

* **Me / Jane / both** selector, plus first-person order for two appointments.
* Select the visible, synced Google calendar(s) relevant to each patient on the phone using runtime `READ_CALENDAR` permission; Jane must authorise sharing her diary or sync her Google account on the device.
* Enter actual NHS-offered time(s), per-slot duration, consecutive gap, and before/after travel buffers.
* Query only selected calendars' **local busy instances** (including recurring events), not descriptions or attendees; reject a missing or inaccessible calendar, overlap, invalid time or UK daylight-saving ambiguity.
* Open the **official NHS booking website** in the device browser for manual patient data entry and submission.
* For each appointment, after NHS confirmation is received, tick the confirmation attestation to open a **draft** Google Calendar event which the user then saves themselves.
* No NHS number/date-of-birth storage, no Internet permission in the app, and no Google OAuth refresh tokens.

## Current limitations — this is not an unattended auto-booker

The current app does **not** scrape NHS slots or submit appointments. A date/time entered in the app must be independently verified as bookable on the official NHS website. The only proof of booking is the provider's confirmation email/text. For two people, each booking is separate and may partly succeed. The app doesn't silently create, cancel or modify NHS appointments.

The app reads Google calendars already synced to the phone; a local calendar sync delay may mean recently created events are not yet visible. Before booking, ensure Google Calendar sync has completed and select **all** calendars containing relevant busy events for each person. Multiple events and invisible calendars are not inferred as free.

## Build / debug APK

Android Studio: open this folder as a project and install Android SDK 35 when prompted. The project uses AGP 8.9.2, Gradle 8.11.1 and Java 17.

Build:
```
gradle :app:assembleDebug
```

The debug APK is `app/build/outputs/apk/debug/app-debug.apk`. The GitHub Actions workflow `.github/workflows/jns-nhs-mobile-debug.yml` can build an **unsigned-for-release, developer-test-only** APK; this must not be presented as a verified production app or deployed silently to any phone.

The Gradle wrapper properties are provided; use Android Studio's Gradle integration or an installed Gradle 8.11.1, as the Gradle wrapper JAR is not committed.

Test the pure Java planner with JDK 17+:
```
mkdir -p /tmp/jns-classes
javac -d /tmp/jns-classes app/src/main/java/uk/co/jnsystems/nhsbooker/AppointmentPlanner.java core-tests/PlannerSmokeTest.java
java -cp /tmp/jns-classes PlannerSmokeTest
```

## Safe evolution

The previous Python Playwright implementation remains **undeployed**; it could become an optional JNS-secured service for provider slot discovery or automated submissions **after** live NHS site inspection, site access approval, a proper consent UI, confirmation parsing, and transactional handling of half-completed paired bookings. It is not required to use the Android companion app.

Official Mersey Care entry: https://www.merseycare.nhs.uk/bloodtestsouthportformby. Mersey Care requires NHS booking confirmation and the blood-test request form at the appointment.
