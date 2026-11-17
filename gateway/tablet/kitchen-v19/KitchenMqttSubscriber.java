package uk.jns.hikvisiontalk;

import android.os.Handler;
import android.os.Looper;
import org.eclipse.paho.client.mqttv3.IMqttActionListener;
import org.eclipse.paho.client.mqttv3.IMqttToken;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttAsyncClient;
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.json.JSONObject;

import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.util.Arrays;

/**
 * MQTT 3.1.1 read-only client for the existing kitchen Android app.
 * Requires the Paho *Java* MQTT client jar, not a second Android Service.
 * Install only after testing on the real Android 4 tablet.
 */
public final class KitchenMqttSubscriber implements MqttCallbackExtended {
    private static final String BROKER_HOST = "mqtt-infra-a.home.arpa";
    private static final int BROKER_PORT = 8883;
    private static final String ALARM_TOPIC = "jns/tablet/kitchen/alarm/state";
    private static final String DOORBELL_TOPIC = "jns/security/doorbell/press";
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final DisplayPolicy policy;
    private final MqttAsyncClient client;
    private final MqttConnectOptions options;

    /**
     * @param clientId unique per tablet, e.g. 'jns-kitchen-...' (no secret)
     * @param username dedicated read-only Mosquitto user (provisioned locally)
     * @param password no static credential in the distributable APK
     * @param caCertificate trusted JNS MQTT root CA X.509 certificate stream;
     *                      caller closes it. Do not use trust-all TLS.
     */
    public KitchenMqttSubscriber(DisplayPolicy policy, String clientId,
                                 String username, char[] password,
                                 InputStream caCertificate) throws Exception {
        if (policy == null || clientId == null || username == null ||
            password == null || caCertificate == null) {
            throw new IllegalArgumentException("Required MQTT settings missing");
        }
        this.policy = policy;
        SSLContext context = trustedContext(caCertificate);
        this.client = new MqttAsyncClient(
            "ssl://" + BROKER_HOST + ":" + BROKER_PORT,
            clientId, new MemoryPersistence());
        this.options = new MqttConnectOptions();
        options.setUserName(username);
        options.setPassword(password);
        options.setCleanSession(true);
        options.setAutomaticReconnect(true);
        options.setKeepAliveInterval(15);
        options.setConnectionTimeout(8);
        options.setSocketFactory(new VerifiedTlsSocketFactory(
            context.getSocketFactory()));
        client.setCallback(this);
    }

    public void start() throws Exception {
        client.connect(options, null, new IMqttActionListener() {
            public void onSuccess(IMqttToken token) { /* connectComplete subscribes */ }
            public void onFailure(IMqttToken token, Throwable error) {
                privacyLock();
            }
        });
    }

    public void stop() {
        privacyLock();
        try { client.disconnectForcibly(1000, 1000); }
        catch (Exception ignored) { /* already disconnected */ }
        try { client.close(); }
        catch (Exception ignored) { /* already closed */ }
    }

    public void connectComplete(boolean reconnect, String serverURI) {
        ui.post(new Runnable() { public void run() { policy.onConnected(); } });
        try {
            // Exact topics only: no wildcard subscriptions or alarm control writes.
            client.subscribe(new String[]{ALARM_TOPIC, DOORBELL_TOPIC},
                             new int[]{1, 1});
        } catch (Exception ignored) {
            privacyLock();
        }
    }

    public void connectionLost(Throwable cause) {
        privacyLock();
    }

    public void deliveryComplete(IMqttDeliveryToken token) { /* read-only */ }

