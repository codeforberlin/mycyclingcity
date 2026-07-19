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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class EconomyShopGuiApplier {
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
        int matched = 0;
        int missing = 0;
        int catalogItems = 0;

        for (JsonElement categoryElement : categories) {
            if (!categoryElement.isJsonObject()) {
                continue;
            }
            JsonObject category = categoryElement.getAsJsonObject();
            if (!category.has("section") || !category.has("items")) {
                continue;
            }

            String section = category.get("section").getAsString();
            JsonArray items = category.getAsJsonArray("items");
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

                String material = normalizeMaterial(item.get("material").getAsString());
                int buyPrice = item.get("buy_price_velos").getAsInt();
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
                        new EconomyShopGuiYamlWriter.PriceUpdate(material, itemLoc, buyPrice, displayName)
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

        if (yamlUpdated > 0 && config.esguiReloadAfterSync()) {
            try {
                if (!EconomyShopGuiReloader.reload(logger, config.esguiReloadCycleFallback())) {
                    logger.warning(
                            "EconomyShopGUI YAML prices were saved, but reload failed — "
                                    + "run /sreload or /mccbridge esguireload"
                    );
                }
            } catch (Throwable ex) {
                logger.log(Level.WARNING, "EconomyShopGUI reload failed after YAML sync", ex);
            }
        }

        if (matched > 0 && yamlUpdated == 0) {
            return ApplyResult.failed("EconomyShopGUI prices could not be written to shop YAML files");
        }

        logger.info(
                "EconomyShopGUI sync applied: matched="
                        + matched
                        + " yaml_updated="
                        + yamlUpdated
                        + " yaml_skipped="
                        + yamlSkipped
                        + " missing="
                        + missing
        );
        return ApplyResult.ok(yamlUpdated, 0, missing);
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
                            + " Preise, "
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
