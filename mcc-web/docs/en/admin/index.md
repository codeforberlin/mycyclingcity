# Admin GUI Manual

This manual explains how to use the Django Admin interface for managing MyCyclingCity.

## Accessing the Admin Interface

1. Navigate to: `http://your-domain/admin/`
2. Log in with your superuser credentials
3. You'll see the admin dashboard with all available models

## Main Sections

The admin interface is organized into the following sections:

### MCC Core API & Models

Core functionality for cyclists, groups, and mileage tracking.

#### Group Types

- **Purpose**: Define types of groups (e.g., classes, teams)
- **Key Fields**:
  - `name`: Group type name
  - `description`: Description of the group type
  - `is_active`: Enable/disable group type
- **Usage**: Create group types before creating groups

#### Groups

- **Purpose**: Manage cycling groups (classes, teams, etc.)
- **Key Fields**:
  - `name`: Group name
  - `group_type`: Type of group
  - `school_name`: Associated school
  - `distance_total`: Total kilometers traveled
  - `is_active`: Active status
- **Features**:
  - View aggregated mileage
  - Track group progress
  - Manage group hierarchy (parent/child groups)

#### Cyclists

- **Purpose**: Manage individual cyclists
- **Key Fields**:
  - `user`: Associated Django user
  - `id_tag`: RFID tag identifier
  - `coin_conversion_factor`: Coins per kilometer
  - `distance_total`: Total kilometers
  - `coins_total`: Total coins earned
- **Features**:
  - Link cyclists to users
  - Configure coin conversion
  - View cycling statistics

#### Travel Tracks

- **Purpose**: Manage travel routes and tracks
- **Key Fields**:
  - `name`: Track name
  - `gpx_file`: GPX route file
  - `distance_km`: Track distance
  - `milestones`: Associated milestones
- **Usage**: Upload GPX files to create travel tracks

#### Milestones

- **Purpose**: Define milestones along travel tracks
- **Key Fields**:
  - `name`: Milestone name
  - `travel_track`: Associated track
  - `position_km`: Position on track
  - `is_locked`: Lock status
- **Features**:
  - Track group progress toward milestones
  - Award achievements

#### Events

- **Purpose**: Manage cycling events
- **Key Fields**:
  - `name`: Event name
  - `start_date`: Event start
  - `end_date`: Event end
  - `groups`: Participating groups
- **Usage**: Create and manage cycling events

### IoT Management

Device and firmware management for ESP32 devices.

#### Devices

- **Purpose**: Manage ESP32 tachometer devices
- **Key Fields**:
  - `name`: Device identifier
  - `display_name`: Human-readable name
  - `group`: Associated group
  - `distance_total`: Total device mileage
  - `last_active`: Last activity timestamp
- **Features**:
  - Monitor device status
  - View device statistics
  - Configure device settings

#### Device Configurations

- **Purpose**: Server-side device configuration
- **Key Fields**:
  - `device`: Associated device
  - `device_specific_api_key`: Device API key
  - `send_interval_seconds`: Data transmission interval
  - `wheel_size`: Wheel circumference
- **Features**:
  - Configure device parameters remotely
  - API key management
  - Configuration synchronization

#### Firmware Images

- **Purpose**: Manage firmware versions for OTA updates
- **Key Fields**:
  - `version`: Firmware version
  - `file`: Firmware binary
  - `is_active`: Active version
  - `release_notes`: Version notes
- **Usage**: Upload firmware for automatic device updates

#### Device Health

- **Purpose**: Monitor device health status
- **Key Fields**:
  - `device`: Associated device
  - `status`: Health status (online/offline/warning/error)
  - `last_heartbeat`: Last heartbeat timestamp
  - `consecutive_failures`: Error count
- **Features**:
  - Real-time device monitoring
  - Health status tracking
  - Error reporting

### MCC Game Interface

Game room and session management.

#### Game Rooms

