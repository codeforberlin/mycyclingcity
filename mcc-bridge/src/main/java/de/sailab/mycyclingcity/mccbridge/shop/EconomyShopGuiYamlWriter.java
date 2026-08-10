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
    private static final Pattern SELL_LINE = Pattern.compile("^(?<indent>\\s*)sell:\\s*(?<value>.+?)\\s*$");
    private static final Pattern KEY_LINE = Pattern.compile("^(?<indent>\\s*)(?<quote>['\"]?)(?<key>[^'\":]+)\\2:\\s*$");

    private EconomyShopGuiYamlWriter() {
    }

    /**
     * @param buyPrice  purchase price in Velos
     * @param sellPrice refund price in Velos (MCC policy: equal to buy for 100% refund)
     */
    record PriceUpdate(
            String section,
            String material,
            String itemLoc,
            int buyPrice,
            int sellPrice,
            String displayName
    ) {
        PriceUpdate(String material, String itemLoc, int buyPrice, String displayName) {
            this("", material, itemLoc, buyPrice, buyPrice, displayName);
        }
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

        Map<String, PriceUpdate> locToUpdate = new HashMap<>();
        for (PriceUpdate update : updates) {
            if (update.itemLoc() != null && !update.itemLoc().isBlank()) {
                locToUpdate.put(update.itemLoc(), update);
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
            PriceUpdate priceUpdate = locToUpdate.remove(itemLoc);
            if (priceUpdate == null) {
                continue;
            }

            if (replacePricesInItemBlock(lines, index, indent, priceUpdate.buyPrice(), priceUpdate.sellPrice())) {
                updated++;
            } else {
                skipped++;
            }
        }

        skipped += locToUpdate.size();

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

    /**
     * Update buy: and sell: inside an item block. Inserts sell after buy when missing.
     */
    private static boolean replacePricesInItemBlock(
            List<String> lines,
            int itemLineIndex,
            int itemIndent,
            int buyPrice,
            int sellPrice
    ) {
        int buyLineIndex = -1;
        int sellLineIndex = -1;
        String priceIndent = null;

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
                buyLineIndex = index;
                priceIndent = buyMatcher.group("indent");
                lines.set(index, priceIndent + "buy: " + buyPrice);
                continue;
            }

            Matcher sellMatcher = SELL_LINE.matcher(line);
            if (sellMatcher.matches() && indent > itemIndent) {
                sellLineIndex = index;
                lines.set(index, sellMatcher.group("indent") + "sell: " + sellPrice);
            }
        }

        if (buyLineIndex < 0) {
            return false;
        }

        if (sellLineIndex < 0) {
            String indent = priceIndent != null ? priceIndent : " ".repeat(itemIndent + 2);
            lines.add(buyLineIndex + 1, indent + "sell: " + sellPrice);
        }
        return true;
    }

    private static int leadingSpaces(String line) {
        int count = 0;
        while (count < line.length() && line.charAt(count) == ' ') {
            count++;
        }
        return count;
    }
}
