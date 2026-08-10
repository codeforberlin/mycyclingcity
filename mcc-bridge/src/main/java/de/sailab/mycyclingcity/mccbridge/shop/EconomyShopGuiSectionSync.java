package de.sailab.mycyclingcity.mccbridge.shop;

import org.bukkit.Bukkit;
import org.bukkit.plugin.Plugin;

import java.io.IOException;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Syncs MCC catalog category {@code enabled} → EconomyShopGUI section {@code enable}.
 */
final class EconomyShopGuiSectionSync {
    private static final Pattern ENABLE_LINE = Pattern.compile(
            "^(?<indent>\\s*)enable:\\s*(?<value>\\S+)\\s*$"
    );

    private EconomyShopGuiSectionSync() {
    }

    record ApplyStats(int updated, int missing, boolean itemsReloaded) {
    }

    static ApplyStats applyCategoryEnabled(String section, boolean enabled, Logger logger) {
        Boolean currentYaml = readEnableFromSectionFile(section);
        if (currentYaml != null && currentYaml == enabled) {
            // Keep ConfigManager in sync without counting as a change.
            setEnableViaConfigManager(section, enabled, logger);
            return new ApplyStats(0, 0, false);
        }

        boolean apiOk = setEnableViaConfigManager(section, enabled, logger);
        boolean yamlOk = writeEnableInSectionFile(section, enabled, logger);
        if (yamlOk && !apiOk) {
            // Memory still had the old flag — force re-read from the file we just wrote.
            reloadSectionFromDisk(section, logger);
        }
        if (!yamlOk && !apiOk) {
            return new ApplyStats(0, 1, false);
        }
        return new ApplyStats(1, 0, false);
    }

    private static Boolean readEnableFromSectionFile(String section) {
        Path sectionFile = EconomyShopGuiFiles.resolveSectionFile(section);
        if (sectionFile == null) {
            return null;
        }
        try {
            for (String line : Files.readAllLines(sectionFile)) {
                Matcher matcher = ENABLE_LINE.matcher(line);
                if (matcher.matches()) {
                    return Boolean.parseBoolean(matcher.group("value"));
                }
            }
        } catch (IOException ignored) {
            return null;
        }
        return null;
    }

    static boolean reloadSectionFromDisk(String section, Logger logger) {
        try {
            Class<?> configManager = Class.forName("me.gypopo.economyshopgui.files.ConfigManager");
            Method getSection = configManager.getMethod("getSection", String.class);
            Object config = getSection.invoke(null, section);
            if (config == null) {
                Method getSections = configManager.getMethod("getSections");
                @SuppressWarnings("unchecked")
                java.util.Set<String> keys = (java.util.Set<String>) getSections.invoke(null);
                if (keys != null) {
                    for (String key : keys) {
                        if (key != null && key.equalsIgnoreCase(section)) {
                            config = getSection.invoke(null, key);
                            break;
                        }
                    }
                }
            }
            if (config == null) {
                return false;
            }
            Method reload = config.getClass().getMethod("reload");
            reload.invoke(config);
            return true;
        } catch (ReflectiveOperationException | LinkageError | ClassCastException ex) {
            logger.log(Level.FINE, "EconomyShopGUI section Config.reload skipped for " + section, ex);
            return false;
        }
    }

    static boolean reloadShopFromDisk(String section, Logger logger) {
        try {
            Class<?> configManager = Class.forName("me.gypopo.economyshopgui.files.ConfigManager");
            Method getShop = configManager.getMethod("getShop", String.class);
            Object config = getShop.invoke(null, section);
            if (config == null) {
                Method getShops = configManager.getMethod("getShops");
                @SuppressWarnings("unchecked")
                java.util.Set<String> keys = (java.util.Set<String>) getShops.invoke(null);
                if (keys != null) {
                    for (String key : keys) {
                        if (key != null && key.equalsIgnoreCase(section)) {
                            config = getShop.invoke(null, key);
                            break;
                        }
                    }
                }
            }
            if (config == null) {
                return false;
            }
            Method reload = config.getClass().getMethod("reload");
            reload.invoke(config);
            return true;
        } catch (ReflectiveOperationException | LinkageError | ClassCastException ex) {
            logger.log(Level.FINE, "EconomyShopGUI shop Config.reload skipped for " + section, ex);
            return false;
        }
    }

