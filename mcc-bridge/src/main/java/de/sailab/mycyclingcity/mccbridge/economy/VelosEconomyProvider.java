package de.sailab.mycyclingcity.mccbridge.economy;

import de.sailab.mycyclingcity.mccbridge.MccBridgeConfig;
import de.sailab.mycyclingcity.mccbridge.team.TeamResolver;
import de.sailab.mycyclingcity.mccbridge.ws.MccWebSocketClient;
import net.milkbowl.vault.economy.Economy;
import net.milkbowl.vault.economy.EconomyResponse;
import org.bukkit.OfflinePlayer;

import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

public class VelosEconomyProvider implements Economy {
    private static final long CACHE_TTL_MS = 3000L;

    private final MccBridgeConfig config;
    private final TeamResolver teamResolver;
    private final MccWebSocketClient webSocketClient;
    private final ConcurrentHashMap<String, CachedBalance> balanceCache = new ConcurrentHashMap<>();

    public VelosEconomyProvider(
            MccBridgeConfig config,
            TeamResolver teamResolver,
            MccWebSocketClient webSocketClient
    ) {
        this.config = config;
        this.teamResolver = teamResolver;
        this.webSocketClient = webSocketClient;
    }

    @Override
    public boolean isEnabled() {
        return true;
    }

    @Override
    public String getName() {
        return "MCC-Bridge";
    }

    @Override
    public boolean hasBankSupport() {
        return false;
    }

    @Override
    public int fractionalDigits() {
        return 0;
    }

    @Override
    public String format(double amount) {
        return String.format("%.0f%s", amount, config.currencySymbol());
    }

    @Override
    public String currencyNamePlural() {
        return config.currencyName();
    }

    @Override
    public String currencyNameSingular() {
        return config.currencyName();
    }

    @Override
    public boolean hasAccount(String playerName) {
        return teamResolver.resolveTeamMcUsername(
                org.bukkit.Bukkit.getOfflinePlayer(playerName)
        ).isPresent();
    }

    @Override
    public boolean hasAccount(OfflinePlayer player) {
        return teamResolver.resolveTeamMcUsername(player).isPresent();
    }

    @Override
    public boolean hasAccount(String playerName, String worldName) {
        return hasAccount(playerName);
    }

    @Override
    public boolean hasAccount(OfflinePlayer player, String worldName) {
        return hasAccount(player);
    }

    @Override
    public double getBalance(String playerName) {
        return getBalance(org.bukkit.Bukkit.getOfflinePlayer(playerName));
    }

    @Override
    public double getBalance(OfflinePlayer player) {
        Optional<String> team = teamResolver.resolveTeamMcUsername(player);
        if (team.isEmpty()) {
            return 0D;
        }
        return fetchBalance(team.get());
    }

    @Override
    public double getBalance(String playerName, String world) {
        return getBalance(playerName);
    }

    @Override
    public double getBalance(OfflinePlayer player, String world) {
        return getBalance(player);
    }

    @Override
    public boolean has(String playerName, double amount) {
        return getBalance(playerName) >= amount;
    }

    @Override
    public boolean has(OfflinePlayer player, double amount) {
        return getBalance(player) >= amount;
    }

    @Override
    public boolean has(String playerName, String worldName, double amount) {
        return has(playerName, amount);
    }

    @Override
    public boolean has(OfflinePlayer player, String worldName, double amount) {
        return has(player, amount);
    }

    @Override
    public EconomyResponse withdrawPlayer(String playerName, double amount) {
        return withdrawPlayer(org.bukkit.Bukkit.getOfflinePlayer(playerName), amount);
    }

    @Override
    public EconomyResponse withdrawPlayer(OfflinePlayer player, double amount) {
        Optional<String> team = teamResolver.resolveTeamMcUsername(player);
        if (team.isEmpty()) {
            return new EconomyResponse(0, 0, EconomyResponse.ResponseType.FAILURE, "No team mapping");
        }
        if (amount <= 0) {
            return new EconomyResponse(0, getBalance(player), EconomyResponse.ResponseType.FAILURE, "Invalid amount");
        }
        int spendAmount = (int) Math.round(amount);
        try {
            var response = webSocketClient.spendTeamVelos(team.get(), spendAmount).get(10, TimeUnit.SECONDS);
            if (!"ok".equals(response.get("status").getAsString())) {
                return new EconomyResponse(0, getBalance(player), EconomyResponse.ResponseType.FAILURE, "MCC rejected spend");
            }
            balanceCache.remove(team.get());
            double newBalance = fetchBalance(team.get());
            return new EconomyResponse(spendAmount, newBalance, EconomyResponse.ResponseType.SUCCESS, null);
        } catch (Exception ex) {
            return new EconomyResponse(0, getBalance(player), EconomyResponse.ResponseType.FAILURE, ex.getMessage());
        }
    }

