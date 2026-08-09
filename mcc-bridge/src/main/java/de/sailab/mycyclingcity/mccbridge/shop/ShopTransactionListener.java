package de.sailab.mycyclingcity.mccbridge.shop;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import de.sailab.mycyclingcity.mccbridge.team.TeamResolver;
import de.sailab.mycyclingcity.mccbridge.ws.MccWebSocketClient;
import me.gypopo.economyshopgui.api.events.PostTransactionEvent;
import me.gypopo.economyshopgui.api.events.PreTransactionEvent;
import me.gypopo.economyshopgui.objects.ShopItem;
import me.gypopo.economyshopgui.util.EcoType;
import me.gypopo.economyshopgui.util.Transaction;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.inventory.ItemStack;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

/**
 * Tracks shop buys into the MCC purchase ledger and gates sells by remaining credit.
 * MCC-Bridge loads before EconomyShopGUI; register this listener after ESGUI enables.
 *
 * <p>SellGUI multi-item sells must not be cancelled when credit is insufficient:
 * EconomyShopGUI then builds {@code PostTransactionEvent} with a null prices map and NPEs,
 * which breaks returning items from the sell GUI. Instead we partially shrink the event
 * item/price maps (and hand non-credited stacks back to the player) so ESGUI can finish.
 */
public final class ShopTransactionListener implements Listener {
    private final TeamResolver teamResolver;
    private final MccWebSocketClient webSocketClient;
    private final Logger logger;

    /** Credits consumed in PreTransaction for sells; restored if PostTransaction fails. */
    private final ConcurrentHashMap<UUID, List<Map<String, Object>>> pendingSellConsumes =
            new ConcurrentHashMap<>();

    public ShopTransactionListener(
            TeamResolver teamResolver,
            MccWebSocketClient webSocketClient,
            Logger logger
    ) {
        this.teamResolver = teamResolver;
        this.webSocketClient = webSocketClient;
        this.logger = logger;
    }