    static boolean reloadShopItems(Logger logger) {
        Plugin plugin = Bukkit.getPluginManager().getPlugin("EconomyShopGUI");
        if (plugin == null || !plugin.isEnabled()) {
            plugin = Bukkit.getPluginManager().getPlugin("EconomyShopGUI-Premium");
        }
        if (plugin == null || !plugin.isEnabled()) {
            return false;
        }
        try {
            Field field = plugin.getClass().getField("startupReload");
            Object startupReload = field.get(plugin);
            if (startupReload == null) {
                return false;
            }
            Method loadItems = startupReload.getClass().getMethod("loadItems");
            loadItems.invoke(startupReload);
            logger.info("EconomyShopGUI shop items reloaded after section enable sync");
            return true;
        } catch (ReflectiveOperationException | LinkageError ex) {
            logger.log(Level.WARNING, "EconomyShopGUI loadItems after section sync failed", ex);
            return false;
        }
    }

    private static boolean writeEnableInSectionFile(String section, boolean enabled, Logger logger) {
        Path sectionFile = EconomyShopGuiFiles.resolveSectionFile(section);
        if (sectionFile == null) {
            logger.warning("EconomyShopGUI section file not found for: " + section);
            return false;
        }
        List<String> lines;
        try {
            lines = new ArrayList<>(Files.readAllLines(sectionFile));
        } catch (IOException ex) {
            logger.warning("Failed to read section file " + sectionFile + ": " + ex.getMessage());
            return false;
        }

        boolean found = false;
        for (int i = 0; i < lines.size(); i++) {
            Matcher matcher = ENABLE_LINE.matcher(lines.get(i));
            if (matcher.matches()) {
                lines.set(i, matcher.group("indent") + "enable: " + enabled);
                found = true;
                break;
            }
        }
        if (!found) {
            lines.add(0, "enable: " + enabled);
        }

        try {
            Path backup = sectionFile.resolveSibling(sectionFile.getFileName() + ".bak");
            Files.copy(sectionFile, backup, StandardCopyOption.REPLACE_EXISTING);
            Files.write(sectionFile, lines);
            logger.info(
                    "EconomyShopGUI section "
                            + section
                            + " enable="
                            + enabled
                            + " written to "
                            + sectionFile.getFileName()
            );
            return true;
        } catch (IOException ex) {
            logger.warning("Failed to write section file " + sectionFile + ": " + ex.getMessage());
            return false;
        }
    }

    private static boolean setEnableViaConfigManager(String section, boolean enabled, Logger logger) {
        try {
            Class<?> configManager = Class.forName("me.gypopo.economyshopgui.files.ConfigManager");
            Method getSection = configManager.getMethod("getSection", String.class);
            Object config = getSection.invoke(null, section);
            if (config == null) {
                // Case-insensitive lookup across known section keys.
                Method getSections = configManager.getMethod("getSections");
                @SuppressWarnings("unchecked")
                java.util.Set<String> keys = (java.util.Set<String>) getSections.invoke(null);
                if (keys != null) {
                    for (String key : keys) {
                        if (key != null && key.equalsIgnoreCase(section)) {
                            config = getSection.invoke(null, key);
                            section = key;
                            break;
                        }
                    }
                }
            }
            if (config == null) {
                logger.fine("EconomyShopGUI ConfigManager has no section '" + section + "'");
                return false;
            }

            Method set = config.getClass().getMethod("set", String.class, Object.class);
            set.invoke(config, "enable", enabled);

            Method saveSection = configManager.getMethod("saveSection", String.class);
            saveSection.invoke(null, section);
            logger.info("EconomyShopGUI ConfigManager section '" + section + "' enable=" + enabled);
            return true;
        } catch (ReflectiveOperationException | LinkageError | ClassCastException ex) {
            logger.log(
                    Level.FINE,
                    "EconomyShopGUI ConfigManager enable sync skipped for " + section,
                    ex
            );
            return false;
        }
    }

    static String normalizeSectionKey(String section) {
        if (section == null) {
            return "";
        }
        String normalized = section.trim().replace("\\", "/");
        if (normalized.toLowerCase(Locale.ROOT).endsWith(".yml")) {
            normalized = normalized.substring(0, normalized.length() - 4);
        }
        int slash = normalized.lastIndexOf('/');
        if (slash >= 0) {
            normalized = normalized.substring(slash + 1);
        }
        return normalized;
    }
}
