package de.sailab.mycyclingcity.mccbridge.shop;

import org.bukkit.Bukkit;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.stream.Stream;

final class EconomyShopGuiFiles {
    private static final String[] PLUGIN_FOLDERS = {"EconomyShopGUI", "EconomyShopGUI-Premium"};

    private EconomyShopGuiFiles() {
    }

    static Path resolveShopFile(String section) {
        String normalized = section.replace("\\", "/");
        if (normalized.toLowerCase(Locale.ROOT).endsWith(".yml")) {
            normalized = normalized.substring(0, normalized.length() - 4);
        } else if (normalized.toLowerCase(Locale.ROOT).endsWith(".yaml")) {
            normalized = normalized.substring(0, normalized.length() - 5);
        }

        String expectedRelPath = normalized + ".yml";
        for (String pluginFolder : PLUGIN_FOLDERS) {
            Path shopsDir = Bukkit.getPluginsFolder()
                    .toPath()
                    .resolve(pluginFolder)
                    .resolve("shops");
            if (!Files.isDirectory(shopsDir)) {
                continue;
            }

            Path exact = shopsDir.resolve(expectedRelPath);
            if (Files.isRegularFile(exact)) {
                return exact;
            }

            Path nested = findYamlRelativeTo(shopsDir, expectedRelPath);
            if (nested != null) {
                return nested;
            }

            String basename = expectedRelPath.contains("/")
                    ? expectedRelPath.substring(expectedRelPath.lastIndexOf('/') + 1)
                    : expectedRelPath;
            Path flatMatch = findYamlRelativeTo(shopsDir, basename);
            if (flatMatch != null) {
                return flatMatch;
            }

            if (!normalized.contains("/")) {
                Path stemMatch = findByFileStem(shopsDir, normalized);
                if (stemMatch != null) {
                    return stemMatch;
                }
            }
        }
        return null;
    }

    private static Path findByFileStem(Path root, String stem) {
        String stemLower = stem.toLowerCase(Locale.ROOT);
        try (Stream<Path> walk = Files.walk(root)) {
            return walk
                    .filter(Files::isRegularFile)
                    .filter(path -> {
                        String fileName = path.getFileName().toString().toLowerCase(Locale.ROOT);
                        if (fileName.endsWith(".yaml")) {
                            fileName = fileName.substring(0, fileName.length() - 5);
                        } else if (fileName.endsWith(".yml")) {
                            fileName = fileName.substring(0, fileName.length() - 4);
                        }
                        return fileName.equals(stemLower);
                    })
                    .findFirst()
                    .orElse(null);
        } catch (IOException ex) {
            Bukkit.getLogger().fine("Could not scan EconomyShopGUI shops dir: " + ex.getMessage());
            return null;
        }
    }

    private static Path findYamlRelativeTo(Path root, String expectedRelPath) {
        String expectedLower = expectedRelPath.replace("\\", "/").toLowerCase(Locale.ROOT);
        try (Stream<Path> walk = Files.walk(root)) {
            return walk
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".yml")
                            || path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".yaml"))
                    .filter(path -> root.relativize(path).toString().replace("\\", "/")
                            .equalsIgnoreCase(expectedRelPath))
                    .findFirst()
                    .orElse(null);
        } catch (IOException ex) {
            Bukkit.getLogger().fine("Could not scan EconomyShopGUI shops dir: " + ex.getMessage());
            return null;
        }
    }
}
