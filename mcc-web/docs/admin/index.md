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
