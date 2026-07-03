# Minecraft Integration - Documentation

## Overview

The Minecraft module synchronizes **group Velos** between MyCyclingCity and a Minecraft server. Leaf groups with `mc_username` are mirrored via RCON scoreboards and optional WebSocket spending.

## Main Features

### 1. Group Velos Synchronization

- **MyCyclingCity → Minecraft**: Earn/admin updates enqueue outbox events and update scoreboards
- **Minecraft → MyCyclingCity**: WebSocket spend events reduce `Group.velos_spendable`
- **Scoreboards**: `group_velos_total` and `group_velos_spendable` (configurable)

### 2. RCON Communication

- Create scoreboard objectives and set player scores
- Health checks and manual tests via admin GUI

### 3. Outbox Pattern

- Asynchronous processing with retry and TTL cleanup
- Event types: `update_group_velos`, `sync_all` (legacy `update_player_coins` is skipped)

### 4. WebSocket Support

- Signed events from Minecraft plugins
- `SPEND_GROUP_VELOS` (legacy alias: `SPEND_COINS`)

### 5. Snapshot System

- Periodic read of group scoreboards
- Optional: write `velos_spendable` back to the database from the scoreboard

## Configuration

```env
# RCON
MCC_MINECRAFT_RCON_HOST=127.0.0.1
MCC_MINECRAFT_RCON_PORT=25575
MCC_MINECRAFT_RCON_PASSWORD=your-rcon-password

# Group Velos scoreboards (active)
MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_TOTAL=group_velos_total
MCC_MINECRAFT_SCOREBOARD_GROUP_VELOS_SPENDABLE=group_velos_spendable

# Legacy (unused)
MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL=player_coins_total
MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE=player_coins_spendable

MCC_MINECRAFT_WORKER_POLL_INTERVAL=1
MCC_MINECRAFT_RCON_HEALTH_INTERVAL=30
MCC_MINECRAFT_SNAPSHOT_INTERVAL=60
MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE=True

MCC_MINECRAFT_OUTBOX_DONE_TTL_DAYS=7
MCC_MINECRAFT_OUTBOX_FAILED_TTL_DAYS=30
MCC_MINECRAFT_OUTBOX_MAX_EVENTS=50000

MCC_MINECRAFT_WS_ENABLED=False
MCC_MINECRAFT_WS_SHARED_SECRET=your-shared-secret
MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS=server1,server2
```

## Admin GUI

At `/admin/minecraft/` (superusers only):

- Worker and snapshot control
- Manual actions: sync, snapshot, RCON test, cleanup
- **Groups table**: DB values vs. scoreboard snapshot per `mc_username`

## Data Models

### MinecraftOutboxEvent

- `update_group_velos` – scoreboard update for one group
- `sync_all` – all groups with `mc_username`
- `update_player_coins` – deprecated; worker marks done without action

### MinecraftPlayerScoreboardSnapshot

- `player_name` – Minecraft name (= `Group.mc_username`)
- `group` – link to leaf group
- `velos_total`, `velos_spendable` – last RCON values

## WebSocket

Endpoint: `ws://your-domain/ws/minecraft/events/`

```json
{
  "type": "SPEND_GROUP_VELOS",
  "player": "GroupMcName",
  "amount": 100,
  "server_id": "server1",
  "signature": "hmac-signature"
}
```

Success response: `{"status": "ok"}`

## Group Linking

1. **MCC Core API & Models** → **Group** (leaf group)
2. Set `mc_username` (Minecraft team name)
3. After earn or manual sync, Velos are pushed to the server

## Workflow

**Earn → Minecraft:** VelosEarn → outbox `update_group_velos` → worker → RCON → snapshot

**Spend in Minecraft:** plugin → WebSocket `SPEND_GROUP_VELOS` → `velos_spendable` − amount → outbox → scoreboard update

## Troubleshooting

- Check outbox and worker logs (`logs/minecraft.log`)
- RCON test in admin GUI
- Group must have `mc_username`
- Match `.env` scoreboard names with server objectives

## Related Documentation

- [Admin GUI Handbook](index.md)
