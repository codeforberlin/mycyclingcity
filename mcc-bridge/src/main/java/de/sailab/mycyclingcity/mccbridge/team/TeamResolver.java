package de.sailab.mycyclingcity.mccbridge.team;

import de.sailab.mycyclingcity.mccbridge.MccBridgeConfig;
import net.luckperms.api.LuckPerms;
import net.luckperms.api.model.user.User;
import org.bukkit.Bukkit;
import org.bukkit.OfflinePlayer;

import java.util.Map;
import java.util.Optional;

public class TeamResolver {
    private final MccBridgeConfig config;
    private LuckPerms luckPerms;

    public TeamResolver(MccBridgeConfig config) {
        this.config = config;
    }

    public void setLuckPerms(LuckPerms luckPerms) {
        this.luckPerms = luckPerms;
    }

    public Optional<String> resolveTeamMcUsername(OfflinePlayer player) {
        if (player == null || player.getName() == null) {
            return Optional.empty();
        }

        String override = config.playerOverrides().get(player.getName());
        if (override != null && !override.isBlank()) {
            return Optional.of(override);
        }

        if ("luckperms".equalsIgnoreCase(config.resolution()) && luckPerms != null) {
            User user = luckPerms.getUserManager().getUser(player.getUniqueId());
            if (user != null) {
                for (var group : user.getInheritedGroups(user.getQueryOptions())) {
                    String mapped = config.teamGroups().get(group.getName());
                    if (mapped != null && !mapped.isBlank()) {
                        return Optional.of(mapped);
                    }
                }
            }
        }

        for (Map.Entry<String, String> entry : config.teamGroups().entrySet()) {
            if (player.isOnline() && player.getPlayer() != null
                    && player.getPlayer().hasPermission("group." + entry.getKey())) {
                return Optional.of(entry.getValue());
            }
        }

        return Optional.empty();
    }
}