- **Purpose**: Manage multiplayer game rooms
- **Key Fields**:
  - `room_code`: Unique room identifier
  - `is_active`: Room status
  - `master_session_key`: Master session
  - `device_assignments`: Cyclist-device mappings
- **Features**:
  - View active game rooms
  - Monitor room activity
  - Manage room state

#### Game Sessions

- **Purpose**: Track individual game sessions
- **Key Fields**:
  - `session_key`: Session identifier
  - `room_code`: Associated room
  - `expire_date`: Session expiration
- **Features**:
  - Monitor active sessions
  - Cleanup expired sessions
  - Debug game state

### Kiosk Management

Kiosk device and playlist management.

#### Kiosk Devices

- **Purpose**: Manage kiosk display devices
- **Key Fields**:
  - `uid`: Unique device identifier
  - `name`: Device name
  - `is_active`: Active status
- **Usage**: Configure kiosk displays

### Management (Mgmt)

System administration and monitoring functions.

#### Server Control

- **Purpose**: Control Gunicorn server (Start, Stop, Restart, Reload)
- **Access**: `/admin/server/`
- **Features**:
  - Display server status
  - Start/stop/restart server
  - Reload configuration (without restart)
  - Display server metrics
  - Perform health checks
- **Usage**: Only available for superusers

#### Log File Viewer

- **Purpose**: View application log files directly in Admin GUI
- **Access**: `/admin/logs/`
- **Features**:
  - Browse and filter log files
  - Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Search in logs
  - View rotated log files
  - Auto-refresh for live view
  - Select any log file from `logs/` directory
- **Available Logs**:
  - API Application Logs (`api.log`)
  - Management Application Logs (`mgmt.log`)
  - IoT Application Logs (`iot.log`)
  - Kiosk Application Logs (`kiosk.log`)
  - Game Application Logs (`game.log`)
  - Map Application Logs (`map.log`)
  - Leaderboard Application Logs (`leaderboard.log`)
  - Django Framework Logs (`django.log`)

#### Backup Management

- **Purpose**: Manage database backups
- **Access**: `/admin/backup/`
- **Features**:
  - Create backups
  - Display backup list (with size and date)
  - Download backups
  - Backup management
- **Usage**: Backups are stored in `backups/` directory

#### Gunicorn Configuration

- **Purpose**: Configure Gunicorn server via Admin GUI
- **Access**: `/admin/mgmt/gunicornconfig/`
- **Key Settings**:
  - `log_level`: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - `workers`: Number of worker processes (0 = automatic)
  - `threads`: Threads per worker
  - `worker_class`: Worker class (gthread, sync)
  - `bind`: Bind address and port
- **Features**:
  - Change configuration without environment variables
  - Server restart required after changes
  - Link to Server Control for restart

#### Logging Configuration

- **Purpose**: Configure application logging
- **Access**: `/admin/mgmt/loggingconfig/`
- **Features**:
  - Configure log level per logger
  - Enable/disable logging to database
  - Enable DEBUG/INFO logs in database
  - Enable/disable request logging

#### Performance Monitoring

- **Purpose**: Monitor system performance
- **Models**:
  - **Request Logs**: HTTP request logs with performance data
  - **Performance Metrics**: Aggregated performance metrics
  - **Alert Rules**: Rules for performance alerts
- **Features**:
  - Analyze request times
  - Identify slow requests
  - Track performance trends

#### Minecraft Control

- **Purpose**: Control Minecraft server and manage coin synchronization
- **Access**: `/admin/minecraft/`
- **Features**:
  - Start/stop bridge worker (coin synchronization)
  - Start/stop snapshot worker (status capture)
  - Manual synchronization of all players
  - Update scoreboard snapshot
  - Test RCON connection
  - Manage outbox events
  - Display player list with coin status
- **Documentation**: See [Minecraft Integration Documentation](minecraft.md)

### Historical Reports & Analytics

Historical reports and analytics.

#### Analytics Dashboard

