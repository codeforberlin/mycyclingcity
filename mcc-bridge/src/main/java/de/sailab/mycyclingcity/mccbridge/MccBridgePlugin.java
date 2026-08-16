package de.sailab.mycyclingcity.mccbridge;

import de.sailab.mycyclingcity.mccbridge.economy.VelosEconomyProvider;
import de.sailab.mycyclingcity.mccbridge.vehiclesplus.VehiclesPlusGarageCleaner;
import de.sailab.mycyclingcity.mccbridge.region.RegionOutlineService;
import de.sailab.mycyclingcity.mccbridge.shop.EconomyShopGuiApplier;
import de.sailab.mycyclingcity.mccbridge.shop.EconomyShopGuiReloader;
import de.sailab.mycyclingcity.mccbridge.shop.ShopTransactionListener;
import de.sailab.mycyclingcity.mccbridge.team.TeamResolver;
import de.sailab.mycyclingcity.mccbridge.ws.MccWebSocketClient;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.luckperms.api.LuckPerms;
import net.milkbowl.vault.economy.Economy;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.server.PluginEnableEvent;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.RegisteredServiceProvider;
import org.bukkit.plugin.java.JavaPlugin;

import java.nio.file.Files;
import java.nio.file.Path;

public final class MccBridgePlugin extends JavaPlugin {
    private MccBridgeConfig bridgeConfig;
    private TeamResolver teamResolver;
    private EconomyShopGuiApplier esguiApplier;
    private RegionOutlineService regionOutlineService;
    private MccWebSocketClient webSocketClient;
    private VelosEconomyProvider economyProvider;
    private boolean shopListenerRegistered;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        bridgeConfig = new MccBridgeConfig();
        reloadBridgeConfig();

        teamResolver = new TeamResolver(bridgeConfig);
        esguiApplier = new EconomyShopGuiApplier(this, bridgeConfig);
        regionOutlineService = new RegionOutlineService(this, bridgeConfig);
        getServer().getPluginManager().registerEvents(regionOutlineService, this);
        regionOutlineService.start();
        loadCachedRegions();

        webSocketClient = new MccWebSocketClient(this, bridgeConfig, esguiApplier, regionOutlineService);
        economyProvider = new VelosEconomyProvider(bridgeConfig, teamResolver, webSocketClient);
        getServer().getServicesManager().register(
                Economy.class, economyProvider, this, org.bukkit.plugin.ServicePriority.Highest
        );

        if (getServer().getPluginManager().getPlugin("Vault") == null
                && getServer().getPluginManager().getPlugin("VaultUnlocked") == null) {
            getLogger().warning(
                    "Vault/VaultUnlocked not found — EconomyShopGUI will not find a Vault economy"
            );
        } else {
            RegisteredServiceProvider<Economy> economyRegistration =
                    getServer().getServicesManager().getRegistration(Economy.class);
            if (economyRegistration != null) {
                getLogger().info(
                        "Velos economy registered via Vault as '"
                                + economyRegistration.getProvider().getName()
                                + "'"
                );
            } else {
                getLogger().warning("Vault economy registration missing after MCC-Bridge startup");
            }
        }

        if (getServer().getPluginManager().getPlugin("LuckPerms") != null) {
            RegisteredServiceProvider<LuckPerms> provider =
                    getServer().getServicesManager().getRegistration(LuckPerms.class);
            if (provider != null) {
                teamResolver.setLuckPerms(provider.getProvider());
                getLogger().info("LuckPerms team resolution enabled");
            }
        }

        getServer().getPluginManager().registerEvents(new Listener() {
            @EventHandler
            public void onPluginEnable(PluginEnableEvent event) {
                if (isEconomyShopGuiPlugin(event.getPlugin())) {
                    tryRegisterShopTransactionListener();
                }
            }
        }, this);
        tryRegisterShopTransactionListener();

