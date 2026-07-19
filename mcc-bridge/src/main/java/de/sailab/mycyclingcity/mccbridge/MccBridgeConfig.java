package de.sailab.mycyclingcity.mccbridge;

import org.bukkit.configuration.file.FileConfiguration;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public final class MccBridgeConfig {
    private String websocketUrl;
    private String sharedSecret;
    private String serverId;
    private int reconnectSeconds;
    private int heartbeatSeconds;
    private boolean catalogSyncOnConnect;
    private boolean esguiSyncOnCatalog;
    private boolean esguiAddMissingItems;
    private int esguiDefaultSellPrice;
    private boolean esguiReloadAfterSync;
    private boolean esguiReloadCycleFallback;
    private String currencyName;
    private String currencySymbol;
    private String resolution;
    private Map<String, String> staticTeamGroups = Collections.emptyMap();
    private final Map<String, String> runtimeTeamGroups = new LinkedHashMap<>();
    private Map<String, String> playerOverrides;

    public void load(FileConfiguration config) {
        websocketUrl = config.getString("mcc.websocket_url", "ws://127.0.0.1:8000/ws/minecraft/events/");
        sharedSecret = config.getString("mcc.shared_secret", "SECRET");
        serverId = config.getString("mcc.server_id", "velo-stadt-1");
        reconnectSeconds = Math.max(5, config.getInt("mcc.reconnect_seconds", 15));
        heartbeatSeconds = config.getInt("mcc.heartbeat_seconds", 60);
        if (heartbeatSeconds < 0) {
            heartbeatSeconds = 0;
        } else if (heartbeatSeconds > 0 && heartbeatSeconds < 15) {
            // Keep presence fresher than MCC Admin STALE_AFTER (5 min)
            heartbeatSeconds = 15;
        }
        catalogSyncOnConnect = config.getBoolean("mcc.catalog_sync_on_connect", true);
        esguiSyncOnCatalog = config.getBoolean("mcc.esgui_sync_on_catalog", true);
        esguiAddMissingItems = config.getBoolean("mcc.esgui_add_missing_items", false);
        esguiDefaultSellPrice = config.getInt("mcc.esgui_default_sell_price", -1);
        esguiReloadAfterSync = config.getBoolean("mcc.esgui_reload_after_sync", true);
        esguiReloadCycleFallback = config.getBoolean("mcc.esgui_reload_cycle_fallback", true);
        currencyName = config.getString("vault.currency_name", "Velos");
        currencySymbol = config.getString("vault.currency_symbol", " Velos");
        resolution = config.getString("team.resolution", "luckperms");
        staticTeamGroups = readStringMap(config, "team.team_groups");
        runtimeTeamGroups.clear();
        playerOverrides = readStringMap(config, "team.player_overrides");
    }

    public void upsertTeamGroup(String lpGroup, String mcUsername) {
        if (lpGroup == null || lpGroup.isBlank() || mcUsername == null || mcUsername.isBlank()) {
            return;
        }
        runtimeTeamGroups.put(lpGroup, mcUsername);
    }

    public void removeTeamGroup(String lpGroup) {
        if (lpGroup == null || lpGroup.isBlank()) {
            return;
        }
        runtimeTeamGroups.remove(lpGroup);
    }

    private Map<String, String> readStringMap(FileConfiguration config, String path) {
        if (!config.isConfigurationSection(path)) {
            return Collections.emptyMap();
        }
        Map<String, String> values = new LinkedHashMap<>();
        for (String key : config.getConfigurationSection(path).getKeys(false)) {
            String value = config.getString(path + "." + key);
            if (value != null && !value.isBlank()) {
                values.put(key, value);
            }
        }
        return values;
    }

    public String websocketUrl() {
        return websocketUrl;
    }

    public String sharedSecret() {
        return sharedSecret;
    }

    public String serverId() {
        return serverId;
    }

    public int reconnectSeconds() {
        return reconnectSeconds;
    }

    /** Application HEARTBEAT interval in seconds; 0 disables. */
    public int heartbeatSeconds() {
        return heartbeatSeconds;
    }

    public boolean catalogSyncOnConnect() {
        return catalogSyncOnConnect;
    }

    public boolean esguiSyncOnCatalog() {
        return esguiSyncOnCatalog;
    }

    public boolean esguiAddMissingItems() {
        return esguiAddMissingItems;
    }

    public int esguiDefaultSellPrice() {
        return esguiDefaultSellPrice;
    }

    public boolean esguiReloadAfterSync() {
        return esguiReloadAfterSync;
    }

    public boolean esguiReloadCycleFallback() {
        return esguiReloadCycleFallback;
    }

    public String currencyName() {
        return currencyName;
    }

    public String currencySymbol() {
        return currencySymbol;
    }

    public String resolution() {
        return resolution;
    }

    public Map<String, String> teamGroups() {
        Map<String, String> merged = new LinkedHashMap<>(staticTeamGroups);
        merged.putAll(runtimeTeamGroups);
        return merged;
    }

    public Map<String, String> playerOverrides() {
        return playerOverrides;
    }
}
