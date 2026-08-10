package de.sailab.mycyclingcity.mccbridge.shop;

import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.plugin.Plugin;
import org.yaml.snakeyaml.Yaml;

import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.logging.Logger;

public final class EconomyShopGuiReloader {
    private static final List<String> RELOAD_COMMANDS = List.of(
            "sreload",
            "economyshopgui:sreload",
            "eshop reload",
            "editshop reload",
            "economyshopgui reload"
    );

    private static final List<String> RELOAD_METHOD_NAMES = List.of(
            "reload",
            "onreload",
            "loadshops",
            "reloadshops",
            "loadsections",
            "reloadsections",
            "loadconfigs",
            "reloadconfigs",
            "loadfiles",
            "reloadfiles"
    );

    private EconomyShopGuiReloader() {
    }

    /**
     * Soft reload helpers for diagnostics / manual {@code /mccbridge esguireload}.
     *
     * <p><strong>Do not</strong> disable/enable EconomyShopGUI on Paper — that corrupts the
     * plugin classloader ("zip file error") until a full server restart. Catalog sync applies
     * live prices via {@link EconomyShopGuiLivePricer} instead.
     *
     * @param allowPluginCycle ignored (kept for call-site compatibility); cycle is never used
     */
    public static boolean reload(Logger logger, boolean allowPluginCycle) {
        Plugin plugin = resolveEconomyShopGuiPlugin();
        if (plugin == null) {
            logger.warning(
                    "EconomyShopGUI is not enabled. Shop YAML files were updated on disk, "
                            + "but ingame prices will not refresh until the plugin loads."
            );
            logStartupHints(logger);
            return false;
        }

        if (allowPluginCycle) {
            logger.info(
                    "EconomyShopGUI plugin disable/enable is disabled on Paper "
                            + "(breaks classloader); using soft reload only"
            );
        }

        ConsoleCommandSender console = Bukkit.getConsoleSender();

        for (String commandLine : RELOAD_COMMANDS) {
            if (runCommandLine(console, commandLine, logger)) {
                return true;
            }
        }

        if (reloadViaPluginMethods(plugin, console, logger)) {
            return true;
        }

        logger.warning(
                "EconomyShopGUI soft reload failed. Live price sync does not need this; "
                        + "if /shop is broken, restart Paper."
        );
        logStartupHints(logger);
        return false;
    }

    public static void logDiagnostics(Logger logger) {
        Plugin plugin = resolveEconomyShopGuiPlugin();
        if (plugin == null) {
            logger.info("EconomyShopGUI diagnostics: plugin not enabled");
            logStartupHints(logger);
            return;
        }

        logger.info(
                "EconomyShopGUI diagnostics: plugin="
                        + plugin.getName()
                        + " enabled="
                        + plugin.isEnabled()
                        + " version="
                        + plugin.getPluginMeta().getVersion()
        );

        List<String> available = new ArrayList<>();
        for (String commandLine : RELOAD_COMMANDS) {
            if (isCommandRegistered(commandLine)) {
                available.add("/" + commandLine);
            }
        }
        logger.info(
                "EconomyShopGUI diagnostics: reload strategy=live ShopItem fields "
                        + "(no plugin cycle); soft commands available="
                        + (available.isEmpty() ? "none" : String.join(", ", available))
        );
        logStartupHints(logger);
    }

    private static void logStartupHints(Logger logger) {
        if (isSreloadDisabledInConfig()) {
            logger.warning(
                    "EconomyShopGUI config has commands.sreload=false — set it to true in "
                            + "plugins/EconomyShopGUI/config.yml"
            );
        }
    }

    private static boolean isSreloadDisabledInConfig() {
        for (String pluginFolder : List.of("EconomyShopGUI", "EconomyShopGUI-Premium")) {
            Path configFile = Bukkit.getPluginsFolder()
                    .toPath()
                    .resolve(pluginFolder)
                    .resolve("config.yml");
            if (!Files.isRegularFile(configFile)) {
                continue;
            }
            try (InputStream input = Files.newInputStream(configFile)) {
                Yaml yaml = new Yaml();
                Object loaded = yaml.load(input);
                if (!(loaded instanceof Map<?, ?> root)) {
                    continue;
                }
                Object commandsObject = root.get("commands");
                if (!(commandsObject instanceof Map<?, ?> commands)) {
                    continue;
                }
                Object sreload = commands.get("sreload");
                return Boolean.FALSE.equals(sreload) || "false".equalsIgnoreCase(String.valueOf(sreload));
            } catch (IOException ex) {
                Bukkit.getLogger().fine("Could not read EconomyShopGUI config.yml: " + ex.getMessage());
            }
        }
        return false;
    }

