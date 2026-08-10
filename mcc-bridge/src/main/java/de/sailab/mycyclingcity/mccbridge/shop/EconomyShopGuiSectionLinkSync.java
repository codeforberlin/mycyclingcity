package de.sailab.mycyclingcity.mccbridge.shop;

import org.bukkit.Bukkit;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.logging.Logger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Removes/restores parent-shop linker tiles for disabled EconomyShopGUI subsections.
 *
 * <p>ESGUI item {@code hidden:} does not hide subsection linkers. Disabled linkers are
 * removed from the parent shop YAML and stored under
 * {@code plugins/MCC-Bridge/disabled-linkers/}. The matching section/shop YAML files are
 * renamed to {@code *.mcc-disabled} so ESGUI cannot surface them.
 */
final class EconomyShopGuiSectionLinkSync {
    private static final String DISABLED_SUFFIX = ".mcc-disabled";
    private static final String STASH_DIR = "disabled-linkers";

    private static final Pattern KEY_LINE = Pattern.compile(
            "^(?<indent>\\s*)(?<quote>['\"]?)(?<key>[^'\":]+)\\2:\\s*$"
    );
    private static final Pattern SECTION_PROP = Pattern.compile(
            "^(?<indent>\\s*)section:\\s*(?<value>\\S+)\\s*$"
    );
    private static final Pattern HIDDEN_PROP = Pattern.compile(
            "^(?<indent>\\s*)hidden:\\s*(?<value>\\S+)\\s*$"
    );

    private EconomyShopGuiSectionLinkSync() {
    }

    record ApplyStats(int filesUpdated, int linkersUpdated, Set<String> parentShops) {
    }

    static ApplyStats syncLinkerVisibility(Map<String, Boolean> sectionEnabled, Logger logger) {
        if (sectionEnabled == null || sectionEnabled.isEmpty()) {
            return new ApplyStats(0, 0, Set.of());
        }

        Map<String, Boolean> normalized = normalizeKeys(sectionEnabled);
        int filesUpdated = 0;
        int linkersUpdated = 0;
        Set<String> parentShops = new HashSet<>();

        // Park / restore section+shop YAML files first (canonical ESGUI discovery).
        for (Map.Entry<String, Boolean> entry : normalized.entrySet()) {
            if (entry.getValue()) {
                if (restoreSectionFiles(entry.getKey(), logger)) {
                    filesUpdated++;
                }
            } else if (parkSectionFiles(entry.getKey(), logger)) {
                filesUpdated++;
            }
        }

        for (Path shopFile : EconomyShopGuiFiles.listShopFiles()) {
            // Never treat parked files as live shops.
            if (shopFile.getFileName().toString().endsWith(DISABLED_SUFFIX)) {
                continue;
            }
            int updated = applyToShopFile(shopFile, normalized, logger);
            if (updated > 0) {
                filesUpdated++;
                linkersUpdated += updated;
                String stem = fileStem(shopFile);
                if (!stem.isBlank()) {
                    parentShops.add(stem);
                }
            }
        }

        // Restore linkers whose targets are enabled (stash → parent shop).
        for (Map.Entry<String, Boolean> entry : normalized.entrySet()) {
            if (!entry.getValue()) {
                continue;
            }
            int restored = restoreStashedLinkersForSection(entry.getKey(), logger, parentShops);
            linkersUpdated += restored;
            if (restored > 0) {
                filesUpdated++;
            }
        }

        if (linkersUpdated > 0 || filesUpdated > 0) {
            logger.info(
                    "EconomyShopGUI subsection linkers updated: files="
                            + filesUpdated
                            + " linkers="
                            + linkersUpdated
                            + " parents="
                            + parentShops
            );
        }
        return new ApplyStats(filesUpdated, linkersUpdated, parentShops);
    }

    private static Map<String, Boolean> normalizeKeys(Map<String, Boolean> sectionEnabled) {
        Map<String, Boolean> normalized = new HashMap<>();
        for (Map.Entry<String, Boolean> entry : sectionEnabled.entrySet()) {
            if (entry.getKey() == null || entry.getKey().isBlank()) {
                continue;
            }
            normalized.put(
                    EconomyShopGuiSectionSync.normalizeSectionKey(entry.getKey())
                            .toLowerCase(Locale.ROOT),
                    entry.getValue()
            );
        }
        return normalized;
    }

