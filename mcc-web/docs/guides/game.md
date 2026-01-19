# Kilometer-Challenge (Game) - Complete Guide

## Overview

The Kilometer-Challenge is a gamification feature of MyCyclingCity that allows users to create competitive challenges by assigning cyclists to devices and tracking their progress toward a target distance. The system supports both single-player and multi-player modes with real-time synchronization.

## Table of Contents

- [Features](#features)
- [Getting Started](#getting-started)
- [User Interface](#user-interface)
- [Game Modes](#game-modes)
- [API Reference](#api-reference)
- [Technical Details](#technical-details)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Features

### Core Functionality

- **Device Assignment**: Assign cyclists to ESP32 tachometer devices
- **Target Setting**: Set optional target distances in kilometers
- **Real-time Tracking**: Monitor progress with live updates
- **Coin Calculation**: Automatic coin calculation based on distance
- **Winner Detection**: Automatic detection when targets are reached
- **Multi-player Support**: Game rooms for collaborative challenges

### Single-Player Mode

In single-player mode, users can:

- Assign cyclists to devices
- Set a target distance (optional)
- Start the game to track progress
- View real-time results with distance gained and coins earned
- Stop the game to freeze results
- View final statistics

### Multi-Player Mode (Game Rooms)

Game rooms allow multiple players to participate in the same challenge:

- **Room Creation**: Create a room with a unique 8-character code
- **Room Joining**: Join existing rooms by entering the room code
- **QR Code Sharing**: Generate QR codes for easy room sharing
- **Master System**: The room creator becomes the "master" who can:
  - Modify target kilometers
  - Clear all assignments
  - Transfer master role to another participant
  - End the room
- **Real-time Synchronization**: All participants see the same game state
- **Session Management**: Automatic session tracking and cleanup

## Getting Started

### Prerequisites

- Active cyclists in the system
- Active devices (ESP32 tachometers)
- Web browser with JavaScript enabled

### Accessing the Game

Navigate to: `/{language}/game/` (e.g., `/de/game/` or `/en/game/`)

### First Steps

1. **Select Cyclists**: Choose cyclists from the dropdown menu
2. **Select Devices**: Choose available devices
3. **Assign**: Click "Zuweisen" (Assign) to link cyclists to devices
4. **Set Target** (Optional): Enter target distance in kilometers
5. **Start Game**: Click "Spiel starten" to begin tracking

## User Interface

### Main Game Page

The game interface consists of several key sections:

#### Assignment Section

- **Cyclist Dropdown**: Select from available cyclists
- **Device Dropdown**: Select from available devices
- **Assign Button**: Create assignment between cyclist and device
- **Assignment List**: View all current assignments
- **Remove Button**: Remove individual assignments

#### Target Section

- **Target Input**: Enter target distance in kilometers
- **Current Target Display**: Shows the current target (if set)
- **Target Progress**: Visual indicator of progress toward target

#### Game Controls

- **Start Button**: Begin tracking (only visible when game is stopped)
- **Stop Button**: Freeze results (only visible when game is running)
- **Game Status**: Indicator showing if game is active

#### Results Table

Real-time table showing:

- **Cyclist Name**: Name of the assigned cyclist
- **Device**: Device identifier
- **Start Distance**: Distance at game start
- **Current Distance**: Current total distance
- **Progress**: Distance gained during game
- **Coins**: Coins earned during game
- **Status**: Winner indicator (if target reached)

#### Room Controls (Multi-player)

- **Create Room**: Create a new game room
- **Join Room**: Enter room code to join
- **Room Code Display**: Shows current room code
- **Master Controls**: Additional controls for room master
- **Leave Room**: Exit current room

## Game Modes

### Single-Player Mode

**Use Case**: Individual challenges, testing, practice

**Workflow**:

1. Assign cyclists to devices
2. Set target (optional)
3. Start game
4. Monitor progress
5. Stop game when finished

**Features**:

- No room code required
- Full control over assignments
- Can start/stop anytime
- Results stored in session

### Multi-Player Mode (Game Rooms)

**Use Case**: Group challenges, competitions, classroom activities

**Workflow**:

1. Master creates room
2. Master shares room code (or QR code)
3. Participants join room
4. Master sets target
5. All participants assign cyclists
6. Master starts game
7. All participants see synchronized results
8. Master stops game when finished

**Features**:

- Synchronized game state
- Master controls
- QR code sharing
- Session tracking
- Automatic cleanup

## API Reference

### HTMX Endpoints

These endpoints are used for real-time UI updates:

#### Assignment Management

**POST** `/{language}/game/htmx/assignments`

Add or remove cyclist-device assignments.

**Request Parameters**:
- `action`: `add` or `remove`
- `cyclist_id`: Cyclist user ID
- `device_name`: Device identifier

**Response**: HTML fragment with updated assignment list

#### Results Table

**GET** `/{language}/game/htmx/results`

Get the current results table.

**Response**: HTML fragment with results table

**Auto-refresh**: Every 10 seconds when game is active

#### Target Display

**GET** `/{language}/game/htmx/target-km`

Get the current target kilometer display.

**Response**: HTML fragment with target information

**Auto-refresh**: Every 3 seconds in game rooms

#### Game Buttons

**GET** `/{language}/game/htmx/game-buttons`

Get the game control buttons (start/stop).

**Response**: HTML fragment with game buttons

#### Session Sync

**POST** `/{language}/game/htmx/sync-session`

Synchronize session with game room.

**Request Parameters**:
- `room_code`: Room code to sync with

**Response**: JSON status

### REST API Endpoints

#### Get Game Players

**GET** `/{language}/game/api/game/cyclists`

Get list of available cyclists for the game.

**Response**:
```json
{
  "cyclists": [
    {
      "id": 1,
      "username": "MaxMustermann",
      "distance_total": 150.5,
      "coins_total": 300
    }
  ]
}
```

#### Get Game Devices

**GET** `/{language}/game/api/game/devices`

Get list of available devices.

**Response**:
```json
{
  "devices": [
    {
      "name": "MCC-Device_AB12",
      "display_name": "Device 1",
      "distance_total": 500.2
    }
  ]
}
```

#### Start/Stop Game

**POST** `/{language}/game/api/game/start`

Start or stop the game.

**Request Parameters**:
- `action`: `start` or `stop`

**Response**:
```json
{
  "status": "game_started" // or "game_stopped"
}
```

#### Get Game Data

**GET** `/{language}/game/api/game/data`

Get current game state and statistics.

**Response**:
```json
{
  "is_game_active": true,
  "is_game_stopped": false,
  "assignments": {
    "device1": "cyclist1"
  },
  "start_distances": {
    "cyclist1": 100.5
  },
  "current_distances": {
    "cyclist1": 150.2
  },
  "progress": {
    "cyclist1": 49.7
  },
  "coins": {
    "cyclist1": 99.4
  },
  "target_km": 200.0,
  "winners": []
}
```

#### End Session

**POST** `/{language}/game/api/session/end`

End the current game session.

**Response**:
```json
{
  "status": "session_ended"
}
```

#### Goal Reached Sound

**GET** `/{language}/game/api/sound/goal_reached`

Get the winner sound file.

**Response**: Audio file (MP3/WAV)

#### Get Game Images

**GET** `/{language}/game/api/game/images`

Get game-related images.

**Response**: JSON with image URLs

### Room Management Endpoints

#### Create Room

**POST** `/{language}/game/room/create`

Create a new game room.

**Response**:
```json
{
  "room_code": "ABC123XY",
  "url": "/de/game/room/ABC123XY/"
}
```

#### Join Room

**POST** `/{language}/game/room/join`

Join an existing game room.

**Request Parameters**:
- `room_code`: 8-character room code

**Response**: Redirect to room page or error

#### Leave Room

**POST** `/{language}/game/room/leave`

Leave the current game room.

**Response**: Redirect to main game page

#### End Room

**POST** `/{language}/game/room/end`

End the game room (master only).

**Response**: JSON status

#### Transfer Master

**POST** `/{language}/game/room/transfer-master`

Transfer master role to another participant.

**Request Parameters**:
- `target_cyclist_id`: User ID of new master

**Response**: JSON status

#### Generate QR Code

**GET** `/{language}/game/room/{room_code}/qr`

Generate QR code for room sharing.

**Response**: PNG image with QR code

## Technical Details

### Session Management

Game state is stored in Django sessions:

- **Single-player**: State stored in user session
- **Multi-player**: State synchronized via `GameRoom` model
- **Session Keys**: Used for master identification
- **Expiration**: Sessions expire based on Django settings

### Data Flow

1. **Assignment**: User assigns cyclist to device
   - Stored in session: `device_assignments`
   - Format: `{"device_name": "cyclist_user_id"}`

2. **Game Start**: User clicks "Start Game"
   - Current distances fetched from `Cyclist.distance_total`
   - Stored in session: `start_distances`
   - Format: `{"cyclist_user_id": start_distance}`

3. **Progress Calculation**: Real-time updates
   - Current distance: `Cyclist.distance_total`
   - Progress: `current_distance - start_distance`
   - Coins: `progress × coin_conversion_factor`

4. **Game Stop**: User clicks "Stop Game"
   - Current distances stored: `stop_distances`
   - Results frozen
   - Final statistics calculated

### HTMX Integration

The game uses HTMX for real-time updates without full page reloads:

- **Results Table**: Updates every 10 seconds during active game
- **Target Display**: Updates every 3 seconds in rooms
- **Assignment Changes**: Trigger immediate table refresh
- **Game Buttons**: Update based on game state

### Room Code Generation

Room codes are 8-character alphanumeric strings:

- **Character Set**: Uppercase letters and numbers
- **Excluded Characters**: 0, O, I, 1 (to avoid confusion)
- **Uniqueness**: Guaranteed by database constraint
- **Format**: `[A-Z2-9]{8}`

### Winner Detection

When a cyclist reaches the target distance:

1. **Detection**: Checked on every results table update
2. **Announcement**: Popup modal appears with winner information
3. **Sound**: Winner sound is played
4. **Visual**: Winner marked in results table
5. **Continuation**: Game continues (no auto-stop)

### Models

#### GameRoom

Stores shared game room state:

```python
{
    "room_code": "ABC123XY",              # Unique 8-character code
    "master_session_key": "...",          # Session key of master
    "is_active": true,                    # Room status
    "device_assignments": {               # Cyclist-device mappings
        "device1": "cyclist1",
        "device2": "cyclist2"
    },
    "start_distances": {                  # Distances at game start
        "cyclist1": 100.5,
        "cyclist2": 200.0
    },
    "stop_distances": {                   # Distances at game stop
        "cyclist1": 150.2,
        "cyclist2": 250.5
    },
    "is_game_stopped": false,             # Game status
    "announced_winners": [],              # Winners who reached target
    "current_target_km": 200.0,           # Current target
    "active_sessions": [...],             # Active session keys
    "session_to_cyclist": {...}          # Session-cyclist mapping
}
```

#### GameSession

Tracks individual game sessions (Django Session model extended):

- Session key
- Room code (if in room)
- Expiration date
- Game data

## Permissions

### Master Permissions

The room creator (master) can:

- Modify target kilometers
- Clear all assignments
- Transfer master role to another participant
- End the room
- Start/stop the game

### Participant Permissions

Regular participants can:

- Add/remove own assignments
- View game state
- Leave the room
- View results

## Best Practices

### Setting Up a Game

1. **Prepare Cyclists**: Ensure all cyclists are registered
2. **Prepare Devices**: Verify devices are active and reporting
3. **Set Clear Targets**: Define target distances before starting
4. **Test Assignments**: Verify assignments work correctly
5. **Communicate Rules**: Explain game rules to participants

### Running Multi-Player Games

1. **Create Room Early**: Create room before participants arrive
2. **Share Code Clearly**: Display room code prominently
3. **Use QR Codes**: Generate QR codes for easy joining
4. **Monitor Progress**: Check results table regularly
5. **Manage Master Role**: Transfer if creator leaves
6. **Clean Up**: End rooms when finished

### Performance Optimization

1. **Limit Participants**: Keep room size reasonable (< 50 participants)
2. **Monitor Sessions**: Clean up expired sessions regularly
3. **Database Indexing**: Ensure proper indexes on GameRoom fields
4. **HTMX Caching**: Use appropriate cache headers

## Troubleshooting

### Room Not Found

**Symptoms**: Error when joining room

**Solutions**:
- Verify the 8-character code is correct
- Check if the room was ended
- Ensure you're using the correct URL format
- Verify room is still active

### Synchronization Issues

**Symptoms**: Participants see different game states

**Solutions**:
- Refresh the page to re-sync
- Check if you're still in the room (look for room code display)
- Verify your session is active
- Check network connectivity

### Master Transfer Fails

**Symptoms**: Cannot transfer master role

**Solutions**:
- Ensure the target cyclist has an assignment
- Check that the cyclist is in the `session_to_cyclist` mapping
- Verify the room is still active
- Ensure you are the current master

### Game Not Starting

**Symptoms**: Start button doesn't work

**Solutions**:
- Verify at least one assignment exists
- Check browser console for errors
- Ensure session is valid
- In rooms: Verify you are the master

### Results Not Updating

**Symptoms**: Results table shows old data

**Solutions**:
- Check HTMX is working (browser console)
- Verify game is active
- Refresh the page
- Check network requests in browser dev tools

### Assignment Issues

**Symptoms**: Cannot assign cyclist to device

**Solutions**:
- Verify cyclist exists and is active
- Check device is available
- Ensure no duplicate assignments
- Check browser console for errors

## Future Enhancements

Potential improvements planned:

- **Team-based Challenges**: Group cyclists into teams
- **Historical Statistics**: Track game history and statistics
- **Achievement System**: Badges and achievements
- **Custom Game Modes**: Different game types
- **Leaderboard Integration**: Link to main leaderboard
- **Export Results**: Download game results as CSV/PDF
- **Replay Mode**: Review past games
- **Tournament System**: Multi-round competitions

## Related Documentation

- [Installation Guide](../getting-started/installation.md)
- [Admin GUI Manual](../admin/index.md) - Manage game rooms and sessions
- [API Reference](../api/index.md) - Complete API documentation