    @Override
    public EconomyResponse withdrawPlayer(String playerName, String worldName, double amount) {
        return withdrawPlayer(playerName, amount);
    }

    @Override
    public EconomyResponse withdrawPlayer(OfflinePlayer player, String worldName, double amount) {
        return withdrawPlayer(player, amount);
    }

    @Override
    public EconomyResponse depositPlayer(String playerName, double amount) {
        return new EconomyResponse(0, getBalance(playerName), EconomyResponse.ResponseType.NOT_IMPLEMENTED, "Deposits via MCC only");
    }

    @Override
    public EconomyResponse depositPlayer(OfflinePlayer player, double amount) {
        return new EconomyResponse(0, getBalance(player), EconomyResponse.ResponseType.NOT_IMPLEMENTED, "Deposits via MCC only");
    }

    @Override
    public EconomyResponse depositPlayer(String playerName, String worldName, double amount) {
        return depositPlayer(playerName, amount);
    }

    @Override
    public EconomyResponse depositPlayer(OfflinePlayer player, String worldName, double amount) {
        return depositPlayer(player, amount);
    }

    @Override
    public EconomyResponse createBank(String name, String player) {
        return notImplemented();
    }

    @Override
    public EconomyResponse createBank(String name, OfflinePlayer player) {
        return notImplemented();
    }

    @Override
    public EconomyResponse deleteBank(String name) {
        return notImplemented();
    }

    @Override
    public EconomyResponse bankBalance(String name) {
        return notImplemented();
    }

    @Override
    public EconomyResponse bankHas(String name, double amount) {
        return notImplemented();
    }

    @Override
    public EconomyResponse bankWithdraw(String name, double amount) {
        return notImplemented();
    }

    @Override
    public EconomyResponse bankDeposit(String name, double amount) {
        return notImplemented();
    }

    @Override
    public EconomyResponse isBankOwner(String name, String playerName) {
        return notImplemented();
    }

    @Override
    public EconomyResponse isBankOwner(String name, OfflinePlayer player) {
        return notImplemented();
    }

    @Override
    public EconomyResponse isBankMember(String name, String playerName) {
        return notImplemented();
    }

    @Override
    public EconomyResponse isBankMember(String name, OfflinePlayer player) {
        return notImplemented();
    }

    @Override
    public List<String> getBanks() {
        return Collections.emptyList();
    }

    @Override
    public boolean createPlayerAccount(String playerName) {
        return hasAccount(playerName);
    }

    @Override
    public boolean createPlayerAccount(OfflinePlayer player) {
        return hasAccount(player);
    }

    @Override
    public boolean createPlayerAccount(String playerName, String worldName) {
        return hasAccount(playerName);
    }

    @Override
    public boolean createPlayerAccount(OfflinePlayer player, String worldName) {
        return hasAccount(player);
    }

    private double fetchBalance(String teamMcUsername) {
        CachedBalance cached = balanceCache.get(teamMcUsername);
        long now = System.currentTimeMillis();
        if (cached != null && cached.expiresAtMs > now) {
            return cached.balance;
        }
        try {
            CompletableFuture<Optional<com.google.gson.JsonObject>> future = webSocketClient.getTeamVelos(teamMcUsername);
            Optional<com.google.gson.JsonObject> response = future.get(10, TimeUnit.SECONDS);
            if (response.isEmpty()) {
                return 0D;
            }
            double balance = response.get().get("velos_spendable").getAsDouble();
            balanceCache.put(teamMcUsername, new CachedBalance(balance, now + CACHE_TTL_MS));
            return balance;
        } catch (Exception ex) {
            return cached != null ? cached.balance : 0D;
        }
    }

    private EconomyResponse notImplemented() {
        return new EconomyResponse(0, 0, EconomyResponse.ResponseType.NOT_IMPLEMENTED, "Not supported");
    }

    private record CachedBalance(double balance, long expiresAtMs) {
    }
}