    private static boolean parkSectionFiles(String section, Logger logger) {
        boolean changed = false;
        Path sectionFile = EconomyShopGuiFiles.resolveSectionFile(section);
        Path shopFile = EconomyShopGuiFiles.resolveShopFile(section);
        changed |= parkFile(sectionFile, logger);
        changed |= parkFile(shopFile, logger);
        // Remove leftover .bak that ESGUI might confuse with live configs.
        changed |= deleteSiblingBak(sectionFile, logger);
        changed |= deleteSiblingBak(shopFile, logger);
        return changed;
    }

    private static boolean restoreSectionFiles(String section, Logger logger) {
        boolean changed = false;
        // Prefer restoring beside known live paths; fall back to scanning.
        changed |= restoreParkedNamed(section, "sections", logger);
        changed |= restoreParkedNamed(section, "shops", logger);
        return changed;
    }

    private static boolean parkFile(Path liveFile, Logger logger) {
        if (liveFile == null || !Files.isRegularFile(liveFile)) {
            return false;
        }
        Path parked = Path.of(liveFile.toString() + DISABLED_SUFFIX);
        try {
            Files.move(liveFile, parked, StandardCopyOption.REPLACE_EXISTING);
            logger.info("EconomyShopGUI parked disabled config: " + liveFile.getFileName());
            return true;
        } catch (IOException ex) {
            logger.warning("Failed to park " + liveFile + ": " + ex.getMessage());
            return false;
        }
    }

    private static boolean deleteSiblingBak(Path liveOrNull, Logger logger) {
        if (liveOrNull == null) {
            return false;
        }
        Path bak = Path.of(liveOrNull.toString() + ".bak");
        Path parkedBak = Path.of(liveOrNull.toString() + DISABLED_SUFFIX + ".bak");
        boolean changed = false;
        for (Path path : List.of(bak, parkedBak)) {
            try {
                if (Files.deleteIfExists(path)) {
                    changed = true;
                    logger.fine("Removed leftover ESGUI bak: " + path.getFileName());
                }
            } catch (IOException ex) {
                logger.fine("Could not delete " + path + ": " + ex.getMessage());
            }
        }
        // Also delete weapons.yml.bak when live was weapons.yml.mcc-disabled path base
        String name = liveOrNull.getFileName().toString();
        if (name.endsWith(".yml")) {
            Path siblingBak = liveOrNull.resolveSibling(name + ".bak");
            try {
                if (Files.deleteIfExists(siblingBak)) {
                    changed = true;
                }
            } catch (IOException ignored) {
                // optional cleanup
            }
        }
        return changed;
    }

    private static boolean restoreParkedNamed(String section, String subDir, Logger logger) {
        String sectionKey = EconomyShopGuiSectionSync.normalizeSectionKey(section);
        for (String pluginFolder : new String[] {"EconomyShopGUI", "EconomyShopGUI-Premium"}) {
            Path root = Bukkit.getPluginsFolder().toPath().resolve(pluginFolder).resolve(subDir);
            if (!Files.isDirectory(root)) {
                continue;
            }
            try (var walk = Files.walk(root)) {
                List<Path> parked = walk
                        .filter(Files::isRegularFile)
                        .filter(path -> {
                            String fileName = path.getFileName().toString();
                            return fileName.equalsIgnoreCase(sectionKey + ".yml" + DISABLED_SUFFIX)
                                    || fileName.equalsIgnoreCase(sectionKey + ".yaml" + DISABLED_SUFFIX);
                        })
                        .toList();
                boolean changed = false;
                for (Path path : parked) {
                    String fileName = path.getFileName().toString();
                    String liveName = fileName.substring(0, fileName.length() - DISABLED_SUFFIX.length());
                    Path live = path.resolveSibling(liveName);
                    try {
                        Files.move(path, live, StandardCopyOption.REPLACE_EXISTING);
                        logger.info("EconomyShopGUI restored config: " + liveName);
                        changed = true;
                    } catch (IOException ex) {
                        logger.warning("Failed to restore " + path + ": " + ex.getMessage());
                    }
                }
                if (changed) {
                    return true;
                }
            } catch (IOException ex) {
                logger.fine("Could not scan " + root + ": " + ex.getMessage());
            }
        }
        return false;
    }

