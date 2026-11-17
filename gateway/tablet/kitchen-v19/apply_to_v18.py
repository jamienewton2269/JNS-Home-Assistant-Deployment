#!/usr/bin/env python3
"""Fail-closed patch of a COPY of the existing Hikvision Talk v1.8 source.

This never modifies original v1.8 project. Use on an isolated source copy.
Sources from this folder are added separately to the staged project:
  DisplayPolicy.java, GuestQrScreensaver.java, KitchenMqttSubscriber.java
  jns_guest_portal_qr.png, jns_mqtt_root_ca.crt,
  org.eclipse.paho.client.mqttv3-1.2.5.jar
No credentials/keystore are copied by this patch.
"""
from pathlib import Path
import argparse

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise ValueError("%s anchor mismatch (%d): do not modify source" % (label, count))
    return text.replace(old, new, 1)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    args = p.parse_args()
    project = Path(args.project)
    src = project / "app/src/main/java/com/frontdoor/hikvisiontalk"
    gradle = project / "app/build.gradle"
    activity = src / "MainActivity.java"
    settings = src / "SettingsActivity.java"
    original = activity.read_text(encoding="utf-8")
    # Two different copies of the 4-Nov source may have LF/CRLF line endings.
    main = original.replace("\r\n", "\n")
    st = settings.read_text(encoding="utf-8").replace("\r\n", "\n")
    build = gradle.read_text(encoding="utf-8").replace("\r\n", "\n")
    if 'versionCode 9' not in build or 'versionName "1.8"' not in build:
        raise ValueError("Source is not the verified production v1.8/build 9")
    if 'import uk.jns.hikvisiontalk.DisplayPolicy' in main:
        raise ValueError("Patch already applied")

    main = replace_once(main,
        "import android.graphics.Color;",
        "import android.graphics.Color;\nimport android.graphics.BitmapFactory;\nimport android.graphics.Bitmap;\nimport android.text.InputType;",
        "MainActivity imports")
    main = replace_once(main,
        "import java.util.Locale;",
        "import java.util.Locale;\nimport java.util.UUID;\nimport java.io.InputStream;\n"
        "import uk.jns.hikvisiontalk.DisplayPolicy;\n"
        "import uk.jns.hikvisiontalk.GuestQrScreensaver;\n"
        "import uk.jns.hikvisiontalk.KitchenMqttSubscriber;",
        "MQTT imports")
    main = replace_once(main,
        "    private String sessionPassword;\n",
        """    private String sessionPassword;

    // Never stream camera until a fresh, authenticated MQTT alarm state permits it.
    private DisplayPolicy alarmDisplayPolicy;
    private KitchenMqttSubscriber alarmMqtt;
    private GuestQrScreensaver guestQrScreen;
    private FrameLayout privacyScreen;
    private AlertDialog alarmPinDialog;
    private boolean alarmAllowsCamera = false;
    private boolean doorbellListening = false;
    private long mqttSettingsRevision = Long.MIN_VALUE;
    private final Runnable doorbellStop = new Runnable() {
        public void run() {
            doorbellListening = false;
            replyListening = false;
            applyPlayerVolume();
        }
    };
    private final Runnable alarmMqttTick = new Runnable() {
        public void run() {
            if (destroyed) return;
            if (alarmMqtt != null) alarmMqtt.tick();
            else if (alarmDisplayPolicy != null)
                alarmDisplayPolicy.checkExpiry(System.currentTimeMillis());
            handler.postDelayed(this, 1000L);
        }
    };
""", "policy fields")
    main = replace_once(main,
        "        buildUi();\n",
        """        buildUi();
        initHouseAlarmDisplay();
        refreshAlarmMqtt();
        handler.post(alarmMqttTick);
""", "new secure startup")
    main = replace_once(main,
        "    private void installTalkTouch(final Button button) {",
        """    private void initHouseAlarmDisplay() {
        // No camera pixels must remain visible during a state change.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        privacyScreen = new FrameLayout(this);
        privacyScreen.setBackgroundColor(Color.rgb(5, 9, 15));
        LinearLayout privacyInfo = new LinearLayout(this);
        privacyInfo.setOrientation(LinearLayout.VERTICAL);
        privacyInfo.setGravity(Gravity.CENTER);
        TextView message = new TextView(this);
        message.setText("Front-door video protected\\\\nWaiting for verified alarm status");
        message.setTextColor(Color.WHITE);
        message.setTextSize(18);
        message.setGravity(Gravity.CENTER);
        privacyInfo.addView(message);
        Button configure = new Button(this);
        configure.setText("Configure MQTT");
        configure.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                startActivity(new Intent(MainActivity.this, SettingsActivity.class));
            }
        });
        privacyInfo.addView(configure);
        privacyScreen.addView(privacyInfo, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.CENTER));
        Bitmap qr = BitmapFactory.decodeResource(getResources(),
                                                  R.drawable.jns_guest_portal_qr);
        guestQrScreen = new GuestQrScreensaver(this, qr,
            new GuestQrScreensaver.HiddenCornerTap() {
                public void onCornerTap(long when) {
                    if (alarmDisplayPolicy != null)
                        alarmDisplayPolicy.onSecretCornerTap(when);
                }
            });
        alarmDisplayPolicy = new DisplayPolicy(new DisplayPolicy.View() {
            public void hideAndStopCamera() { secureHideCamera(); }
            public void showFrontCamera() { restoreFrontCamera(); }
            public void showGuestQrOnly() {
                setContentView(guestQrScreen);
                guestQrScreen.enterAwayScreensaver();
                getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            }
            public void showPrivacyLock() {
                guestQrScreen.leaveAwayScreensaver();
                setContentView(privacyScreen);
                getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            }
            public void stopIncomingAudio() { stopHouseAudio(); }
            public void listenToFrontDoor(int milliseconds) {
                listenForDoorbell(milliseconds);
            }
            public void showLocalPinEntry() { showStagedPinDialog(); }
            public void hideLocalPinEntry() {
                if (alarmPinDialog != null) {
                    alarmPinDialog.dismiss();
                    alarmPinDialog = null;
                }
            }
        });
    }

    private void secureHideCamera() {
        alarmAllowsCamera = false;
        // Cover a native SurfaceView before changing native decoder state.
        if (surface != null) surface.setVisibility(View.INVISIBLE);
        setContentView(privacyScreen);
        if (guestQrScreen != null) guestQrScreen.leaveAwayScreensaver();
        if (fullScreen) {
            fullScreen = false;
            fsBack = null;
            fsTalk = null;
        }
        rtspConnecting = false;
        releasePlayer();
    }

    private void restoreFrontCamera() {
        alarmAllowsCamera = true;
        if (guestQrScreen != null) guestQrScreen.leaveAwayScreensaver();
        ViewGroup oldParent = (ViewGroup)surface.getParent();
        if (oldParent != null && oldParent != videoFrame)
            oldParent.removeView(surface);
        if (surface.getParent() != videoFrame)
            videoFrame.addView(surface, 0, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        surface.setVisibility(View.VISIBLE);
        setContentView(normalRoot);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
        if (rtspWanted) handler.postDelayed(new Runnable() {
            public void run() { if (alarmAllowsCamera) startRtsp(); }
        }, 150L);
    }

    private void stopHouseAudio() {
        doorbellListening = false;
        replyListening = false;
        handler.removeCallbacks(doorbellStop);
        handler.removeCallbacks(replyTimeout);
        if (pttPressed) {
            pttPressed = false;
            new Thread(new Runnable() {
                public void run() { try { vacam.stopTalk(); } catch (Exception ignored) {} }
            }, "secure-stop-talk").start();
        }
        applyPlayerVolume();
    }

    private void listenForDoorbell(int durationMs) {
        if (!alarmAllowsCamera || destroyed || pttPressed) return;
        doorbellListening = true;
        replyListening = true;
        handler.removeCallbacks(doorbellStop);
        handler.removeCallbacks(replyTimeout);
        applyPlayerVolume();
        if (rtspWanted && (rtsp == null || !rtsp.isStarted())) startRtsp();
        handler.postDelayed(doorbellStop, durationMs);
        log("Doorbell: listening to front camera for " + (durationMs / 1000) + " seconds.");
    }

    private void showStagedPinDialog() {
        if (alarmPinDialog != null) return;
        // Keypad visual only; no PIN is collected or checked without a secure backend.
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(18, 12, 18, 12);
        TextView explanatory = new TextView(this);
        explanatory.setText("Alarm PIN controls are not enabled yet.");
        explanatory.setGravity(Gravity.CENTER);
        panel.addView(explanatory);
        String[][] keys = {
            {"1", "2", "3"}, {"4", "5", "6"},
            {"7", "8", "9"}, {"", "0", ""}
        };
        for (int i = 0; i < keys.length; ++i) {
            LinearLayout row = new LinearLayout(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            for (int j = 0; j < keys[i].length; ++j) {
                Button key = new Button(this);
                key.setText(keys[i][j]);
                key.setEnabled(false);
                row.addView(key, new LinearLayout.LayoutParams(0, 54, 1f));
            }
            panel.addView(row);
        }
        Button armHome = new Button(this);
        armHome.setText("ARM HOME (UNAVAILABLE)");
        armHome.setEnabled(false);
        panel.addView(armHome);
        Button disarm = new Button(this);
        disarm.setText("DISARM (UNAVAILABLE)");
        disarm.setEnabled(false);
        panel.addView(disarm);
        alarmPinDialog = new AlertDialog.Builder(this)
            .setTitle("House alarm - keypad preview")
            .setView(panel)
            .setPositiveButton("Close", new DialogInterface.OnClickListener() {
                public void onClick(DialogInterface dialog, int which) {
                    alarmPinDialog = null;
                }
            })
            .create();
        alarmPinDialog.show();
    }

    private void refreshAlarmMqtt() {
        long rev = prefs.getLong("mqtt_config_revision", 0L);
        if (rev == mqttSettingsRevision) return;
        mqttSettingsRevision = rev;
        if (alarmMqtt != null) {
            alarmMqtt.stop();
            alarmMqtt = null;
        }
        if (alarmDisplayPolicy != null) alarmDisplayPolicy.onDisconnected();
        String name = prefs.getString("mqtt_username", "").trim();
        String password = prefs.getString("mqtt_password", "");
        if (!prefs.getBoolean("mqtt_enabled", false) ||
            name.length() == 0 || password.length() == 0) {
            log("Alarm MQTT not configured. Front-door video remains protected.");
            return;
        }
        String id = prefs.getString("mqtt_client_id", "");
        if (id.length() == 0) {
            id = "jns-kitchen-" +
                UUID.randomUUID().toString().replace("-", "").substring(0, 9);
            prefs.edit().putString("mqtt_client_id", id).commit();
        }
        InputStream ca = null;
        try {
            ca = getResources().openRawResource(R.raw.jns_mqtt_root_ca);
            alarmMqtt = new KitchenMqttSubscriber(alarmDisplayPolicy, id,
                name, password.toCharArray(), ca);
            alarmMqtt.start();
        } catch (Exception e) {
            alarmDisplayPolicy.onDisconnected();
            log("Alarm MQTT connection unavailable: " + e.getClass().getSimpleName());
        } finally {
            if (ca != null) try { ca.close(); } catch (Exception ignored) {}
        }
    }

    private void installTalkTouch(final Button button) {""", "security view implementation")

    main = replace_once(main,
        "        if (!rtspWanted || destroyed || rtspConnecting || !surface.getHolder().getSurface().isValid()) return;",
        "        if (!alarmAllowsCamera || !rtspWanted || destroyed || rtspConnecting || !surface.getHolder().getSurface().isValid()) return;",
        "camera start privacy guard")
    main = replace_once(main,
        "        if (!rtspWanted || destroyed) return;\n",
        "        if (!alarmAllowsCamera || !rtspWanted || destroyed) return;\n",
        "camera reconnect privacy guard")
    main = replace_once(main,
        "        boolean feedback = replyListening && !pttPressed && !muteCheck.isChecked();",
        "        boolean feedback = alarmAllowsCamera && replyListening && !pttPressed &&\n            (doorbellListening || !muteCheck.isChecked());",
        "speaker-only doorbell gain")
    main = replace_once(main,
        "        if (rtsp != null && rtsp.isStarted()) {\n            try { rtsp.setSurface(holder.getSurface()); } catch (Throwable ignored) {}\n        } else if (rtspWanted) {",
        "        if (!alarmAllowsCamera) return;\n        if (rtsp != null && rtsp.isStarted()) {\n            try { rtsp.setSurface(holder.getSurface()); } catch (Throwable ignored) {}\n        } else if (rtspWanted) {",
        "surface create guard")
    main = replace_once(main,
        "        if (rtsp != null && rtsp.isStarted()) try { rtsp.setSurface(holder.getSurface()); } catch (Throwable ignored) {}",
        "        if (alarmAllowsCamera && rtsp != null && rtsp.isStarted()) try { rtsp.setSurface(holder.getSurface()); } catch (Throwable ignored) {}",
        "surface change guard")
    main = replace_once(main,
        "        reloadRemoteButtons();\n    }\n\n    public void onBackPressed() {",
        """        reloadRemoteButtons();
        if (alarmDisplayPolicy != null) {
            alarmDisplayPolicy.checkExpiry(System.currentTimeMillis());
            refreshAlarmMqtt();
        }
    }

    public void onBackPressed() {""", "return from settings")
    main = replace_once(main,
        "        handler.removeCallbacksAndMessages(null);\n        releasePlayer();\n        vacam.disconnect();\n",
        "        handler.removeCallbacksAndMessages(null);\n        if (alarmMqtt != null) { alarmMqtt.stop(); alarmMqtt = null; }\n        if (guestQrScreen != null) guestQrScreen.leaveAwayScreensaver();\n        releasePlayer();\n        vacam.disconnect();\n",
        "shutdown MQTT")
    main = replace_once(main,
        "    private void enterFullScreen() {\n",
        "    private void enterFullScreen() {\n        if (!alarmAllowsCamera) return;\n",
        "fullscreen privacy guard")

    st = replace_once(st, "        addTitle(\"Local app updates\");",
        """        addTitle("House alarm / secure MQTT");
        addCheck("Enable alarm-aware display and doorbell listening",
                 "mqtt_enabled", false);
        addEdit("MQTT read-only account name", "mqtt_username", "", false);
        addEdit("MQTT read-only password (saved only in private app data)",
                "mqtt_password", "", true);
        TextView mqttNote = new TextView(this);
        mqttNote.setText("TLS 1.2 and the JNS MQTT CA are mandatory. "
            + "No plaintext fallback. If disconnected, front-door video is hidden. "
            + "The alarm account can ONLY read its status and doorbell messages.");
        root.addView(mqttNote);
        Button forgetMqtt = new Button(this);
        forgetMqtt.setText("Forget MQTT access");
        forgetMqtt.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) {
                prefs.edit().remove("mqtt_password").putBoolean("mqtt_enabled", false)
                     .putLong("mqtt_config_revision", System.currentTimeMillis()).commit();
                Toast.makeText(SettingsActivity.this,
                    "MQTT access forgotten; video locked until reconfigured.",
                    Toast.LENGTH_LONG).show();
                finish();
            }
        });
        root.addView(forgetMqtt);

        addTitle("Local app updates");""", "MQTT settings UI")
    st = replace_once(st,
        "                finish();\n            }\n        });\n        root.addView(save);",
        "                prefs.edit().putLong(\"mqtt_config_revision\", System.currentTimeMillis()).commit();\n                finish();\n            }\n        });\n        root.addView(save);",
        "MQTT settings revision")
    build = replace_once(build,
        'versionCode 9',
        'versionCode 10',
        "new versionCode")
    build = replace_once(build,
        'versionName "1.8"',
        'versionName "1.9"',
        "new versionName")
    build = replace_once(build,
        "dependencies {\n}",
        "dependencies {\n    implementation files('libs/org.eclipse.paho.client.mqttv3-1.2.5.jar')\n}",
        "Paho local jar")
    # Everything passed anchor validation; now write into the staging COPY only.
    activity.write_text(main, encoding="utf-8")
    settings.write_text(st, encoding="utf-8")
    gradle.write_text(build, encoding="utf-8")
    print("PASS: staged v1.9 privacy guards, screen integration, settings and version")
    print("No credentials or keystore touched. Verify gradle build and device tests.")

if __name__ == "__main__":
    main()
