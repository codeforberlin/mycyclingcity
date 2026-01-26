# Minecraft Integration - Documentation

## Overview

The Minecraft module enables integration between MyCyclingCity and a Minecraft server. It synchronizes cyclists' coins between the Django database and Minecraft scoreboards, allowing players to use their earned coins in the Minecraft server.

## Main Features

### 1. Coin Synchronization

- **Bidirectional Sync**: Coins are synchronized from MyCyclingCity to Minecraft and back
- **Scoreboard Integration**: Uses Minecraft scoreboards for coin display
- **Real-time Updates**: Changes are immediately transmitted to the Minecraft server

### 2. RCON Communication

- **Remote Management**: Communication with the Minecraft server via RCON (Remote Console)
- **Scoreboard Management**: Automatic creation and management of scoreboard objectives
- **Player Score Updates**: Real-time update of player scores

### 3. Outbox Pattern

- **Asynchronous Processing**: Events are stored in an outbox and processed asynchronously
- **Error Handling**: Automatic retry on errors
- **Event Tracking**: Full traceability of all synchronization events

### 4. WebSocket Support

- **Real-time Communication**: WebSocket endpoint for direct communication with Minecraft plugins
- **Secure Authentication**: Signature-based authentication
- **Coin Spending**: Support for direct coin spending from Minecraft

### 5. Snapshot System

- **Status Capture**: Periodic capture of scoreboard status
- **Comparison**: Comparison between database and Minecraft server
- **Synchronization**: Automatic synchronization on discrepancies

## Configuration

### Required Settings

Add the following settings to your `.env` file:

```env
# RCON Connection
MCC_MINECRAFT_RCON_HOST=127.0.0.1
MCC_MINECRAFT_RCON_PORT=25575
MCC_MINECRAFT_RCON_PASSWORD=your-rcon-password

# Scoreboard Names
MCC_MINECRAFT_SCOREBOARD_COINS_TOTAL=player_coins_total
MCC_MINECRAFT_SCOREBOARD_COINS_SPENDABLE=player_coins_spendable

# Worker Intervals (in seconds)
MCC_MINECRAFT_WORKER_POLL_INTERVAL=1
MCC_MINECRAFT_RCON_HEALTH_INTERVAL=30
MCC_MINECRAFT_SNAPSHOT_INTERVAL=60

# Snapshot Settings
MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE=True

# Outbox Settings
MCC_MINECRAFT_OUTBOX_DONE_TTL_DAYS=7
MCC_MINECRAFT_OUTBOX_FAILED_TTL_DAYS=30
MCC_MINECRAFT_OUTBOX_MAX_EVENTS=50000

# WebSocket (optional)
MCC_MINECRAFT_WS_ENABLED=False
MCC_MINECRAFT_WS_SHARED_SECRET=your-secret-key
MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS=server1,server2
```

### RCON Setup in Minecraft Server

Enable RCON in `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=your-rcon-password
```

## Admin GUI

### Access

Navigate to `/admin/minecraft/` in the Django Admin Interface (superusers only).

### Functions

#### Worker Control

- **Start**: Starts the Minecraft bridge worker
- **Stop**: Stops the worker
- **Status**: Shows the current worker status

#### Snapshot Worker

- **Start**: Starts the snapshot worker (periodic status capture)
- **Stop**: Stops the snapshot worker
- **Status**: Shows the snapshot worker status

#### Manual Actions

- **Sync**: Manual full synchronization of all players
- **Snapshot**: Manual update of the scoreboard snapshot
- **RCON Test**: Tests the RCON connection
- **Cleanup**: Cleans up old outbox events

### Status Display

The Admin Interface shows:

- **Worker Status**: Whether the bridge worker is running
- **Snapshot Status**: Whether the snapshot worker is running
- **Outbox Status**: Number of pending, processing, and failed events
- **RCON Status**: Connection status to the Minecraft server
- **Player List**: All players with their coin values and snapshot status

## Data Models

### MinecraftOutboxEvent

Stores events for asynchronous processing:

- `event_type`: Type of event (`update_player_coins`, `sync_all`)
- `payload`: JSON data of the event
- `status`: Status (`pending`, `processing`, `done`, `failed`)
- `attempts`: Number of processing attempts
- `last_error`: Last error message (if any)

### MinecraftPlayerScoreboardSnapshot

Stores snapshots of scoreboard status:

- `player_name`: Minecraft username
- `cyclist`: Link to Cyclist model
- `coins_total`: Total coins (from scoreboard)
- `coins_spendable`: Spendable coins (from scoreboard)
- `source`: Source of snapshot (`rcon`)
- `captured_at`: Timestamp of capture

### MinecraftWorkerState

Stores worker status:

- `is_running`: Whether the worker is running
- `pid`: Process ID of the worker
- `started_at`: Start time
- `last_heartbeat`: Last heartbeat
- `last_error`: Last error message

## Worker Processes

### Bridge Worker

The bridge worker continuously processes events from the outbox:

```bash
python manage.py minecraft_bridge_worker
```

**Functions:**
- Processes `update_player_coins` events
- Processes `sync_all` events
- Updates scoreboards via RCON
- Creates snapshots after updates

**Start/Stop via Script:**
```bash
scripts/minecraft.sh start
scripts/minecraft.sh stop
scripts/minecraft.sh status
```

### Snapshot Worker

The snapshot worker periodically captures scoreboard status:

```bash
python manage.py minecraft_snapshot_worker
```

**Functions:**
- Reads all player scores from the Minecraft server
- Updates the snapshot table
- Synchronizes `coins_spendable` back to database (optional)

**Start/Stop via Script:**
```bash
scripts/minecraft.sh snapshot-start
scripts/minecraft.sh snapshot-stop
scripts/minecraft.sh snapshot-status
```

## WebSocket Integration

### Activation

Set in `.env`:

```env
MCC_MINECRAFT_WS_ENABLED=True
MCC_MINECRAFT_WS_SHARED_SECRET=your-secret-key
MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS=server1
```

### Endpoint

WebSocket endpoint: `ws://your-domain/ws/minecraft/events/`

### Supported Events

#### SPEND_COINS

Player spends coins in Minecraft:

```json
{
  "type": "SPEND_COINS",
  "player": "PlayerName",
  "amount": 100,
  "server_id": "server1",
  "signature": "hmac-signature"
}
```

**Response:**
```json
{
  "status": "ok"
}
```

### Signature Calculation

The signature is calculated with HMAC-SHA256:

```python
import hmac
import hashlib
import json

payload = {"type": "SPEND_COINS", "player": "PlayerName", "amount": 100}
message = json.dumps(payload, sort_keys=True)
signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
```

## Management Commands

### Full Synchronization

```bash
python manage.py minecraft_sync_full
```

Synchronizes all players with a Minecraft username.

### Update Snapshot

```bash
python manage.py minecraft_snapshot_refresh
```

Manually updates the scoreboard snapshot.

### Cleanup Outbox

```bash
python manage.py minecraft_outbox_cleanup
```

Cleans up old events from the outbox (automatically after TTL).

## Player Linking

To link a cyclist with a Minecraft player:

1. Navigate to **MCC Core API & Models** → **Cyclists**
2. Select the cyclist
3. Enter the Minecraft username in the `mc_username` field
4. Save

After linking, coins will be automatically synchronized.

## Workflow

### Coin Update from MyCyclingCity to Minecraft

1. Cyclist earns coins (e.g., by cycling)
2. `coins_total` or `coins_spendable` is updated in the database
3. Event is queued in the outbox
4. Bridge worker processes the event
5. RCON command is sent to Minecraft server
6. Scoreboard is updated
7. Snapshot is created

### Coin Spending from Minecraft to MyCyclingCity

1. Player spends coins in Minecraft (e.g., via plugin)
2. Plugin sends WebSocket event to MyCyclingCity
3. `coins_spendable` is reduced in the database
4. Event is queued in the outbox
5. Bridge worker updates the scoreboard
6. Snapshot is updated

## Troubleshooting

### RCON Connection Fails

1. Check RCON settings in `server.properties`
2. Test the connection in Admin GUI (`RCON Test`)
3. Check firewall settings
4. Ensure the Minecraft server is running

### Worker Won't Start

1. Check logs: `logs/minecraft_action.log`
2. Ensure the script is executable: `chmod +x scripts/minecraft.sh`
3. Check the Python environment
4. Check the database connection

### Coins Not Synchronizing

1. Check the outbox in Admin GUI
2. Check failed events
3. Check logs: `logs/minecraft.log`
4. Ensure the worker is running
5. Check if the player has an `mc_username`

### Snapshot Shows Wrong Values

1. Manually run a snapshot (Admin GUI)
2. Check the RCON connection
3. Check if scoreboards exist in Minecraft
4. Run a full synchronization

## Best Practices

1. **Regular Snapshots**: Keep the snapshot worker running to detect discrepancies early
2. **Outbox Monitoring**: Regularly monitor the outbox for failed events
3. **RCON Security**: Use a strong RCON password
4. **WebSocket Security**: Use a strong shared secret
5. **Backup**: Regularly backup outbox events and snapshots
6. **Logging**: Enable verbose logging for debugging

## Related Documentation

- [Admin GUI Manual](index.md) - Overview of all admin functions
- [Server Control](index.md#server-control) - Server management
- [Log File Viewer](index.md#log-file-viewer) - View log files