    @EventHandler(priority = EventPriority.HIGH, ignoreCancelled = true)
    public void onPreTransaction(PreTransactionEvent event) {
        if (!isSell(event.getTransactionType())) {
            return;
        }

        Player player = event.getPlayer();
        Optional<String> team = teamResolver.resolveTeamMcUsername(player);
        if (team.isEmpty()) {
            cancelMultiSafe(event);
            logger.warning("Shop sell cancelled: no team mapping for " + player.getName());
            return;
        }

        List<Map<String, Object>> items = collectItems(event);
        if (items.isEmpty()) {
            cancelMultiSafe(event);
            logger.warning("Shop sell cancelled: no items for " + player.getName());
            return;
        }

        boolean multi = isMultiItemSell(event);
        try {
            JsonObject response = webSocketClient
                    .consumeShopSellCredit(team.get(), items, multi)
                    .get(10, TimeUnit.SECONDS);
            if (!"ok".equals(response.get("status").getAsString())) {
                cancelMultiSafe(event);
                String error = response.has("error") ? response.get("error").getAsString() : "unknown";
                logger.info(
                        "Shop sell blocked for "
                                + player.getName()
                                + " team="
                                + team.get()
                                + " reason="
                                + error
                );
                return;
            }

            List<Map<String, Object>> consumed = parseConsumed(response, items);
            if (multi) {
                if (consumed.isEmpty()) {
                    // Cancel safely: SellGUI keeps stacks in its inventory and addUnsoldItems
                    // returns them. Do not hand items back here (would duplicate).
                    cancelMultiSafe(event);
                    logger.info(
                            "Shop sellgui: no ledger credit for any item, returning all to "
                                    + player.getName()
                    );
                    return;
                }
                applyPartialSell(event, player, consumed);
                if (event.getItems() == null || event.getItems().isEmpty()) {
                    // Remainder already returned to the player; let ESGUI finish with empty
                    // maps (must not cancel — that would return the sell-GUI stacks again).
                    pendingSellConsumes.put(player.getUniqueId(), consumed);
                    return;
                }
            }

            pendingSellConsumes.put(player.getUniqueId(), consumed);
        } catch (Exception ex) {
            cancelMultiSafe(event);
            logger.warning("Shop sell credit check failed: " + ex.getMessage());
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPostTransaction(PostTransactionEvent event) {
        Transaction.Type type = event.getTransactionType();
        Transaction.Result result = event.getTransactionResult();
        Player player = event.getPlayer();

        if (isSell(type)) {
            List<Map<String, Object>> consumed = pendingSellConsumes.remove(player.getUniqueId());
            if (consumed != null && !isSuccess(result)) {
                restoreCredits(player, consumed);
            }
            return;
        }

        if (!isBuy(type) || !isSuccess(result)) {
            return;
        }

        Optional<String> team = teamResolver.resolveTeamMcUsername(player);
        if (team.isEmpty()) {
            logger.warning("Shop purchase not recorded: no team mapping for " + player.getName());
            return;
        }

        for (Map<String, Object> item : collectItems(event)) {
            String material = String.valueOf(item.get("material"));
            int amount = ((Number) item.get("amount")).intValue();
            try {
                var response = webSocketClient.recordShopPurchase(team.get(), material, amount)
                        .get(10, TimeUnit.SECONDS);
                if (!"ok".equals(response.get("status").getAsString())) {
                    String error = response.has("error") ? response.get("error").getAsString() : "unknown";
                    logger.warning(
                            "Failed to record shop purchase for "
                                    + player.getName()
                                    + " "
                                    + material
                                    + "x"
                                    + amount
                                    + ": "
                                    + error
                    );
                }
            } catch (Exception ex) {
                logger.warning("Failed to record shop purchase: " + ex.getMessage());
            }
        }
    }

    /**
     * Shrink SellGUI item/price maps to ledger-consumed amounts and return the remainder
     * to the player immediately. ESGUI still removes the original stacks from the sell GUI
     * after PreTransaction; without this hand-back those leftovers would be lost.
     */
    private void applyPartialSell(
            PreTransactionEvent event,
            Player player,
            List<Map<String, Object>> consumed
    ) {
        Map<ShopItem, Integer> shopItems = event.getItems();
        Map<EcoType, Double> prices = event.getPrices();
        if (shopItems == null || shopItems.isEmpty()) {
            return;
        }

        Map<String, Integer> remaining = new HashMap<>();
        for (Map<String, Object> entry : consumed) {
            String material = String.valueOf(entry.get("material")).toUpperCase(Locale.ROOT);
            int amount = ((Number) entry.get("amount")).intValue();
            if (amount > 0) {
                remaining.merge(material, amount, Integer::sum);
            }
        }

        Iterator<Map.Entry<ShopItem, Integer>> it = shopItems.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<ShopItem, Integer> entry = it.next();
            ShopItem shopItem = entry.getKey();
            int requested = entry.getValue() == null ? 0 : entry.getValue();
            String material = materialOf(shopItem);
            if (material == null || requested <= 0) {
                it.remove();
                continue;
            }
            int allowed = Math.min(requested, remaining.getOrDefault(material, 0));
            if (allowed > 0) {
                remaining.put(material, remaining.getOrDefault(material, 0) - allowed);
            }
            int giveBack = requested - allowed;
            if (giveBack > 0) {
                giveItemBack(player, shopItem, giveBack);
            }
            if (allowed <= 0) {
                it.remove();
            } else if (allowed != requested) {
                entry.setValue(allowed);
            }
        }

        if (prices != null) {
            Map<EcoType, Double> rebuilt = rebuildPrices(player, shopItems);
            prices.clear();
            prices.putAll(rebuilt);
            if (!shopItems.isEmpty()) {
                ShopItem primary = shopItems.keySet().iterator().next();
                Double primaryPrice = prices.get(primary.getEcoType());
                if (primaryPrice != null) {
                    event.setPrice(primaryPrice);
                }
            }
        }

        logger.info(
                "Shop sellgui partial for "
                        + player.getName()
                        + " kept="
                        + shopItems
                        + " returned_remainder=true"
        );
    }

    /**
     * EconomyShopGUI-API (compileOnly) does not expose getSellPrice; the runtime plugin does.
     * Reflect so we can shrink SellGUI payouts after a partial ledger consume.
     */
    private static Map<EcoType, Double> rebuildPrices(Player player, Map<ShopItem, Integer> shopItems) {
        Map<EcoType, Double> rebuilt = new HashMap<>();
        for (Map.Entry<ShopItem, Integer> entry : shopItems.entrySet()) {
            ShopItem shopItem = entry.getKey();
            int amount = entry.getValue() == null ? 0 : entry.getValue();
            ItemStack stack = stackOf(shopItem);
            if (stack == null || amount <= 0) {
                continue;
            }
            double price = invokeSellPrice(shopItem, player, stack, amount);
            if (price < 0) {
                continue;
            }
            rebuilt.merge(shopItem.getEcoType(), price, Double::sum);
        }
        return rebuilt;
    }

    private static double invokeSellPrice(ShopItem shopItem, Player player, ItemStack stack, int amount) {
        try {
            var method = shopItem.getClass().getMethod(
                    "getSellPrice",
                    Player.class,
                    ItemStack.class,
                    int.class
            );
            Object value = method.invoke(shopItem, player, stack, amount);
            if (value instanceof Number number) {
                return number.doubleValue();
            }
        } catch (ReflectiveOperationException ignored) {
            // fall through
        }
        return -1;
    }

    private static void giveItemBack(Player player, ShopItem shopItem, int amount) {
        ItemStack stack = stackOf(shopItem);
        if (stack == null || amount <= 0) {
            return;
        }
        ItemStack give = stack.clone();
        give.setAmount(amount);
        Map<Integer, ItemStack> leftover = player.getInventory().addItem(give);
        for (ItemStack drop : leftover.values()) {
            player.getWorld().dropItemNaturally(player.getLocation(), drop);
        }
    }

    private static ItemStack stackOf(ShopItem shopItem) {
        if (shopItem == null) {
            return null;
        }
        ItemStack stack = shopItem.getItemToGive();
        if (stack == null || stack.getType().isAir()) {
            stack = shopItem.getShopItem();
        }
        if (stack == null || stack.getType().isAir()) {
            return null;
        }
        return stack;
    }

    /**
     * EconomyShopGUI SellGUI cancels by returning a null prices map to PostTransaction.
     * Clearing the items map first avoids NPE when items would otherwise be non-empty.
     */
    private static void cancelMultiSafe(PreTransactionEvent event) {
        Map<ShopItem, Integer> items = event.getItems();
        if (items != null && !items.isEmpty()) {
            items.clear();
        }
        Map<EcoType, Double> prices = event.getPrices();
        if (prices != null && !prices.isEmpty()) {
            prices.clear();
        }
        event.setCancelled(true);
    }

    private static boolean isMultiItemSell(PreTransactionEvent event) {
        Map<ShopItem, Integer> multi = event.getItems();
        return multi != null && !multi.isEmpty();
    }

    private static List<Map<String, Object>> parseConsumed(
            JsonObject response,
            List<Map<String, Object>> requested
    ) {
        if (!response.has("consumed") || !response.get("consumed").isJsonArray()) {
            return requested;
        }
        JsonArray array = response.getAsJsonArray("consumed");
        List<Map<String, Object>> consumed = new ArrayList<>();
        for (JsonElement element : array) {
            if (!element.isJsonObject()) {
                continue;
            }
            JsonObject row = element.getAsJsonObject();
            if (!row.has("material") || !row.has("amount")) {
                continue;
            }
            String material = row.get("material").getAsString().toUpperCase(Locale.ROOT);
            int amount = row.get("amount").getAsInt();
            if (amount > 0) {
                consumed.add(itemEntry(material, amount));
            }
        }
        return consumed;
    }

    private void restoreCredits(Player player, List<Map<String, Object>> items) {
        Optional<String> team = teamResolver.resolveTeamMcUsername(player);
        if (team.isEmpty()) {
            return;
        }
        for (Map<String, Object> item : items) {
            String material = String.valueOf(item.get("material"));
            int amount = ((Number) item.get("amount")).intValue();
            try {
                webSocketClient.recordShopPurchase(team.get(), material, amount)
                        .get(10, TimeUnit.SECONDS);
                logger.info(
                        "Restored shop sell credit after failed sell: "
                                + team.get()
                                + " "
                                + material
                                + "x"
                                + amount
                );
            } catch (Exception ex) {
                logger.warning("Failed to restore shop sell credit: " + ex.getMessage());
            }
        }
    }

    private static List<Map<String, Object>> collectItems(PreTransactionEvent event) {
        Map<ShopItem, Integer> multi = event.getItems();
        if (multi != null && !multi.isEmpty()) {
            return fromShopItemMap(multi);
        }
        return singleItem(event.getShopItem(), event.getAmount());
    }

    private static List<Map<String, Object>> collectItems(PostTransactionEvent event) {
        Map<ShopItem, Integer> multi = event.getItems();
        if (multi != null && !multi.isEmpty()) {
            return fromShopItemMap(multi);
        }
        return singleItem(event.getShopItem(), event.getAmount());
    }

    private static List<Map<String, Object>> fromShopItemMap(Map<ShopItem, Integer> multi) {
        Map<String, Integer> totals = new HashMap<>();
        for (Map.Entry<ShopItem, Integer> entry : multi.entrySet()) {
            String material = materialOf(entry.getKey());
            if (material == null || entry.getValue() == null || entry.getValue() <= 0) {
                continue;
            }
            totals.merge(material, entry.getValue(), Integer::sum);
        }
        List<Map<String, Object>> items = new ArrayList<>();
        for (Map.Entry<String, Integer> entry : totals.entrySet()) {
            items.add(itemEntry(entry.getKey(), entry.getValue()));
        }
        return items;
    }

    private static List<Map<String, Object>> singleItem(ShopItem shopItem, int amount) {
        List<Map<String, Object>> items = new ArrayList<>();
        String material = materialOf(shopItem);
        if (material != null && amount > 0) {
            items.add(itemEntry(material, amount));
        }
        return items;
    }

    private static Map<String, Object> itemEntry(String material, int amount) {
        Map<String, Object> entry = new HashMap<>();
        entry.put("material", material);
        entry.put("amount", amount);
        return entry;
    }

    private static String materialOf(ShopItem shopItem) {
        ItemStack stack = stackOf(shopItem);
        if (stack == null) {
            return null;
        }
        return stack.getType().name().toUpperCase(Locale.ROOT);
    }

    private static boolean isBuy(Transaction.Type type) {
        return Transaction.Mode.getFromType(type) == Transaction.Mode.BUY;
    }

    private static boolean isSell(Transaction.Type type) {
        return Transaction.Mode.getFromType(type) == Transaction.Mode.SELL;
    }

    private static boolean isSuccess(Transaction.Result result) {
        return result == Transaction.Result.SUCCESS
                || result == Transaction.Result.SUCCESS_COMMANDS_EXECUTED;
    }
}
