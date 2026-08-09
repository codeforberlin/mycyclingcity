package de.sailab.mycyclingcity.mccbridge.region;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import de.sailab.mycyclingcity.mccbridge.MccBridgeConfig;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextColor;
import org.bukkit.Bukkit;
import org.bukkit.Color;
import org.bukkit.Particle;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

/**
 * Renders dust particle cuboid outlines for protected regions near players.
 */
public final class RegionOutlineService implements Listener {
    private static final int CORNER_POST_HEIGHT = 3;
    private static final int EDGE_STEP = 2;

    private final JavaPlugin plugin;
    private final MccBridgeConfig config;
    private final Logger logger;

    private volatile List<ProtectedRegionOutline> regions = List.of();
    private volatile boolean outlineEnabled = true;
    private volatile boolean enterHintEnabled = true;
    private volatile int viewDistance = 48;

    private BukkitTask task;
    private final Map<UUID, String> lastRegionByPlayer = new ConcurrentHashMap<>();

    public RegionOutlineService(JavaPlugin plugin, MccBridgeConfig config) {
        this.plugin = plugin;
        this.config = config;
        this.logger = plugin.getLogger();
    }

    public void start() {
        stop();
        long period = Math.max(5L, config.regionOutlinePeriodTicks());
        task = plugin.getServer().getScheduler().runTaskTimer(plugin, this::tick, period, period);
        logger.info("Region outline renderer started (period=" + period + " ticks)");
    }

    public void stop() {
        if (task != null) {
            task.cancel();
            task = null;
        }
        lastRegionByPlayer.clear();
    }

    public int regionCount() {
        return regions.size();
    }

    public boolean isOutlineEnabled() {
        return outlineEnabled && config.regionOutlineEnabled();
    }

    public void applyPayload(JsonObject payload) {
        if (payload == null) {
            return;
        }
        if (payload.has("outline_enabled")) {
            outlineEnabled = payload.get("outline_enabled").getAsBoolean();
        }
        if (payload.has("enter_hint_enabled")) {
            enterHintEnabled = payload.get("enter_hint_enabled").getAsBoolean();
        }
        if (payload.has("view_distance")) {
            viewDistance = Math.max(8, payload.get("view_distance").getAsInt());
        }

        List<ProtectedRegionOutline> parsed = new ArrayList<>();
        if (payload.has("regions") && payload.get("regions").isJsonArray()) {
            for (JsonElement element : payload.getAsJsonArray("regions")) {
                if (!element.isJsonObject()) {
                    continue;
                }
                ProtectedRegionOutline outline = parseRegion(element.getAsJsonObject());
                if (outline != null) {
                    parsed.add(outline);
                }
            }
        }
        regions = List.copyOf(parsed);
        logger.info(
                "Protected regions outline updated: count="
                        + regions.size()
                        + " enabled="
                        + outlineEnabled
                        + " view_distance="
                        + viewDistance
        );
    }

    private ProtectedRegionOutline parseRegion(JsonObject row) {
        if (!row.has("region_id") || !row.has("world")) {
            return null;
        }
        String regionId = row.get("region_id").getAsString();
        String displayName = row.has("display_name")
                ? row.get("display_name").getAsString()
                : regionId;
        String world = row.get("world").getAsString();
        int minX = row.get("min_x").getAsInt();
        int minY = row.get("min_y").getAsInt();
        int minZ = row.get("min_z").getAsInt();
        int maxX = row.get("max_x").getAsInt();
        int maxY = row.get("max_y").getAsInt();
        int maxZ = row.get("max_z").getAsInt();

        int r = 64;
        int g = 160;
        int b = 255;
        if (row.has("color_rgb") && row.get("color_rgb").isJsonArray()) {
            JsonArray rgb = row.getAsJsonArray("color_rgb");
            if (rgb.size() >= 3) {
                r = rgb.get(0).getAsInt();
                g = rgb.get(1).getAsInt();
                b = rgb.get(2).getAsInt();
            }
        }

        List<String> members = new ArrayList<>();
        if (row.has("members") && row.get("members").isJsonArray()) {
            for (JsonElement member : row.getAsJsonArray("members")) {
                members.add(member.getAsString());
            }
        }

        return new ProtectedRegionOutline(
                regionId,
                displayName,
                world,
                minX,
                minY,
                minZ,
                maxX,
                maxY,
                maxZ,
                r,
                g,
                b,
                members
        );
    }