    public void messageArrived(String topic, MqttMessage message) {
        final long receivedMs = System.currentTimeMillis();
        if (ALARM_TOPIC.equals(topic)) {
            try {
                final JSONObject body = new JSONObject(new String(message.getPayload(), "UTF-8"));
                if (body.getInt("v") != 1) throw new IllegalArgumentException("schema");
                final String state = body.getString("state");
                final long sentMs = body.getLong("ts_ms");
                ui.post(new Runnable() { public void run() {
                    policy.onAlarmState(state, sentMs, receivedMs);
                }});
            } catch (Exception ignored) {
                privacyLock();
            }
        } else if (DOORBELL_TOPIC.equals(topic)) {
            final boolean retained = message.isRetained();
            final String payload;
            try { payload = new String(message.getPayload(), "UTF-8"); }
            catch (Exception ignored) { return; }
            ui.post(new Runnable() { public void run() {
                policy.onDoorbellPress(retained, payload, receivedMs);
            }});
        }
    }

    /** Called by existing app Handler at least once per second. */
    public void tick() { policy.checkExpiry(System.currentTimeMillis()); }

    private void privacyLock() {
        ui.post(new Runnable() { public void run() { policy.onDisconnected(); } });
    }

    private static SSLContext trustedContext(InputStream ca) throws Exception {
        Certificate cert = CertificateFactory.getInstance("X.509")
                                         .generateCertificate(ca);
        KeyStore store = KeyStore.getInstance(KeyStore.getDefaultType());
        store.load(null, null);
        store.setCertificateEntry("jns-mqtt-ca", cert);
        TrustManagerFactory tm = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
        tm.init(store);
        SSLContext ctx = SSLContext.getInstance("TLSv1.2");
        ctx.init(null, tm.getTrustManagers(), null);
        return ctx;
    }

    /** Enforces both CA chain validation and the configured DNS hostname. */
    private static final class VerifiedTlsSocketFactory extends SSLSocketFactory {
        private final SSLSocketFactory delegate;
        VerifiedTlsSocketFactory(SSLSocketFactory delegate) { this.delegate = delegate; }
        public String[] getDefaultCipherSuites(){ return delegate.getDefaultCipherSuites(); }
        public String[] getSupportedCipherSuites(){ return delegate.getSupportedCipherSuites(); }
        public Socket createSocket() throws IOException {
            // An unnamed SSL socket cannot be authenticated against the DNS name.
            throw new IOException("Host-bound TLS socket required");
        }
        public Socket createSocket(String host,int port) throws IOException {
            return validate(delegate.createSocket(host,port),host);
        }
        public Socket createSocket(String host,int port,InetAddress local,int localPort) throws IOException {
            return validate(delegate.createSocket(host,port,local,localPort),host);
        }
        public Socket createSocket(InetAddress host,int port) throws IOException {
            // IP-only address must never bypass broker hostname checks.
            throw new IOException("DNS name required");
        }
        public Socket createSocket(InetAddress host,int port,InetAddress local,int localPort) throws IOException {
            throw new IOException("DNS name required");
        }
        public Socket createSocket(Socket socket,String host,int port,boolean autoClose) throws IOException {
            return validate(delegate.createSocket(socket,host,port,autoClose),host);
        }
        private Socket validate(Socket socket,String host) throws IOException {
            if (!BROKER_HOST.equals(host) || !(socket instanceof SSLSocket)) {
                socket.close();
                throw new IOException("Unexpected MQTT TLS hostname/socket");
            }
            SSLSocket ssl=(SSLSocket) socket;
            if (!Arrays.asList(ssl.getSupportedProtocols()).contains("TLSv1.2")) {
                ssl.close();
                throw new IOException("Device lacks TLSv1.2; refusing plaintext fallback");
            }
            ssl.setEnabledProtocols(new String[]{"TLSv1.2"});
            try {
                ssl.startHandshake(); // verifies the peer against the pinned CA
                if (!HttpsURLConnection.getDefaultHostnameVerifier().verify(
                        host, ssl.getSession())) {
                    throw new IOException("MQTT certificate hostname mismatch");
                }
                return ssl;
            } catch (IOException e) {
                ssl.close();
                throw e;
            }
        }
    }
}