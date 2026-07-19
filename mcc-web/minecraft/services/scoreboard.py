from minecraft.services.team_scoreboard import refresh_team_scoreboard_snapshot, update_snapshot


def refresh_scoreboard_snapshot() -> int:
    """Read registered team spendable scores from Minecraft."""
    return refresh_team_scoreboard_snapshot()


__all__ = [
    "refresh_scoreboard_snapshot",
    "update_snapshot",
]