        getServer().getScheduler().runTaskAsynchronously(this, webSocketClient::connect);
        getLogger().info(
                "MCC-Bridge enabled (must load before EconomyShopGUI via plugin.yml loadbefore)"
        );
    }

    @Override
    public void onDisable() {
        if (regionOutlineService != null) {
            regionOutlineService.stop();
        }
        if (webSocketClient != null) {
            webSocketClient.disconnect();
        }
        getServer().getServicesManager().unregisterAll(this);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("mccbridge")) {
            return false;
        }
        if (!sender.hasPermission("mccbridge.admin")) {
            sender.sendMessage("Missing permission: mccbridge.admin");
            return true;
        }
        if (args.length == 0) {
            sender.sendMessage(
                    "Usage: /mccbridge <status|reload|synccatalog|syncregions|esguireload|esguistatus|vpremove>"
            );
            return true;
        }
        switch (args[0].toLowerCase()) {
            case "status" -> {
                sender.sendMessage("WebSocket connected: " + webSocketClient.isConnected());
                sender.sendMessage("Server ID: " + bridgeConfig.serverId());
                sender.sendMessage("Heartbeat seconds: " + bridgeConfig.heartbeatSeconds());
                sender.sendMessage("Team mappings: " + bridgeConfig.teamGroups().size());
                sender.sendMessage(
                        "LuckPerms sync: configure teams in MCC Admin (auto LP group on register)"
                );
                sender.sendMessage("EconomyShopGUI sync: " + bridgeConfig.esguiSyncOnCatalog());
                sender.sendMessage(
                        "EconomyShopGUI installed: " + esguiApplier.isEconomyShopGuiAvailable()
                );
                sender.sendMessage("Shop sell ledger listener: " + shopListenerRegistered);
                sender.sendMessage(
                        "Region outlines: "
                                + regionOutlineService.regionCount()
                                + " regions, enabled="
                                + regionOutlineService.isOutlineEnabled()
                );
                sender.sendMessage(
                        "VehiclesPlus: "
                                + (VehiclesPlusGarageCleaner.isVehiclesPlusPresent()
                                        ? VehiclesPlusGarageCleaner.pluginVersionHint()
                                        : "not loaded")
                );
            }
            case "reload" -> {
                reloadBridgeConfig();
                sender.sendMessage("MCC-Bridge config reloaded");
            }
            case "synccatalog" -> {
                getServer().getScheduler().runTaskAsynchronously(this, () -> {
                    webSocketClient.syncCatalog().whenComplete((result, error) -> {
                        Runnable notify = () -> {
                            if (error != null) {
                                sender.sendMessage("Catalog sync failed: " + error.getMessage());
                                return;
                            }
                            sender.sendMessage(
                                    "Catalog sync completed (EconomyShopGUI updated if enabled)"
                            );
                        };
                        if (sender instanceof org.bukkit.entity.Player) {
                            getServer().getScheduler().runTask(this, notify);
                        } else {
                            notify.run();
                        }
                    });
                });
            }
            case "syncregions" -> {
                getServer().getScheduler().runTaskAsynchronously(this, () -> {
                    webSocketClient.syncProtectedRegions().whenComplete((result, error) -> {
                        Runnable notify = () -> {
                            if (error != null) {
                                sender.sendMessage("Regions sync failed: " + error.getMessage());
                                return;
                            }
                            sender.sendMessage(
                                    "Regions sync completed ("
                                            + regionOutlineService.regionCount()
                                            + " regions)"
                            );
                        };
                        if (sender instanceof org.bukkit.entity.Player) {
                            getServer().getScheduler().runTask(this, notify);
                        } else {
                            notify.run();
                        }
                    });
                });
            }
            case "esguistatus" -> EconomyShopGuiReloader.logDiagnostics(getLogger());
            case "esguireload" -> getServer().getScheduler().runTask(this, () -> {
                boolean ok = EconomyShopGuiReloader.reload(
                        getLogger(), bridgeConfig.esguiReloadCycleFallback()
                );
                sender.sendMessage(
                        ok
                                ? "EconomyShopGUI reload OK"
                                : "EconomyShopGUI reload failed — see server log"
                );
            });
            case "vpremove" -> {
                if (args.length < 3) {
                    sender.sendMessage("Usage: /mccbridge vpremove <garage|player> <modelId|*>");
                    return true;
                }
                String garageName = args[1];
                String modelId = args[2];
                // Console/RCON is already on the main thread — run inline so the
                // caller gets a result after the garage was actually updated.
                Runnable work = () -> {
                    try {
                        int n = VehiclesPlusGarageCleaner.removeFromGarage(
                                garageName, modelId, getLogger()
                        );
                        sender.sendMessage(
                                "VehiclesPlus: removed " + n + " vehicle(s) from garage '"
                                        + garageName + "' (model=" + modelId + ")"
                        );
                    } catch (Exception ex) {
                        getLogger().warning("[vpremove] failed: " + ex.getMessage());
                        sender.sendMessage("VehiclesPlus remove failed: " + ex.getMessage());
                    }
                };
                if (getServer().isPrimaryThread()) {
                    work.run();
                } else {
                    getServer().getScheduler().runTask(this, work);
                }
            }
            default -> sender.sendMessage(
                    "Usage: /mccbridge <status|reload|synccatalog|syncregions|esguireload|esguistatus|vpremove>"
            );
        }
        return true;
    }

    private void loadCachedRegions() {
        try {
            Path path = getDataFolder().toPath().resolve("regions.json");
            if (!Files.isRegularFile(path)) {
                return;
            }
            String json = Files.readString(path);
            JsonObject regions = JsonParser.parseString(json).getAsJsonObject();
            regionOutlineService.applyPayload(regions);
            getLogger().info("Loaded cached protected regions from " + path);
        } catch (Exception ex) {
            getLogger().warning("Failed to load cached regions: " + ex.getMessage());
        }
    }

    private void reloadBridgeConfig() {
        reloadConfig();
        bridgeConfig.load(getConfig());
        esguiApplier = new EconomyShopGuiApplier(this, bridgeConfig);
        if (teamResolver != null) {
            teamResolver = new TeamResolver(bridgeConfig);
            if (getServer().getPluginManager().getPlugin("LuckPerms") != null) {
                RegisteredServiceProvider<LuckPerms> provider =
                        getServer().getServicesManager().getRegistration(LuckPerms.class);
                if (provider != null) {
                    teamResolver.setLuckPerms(provider.getProvider());
                }
            }
        }
    }

    private void tryRegisterShopTransactionListener() {
        if (shopListenerRegistered || !esguiApplier.isEconomyShopGuiAvailable()) {
            return;
        }
        try {
            getServer().getPluginManager().registerEvents(
                    new ShopTransactionListener(teamResolver, webSocketClient, getLogger()),
                    this
            );
            shopListenerRegistered = true;
            getLogger().info("Shop purchase/sell ledger listener registered");
        } catch (NoClassDefFoundError | Exception ex) {
            getLogger().warning(
                    "Could not register EconomyShopGUI transaction listener: " + ex.getMessage()
            );
        }
    }

    private static boolean isEconomyShopGuiPlugin(Plugin plugin) {
        String name = plugin.getName();
        return "EconomyShopGUI".equals(name) || "EconomyShopGUI-Premium".equals(name);
    }
}
