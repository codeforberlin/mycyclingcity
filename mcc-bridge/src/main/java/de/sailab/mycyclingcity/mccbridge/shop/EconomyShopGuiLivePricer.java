package de.sailab.mycyclingcity.mccbridge.shop;

import me.gypopo.economyshopgui.api.EconomyShopGUIHook;
import me.gypopo.economyshopgui.objects.ShopItem;
import me.gypopo.economyshopgui.objects.shops.ShopSection;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Applies catalog prices to EconomyShopGUI in-memory {@link ShopItem}s.
 *
 * <p>Paper does not safely support disable/enable of EconomyShopGUI (classloader zip
 * errors). {@code /sreload} reloads the main config but does not reliably refresh
 * shop item buy/sell fields — so we patch {@code buyPrice}/{@code sellPrice} directly
 * after writing YAML.
 */
final class EconomyShopGuiLivePricer {
    private EconomyShopGuiLivePricer() {
    }

    record ApplyStats(int updated, int missing) {
    }

    static ApplyStats applySectionPrices(
            String sectionName,
            List<EconomyShopGuiYamlWriter.PriceUpdate> updates,
            Logger logger
    ) {
        if (updates == null || updates.isEmpty()) {
            return new ApplyStats(0, 0);
        }

        ShopSection section;
        try {
            section = EconomyShopGUIHook.getShopSection(sectionName);
        } catch (Throwable ex) {
            logger.log(Level.WARNING, "EconomyShopGUI getShopSection(" + sectionName + ") failed", ex);
            return new ApplyStats(0, updates.size());
        }
        if (section == null) {
            logger.warning("EconomyShopGUI section not loaded: " + sectionName);
            return new ApplyStats(0, updates.size());
        }

        int updated = 0;
        int missing = 0;
        for (EconomyShopGuiYamlWriter.PriceUpdate update : updates) {
            if (applyOne(section, sectionName, update, logger)) {
                updated++;
            } else {
                missing++;
            }
        }
        return new ApplyStats(updated, missing);
    }

    private static boolean applyOne(
            ShopSection section,
            String sectionName,
            EconomyShopGuiYamlWriter.PriceUpdate update,
            Logger logger
    ) {
        String itemLoc = update.itemLoc();
        if (itemLoc == null || itemLoc.isBlank()) {
            return false;
        }

        ShopItem shopItem = resolveShopItem(section, sectionName, itemLoc);
        if (shopItem == null) {
            logger.fine("EconomyShopGUI live price miss: " + sectionName + " / " + itemLoc);
            return false;
        }

        try {
            setDoubleField(shopItem, "buyPrice", update.buyPrice());
            setDoubleField(shopItem, "sellPrice", update.sellPrice());
            syncBasePriceMaps(section, shopItem, update.buyPrice(), update.sellPrice());
            return true;
        } catch (ReflectiveOperationException ex) {
            logger.log(
                    Level.WARNING,
                    "Failed to set live EconomyShopGUI price for " + sectionName + " / " + itemLoc,
                    ex
            );
            return false;
        }
    }

    private static ShopItem resolveShopItem(ShopSection section, String sectionName, String itemLoc) {
        try {
            ShopItem direct = section.getShopItem(itemLoc);
            if (direct != null) {
                return direct;
            }
        } catch (Throwable ignored) {
            // try path forms below
        }

        String fullPath = sectionName + "." + itemLoc;
        try {
            ShopItem byPath = EconomyShopGUIHook.getShopItem(fullPath);
            if (byPath != null) {
                return byPath;
            }
        } catch (Throwable ignored) {
            // fall through
        }

        try {
            return EconomyShopGUIHook.getShopItem(itemLoc);
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static void setDoubleField(Object target, String fieldName, double value)
            throws ReflectiveOperationException {
        Field field = findField(target.getClass(), fieldName);
        field.setAccessible(true);
        field.setDouble(target, value);
    }

    private static Field findField(Class<?> type, String name) throws NoSuchFieldException {
        Class<?> current = type;
        while (current != null) {
            try {
                return current.getDeclaredField(name);
            } catch (NoSuchFieldException ignored) {
                current = current.getSuperclass();
            }
        }
        throw new NoSuchFieldException(name);
    }

    /**
     * Keep CreateItem base-price maps in sync (used by some price lookups).
     */
    private static void syncBasePriceMaps(ShopSection section, ShopItem shopItem, double buy, double sell) {
        String itemPath;
        try {
            itemPath = shopItem.getItemPath();
        } catch (Throwable ex) {
            return;
        }
        if (itemPath == null || itemPath.isBlank()) {
            return;
        }

        try {
            Method addBuy = section.getClass().getMethod("addNewBuyPrice", String.class, Double.class);
            Method addSell = section.getClass().getMethod("addNewSellPrice", String.class, Double.class);
            addBuy.invoke(section, itemPath, buy);
            addSell.invoke(section, itemPath, sell);
        } catch (Throwable ignored) {
            // optional cache; ShopItem fields are authoritative for getBuyPrice/getSellPrice
        }
    }
}
