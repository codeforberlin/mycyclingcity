package de.sailab.mycyclingcity.mccbridge.shop;

import org.yaml.snakeyaml.Yaml;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.logging.Logger;

final class EconomyShopGuiYamlIndex {
    private EconomyShopGuiYamlIndex() {
    }

    static Map<String, String> loadSectionIndex(String section, Logger logger) {
        Path shopFile = EconomyShopGuiFiles.resolveShopFile(section);
        if (shopFile == null || !Files.isRegularFile(shopFile)) {
            logger.warning("EconomyShopGUI shop file not found for section: " + section);
            return Map.of();
        }

        try (InputStream input = Files.newInputStream(shopFile)) {
            Yaml yaml = new Yaml();
            Object loaded = yaml.load(input);
            Map<String, String> index = parseShopYaml(loaded);
            logger.info(
                    "EconomyShopGUI YAML index for '"
                            + section
                            + "' loaded "
                            + index.size()
                            + " materials from "
                            + shopFile.getFileName()
            );
            return index;
        } catch (IOException ex) {
            logger.warning("Failed to read EconomyShopGUI shop file " + shopFile + ": " + ex.getMessage());
            return Map.of();
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, String> parseShopYaml(Object loaded) {
        Map<String, String> index = new HashMap<>();
        if (!(loaded instanceof Map<?, ?> root)) {
            return index;
        }

        Object pagesObject = root.get("pages");
        if (!(pagesObject instanceof Map<?, ?> pages)) {
            return index;
        }

        for (Map.Entry<?, ?> pageEntry : pages.entrySet()) {
            String pageKey = String.valueOf(pageEntry.getKey());
            if (!(pageEntry.getValue() instanceof Map<?, ?> page)) {
                continue;
            }
            Object itemsObject = page.get("items");
            if (!(itemsObject instanceof Map<?, ?> items)) {
                continue;
            }
            for (Map.Entry<?, ?> itemEntry : items.entrySet()) {
                String itemKey = String.valueOf(itemEntry.getKey());
                if (!(itemEntry.getValue() instanceof Map<?, ?> item)) {
                    continue;
                }
                Object materialObject = item.get("material");
                if (materialObject == null) {
                    continue;
                }
                String material = normalizeMaterial(String.valueOf(materialObject));
                if (material.isBlank()) {
                    continue;
                }
                index.putIfAbsent(material, pageKey + ".items." + itemKey);
            }
        }
        return index;
    }

    private static String normalizeMaterial(String material) {
        String normalized = material.trim().toUpperCase(Locale.ROOT);
        if (normalized.startsWith("MINECRAFT:")) {
            normalized = normalized.substring("MINECRAFT:".length());
        }
        return normalized.replace('-', '_');
    }
}