    private static boolean reloadViaPluginMethods(Plugin plugin, CommandSender sender, Logger logger) {
        Set<Integer> visited = new HashSet<>();
        return invokeReloadMethods(plugin, sender, logger, visited);
    }

    private static boolean invokeReloadMethods(
            Object target,
            CommandSender sender,
            Logger logger,
            Set<Integer> visited
    ) {
        if (!visited.add(System.identityHashCode(target))) {
            return false;
        }

        boolean reloaded = false;
        try {
            for (Method method : target.getClass().getMethods()) {
                if (!isReloadMethodName(method.getName())) {
                    continue;
                }
                if (tryInvokeReload(method, target, sender, logger)) {
                    reloaded = true;
                }
            }
        } catch (LinkageError ex) {
            logger.fine("EconomyShopGUI reload reflection skipped: " + ex.getMessage());
        }
        return reloaded;
    }

    private static boolean runCommandLine(ConsoleCommandSender console, String commandLine, Logger logger) {
        if (!isCommandRegistered(commandLine)) {
            return false;
        }

        String[] parts = commandLine.split(" ");
        String label = parts[0];
        String[] args = parts.length > 1 ? Arrays.copyOfRange(parts, 1, parts.length) : new String[0];

        Command command = Bukkit.getPluginCommand(stripNamespace(label));
        if (command == null) {
            command = Bukkit.getServer().getCommandMap().getCommand(stripNamespace(label));
        }
        if (command == null) {
            return false;
        }

        try {
            command.execute(console, label, args);
            logger.info("EconomyShopGUI soft reload triggered via /" + commandLine);
            return true;
        } catch (Exception ex) {
            logger.fine("EconomyShopGUI reload via /" + commandLine + " failed: " + ex.getMessage());
            return false;
        }
    }

    private static boolean isCommandRegistered(String commandLine) {
        String label = stripNamespace(commandLine.split(" ")[0]);
        return Bukkit.getPluginCommand(label) != null || Bukkit.getServer().getCommandMap().getCommand(label) != null;
    }

    private static boolean tryInvokeReload(Method method, Object target, CommandSender sender, Logger logger) {
        try {
            Class<?>[] parameterTypes = method.getParameterTypes();
            if (parameterTypes.length == 1 && CommandSender.class.isAssignableFrom(parameterTypes[0])) {
                method.invoke(target, sender);
                logger.info("EconomyShopGUI reload triggered via " + describeMethod(method));
                return true;
            }
            if (parameterTypes.length == 0) {
                method.invoke(target);
                logger.info("EconomyShopGUI reload triggered via " + describeMethod(method));
                return true;
            }
        } catch (ReflectiveOperationException | LinkageError ex) {
            logger.fine("EconomyShopGUI reload via " + describeMethod(method) + " failed: " + ex.getMessage());
        }
        return false;
    }

    private static String describeMethod(Method method) {
        return method.getDeclaringClass().getSimpleName() + "." + method.getName() + "()";
    }

    private static boolean isReloadMethodName(String name) {
        return RELOAD_METHOD_NAMES.contains(name.toLowerCase(Locale.ROOT));
    }

    private static Plugin resolveEconomyShopGuiPlugin() {
        Plugin plugin = Bukkit.getPluginManager().getPlugin("EconomyShopGUI");
        if (plugin != null && plugin.isEnabled()) {
            return plugin;
        }
        plugin = Bukkit.getPluginManager().getPlugin("EconomyShopGUI-Premium");
        if (plugin != null && plugin.isEnabled()) {
            return plugin;
        }
        return null;
    }

    private static String stripNamespace(String label) {
        int separator = label.indexOf(':');
        return separator >= 0 ? label.substring(separator + 1) : label;
    }
}