    private static int applyToShopFile(
            Path shopFile,
            Map<String, Boolean> sectionEnabled,
            Logger logger
    ) {
        List<String> lines;
        try {
            lines = new ArrayList<>(Files.readAllLines(shopFile));
        } catch (IOException ex) {
            logger.warning("Failed to read shop file " + shopFile + ": " + ex.getMessage());
            return 0;
        }

        // Drop legacy in-file stash so ESGUI cannot parse it as shop content.
        boolean strippedLegacy = stripLegacyInFileStash(lines);

        List<ActiveLinker> active = findActiveLinkers(lines);
        int updated = 0;
        for (int i = active.size() - 1; i >= 0; i--) {
            ActiveLinker linker = active.get(i);
            Boolean enabled = sectionEnabled.get(linker.targetSection().toLowerCase(Locale.ROOT));
            if (enabled == null || enabled) {
                continue;
            }
            if (stashActiveLinker(shopFile, lines, linker, logger)) {
                updated++;
            }
        }

        if (updated == 0 && !strippedLegacy) {
            return 0;
        }

        try {
            Path backup = shopFile.resolveSibling(shopFile.getFileName() + ".bak");
            Files.copy(shopFile, backup, StandardCopyOption.REPLACE_EXISTING);
            Files.write(shopFile, lines);
            return Math.max(updated, strippedLegacy ? 1 : 0);
        } catch (IOException ex) {
            logger.warning("Failed to write shop file " + shopFile + ": " + ex.getMessage());
            return 0;
        }
    }

    private static boolean stripLegacyInFileStash(List<String> lines) {
        int root = -1;
        for (int i = 0; i < lines.size(); i++) {
            if (lines.get(i).trim().equals("mcc-disabled-linkers:")) {
                root = i;
                break;
            }
        }
        if (root < 0) {
            return false;
        }
        int end = lines.size();
        for (int i = root + 1; i < lines.size(); i++) {
            String line = lines.get(i);
            if (!line.isBlank() && leadingSpaces(line) == 0) {
                end = i;
                break;
            }
        }
        for (int i = end - 1; i >= root; i--) {
            lines.remove(i);
        }
        while (!lines.isEmpty() && lines.get(lines.size() - 1).isBlank()) {
            lines.remove(lines.size() - 1);
        }
        return true;
    }

