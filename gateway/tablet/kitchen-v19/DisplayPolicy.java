package uk.jns.hikvisiontalk;

/**
 * Fail-closed kitchen tablet display/listening policy (Java 7, Android API 14).
 * Call on the Android UI thread. It does NOT authenticate or submit alarm codes.
 */
public final class DisplayPolicy {
    public enum Screen { PRIVACY_LOCK, GUEST_QR, FRONT_CAMERA }

    public interface View {
        /** This must stop native video decoding AND cover the view immediately. */
        void hideAndStopCamera();
        void showFrontCamera();
        void showGuestQrOnly();
        void showPrivacyLock();
        void stopIncomingAudio();
        /** Enable incoming camera sound only; NEVER enable tablet microphone. */
        void listenToFrontDoor(int milliseconds);
        void showLocalPinEntry();
        void hideLocalPinEntry();
    }

    private static final long STATE_MAX_AGE_MS = 15000L;
    private static final long FUTURE_SKEW_MS = 5000L;
    private static final long DOORBELL_DUPLICATE_MS = 2000L;
    private static final int LISTEN_DURATION_MS = 45000;
    private static final long PIN_PAD_TIMEOUT_MS = 30000L;
    private static final long CORNER_TAP_WINDOW_MS = 1800L;

    private final View view;
    private Screen screen = Screen.PRIVACY_LOCK;
    private boolean connected;
    private long lastStateTimeMs = -1L;
    private long lastDoorbellMs = -1L;
    private long firstCornerTapMs = -1L;
    private long pinPadDeadlineMs = -1L;
    private long listenDeadlineMs = -1L;
    private int cornerTaps;
    private String lastAlarmState = "unknown";

    public DisplayPolicy(View view) {
        if (view == null) throw new IllegalArgumentException("view");
        this.view = view;
        render(Screen.PRIVACY_LOCK);
    }

    public Screen getScreen() { return screen; }

    /** Never infer a disarmed state from reconnect alone. */
    public void onConnected() {
        connected = true;
        lastStateTimeMs = -1L;
        lastAlarmState = "unknown";
        render(Screen.PRIVACY_LOCK);
    }

    public void onDisconnected() {
        connected = false;
        lastStateTimeMs = -1L;
        lastAlarmState = "unknown";
        render(Screen.PRIVACY_LOCK);
    }

    /** Accept only a fresh authenticated MQTT state message; no optimistic UI. */
    public void onAlarmState(String state, long publishedAtMs, long nowMs) {
        if (!connected || state == null || publishedAtMs <= 0 ||
            publishedAtMs > nowMs + FUTURE_SKEW_MS ||
            nowMs - publishedAtMs > STATE_MAX_AGE_MS) {
            lastStateTimeMs = -1L;
            lastAlarmState = "unknown";
            render(Screen.PRIVACY_LOCK);
            return;
        }
        lastStateTimeMs = nowMs;
        lastAlarmState = state;
        if ("armed_away".equals(state)) {
            render(Screen.GUEST_QR);
        } else if ("disarmed".equals(state) || "armed_home".equals(state)) {
            render(Screen.FRONT_CAMERA);
        } else {
            // Unknown, arming, pending, triggered, unavailable => cover the camera.
            render(Screen.PRIVACY_LOCK);
        }
    }

    /** Existing doorbell topic; only fresh, nonretained messages can trigger sound. */
    public void onDoorbellPress(boolean retained, String payload, long nowMs) {
        checkExpiry(nowMs);
        if (!connected || screen != Screen.FRONT_CAMERA || retained ||
            !"pressed".equals(payload) ||
            (lastDoorbellMs >= 0 && nowMs - lastDoorbellMs < DOORBELL_DUPLICATE_MS)) {
            return;
        }
        lastDoorbellMs = nowMs;
        listenDeadlineMs = nowMs + LISTEN_DURATION_MS;
        view.listenToFrontDoor(LISTEN_DURATION_MS);
    }

    /** Physical hidden corner, not a security boundary. Never submit codes via MQTT. */
    public void onSecretCornerTap(long nowMs) {
        checkExpiry(nowMs);
        if (screen != Screen.GUEST_QR) return;
        if (firstCornerTapMs < 0 || nowMs - firstCornerTapMs > CORNER_TAP_WINDOW_MS) {
            firstCornerTapMs = nowMs;
            cornerTaps = 0;
        }
        if (++cornerTaps == 3) {
            firstCornerTapMs = -1L;
            cornerTaps = 0;
            pinPadDeadlineMs = nowMs + PIN_PAD_TIMEOUT_MS;
            view.showLocalPinEntry();
        }
    }

    public void dismissPinPad() {
        pinPadDeadlineMs = -1L;
        view.hideLocalPinEntry();
    }

    /** Call once per second using Handler; also on resume/foreground. */
    public void checkExpiry(long nowMs) {
        if (connected && lastStateTimeMs > 0 &&
            nowMs - lastStateTimeMs > STATE_MAX_AGE_MS) {
            lastStateTimeMs = -1L;
            lastAlarmState = "unknown";
            render(Screen.PRIVACY_LOCK);
        }
        if (listenDeadlineMs > 0 && nowMs >= listenDeadlineMs) {
            listenDeadlineMs = -1L;
            view.stopIncomingAudio();
        }
        if (pinPadDeadlineMs > 0 && nowMs >= pinPadDeadlineMs) dismissPinPad();
    }

    private void render(Screen next) {
        if (screen == next && next != Screen.PRIVACY_LOCK) return;
        // Audio and video are cut *before* presenting any privacy/away UI.
        if (next != Screen.FRONT_CAMERA) {
            view.hideAndStopCamera();
            view.stopIncomingAudio();
            listenDeadlineMs = -1L;
        }
        if (screen != next || next == Screen.PRIVACY_LOCK) {
            dismissPinPad();
        }
        screen = next;
        if (next == Screen.GUEST_QR) view.showGuestQrOnly();
        else if (next == Screen.FRONT_CAMERA) view.showFrontCamera();
        else view.showPrivacyLock();
    }
}
