package de.sailab.mycyclingcity.mccbridge.shop;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.logging.Logger;

final class EconomyShopGuiYamlWriter {
    private static final Pattern BUY_LINE = Pattern.compile("^(?<indent>\\s*)buy:\\s*(?<value>.+?)\\s*$");
    private static final Pattern KEY_LINE = Pattern.compile("^(?<indent>\\s*)(?<quote>['\"]?)(?<key>[^'\":]+)\\2:\\s*$");

    private EconomyShopGuiYamlWriter() {
    }

    record PriceUpdate(String material, String itemLoc, int buyPrice, String displayName) {
    }

    record WriteResult(int updated, int skipped) {
    }

    static WriteResult applyPriceUpdates(Path shopFile, List<PriceUpdate> updates, Logger logger) {
        if (updates.isEmpty()) {
            return new WriteResult(0, 0);
        }

        List<String> lines;
        try {
            lines = new ArrayList<>(Files.readAllLines(shopFile));
        } catch (IOException ex) {
            logger.warning("Failed to read EconomyShopGUI shop file " + shopFile + ": " + ex.getMessage());
            return new WriteResult(0, updates.size());
        }

        Map<String, Integer> locToPrice = new HashMap<>();
        for (PriceUpdate update : updates) {
            if (update.itemLoc() != null && !update.itemLoc().isBlank()) {
                locToPrice.put(update.itemLoc(), update.buyPrice());
            }
        }

        int updated = 0;
        int skipped = 0;
        int pagesIndent = -1;
        int pageIndent = -1;
        int itemsIndent = -1;
        String currentPage = null;
        boolean inItems = false;

        for (int index = 0; index < lines.size(); index++) {
            String line = lines.get(index);
            String trimmed = line.trim();
            int indent = leadingSpaces(line);

            if (trimmed.equals("pages:")) {
                pagesIndent = indent;
                pageIndent = -1;
                itemsIndent = -1;
                currentPage = null;
                inItems = false;
                continue;
            }

            if (pagesIndent < 0) {
                continue;
            }

            Matcher keyMatcher = KEY_LINE.matcher(line);
            if (!keyMatcher.matches()) {
                continue;
            }

            if (trimmed.equals("items:")) {
                if (currentPage != null && pageIndent >= 0 && indent > pageIndent) {
                    inItems = true;
                    itemsIndent = indent;
                }
                continue;
            }

            if (indent <= pagesIndent) {
                currentPage = null;
                inItems = false;
                pageIndent = -1;
                itemsIndent = -1;
                continue;
            }

            if (pageIndent < 0 || indent <= pageIndent) {
                if (indent > pagesIndent && trimmed.startsWith("page")) {
                    currentPage = keyMatcher.group("key");
                    pageIndent = indent;
                    inItems = false;
                    itemsIndent = -1;
                }
                continue;
            }

            if (inItems && indent <= itemsIndent) {
                inItems = false;
            }

            if (!inItems || currentPage == null) {
                continue;
            }

            if (indent <= itemsIndent) {
                continue;
            }

            String itemKey = keyMatcher.group("key");
            String itemLoc = currentPage + ".items." + itemKey;
            Integer buyPrice = locToPrice.remove(itemLoc);
            if (buyPrice == null) {
                continue;
            }

            if (replaceBuyInItemBlock(lines, index, indent, buyPrice)) {
                updated++;
            } else {
                skipped++;
            }
        }

        skipped += locToPrice.size();

        if (updated == 0) {
            return new WriteResult(0, skipped > 0 ? skipped : updates.size());
        }

        try {
            Path backup = shopFile.resolveSibling(shopFile.getFileName() + ".bak");
            Files.copy(shopFile, backup, StandardCopyOption.REPLACE_EXISTING);
            Files.write(shopFile, lines);
        } catch (IOException ex) {
            logger.warning("Failed to write EconomyShopGUI shop file " + shopFile + ": " + ex.getMessage());
            return new WriteResult(0, updates.size());
        }

        return new WriteResult(updated, skipped);
    }

    private static boolean replaceBuyInItemBlock(List<String> lines, int itemLineIndex, int itemIndent, int buyPrice) {
        for (int index = itemLineIndex + 1; index < lines.size(); index++) {
            String line = lines.get(index);
            if (line.isBlank()) {
                continue;
            }

            int indent = leadingSpaces(line);
            Matcher siblingMatcher = KEY_LINE.matcher(line);
            if (siblingMatcher.matches() && indent <= itemIndent) {
                break;
            }

            Matcher buyMatcher = BUY_LINE.matcher(line);
            if (buyMatcher.matches() && indent > itemIndent) {
                lines.set(index, buyMatcher.group("indent") + "buy: " + buyPrice);
                return true;
            }
        }
        return false;
    }

    private static int leadingSpaces(String line) {
        int count = 0;
        while (count < line.length() && line.charAt(count) == ' ') {
            count++;
        }
        return count;
    }
}
