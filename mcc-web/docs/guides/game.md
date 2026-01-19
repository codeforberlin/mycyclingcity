# Kilometer-Challenge (Game)

## Overview

The Kilometer-Challenge is a gamification feature of MyCyclingCity that allows users to create competitive challenges by assigning cyclists to devices and tracking their progress toward a target distance.

## Features

### Single-Player Mode

In single-player mode, users can:

- Assign cyclists to devices
- Set a target distance (optional)
- Start the game to track progress
- View real-time results with distance gained and coins earned
- Stop the game to freeze results

### Multi-Player Mode (Game Rooms)

Game rooms allow multiple players to participate in the same challenge:

- **Room Creation**: Create a room with a unique 8-character code
- **Room Joining**: Join existing rooms by entering the room code
- **Master System**: The room creator becomes the "master" who can:
  - Modify target kilometers
  - Clear all assignments
  - Transfer master role to another participant
  - End the room
- **Real-time Synchronization**: All participants see the same game state
- **QR Code**: Generate QR codes for easy room sharing

## How to Play

### Basic Workflow

1. **Assign Cyclists to Devices**: Select a cyclist and assign them to a device
2. **Set Target (Optional)**: Set a target distance in kilometers
3. **Start Game**: Click "Spiel starten" to begin tracking
4. **Monitor Progress**: Watch real-time updates of distance and coins
5. **Stop Game**: Click "Spiel stoppen" to freeze results

### Game Rooms

1. **Create Room**: Click "Raum erstellen" to create a new game room
2. **Share Code**: Share the 8-character room code with other players
3. **Join Room**: Other players enter the code at `/de/game/room/join`
4. **Play Together**: All participants see synchronized game state
5. **Master Controls**: Only the master can modify settings

## Technical Details

### Session Management

- Game state is stored in Django sessions
- In game rooms, state is synchronized via `GameRoom` model
- Active sessions are tracked for master transfer functionality

### Data Flow

1. Assignments are stored in session: `device_assignments`
2. Start distances are captured when game starts
3. Current distances are fetched from `Cyclist.distance_total`
4. Progress is calculated as: `current_distance - start_distance`
5. Coins are calculated using `coin_conversion_factor`

### HTMX Integration

The game uses HTMX for real-time updates:

- Results table updates every 10 seconds during active game
- Target kilometer display updates every 3 seconds in rooms
- Assignment changes trigger immediate table refresh

### API Endpoints

- `POST /de/game/htmx/assignments` - Add/remove assignments
- `GET /de/game/htmx/results` - Get results table
- `GET /de/game/htmx/target-km` - Get target kilometer display
- `POST /de/game/api/game/start` - Start/stop game
- `POST /de/game/room/create` - Create game room
- `POST /de/game/room/join` - Join game room
- `POST /de/game/room/end` - End game room (master only)
- `POST /de/game/room/transfer-master` - Transfer master role

## Models

### GameRoom

Stores shared game room state:

- `room_code`: Unique 8-character code (uppercase alphanumeric, excludes 0, O, I, 1)
- `master_session_key`: Session key of the room master
- `is_active`: Whether the room is active
- `device_assignments`: JSON mapping of device names to cyclist user_ids
- `start_distances`: JSON mapping of cyclist user_ids to start distances
- `stop_distances`: JSON mapping of cyclist user_ids to stop distances
- `is_game_stopped`: Whether the game is stopped
- `announced_winners`: List of user_ids who have reached the target
- `current_target_km`: Current target distance in kilometers
- `active_sessions`: List of session keys currently in the room
- `session_to_cyclist`: JSON mapping for master transfer functionality

## Permissions

### Master Permissions

- Modify target kilometers
- Clear all assignments
- Transfer master role
- End the room

### Participant Permissions

- Add/remove own assignments
- View game state
- Leave the room

## Winner Detection

When a cyclist reaches the target distance:

- A popup modal appears with winner information
- Winner sound is played
- Winner is marked in the results table
- Game continues (no auto-stop)

## Best Practices

1. **Set Clear Targets**: Define target distances before starting
2. **Coordinate in Rooms**: Use game rooms for group challenges
3. **Monitor Progress**: Check results table regularly
4. **Master Management**: Transfer master role if creator leaves
5. **Room Cleanup**: End rooms when finished to free resources

## Troubleshooting

### Room Not Found

- Verify the 8-character code is correct
- Check if the room was ended
- Ensure you're using the correct URL format

### Synchronization Issues

- Refresh the page to re-sync
- Check if you're still in the room (look for room code display)
- Verify your session is active

### Master Transfer Fails

- Ensure the target cyclist has an assignment
- Check that the cyclist is in the `session_to_cyclist` mapping
- Verify the room is still active

## Future Enhancements

Potential improvements:

- Team-based challenges
- Historical game statistics
- Achievement system
- Custom game modes
- Integration with leaderboard
