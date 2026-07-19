package de.sailab.mycyclingcity.mccbridge;

import de.sailab.mycyclingcity.mccbridge.economy.VelosEconomyProvider;
import de.sailab.mycyclingcity.mccbridge.shop.EconomyShopGuiApplier;
import de.sailab.mycyclingcity.mccbridge.shop.EconomyShopGuiReloader;
import de.sailab.mycyclingcity.mccbridge.team.TeamResolver;
import de.sailab.mycyclingcity.mccbridge.ws.MccWebSocketClient;
import net.luckperms.api.LuckPerms;
import net.milkbowl.vault.economy.Economy;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.plugin.RegisteredServiceProvider;
import org.bukkit.plugin.java.JavaPlugin;

public final class MccBridgePlugin extends JavaPlugin {
    private MccBridgeConfig bridgeConfig;
    private TeamResolver teamResolver;
    private EconomyShopGuiApplier esguiApplier;
    private MccWebSocketClient webSocketClient;
    private VelosEconomyProvider economyProvider;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        bridgeConfig = new MccBridgeConfig();
        reloadBridgeConfig();

        teamResolver = new TeamResolver(bridgeConfig);
        esguiApplier = new EconomyShopGuiApplier(this, bridgeConfig);
        webSocketClient = new MccWebSocketClient(this, bridgeConfig, esguiApplier);
        economyProvider = new VelosEconomyProvider(bridgeConfig, teamResolver, webSocketClient);
        getServer().getServicesManager().register(Economy.class, economyProvider, this, org.bukkit.plugin.ServicePriority.Highest);

        if (getServer().getPluginManager().getPlugin("Vault") == null
                && getServer().getPluginManager().getPlugin("VaultUnlocked") == null) {
            getLogger().warning("Vault/VaultUnlocked not found — EconomyShopGUI will not find a Vault economy");
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
            RegisteredServiceProvider<LuckPerms> provider = getServer().getServicesManager().getRegistration(LuckPerms.class);
            if (provider != null) {
                teamResolver.setLuckPerms(provider.getProvider());
                getLogger().info("LuckPerms team resolution enabled");
            }
        }

        getServer().getScheduler().runTaskAsynchronously(this, webSocketClient::connect);
        getLogger().info("MCC-Bridge enabled (must load before EconomyShopGUI via plugin.yml loadbefore)");
    }

    @Override
    public void onDisable() {
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
            sender.sendMessage("Usage: /mccbridge <status|reload|synccatalog|esguireload|esguistatus>");
            return true;
        }
        switch (args[0].toLowerCase()) {
            case "status" -> {
                sender.sendMessage("WebSocket connected: " + webSocketClient.isConnected());
                sender.sendMessage("Server ID: " + bridgeConfig.serverId());
                sender.sendMessage("Heartbeat seconds: " + bridgeConfig.heartbeatSeconds());
                sender.sendMessage("Team mappings: " + bridgeConfig.teamGroups().size());
                sender.sendMessage("LuckPerms sync: configure teams in MCC Admin (auto LP group on register)");
                sender.sendMessage("EconomyShopGUI sync: " + bridgeConfig.esguiSyncOnCatalog());
                sender.sendMessage("EconomyShopGUI installed: " + esguiApplier.isEconomyShopGuiAvailable());
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
                            sender.sendMessage("Catalog sync completed (EconomyShopGUI updated if enabled)");
                        };
                        if (sender instanceof org.bukkit.entity.Player player) {
                            getServer().getScheduler().runTask(this, notify);
                        } else {
                            notify.run();
                        }
                    });
                });
            }
            case "esguistatus" -> EconomyShopGuiReloader.logDiagnostics(getLogger());
            case "esguireload" -> getServer().getScheduler().runTask(this, () -> {
                boolean ok = EconomyShopGuiReloader.reload(getLogger(), bridgeConfig.esguiReloadCycleFallback());
                sender.sendMessage(ok ? "EconomyShopGUI reload OK" : "EconomyShopGUI reload failed — see server log");
            });
            default -> sender.sendMessage("Usage: /mccbridge <status|reload|synccatalog|esguireload|esguistatus>");
        }
        return true;
    }

    private void reloadBridgeConfig() {
        reloadConfig();
        bridgeConfig.load(getConfig());
        esguiApplier = new EconomyShopGuiApplier(this, bridgeConfig);
        if (teamResolver != null) {
            teamResolver = new TeamResolver(bridgeConfig);
            if (getServer().getPluginManager().getPlugin("LuckPerms") != null) {
                RegisteredServiceProvider<LuckPerms> provider = getServer().getServicesManager().getRegistration(LuckPerms.class);
                if (provider != null) {
                    teamResolver.setLuckPerms(provider.getProvider());
                }
            }
        }
    }
}
