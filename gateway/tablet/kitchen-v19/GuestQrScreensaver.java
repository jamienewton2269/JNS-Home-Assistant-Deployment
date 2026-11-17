package uk.jns.hikvisiontalk;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Android 4/API14-compatible opaque QR screensaver for ARMED AWAY.
 *
 * The host Activity MUST first stop the native camera decoder/player, mute
 * incoming audio and cover its SurfaceView before displaying this view.
 * Bitmap contains ONLY a guest portal URL (no PIN, token, alarm code).
 * No camera preview, alarm state, or personal details are rendered here.
 */
public final class GuestQrScreensaver extends FrameLayout {
    public interface HiddenCornerTap {
        void onCornerTap(long wallTimeMs);
    }
    private static final long MOVE_INTERVAL_MS = 45000L;
    private static final int[] SHIFT_X_DP = {0, 12, -9, 7, -12, 0};
    private static final int[] SHIFT_Y_DP = {0, -8, 10, 8, -7, 0};

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final LinearLayout content;
    private final Runnable shift = new Runnable() {
        public void run() {
            if (!active) return;
            position = (position + 1) % SHIFT_X_DP.length;
            content.setTranslationX(dp(SHIFT_X_DP[position]));
            content.setTranslationY(dp(SHIFT_Y_DP[position]));
            ui.postDelayed(this, MOVE_INTERVAL_MS);
        }
    };
    private int position = 0;
    private boolean active = false;

    public GuestQrScreensaver(Context context, Bitmap qrBitmap,
                             final HiddenCornerTap callback) {
        super(context);
        if (qrBitmap == null) throw new IllegalArgumentException("QR bitmap missing");
        setBackgroundColor(Color.rgb(5, 9, 15));
        setClickable(true);
        setFocusable(true);
        setVisibility(View.GONE);

        content = new LinearLayout(context);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER);
        int margin = dp(16);
        content.setPadding(margin, margin, margin, margin);

        TextView header = new TextView(context);
        header.setText("GUEST ACCESS");
        header.setTextColor(Color.rgb(218, 227, 237));
        header.setTextSize(19f);
        header.setGravity(Gravity.CENTER);
        content.addView(header, new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT));

        ImageView qr = new ImageView(context);
        qr.setImageBitmap(qrBitmap);
        qr.setBackgroundColor(Color.WHITE);
        qr.setPadding(dp(12), dp(12), dp(12), dp(12));
        qr.setAdjustViewBounds(true);
        qr.setScaleType(ImageView.ScaleType.FIT_CENTER);
        LinearLayout.LayoutParams qrParams =
                new LinearLayout.LayoutParams(dp(250), dp(250));
        qrParams.topMargin = dp(20);
        qrParams.bottomMargin = dp(16);
        content.addView(qr, qrParams);

        TextView label = new TextView(context);
        label.setText("Scan to open the guest portal");
        label.setTextColor(Color.rgb(199, 209, 219));
        label.setTextSize(15f);
        label.setGravity(Gravity.CENTER);
        content.addView(label, new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT));

        TextView testing = new TextView(context);
        testing.setText("TEST ACCESS ONLY");
        testing.setTextColor(Color.rgb(138, 154, 169));
        testing.setTextSize(12f);
        testing.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams foot = new LinearLayout.LayoutParams(
                LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT);
        foot.topMargin = dp(8);
        content.addView(testing, foot);

        addView(content, new FrameLayout.LayoutParams(
                LayoutParams.WRAP_CONTENT, LayoutParams.WRAP_CONTENT, Gravity.CENTER));

        // Invisible corner hit target for the policy's triple-tap PIN launcher.
        // Hidden UI is not an authentication mechanism.
        View corner = new View(context);
        FrameLayout.LayoutParams cornerParams =
                new FrameLayout.LayoutParams(dp(54), dp(54),
                        Gravity.TOP | Gravity.RIGHT);
        addView(corner, cornerParams);
        corner.setOnClickListener(new OnClickListener() {
            public void onClick(View v) {
                if (active && callback != null)
                    callback.onCornerTap(System.currentTimeMillis());
            }
        });
    }

    /** Called ONLY after DisplayPolicy authorizes Screen.GUEST_QR. */
    public void enterAwayScreensaver() {
        if (active) return;
        active = true;
        position = 0;
        content.setTranslationX(0f);
        content.setTranslationY(0f);
        setVisibility(View.VISIBLE);
        setKeepScreenOn(true); // active screensaver remains scannable while away
        ui.postDelayed(shift, MOVE_INTERVAL_MS);
    }

    /** Call immediately on any other state, loss of MQTT, or Activity pause. */
    public void leaveAwayScreensaver() {
        active = false;
        ui.removeCallbacks(shift);
        setKeepScreenOn(false);
        setVisibility(View.GONE);
    }

    @Override protected void onDetachedFromWindow() {
        leaveAwayScreensaver();
        super.onDetachedFromWindow();
    }

    private int dp(int amount) {
        return (int) (amount * getResources().getDisplayMetrics().density + 0.5f);
    }
}