- **Purpose**: Analyze historical data and create reports
- **Access**: `/admin/analytics/`
- **Features**:
  - Time series analysis
  - Group comparisons
  - Export functions
  - Hierarchy breakdown

#### Hierarchy Breakdown

- **Purpose**: Detailed hierarchy analysis
- **Access**: `/admin/analytics/hierarchy/`
- **Features**:
  - Visualize group hierarchy
  - Detailed statistics per level

### Session Management

Game session management and debugging.

#### Session Dashboard

- **Purpose**: Monitor and manage active game sessions
- **Access**: `/admin/game/session/dashboard/`
- **Features**:
  - Display active sessions
  - Edit session data
  - Manage sessions in rooms
  - Manage master sessions
  - Export session data as JSON

## Common Tasks

### Creating a New Cyclist

1. Navigate to **MCC Core API & Models** → **Cyclists**
2. Click **Add Cyclist**
3. Fill in required fields:
   - `user`: Select or create Django user
   - `id_tag`: Enter RFID tag ID
   - `coin_conversion_factor`: Set coins per kilometer
4. Click **Save**

### Assigning a Device to a Group

1. Navigate to **IoT Management** → **Devices**
2. Select the device
3. In the **Group** field, select the target group
4. Click **Save**

### Uploading Firmware

1. Navigate to **IoT Management** → **Firmware Images**
2. Click **Add Firmware Image**
3. Fill in:
   - `version`: Version number (e.g., "1.2.3")
   - `file`: Upload firmware binary (.bin)
   - `is_active`: Check if this is the active version
   - `release_notes`: Describe changes
4. Click **Save**

### Configuring Device Settings

1. Navigate to **IoT Management** → **Device Configurations**
2. Select or create configuration for a device
3. Configure:
   - `send_interval_seconds`: How often device sends data
   - `wheel_size`: Wheel circumference in cm
   - `device_specific_api_key`: Device authentication key
4. Click **Save**

### Viewing Device Health

1. Navigate to **IoT Management** → **Device Health**
2. View status for all devices:
   - **Green**: Online and healthy
   - **Yellow**: Warning (no recent activity)
   - **Red**: Error or offline
3. Click on a device to see detailed health information

### Managing Game Rooms

1. Navigate to **MCC Game Interface** → **Game Rooms**
2. View all active and inactive rooms
3. Click on a room to:
   - View room state
   - See participants
   - Monitor game progress
   - End room if needed

## Advanced Features

### Bulk Actions

Many admin pages support bulk actions:
1. Select multiple items using checkboxes
2. Choose an action from the dropdown
3. Click **Go**

### Filtering and Search

- **List Filters**: Use sidebar filters to narrow results
- **Search**: Use search boxes to find specific items
- **Date Hierarchy**: Click date links to filter by time period

### Inline Editing

Some models support inline editing:
- Edit related objects directly from the parent object
- Add new related objects without leaving the page

### Custom Actions

Some models have custom admin actions:
- **Delete Sessions**: Bulk delete game sessions
- **Export Data**: Export model data to CSV/JSON
- **Cleanup**: Remove expired or orphaned records

## Best Practices

1. **Regular Backups**: Always backup before bulk operations
2. **Test Changes**: Test configuration changes on a development system first
3. **Monitor Health**: Regularly check Device Health status
4. **Cleanup**: Periodically clean up expired sessions and old data
5. **Documentation**: Document custom configurations and changes

## Troubleshooting

### Cannot Access Admin

- Verify you're logged in as a superuser
- Check `ALLOWED_HOSTS` in settings
- Ensure `DEBUG=True` in development

### Changes Not Saving

- Check for validation errors (red text)
- Verify required fields are filled
- Check database permissions

### Device Not Appearing

- Verify device is registered in Devices
- Check Device Health status
- Ensure device has sent at least one heartbeat

## Related Documentation

- [Installation Guide](../getting-started/installation.md)
- [Configuration Guide](../getting-started/configuration.md)
- [API Reference](../api/index.md)
