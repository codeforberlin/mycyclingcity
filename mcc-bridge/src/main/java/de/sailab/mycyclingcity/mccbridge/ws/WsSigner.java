package de.sailab.mycyclingcity.mccbridge.ws;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.TreeMap;

public final class WsSigner {
    private static final Gson GSON = new Gson();

    private WsSigner() {
    }

    public static String sign(Map<String, Object> payload, String secret) {
        try {
            String message = GSON.toJson(new TreeMap<>(payload));
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] digest = mac.doFinal(message.getBytes(StandardCharsets.UTF_8));
            return toHex(digest);
        } catch (Exception ex) {
            throw new IllegalStateException("Failed to sign WebSocket payload", ex);
        }
    }

    public static JsonObject parseJson(String text) {
        return JsonParser.parseString(text).getAsJsonObject();
    }

    private static String toHex(byte[] bytes) {
        StringBuilder builder = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            builder.append(String.format("%02x", value));
        }
        return builder.toString();
    }
}