    private static boolean stashActiveLinker(
            Path shopFile,
            List<String> lines,
            ActiveLinker linker,
            Logger logger
    ) {
        List<String> body = new ArrayList<>();
        for (int i = linker.block().start() + 1; i <= linker.block().endInclusive(); i++) {
            String line = lines.get(i);
            if (HIDDEN_PROP.matcher(line).matches() && leadingSpaces(line) == linker.childIndent()) {
                continue;
            }
            body.add(line);
        }

        Path stashFile = stashPath(fileStem(shopFile), linker.itemKey());
        try {
            Files.createDirectories(stashFile.getParent());
            List<String> stashLines = new ArrayList<>();
            stashLines.add("mcc-page: " + linker.pageKey());
            stashLines.add("mcc-parent: " + fileStem(shopFile));
            stashLines.add("mcc-item: " + linker.itemKey());
            for (String bodyLine : body) {
                int indent = leadingSpaces(bodyLine);
                stashLines.add(bodyLine.substring(indent));
            }
            Files.write(stashFile, stashLines, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            logger.warning("Failed to stash linker " + linker.itemKey() + ": " + ex.getMessage());
            return false;
        }

        for (int i = linker.block().endInclusive(); i >= linker.block().start(); i--) {
            lines.remove(i);
        }
        return true;
    }

    private static int restoreStashedLinkersForSection(
            String section,
            Logger logger,
            Set<String> parentShops
    ) {
        Path stashDir = stashDir();
        if (!Files.isDirectory(stashDir)) {
            return 0;
        }
        int restored = 0;
        try (var list = Files.list(stashDir)) {
            for (Path stashFile : list.filter(Files::isRegularFile).toList()) {
                Map<String, String> meta = readStashMeta(stashFile);
                String target = meta.getOrDefault("section", "").replace("\"", "").replace("'", "");
                if (!target.equalsIgnoreCase(section)) {
                    continue;
                }
                String parent = meta.getOrDefault("mcc-parent", "");
                String itemKey = meta.getOrDefault("mcc-item", fileStem(stashFile));
                String pageKey = meta.getOrDefault("mcc-page", "page1");
                if (parent.isBlank()) {
                    // Filename convention parent__item.yml
                    String name = fileStem(stashFile);
                    int sep = name.indexOf("__");
                    if (sep > 0) {
                        parent = name.substring(0, sep);
                        if (itemKey.isBlank() || itemKey.equals(name)) {
                            itemKey = name.substring(sep + 2);
                        }
                    }
                }
                Path parentShop = EconomyShopGuiFiles.resolveShopFile(parent);
                if (parentShop == null) {
                    logger.warning("Cannot restore linker; parent shop missing: " + parent);
                    continue;
                }
                if (insertLinkerIntoShop(parentShop, pageKey, itemKey, meta, logger)) {
                    Files.deleteIfExists(stashFile);
                    parentShops.add(parent);
                    restored++;
                }
            }
        } catch (IOException ex) {
            logger.warning("Failed scanning linker stash: " + ex.getMessage());
        }
        return restored;
    }

    private static boolean insertLinkerIntoShop(
            Path shopFile,
            String pageKey,
            String itemKey,
            Map<String, String> meta,
            Logger logger
    ) {
        List<String> lines;
        try {
            lines = new ArrayList<>(Files.readAllLines(shopFile));
        } catch (IOException ex) {
            logger.warning("Failed to read " + shopFile + ": " + ex.getMessage());
            return false;
        }

        // Already present?
        for (ActiveLinker existing : findActiveLinkers(lines)) {
            if (existing.itemKey().equals(itemKey)) {
                return false;
            }
        }

        int itemsIndex = findPageItemsIndex(lines, pageKey);
        if (itemsIndex < 0) {
            itemsIndex = findFirstItemsIndex(lines);
        }
        if (itemsIndex < 0) {
            logger.warning("No items: section in " + shopFile.getFileName());
            return false;
        }

        int itemsIndent = leadingSpaces(lines.get(itemsIndex));
        String itemIndent = " ".repeat(itemsIndent + 2);
        String childIndent = " ".repeat(itemsIndent + 4);
        List<String> block = new ArrayList<>();
        block.add(itemIndent + itemKey + ":");
        for (Map.Entry<String, String> entry : meta.entrySet()) {
            String key = entry.getKey();
            if (key.startsWith("mcc-")) {
                continue;
            }
            block.add(childIndent + key + ": " + entry.getValue());
        }
        lines.addAll(itemsIndex + 1, block);
        try {
            Files.write(shopFile, lines);
            return true;
        } catch (IOException ex) {
            logger.warning("Failed to write restored linker into " + shopFile + ": " + ex.getMessage());
            return false;
        }
    }

    private static Map<String, String> readStashMeta(Path stashFile) throws IOException {
        Map<String, String> meta = new HashMap<>();
        for (String line : Files.readAllLines(stashFile)) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("#") || !trimmed.contains(":")) {
                continue;
            }
            int colon = trimmed.indexOf(':');
            String key = trimmed.substring(0, colon).trim();
            String value = trimmed.substring(colon + 1).trim();
            meta.put(key, value);
        }
        return meta;
    }

    private static Path stashDir() {
        return Bukkit.getPluginsFolder().toPath().resolve("MCC-Bridge").resolve(STASH_DIR);
    }

    private static Path stashPath(String parentShop, String itemKey) {
        return stashDir().resolve(parentShop + "__" + itemKey + ".yml");
    }

    private static List<ActiveLinker> findActiveLinkers(List<String> lines) {
        List<ActiveLinker> result = new ArrayList<>();
        int pagesIndent = -1;
        int pageIndent = -1;
        int itemsIndent = -1;
        boolean inItems = false;
        String pageKey = null;
        int itemStart = -1;
        int itemIndent = -1;
        String itemKey = null;

        for (int index = 0; index < lines.size(); index++) {
            String line = lines.get(index);
            String trimmed = line.trim();
            int indent = leadingSpaces(line);

            if (trimmed.equals("pages:")) {
                closeActive(result, lines, itemStart, itemIndent, index - 1, itemKey, pageKey);
                itemStart = -1;
                pagesIndent = indent;
                pageIndent = -1;
                itemsIndent = -1;
                inItems = false;
                pageKey = null;
                continue;
            }
            if (pagesIndent < 0) {
                continue;
            }
            if (indent == 0 && !trimmed.isEmpty() && !trimmed.equals("pages:")) {
                closeActive(result, lines, itemStart, itemIndent, index - 1, itemKey, pageKey);
                break;
            }

            if (itemStart >= 0 && indent <= itemIndent) {
                closeActive(result, lines, itemStart, itemIndent, index - 1, itemKey, pageKey);
                itemStart = -1;
                itemKey = null;
            }

            Matcher keyMatcher = KEY_LINE.matcher(line);
            if (!keyMatcher.matches()) {
                continue;
            }
            String key = keyMatcher.group("key");

            if (trimmed.equals("items:")) {
                if (pageIndent >= 0 && indent > pageIndent) {
                    inItems = true;
                    itemsIndent = indent;
                }
                continue;
            }

            if (indent <= pagesIndent) {
                closeActive(result, lines, itemStart, itemIndent, index - 1, itemKey, pageKey);
                itemStart = -1;
                inItems = false;
                pageIndent = -1;
                itemsIndent = -1;
                pageKey = null;
                continue;
            }

            if (pageIndent < 0 || indent <= pageIndent) {
                if (indent > pagesIndent && trimmed.startsWith("page")) {
                    closeActive(result, lines, itemStart, itemIndent, index - 1, itemKey, pageKey);
                    itemStart = -1;
                    pageIndent = indent;
                    pageKey = key;
                    inItems = false;
                    itemsIndent = -1;
                }
                continue;
            }

            if (inItems && indent <= itemsIndent) {
                closeActive(result, lines, itemStart, itemIndent, index - 1, itemKey, pageKey);
                itemStart = -1;
                inItems = false;
                itemsIndent = -1;
                continue;
            }

            if (inItems && indent > itemsIndent && itemStart < 0) {
                itemStart = index;
                itemIndent = indent;
                itemKey = key;
            }
        }
        closeActive(result, lines, itemStart, itemIndent, lines.size() - 1, itemKey, pageKey);
        return result;
    }

    private static void closeActive(
            List<ActiveLinker> result,
            List<String> lines,
            int start,
            int itemIndent,
            int endInclusive,
            String itemKey,
            String pageKey
    ) {
        if (start < 0 || endInclusive < start || itemKey == null || pageKey == null) {
            return;
        }
        String target = null;
        int childIndent = -1;
        for (int i = start + 1; i <= endInclusive; i++) {
            String line = lines.get(i);
            int indent = leadingSpaces(line);
            if (indent <= itemIndent) {
                break;
            }
            if (childIndent < 0) {
                childIndent = indent;
            }
            if (indent != childIndent) {
                continue;
            }
            Matcher sectionMatcher = SECTION_PROP.matcher(line);
            if (sectionMatcher.matches()) {
                target = sectionMatcher.group("value").replace("\"", "").replace("'", "");
            }
        }
        if (target == null || target.isBlank()) {
            return;
        }
        result.add(new ActiveLinker(
                new ItemBlock(start, endInclusive, itemIndent),
                itemKey,
                pageKey,
                target,
                Math.max(childIndent, itemIndent + 2)
        ));
    }

    private static int findPageItemsIndex(List<String> lines, String pageKey) {
        int pagesIndent = -1;
        int pageIndent = -1;
        boolean inPage = false;
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            String trimmed = line.trim();
            int indent = leadingSpaces(line);
            if (trimmed.equals("pages:")) {
                pagesIndent = indent;
                pageIndent = -1;
                inPage = false;
                continue;
            }
            if (pagesIndent < 0) {
                continue;
            }
            Matcher keyMatcher = KEY_LINE.matcher(line);
            if (!keyMatcher.matches()) {
                continue;
            }
            if (indent > pagesIndent && (pageIndent < 0 || indent <= pageIndent)
                    && keyMatcher.group("key").equals(pageKey)) {
                pageIndent = indent;
                inPage = true;
                continue;
            }
            if (inPage && trimmed.equals("items:") && indent > pageIndent) {
                return i;
            }
            if (inPage && indent <= pageIndent) {
                inPage = false;
            }
        }
        return -1;
    }

    private static int findFirstItemsIndex(List<String> lines) {
        int pagesIndent = -1;
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            String trimmed = line.trim();
            int indent = leadingSpaces(line);
            if (trimmed.equals("pages:")) {
                pagesIndent = indent;
                continue;
            }
            if (pagesIndent >= 0 && trimmed.equals("items:") && indent > pagesIndent) {
                return i;
            }
        }
        return -1;
    }

    private static String fileStem(Path path) {
        String name = path.getFileName().toString();
        int dot = name.lastIndexOf('.');
        return dot > 0 ? name.substring(0, dot) : name;
    }

    private static int leadingSpaces(String line) {
        int count = 0;
        while (count < line.length() && line.charAt(count) == ' ') {
            count++;
        }
        return count;
    }

    private record ItemBlock(int start, int endInclusive, int itemIndent) {
    }

    private record ActiveLinker(
            ItemBlock block,
            String itemKey,
            String pageKey,
            String targetSection,
            int childIndent
    ) {
    }
}