    private void tick() {
        if (!isOutlineEnabled() || regions.isEmpty()) {
            return;
        }
        double viewSq = (double) viewDistance * (double) viewDistance;
        for (Player player : Bukkit.getOnlinePlayers()) {
            World world = player.getWorld();
            String worldName = world.getName();
            double px = player.getLocation().getX();
            double py = player.getLocation().getY();
            double pz = player.getLocation().getZ();
            int footY = player.getLocation().getBlockY();

            String insideId = null;
            String insideName = null;
            TextColor insideColor = null;

            for (ProtectedRegionOutline region : regions) {
                if (!worldName.equalsIgnoreCase(region.world())) {
                    continue;
                }
                if (region.distanceSquaredHorizontal(px, pz) > viewSq) {
                    continue;
                }
                drawOutline(player, world, region, footY);

                int bx = player.getLocation().getBlockX();
                int by = player.getLocation().getBlockY();
                int bz = player.getLocation().getBlockZ();
                if (region.containsBlock(bx, by, bz)) {
                    insideId = region.regionId();
                    insideName = region.displayName();
                    insideColor = TextColor.color(region.red(), region.green(), region.blue());
                }
            }

            maybeShowEnterHint(player, insideId, insideName, insideColor);
        }
    }

    private void maybeShowEnterHint(
            Player player,
            String insideId,
            String insideName,
            TextColor insideColor
    ) {
        UUID id = player.getUniqueId();
        String previous = lastRegionByPlayer.get(id);
        if (insideId == null) {
            lastRegionByPlayer.remove(id);
            return;
        }
        if (insideId.equals(previous)) {
            return;
        }
        lastRegionByPlayer.put(id, insideId);
        if (!enterHintEnabled || !config.regionOutlineEnterHint()) {
            return;
        }
        TextColor color = insideColor != null ? insideColor : NamedTextColor.AQUA;
        player.sendActionBar(
                Component.text("Region: ", NamedTextColor.GRAY)
                        .append(Component.text(insideName == null ? insideId : insideName, color))
        );
    }

    private void drawOutline(Player player, World world, ProtectedRegionOutline region, int footY) {
        int y = Math.max(region.minY(), Math.min(region.maxY(), footY));
        Color color = Color.fromRGB(region.red(), region.green(), region.blue());
        Particle.DustOptions dust = new Particle.DustOptions(color, 1.0f);

        int minX = region.minX();
        int maxX = region.maxX();
        int minZ = region.minZ();
        int maxZ = region.maxZ();

        // Four horizontal edges at foot Y
        for (int x = minX; x <= maxX; x += EDGE_STEP) {
            spawn(player, world, x + 0.5, y + 0.15, minZ + 0.5, dust);
            spawn(player, world, x + 0.5, y + 0.15, maxZ + 0.5, dust);
        }
        for (int z = minZ; z <= maxZ; z += EDGE_STEP) {
            spawn(player, world, minX + 0.5, y + 0.15, z + 0.5, dust);
            spawn(player, world, maxX + 0.5, y + 0.15, z + 0.5, dust);
        }

        // Short corner posts
        int[][] corners = {
                {minX, minZ},
                {minX, maxZ},
                {maxX, minZ},
                {maxX, maxZ},
        };
        for (int[] corner : corners) {
            for (int dy = 0; dy <= CORNER_POST_HEIGHT; dy++) {
                int cy = y + dy;
                if (cy > region.maxY()) {
                    break;
                }
                spawn(player, world, corner[0] + 0.5, cy + 0.2, corner[1] + 0.5, dust);
            }
        }
    }

    private void spawn(
            Player player,
            World world,
            double x,
            double y,
            double z,
            Particle.DustOptions dust
    ) {
        player.spawnParticle(Particle.DUST, x, y, z, 1, 0, 0, 0, 0, dust);
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        lastRegionByPlayer.remove(event.getPlayer().getUniqueId());
    }
}
