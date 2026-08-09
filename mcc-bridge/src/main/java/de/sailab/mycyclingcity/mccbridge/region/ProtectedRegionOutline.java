package de.sailab.mycyclingcity.mccbridge.region;

import java.util.List;

/**
 * Immutable cuboid outline data synced from MCC Django.
 */
public final class ProtectedRegionOutline {
    private final String regionId;
    private final String displayName;
    private final String world;
    private final int minX;
    private final int minY;
    private final int minZ;
    private final int maxX;
    private final int maxY;
    private final int maxZ;
    private final int red;
    private final int green;
    private final int blue;
    private final List<String> members;

    public ProtectedRegionOutline(
            String regionId,
            String displayName,
            String world,
            int minX,
            int minY,
            int minZ,
            int maxX,
            int maxY,
            int maxZ,
            int red,
            int green,
            int blue,
            List<String> members
    ) {
        this.regionId = regionId;
        this.displayName = displayName;
        this.world = world;
        this.minX = Math.min(minX, maxX);
        this.minY = Math.min(minY, maxY);
        this.minZ = Math.min(minZ, maxZ);
        this.maxX = Math.max(minX, maxX);
        this.maxY = Math.max(minY, maxY);
        this.maxZ = Math.max(minZ, maxZ);
        this.red = clamp(red);
        this.green = clamp(green);
        this.blue = clamp(blue);
        this.members = members == null ? List.of() : List.copyOf(members);
    }

    private static int clamp(int value) {
        return Math.max(0, Math.min(255, value));
    }

    public String regionId() {
        return regionId;
    }

    public String displayName() {
        return displayName;
    }

    public String world() {
        return world;
    }

    public int minX() {
        return minX;
    }

    public int minY() {
        return minY;
    }

    public int minZ() {
        return minZ;
    }

    public int maxX() {
        return maxX;
    }

    public int maxY() {
        return maxY;
    }

    public int maxZ() {
        return maxZ;
    }

    public int red() {
        return red;
    }

    public int green() {
        return green;
    }

    public int blue() {
        return blue;
    }

    public List<String> members() {
        return members;
    }

    public boolean containsBlock(int x, int y, int z) {
        return x >= minX && x <= maxX && y >= minY && y <= maxY && z >= minZ && z <= maxZ;
    }

    /** Horizontal distance from point to axis-aligned box (0 if inside XZ). */
    public double distanceSquaredHorizontal(double x, double z) {
        double dx = 0;
        if (x < minX) {
            dx = minX - x;
        } else if (x > maxX) {
            dx = x - maxX;
        }
        double dz = 0;
        if (z < minZ) {
            dz = minZ - z;
        } else if (z > maxZ) {
            dz = z - maxZ;
        }
        return dx * dx + dz * dz;
    }
}
