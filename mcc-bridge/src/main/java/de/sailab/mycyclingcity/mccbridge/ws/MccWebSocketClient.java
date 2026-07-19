package de.sailab.mycyclingcity.mccbridge.ws;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import de.sailab.mycyclingcity.mccbridge.MccBridgeConfig;
import de.sailab.mycyclingcity.mccbridge.shop.EconomyShopGuiApplier;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import org.bukkit.plugin.Plugin;
import org.bukkit.scheduler.BukkitTask;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Logger;

public class MccWebSocketClient {
    private static final Gson GSON = new Gson();

    private final Plugin plugin;
    private final MccBridgeConfig config;
    private final EconomyShopGuiApplier esguiApplier;
    private final Logger logger;
    private final OkHttpClient httpClient;
    private final AtomicInteger requestCounter = new AtomicInteger();
    private final Map<String, CompletableFuture<JsonObject>> pending = new ConcurrentHashMap<>();

    private WebSocket webSocket;
    private volatile boolean connected;
    private BukkitTask heartbeatTask;

    public MccWebSocketClient(Plugin plugin, MccBridgeConfig config, EconomyShopGuiApplier esguiApplier) {
        this.plugin = plugin;
        this.config = config;
        this.esguiApplier = esguiApplier;
        this.logger = plugin.getLogger();
        this.httpClient = new OkHttpClient.Builder()
                .pingInterval(30, TimeUnit.SECONDS)
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.SECONDS)
                .build();
    }

    public void connect() {
        disconnect();
        Request request = new Request.Builder().url(config.websocketUrl()).build();
        webSocket = httpClient.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(@NotNull WebSocket webSocket, @NotNull Response response) {
                connected = true;
                logger.info("Connected to MCC WebSocket");
                startHeartbeat();
                // Immediate presence so Admin shop-push is enabled before first timer tick
                sendHeartbeat().exceptionally(ex -> {
                    logger.fine("Initial heartbeat failed: " + ex.getMessage());
                    return null;
                });
                if (config.catalogSyncOnConnect()) {
                    plugin.getServer().getScheduler().runTaskAsynchronously(plugin, () -> syncCatalog().exceptionally(ex -> {
                        logger.warning("Initial catalog sync failed: " + ex.getMessage());
                        return Optional.empty();
                    }));
                }
            }

            @Override
            public void onMessage(@NotNull WebSocket webSocket, @NotNull String text) {
                handleIncoming(text);
            }

            @Override
            public void onClosed(@NotNull WebSocket webSocket, int code, @NotNull String reason) {
                connected = false;
                stopHeartbeat();
                failPending(new IOException("WebSocket closed: " + reason));
                scheduleReconnect();
            }

            @Override
            public void onFailure(@NotNull WebSocket webSocket, @NotNull Throwable t, @Nullable Response response) {
                connected = false;
                stopHeartbeat();
                logger.warning("MCC WebSocket failure: " + t.getMessage());
                failPending(t);
                scheduleReconnect();
            }
        });
    }

    public void disconnect() {
        connected = false;
        stopHeartbeat();
        if (webSocket != null) {
            webSocket.close(1000, "shutdown");
            webSocket = null;
        }
        failPending(new IOException("WebSocket disconnected"));
    }

    public boolean isConnected() {
        return connected;
    }

    public CompletableFuture<JsonObject> spendTeamVelos(String teamMcUsername, int amount) {
        Map<String, Object> payload = basePayload("SPEND_GROUP_VELOS");
        payload.put("player", teamMcUsername);
        payload.put("amount", amount);
        return sendRequest(payload);
    }

    public CompletableFuture<Optional<JsonObject>> getTeamVelos(String teamMcUsername) {
        Map<String, Object> payload = basePayload("GET_TEAM_VELOS");
        payload.put("player", teamMcUsername);
        return sendRequest(payload).thenApply(response -> {
            if (!"ok".equals(response.get("status").getAsString())) {
                return Optional.empty();
            }
            return Optional.of(response);
        });
    }

    public CompletableFuture<Optional<JsonObject>> syncCatalog() {
        Map<String, Object> payload = basePayload("SYNC_SHOP_CATALOG");
        return sendRequest(payload).thenApply(response -> {
            if (!"ok".equals(response.get("status").getAsString())) {
                String error = response.has("error") ? response.get("error").getAsString() : "unknown";
                logger.warning("Shop catalog sync rejected: " + error);
                return Optional.empty();
            }
            if (response.has("catalog")) {
                JsonObject catalog = response.getAsJsonObject("catalog");
                saveCatalog(catalog);
                applyCatalogToEsgui(catalog);
            }
            return Optional.of(response);
        });
    }

    /**
     * Signed application heartbeat so MCC Admin keeps the bridge "connected"
     * (OkHttp protocol pings alone do not update Django last_seen).
     */
    public CompletableFuture<JsonObject> sendHeartbeat() {
        return sendRequest(basePayload("HEARTBEAT"));
    }

    private void startHeartbeat() {
        stopHeartbeat();
        int seconds = config.heartbeatSeconds();
        if (seconds <= 0) {
            return;
        }
        long periodTicks = seconds * 20L;
        heartbeatTask = plugin.getServer().getScheduler().runTaskTimerAsynchronously(
                plugin,
                () -> {
                    if (!connected || webSocket == null) {
                        return;
                    }
                    sendHeartbeat().exceptionally(ex -> {
                        logger.fine("Heartbeat failed: " + ex.getMessage());
                        return null;
                    });
                },
                periodTicks,
                periodTicks
        );
        logger.info("MCC WebSocket heartbeat every " + seconds + "s");
    }

    private void stopHeartbeat() {
        if (heartbeatTask != null) {
            heartbeatTask.cancel();
            heartbeatTask = null;
        }
    }

    private Map<String, Object> basePayload(String type) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("type", type);
        payload.put("server_id", config.serverId());
        return payload;
    }

    private CompletableFuture<JsonObject> sendRequest(Map<String, Object> payload) {
        String requestId = String.valueOf(requestCounter.incrementAndGet());
        payload.put("request_id", requestId);

        Map<String, Object> signedPayload = new LinkedHashMap<>(payload);
        String signature = WsSigner.sign(signedPayload, config.sharedSecret());
        signedPayload.put("signature", signature);

        CompletableFuture<JsonObject> future = new CompletableFuture<>();
        pending.put(requestId, future);

        String json = GSON.toJson(signedPayload);
        if (!connected || webSocket == null) {
            pending.remove(requestId);
            future.completeExceptionally(new IOException("WebSocket not connected"));
            return future;
        }

        if (!webSocket.send(json)) {
            pending.remove(requestId);
            future.completeExceptionally(new IOException("Failed to send WebSocket message"));
        }
        return future.orTimeout(10, TimeUnit.SECONDS);
    }

    private void handleIncoming(String text) {
        JsonObject response = WsSigner.parseJson(text);
        if (response.has("type") && "REQUEST_CATALOG_SYNC".equals(response.get("type").getAsString())) {
            logger.info("Received catalog sync request from MCC");
            plugin.getServer().getScheduler().runTaskAsynchronously(plugin, () ->
                    syncCatalog().exceptionally(ex -> {
                        logger.warning("Requested catalog sync failed: " + ex.getMessage());
                        return Optional.empty();
                    })
            );
            return;
        }

        if (response.has("type") && "PUSH_TEAM_MAPPING".equals(response.get("type").getAsString())) {
            if (response.has("lp_group") && response.has("mc_username")) {
                String lpGroup = response.get("lp_group").getAsString();
                String mcUsername = response.get("mc_username").getAsString();
                config.upsertTeamGroup(lpGroup, mcUsername);
                logger.info("Team mapping updated from MCC: " + lpGroup + " -> " + mcUsername);
            }
            return;
        }

        if (response.has("type") && "REMOVE_TEAM_MAPPING".equals(response.get("type").getAsString())) {
            if (response.has("lp_group")) {
                config.removeTeamGroup(response.get("lp_group").getAsString());
                logger.info("Team mapping removed from MCC: " + response.get("lp_group").getAsString());
            }
            return;
        }

        if (response.has("request_id")) {
            CompletableFuture<JsonObject> future = pending.remove(response.get("request_id").getAsString());
            if (future != null) {
                future.complete(response);
                return;
            }
        }
        logger.fine("Unhandled WebSocket message: " + text);
    }

    private void failPending(Throwable cause) {
        pending.forEach((id, future) -> future.completeExceptionally(cause));
        pending.clear();
    }

    private void scheduleReconnect() {
        plugin.getServer().getScheduler().runTaskLaterAsynchronously(
                plugin,
                this::connect,
                config.reconnectSeconds() * 20L
        );
    }

    private void saveCatalog(JsonObject catalog) {
        try {
            Path path = plugin.getDataFolder().toPath().resolve("catalog.json");
            Files.createDirectories(path.getParent());
            Files.writeString(path, GSON.toJson(catalog));
            logger.info("Shop catalog saved to " + path);
        } catch (IOException ex) {
            logger.warning("Failed to save shop catalog: " + ex.getMessage());
        }
    }

    private void applyCatalogToEsgui(JsonObject catalog) {
        if (!config.esguiSyncOnCatalog()) {
            return;
        }
        EconomyShopGuiApplier.ApplyResult result = esguiApplier.apply(catalog);
        if (!result.success()) {
            logger.warning(result.message());
            return;
        }
        logger.info(result.message());
    }
}
