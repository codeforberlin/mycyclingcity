package de.sailab.mycyclingcity.mccbridge.shop;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import de.sailab.mycyclingcity.mccbridge.MccBridgeConfig;
import org.bukkit.Bukkit;
import org.bukkit.plugin.Plugin;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class EconomyShopGuiApplier {
    /** EconomyShopGUI: negative buy/sell → item cannot be bought/sold. */
    private static final int DISABLED_ITEM_PRICE = -1;

    private final Plugin plugin;
    private final MccBridgeConfig config;
    private final Logger logger;

    public EconomyShopGuiApplier(Plugin plugin, MccBridgeConfig config) {
        this.plugin = plugin;
        this.config = config;
        this.logger = plugin.getLogger();
    }

    public ApplyResult apply(JsonObject catalog) {
        if (!isEconomyShopGuiAvailable()) {
            return ApplyResult.failed("EconomyShopGUI ist nicht installiert");
        }

        CountDownLatch latch = new CountDownLatch(1);
        ApplyResult[] holder = new ApplyResult[1];
        Bukkit.getScheduler().runTask(plugin, () -> {
            try {
                holder[0] = applyOnMainThread(catalog);
            } catch (Throwable ex) {
                logger.log(Level.WARNING, "EconomyShopGUI sync failed", ex);
                holder[0] = ApplyResult.failed("EconomyShopGUI sync failed: " + ex.getMessage());
            } finally {
                latch.countDown();
            }
        });

        try {
            if (!latch.await(120, TimeUnit.SECONDS)) {
                return ApplyResult.failed("Timeout while applying EconomyShopGUI prices");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ApplyResult.failed("Interrupted while applying EconomyShopGUI prices");
        }

        return holder[0] != null ? holder[0] : ApplyResult.failed("EconomyShopGUI sync returned no result");
    }

    private ApplyResult applyOnMainThread(JsonObject catalog) {
        JsonArray categories = catalog != null && catalog.has("categories")
                ? catalog.getAsJsonArray("categories")
                : new JsonArray();

        Map<Path, List<EconomyShopGuiYamlWriter.PriceUpdate>> updatesByFile = new HashMap<>();
        List<String> sectionsToEnable = new ArrayList<>();
        List<Boolean> sectionEnabledFlags = new ArrayList<>();
        int matched = 0;
        int missing = 0;
        int catalogItems = 0;

        for (JsonElement categoryElement : categories) {
            if (!categoryElement.isJsonObject()) {
                continue;
            }
            JsonObject category = categoryElement.getAsJsonObject();
            if (!category.has("section")) {
                continue;
            }

            String section = category.get("section").getAsString();
            boolean categoryEnabled = !category.has("enabled") || category.get("enabled").getAsBoolean();
            sectionsToEnable.add(section);
            sectionEnabledFlags.add(categoryEnabled);

            JsonArray items = category.has("items") ? category.getAsJsonArray("items") : new JsonArray();
            if (!categoryEnabled) {
                // Section will be hidden — keep existing shop YAML prices for later re-enable.
                continue;
            }

            Map<String, String> materialToItemLoc = EconomyShopGuiYamlIndex.loadSectionIndex(section, logger);
            Path shopFile = EconomyShopGuiFiles.resolveShopFile(section);
            if (shopFile == null) {
                if (!items.isEmpty()) {
                    logger.warning(
                            "EconomyShopGUI shop file not found for section: "
                                    + section
                                    + " ("
                                    + items.size()
                                    + " MCC items skipped)"
                    );
                }
                missing += items.size();
                continue;
            }

            List<EconomyShopGuiYamlWriter.PriceUpdate> sectionUpdates = updatesByFile.computeIfAbsent(
                    shopFile,
                    ignored -> new ArrayList<>()
            );

            for (JsonElement itemElement : items) {
                if (!itemElement.isJsonObject()) {
                    continue;
                }
                JsonObject item = itemElement.getAsJsonObject();
                if (!item.has("material") || !item.has("buy_price_velos")) {
                    continue;
                }
                catalogItems++;

                boolean itemEnabled = !item.has("enabled") || item.get("enabled").getAsBoolean();
                String material = normalizeMaterial(item.get("material").getAsString());
                int buyPrice = itemEnabled ? item.get("buy_price_velos").getAsInt() : DISABLED_ITEM_PRICE;
                int sellPrice = itemEnabled
                        ? (item.has("sell_price_velos")
                                ? item.get("sell_price_velos").getAsInt()
                                : buyPrice)
                        : DISABLED_ITEM_PRICE;
                String itemLoc = item.has("esgui_item_loc") ? item.get("esgui_item_loc").getAsString() : "";
                if (itemLoc == null || itemLoc.isBlank()) {
                    itemLoc = materialToItemLoc.get(material);
                }

                if (itemLoc == null || itemLoc.isBlank()) {
                    if (config.esguiAddMissingItems()) {
                        logger.warning(
                                "EconomyShopGUI additem via command is not implemented; missing item "
                                        + material
                                        + " in section "
                                        + section
                        );
                    }
                    missing++;
                    continue;
                }

                String displayName = item.has("display_name") ? item.get("display_name").getAsString() : "";
                sectionUpdates.add(
                        new EconomyShopGuiYamlWriter.PriceUpdate(
                                section, material, itemLoc, buyPrice, sellPrice, displayName
                        )
                );
                matched++;
            }
        }

        logger.info(
                "EconomyShopGUI catalog parsed: categories="
                        + categories.size()
                        + " items="
                        + catalogItems
                        + " matched="
                        + matched
                        + " missing="
                        + missing
        );

        int yamlUpdated = 0;
        int yamlSkipped = 0;
        for (Map.Entry<Path, List<EconomyShopGuiYamlWriter.PriceUpdate>> entry : updatesByFile.entrySet()) {
            if (entry.getValue().isEmpty()) {
                continue;
            }
            EconomyShopGuiYamlWriter.WriteResult result = EconomyShopGuiYamlWriter.applyPriceUpdates(
                    entry.getKey(),
                    entry.getValue(),
                    logger
            );
            yamlUpdated += result.updated();
            yamlSkipped += result.skipped();
            logger.info(
                    "EconomyShopGUI YAML updated "
                            + result.updated()
                            + " prices in "
                            + entry.getKey().getFileName()
                            + (result.skipped() > 0 ? " (" + result.skipped() + " skipped)" : "")
            );
        }

        int sectionsUpdated = 0;
        int sectionsMissing = 0;
        Map<String, Boolean> sectionEnabled = new HashMap<>();
        for (int i = 0; i < sectionsToEnable.size(); i++) {
            sectionEnabled.put(sectionsToEnable.get(i), sectionEnabledFlags.get(i));
        }

        // Park/restore section files + parent linkers first, then write enable flags
        // (enable writes need the live YAML path after restore).
        EconomyShopGuiSectionLinkSync.ApplyStats linkerStats =
                EconomyShopGuiSectionLinkSync.syncLinkerVisibility(sectionEnabled, logger);

        for (int i = 0; i < sectionsToEnable.size(); i++) {
            String section = sectionsToEnable.get(i);
            boolean enabled = sectionEnabledFlags.get(i);
            EconomyShopGuiSectionSync.ApplyStats sectionStats =
                    EconomyShopGuiSectionSync.applyCategoryEnabled(section, enabled, logger);
            sectionsUpdated += sectionStats.updated();
            sectionsMissing += sectionStats.missing();
        }

        // loadItems() alone does not re-add previously disabled sections; /sreload does.
        // After section/linker changes, soft-reload ESGUI then patch live prices again.
        boolean sectionLayoutChanged = sectionsUpdated > 0 || linkerStats.linkersUpdated() > 0
                || linkerStats.filesUpdated() > 0;
        if (sectionLayoutChanged) {
            Set<String> reloadSections = new java.util.LinkedHashSet<>(sectionsToEnable);
            reloadSections.addAll(linkerStats.parentShops());
            for (String section : reloadSections) {
                EconomyShopGuiSectionSync.reloadShopFromDisk(section, logger);
                EconomyShopGuiSectionSync.reloadSectionFromDisk(section, logger);
            }
            boolean sreloadOk = EconomyShopGuiReloader.reload(logger, false);
            if (!sreloadOk) {
                EconomyShopGuiSectionSync.reloadShopItems(logger);
            }
        } else if (yamlUpdated > 0) {
            for (String section : sectionsToEnable) {
                EconomyShopGuiSectionSync.reloadShopFromDisk(section, logger);
            }
            EconomyShopGuiSectionSync.reloadShopItems(logger);
        }

        int liveUpdated = 0;
        int liveMissing = 0;
        Map<String, List<EconomyShopGuiYamlWriter.PriceUpdate>> bySection = new HashMap<>();
        for (List<EconomyShopGuiYamlWriter.PriceUpdate> fileUpdates : updatesByFile.values()) {
            for (EconomyShopGuiYamlWriter.PriceUpdate update : fileUpdates) {
                if (update.section() == null || update.section().isBlank()) {
                    continue;
                }
                bySection.computeIfAbsent(update.section(), ignored -> new ArrayList<>()).add(update);
            }
        }
        for (Map.Entry<String, List<EconomyShopGuiYamlWriter.PriceUpdate>> entry : bySection.entrySet()) {
            EconomyShopGuiLivePricer.ApplyStats live = EconomyShopGuiLivePricer.applySectionPrices(
                    entry.getKey(),
                    entry.getValue(),
                    logger
            );
            liveUpdated += live.updated();
            liveMissing += live.missing();
        }
        if (liveUpdated > 0 || liveMissing > 0) {
            logger.info(
                    "EconomyShopGUI live prices applied: updated="
                            + liveUpdated
                            + " missing="
                            + liveMissing
            );
        }

        if (matched > 0 && yamlUpdated == 0 && liveUpdated == 0 && sectionsUpdated == 0) {
            return ApplyResult.failed("EconomyShopGUI prices could not be written to shop YAML files");
        }

        logger.info(
                "EconomyShopGUI sync applied: matched="
                        + matched
                        + " yaml_updated="
                        + yamlUpdated
                        + " yaml_skipped="
                        + yamlSkipped
                        + " live_updated="
                        + liveUpdated
                        + " sections_enable_updated="
                        + sectionsUpdated
                        + " sections_missing="
                        + sectionsMissing
                        + " linkers_updated="
                        + linkerStats.linkersUpdated()
                        + " missing="
                        + missing
        );
        int totalUpdated = Math.max(yamlUpdated, liveUpdated)
                + sectionsUpdated
                + linkerStats.linkersUpdated();
        return ApplyResult.ok(totalUpdated, 0, missing + sectionsMissing);
    }

    public boolean isEconomyShopGuiAvailable() {
        return Bukkit.getPluginManager().getPlugin("EconomyShopGUI") != null
                || Bukkit.getPluginManager().getPlugin("EconomyShopGUI-Premium") != null;
    }

    private static String normalizeMaterial(String material) {
        String normalized = material.trim().toUpperCase(Locale.ROOT);
        if (normalized.startsWith("MINECRAFT:")) {
            normalized = normalized.substring("MINECRAFT:".length());
        }
        return normalized.replace('-', '_');
    }

    public record ApplyResult(boolean success, String message, int updated, int added, int missing) {
        public static ApplyResult ok(int updated, int added, int missing) {
            return new ApplyResult(
                    true,
                    "EconomyShopGUI aktualisiert: "
                            + updated
                            + " Änderungen, "
                            + added
                            + " neu, "
                            + missing
                            + " nicht gefunden",
                    updated,
                    added,
                    missing
            );
        }

        public static ApplyResult failed(String message) {
            return new ApplyResult(false, message, 0, 0, 0);
        }
    }
}
