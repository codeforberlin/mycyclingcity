package de.sailab.mycyclingcity.mccbridge.vehiclesplus;

import org.bukkit.Bukkit;
import org.bukkit.plugin.Plugin;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.logging.Logger;

/**
 * Reflection-based VehiclesPlus garage cleanup (no compile dependency on VP).
 *
 * Removes storage vehicles of a given model (or all models) from a garage and
 * deletes them via {@code Vehicle.remove()}, matching the in-game garage UI.
 */
public final class VehiclesPlusGarageCleaner {
    private VehiclesPlusGarageCleaner() {
    }

    public static boolean isVehiclesPlusPresent() {
        return Bukkit.getPluginManager().getPlugin("VehiclesPlus") != null;
    }

    /**
     * @param garageName personal garage name (usually MS login / player name)
     * @param modelId    VehiclesPlus model id, or {@code *} / empty for all
     * @return number of vehicles removed
     */
    public static int removeFromGarage(String garageName, String modelId, Logger logger)
            throws Exception {
        if (!isVehiclesPlusPresent()) {
            throw new IllegalStateException("VehiclesPlus plugin not loaded");
        }
        String garage = garageName == null ? "" : garageName.trim();
        if (garage.isEmpty()) {
            throw new IllegalArgumentException("garage name empty");
        }
        String model = modelId == null ? "" : modelId.trim();
        boolean allModels = model.isEmpty() || "*".equals(model) || "ALL".equalsIgnoreCase(model);

        Class<?> api = Class.forName("nl.sbdeveloper.vehiclesplus.api.VehiclesPlusAPI");
        Method getGarage = api.getMethod("getGarage", String.class);
        @SuppressWarnings("unchecked")
        Optional<Object> garageOpt = (Optional<Object>) getGarage.invoke(null, garage);
        if (garageOpt == null || garageOpt.isEmpty()) {
            if (logger != null) {
                logger.info("[vpremove] garage not found: " + garage);
            }
            return 0;
        }
        Object garageObj = garageOpt.get();
        Method getVehicles = garageObj.getClass().getMethod("getVehicles");
        @SuppressWarnings("unchecked")
        List<UUID> vehicleIds = new ArrayList<>((List<UUID>) getVehicles.invoke(garageObj));
        if (vehicleIds.isEmpty()) {
            return 0;
        }

        Method apiGetVehicle = api.getMethod("getVehicle", UUID.class);
        Method removeVehicleFromGarage = garageObj.getClass().getMethod("removeVehicle", UUID.class);
        int removed = 0;
        for (UUID uuid : vehicleIds) {
            Object vehicle = apiGetVehicle.invoke(null, uuid);
            if (vehicle == null) {
                removeVehicleFromGarage.invoke(garageObj, uuid);
                continue;
            }
            if (!allModels) {
                String vehicleModel = resolveModelId(vehicle);
                if (vehicleModel == null
                        || !vehicleModel.equalsIgnoreCase(model)) {
                    continue;
                }
            }
            removeVehicleFromGarage.invoke(garageObj, uuid);
            Method remove = vehicle.getClass().getMethod("remove");
            remove.invoke(vehicle);
            removed++;
            if (logger != null) {
                logger.info(
                        "[vpremove] removed uuid="
                                + uuid
                                + " model="
                                + resolveModelId(vehicle)
                                + " garage="
                                + garage
                );
            }
        }
        Method forceSave = garageObj.getClass().getMethod("forceSave");
        forceSave.invoke(garageObj);
        return removed;
    }

    private static String resolveModelId(Object vehicle) {
        try {
            Method getModel = vehicle.getClass().getMethod("getVehicleModel");
            Object model = getModel.invoke(vehicle);
            if (model == null) {
                return null;
            }
            // VehicleModel#getId or toString fallback
            try {
                Method getId = model.getClass().getMethod("getId");
                Object id = getId.invoke(model);
                if (id != null) {
                    return id.toString();
                }
            } catch (NoSuchMethodException ignored) {
                // fall through
            }
            String asString = model.toString();
            if (asString != null && !asString.isBlank()) {
                return asString;
            }
        } catch (ReflectiveOperationException ignored) {
            // ignore
        }
        return null;
    }

    public static String pluginVersionHint() {
        Plugin plugin = Bukkit.getPluginManager().getPlugin("VehiclesPlus");
        if (plugin == null) {
            return "missing";
        }
        return plugin.getDescription().getVersion();
    }
}
