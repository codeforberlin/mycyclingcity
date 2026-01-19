# Live Map - User Guide

## Overview

The MyCyclingCity Live Map is an interactive map application that displays real-time cycling activity, showing the positions of active cyclists, travel tracks, milestones, and group progress. The map uses OpenStreetMap (OSM) and Leaflet for visualization and updates automatically every 20 seconds.

## Table of Contents

- [Features](#features)
- [Getting Started](#getting-started)
- [User Interface](#user-interface)
- [Map Features](#map-features)
- [Filtering and Views](#filtering-and-views)
- [Modes](#modes)
- [API Reference](#api-reference)
- [Tips and Best Practices](#tips-and-best-practices)
- [Troubleshooting](#troubleshooting)

## Features

### Core Functionality

- **Real-time Tracking**: Live positions of active cyclists on the map
- **Travel Tracks**: Visual representation of cycling routes (GPX-based)
- **Milestones**: Markers showing progress along travel tracks
- **Group Avatars**: Visual indicators for groups on the map
- **Auto-Update**: Automatic refresh every 20 seconds
- **Multiple Views**: Groups, Devices, and Cyclists views
- **Filtering**: Filter by group type, search by name
- **Mobile Support**: Optimized interface for mobile devices
- **Kiosk Mode**: Full-screen display mode for public displays

### Map Elements

- **Group Avatars**: Circular markers showing group positions
- **Travel Tracks**: Colored polylines showing cycling routes
- **Milestones**: Flag markers indicating progress points
- **Start/End Markers**: Markers showing track start and end points
- **Active Cyclists**: Real-time position indicators

## Getting Started

### Accessing the Map

Navigate to: `/{language}/map/` (e.g., `/de/map/` or `/en/map/`)

### First Steps

1. **View the Map**: The map loads automatically with all active groups
2. **Explore Tracks**: Click on travel tracks to see route details
3. **Check Milestones**: View milestone markers along tracks
4. **Filter Groups**: Use the filter dropdown to focus on specific groups
5. **Switch Views**: Toggle between Groups, Devices, and Cyclists views

## User Interface

### Main Map View

The map interface consists of:

#### Map Area

- **Interactive Map**: OSM-based map with zoom and pan controls
- **Zoom Controls**: +/- buttons in the top-left corner
- **Layer Control**: Toggle visibility of routes and tracks
- **Group Avatars**: Clickable markers showing group positions
- **Travel Tracks**: Colored lines showing cycling routes

#### Control Panel

Located on the right side (desktop) or bottom (mobile):

- **Display Type Selector**: Switch between Groups, Devices, and Cyclists
- **Group Type Filter**: Filter by group type (e.g., classes, teams)
- **Search Box**: Search for specific groups, devices, or cyclists
- **View Switcher**: Toggle between map and table view (mobile)

#### Info Panel

- **Group Information**: Details about selected groups
- **Distance Statistics**: Total kilometers and session kilometers
- **Member Lists**: Direct and nested group members
- **Event Information**: Active events and participants

### Mobile Interface

On mobile devices, the interface adapts:

- **Full-screen Map**: Map takes up the entire screen
- **Bottom Panel**: Collapsible panel with controls and information
- **View Switcher**: Button to toggle between map and table view
- **Layer Control**: Slide-out panel for route visibility
- **Touch-friendly**: Optimized for touch interactions

### Kiosk Mode

For public displays:

- **Full-screen Display**: No browser chrome
- **Auto-refresh**: Continuous updates
- **Large Text**: Readable from distance
- **Minimal Controls**: Simplified interface

## Map Features

### Travel Tracks

Travel tracks are GPX-based routes displayed on the map:

- **Visualization**: Colored polylines showing the route
- **Start/End Markers**: Clear markers indicating track boundaries
- **Group Association**: Tracks are linked to specific groups
- **Progress Tracking**: Shows how far groups have traveled along tracks

**How to Use**:
1. Tracks are automatically displayed when groups are active
2. Click on a track to see details
3. Use the layer control to show/hide specific tracks
4. Toggle "All Routes" to show/hide all tracks at once

### Milestones

Milestones mark important points along travel tracks:

- **Visual Markers**: Flag icons on the map
- **Progress Indicators**: Show group progress toward destinations
- **Achievement Tracking**: Record when groups reach milestones
- **Popup Notifications**: Automatic popups when milestones are reached

**How to Use**:
1. Milestones appear automatically along tracks
2. Click on a milestone marker to see details
3. Popups appear when groups reach milestones
4. Check milestone status in the info panel

### Group Avatars

Group avatars show the current position of groups on the map:

- **Position Markers**: Circular markers with group avatars
- **Real-time Updates**: Positions update every 20 seconds
- **Clickable**: Click to see group details
- **Color Coding**: Different colors for different group types

**How to Use**:
1. Avatars appear automatically for active groups
2. Click on an avatar to see group information
3. Hover (desktop) to see quick details
4. Filter to show only specific groups

### Active Cyclists

Real-time position tracking for individual cyclists:

- **Position Indicators**: Markers showing cyclist locations
- **Device Association**: Linked to ESP32 tachometer devices
- **Live Updates**: Positions update as data is received
- **Session Tracking**: Shows distance traveled in current session

## Filtering and Views

### Display Types

Switch between different views:

#### Groups View

- Shows all groups with their hierarchy
- Displays parent and child groups
- Shows total distance and session distance
- Filter by group type

#### Devices View

- Lists all active ESP32 devices
- Shows device names and locations
- Displays device statistics
- Filter by device status

#### Cyclists View

- Lists all active cyclists
- Shows individual distances
- Displays session kilometers
- Search by cyclist name

### Filtering Options

#### Group Type Filter

Filter groups by type:
- Select "All" to show all groups
- Choose specific group type (e.g., "Class", "Team")
- Filter applies to all views

#### Search Function

Search for specific items:
- Enter name in search box
- Results filter in real-time
- Works across all views
- Case-insensitive search

### URL Parameters

You can customize the map view using URL parameters:

- `?group_id=123` - Show specific group by ID
- `?group_name=Class%201a` - Show specific group by name
- `?show_cyclists=false` - Hide cyclists from view
- `?interval=30` - Set custom refresh interval (seconds)

**Example**:
```
/de/map/?group_id=5&interval=30
```

## Modes

### Standard Mode

Default mode for regular users:

- Full control panel
- All filtering options
- Interactive features
- Info panel visible

### Mobile Mode

Automatically activated on mobile devices:

- Touch-optimized interface
- Collapsible panels
- Simplified controls
- Full-screen map option

### Kiosk Mode

For public displays:

- Full-screen display
- Minimal controls
- Auto-refresh enabled
- Large, readable text

Access: `/{language}/map/kiosk/`

### Ticker Mode

Scrolling ticker view for displays:

- Continuous scrolling
- Group statistics
- Event information
- Minimal interaction

Access: `/{language}/map/ticker/`

## API Reference

### Map API Endpoints

#### Get Group Avatars

**GET** `/api/map/api/group-avatars/`

Get current positions and avatars for all groups.

**Response**:
```json
{
  "groups": [
    {
      "id": 1,
      "name": "Class 1a",
      "avatar_url": "/media/avatars/class1a.png",
      "latitude": 52.52,
      "longitude": 13.405,
      "distance_total": 150.5,
      "current_track_id": 5
    }
  ]
}
```

#### Get New Milestones

**GET** `/api/map/api/new-milestones/`

Get recently reached milestones.

**Response**:
```json
{
  "milestones": [
    {
      "id": 1,
      "name": "Berlin",
      "track_id": 5,
      "position_km": 100.0,
      "reached_by": ["Class 1a"],
      "reached_at": "2026-01-27T10:30:00Z"
    }
  ]
}
```

#### Get All Milestones Status

**GET** `/api/map/api/all-milestones-status/`

Get status of all milestones for all tracks.

**Response**:
```json
{
  "tracks": [
    {
      "id": 5,
      "name": "Berlin to Hamburg",
      "milestones": [
        {
          "id": 1,
          "name": "Berlin",
          "position_km": 0.0,
          "is_reached": true,
          "reached_by": ["Class 1a"]
        },
        {
          "id": 2,
          "name": "Hamburg",
          "position_km": 280.0,
          "is_reached": false,
          "reached_by": []
        }
      ]
    }
  ]
}
```

## Tips and Best Practices

### Optimizing Map Performance

1. **Filter When Possible**: Use filters to reduce the number of displayed items
2. **Close Unused Layers**: Hide tracks you're not viewing
3. **Adjust Refresh Interval**: Increase interval for better performance
4. **Use Mobile Mode**: Mobile mode is optimized for performance

### Viewing Specific Groups

1. **Use URL Parameters**: Bookmark specific group views
2. **Filter by Type**: Narrow down to relevant group types
3. **Search Function**: Quickly find groups by name
4. **Multiple Groups**: Use comma-separated IDs in URL

### Understanding the Data

1. **Total Distance**: Cumulative distance since start
2. **Session Distance**: Distance in current active session
3. **Track Progress**: Position along travel track in kilometers
4. **Milestone Status**: Check which milestones are reached

### Mobile Usage

1. **Full-screen Mode**: Use view switcher for full-screen map
2. **Layer Control**: Access via button in top-right
3. **Table View**: Switch to table for detailed information
4. **Touch Gestures**: Pinch to zoom, drag to pan

## Troubleshooting

### Map Not Loading

**Symptoms**: Blank map or error message

**Solutions**:
- Check internet connection
- Verify JavaScript is enabled
- Clear browser cache
- Try a different browser

### No Groups Visible

**Symptoms**: Map loads but no groups shown

**Solutions**:
- Check if groups are active
- Verify group visibility settings
- Remove filters that might hide groups
- Check if groups have assigned devices

### Positions Not Updating

**Symptoms**: Group positions stay the same

**Solutions**:
- Wait for next auto-refresh (20 seconds)
- Manually refresh the page
- Check if devices are sending data
- Verify network connectivity

### Milestones Not Showing

**Symptoms**: No milestone markers on map

**Solutions**:
- Verify tracks have milestones configured
- Check milestone visibility settings
- Ensure groups are on tracks
- Check layer visibility

### Performance Issues

**Symptoms**: Slow map rendering or lag

**Solutions**:
- Reduce number of visible groups
- Hide unused tracks
- Increase refresh interval
- Use mobile mode for better performance
- Close other browser tabs

### Mobile Display Issues

**Symptoms**: Map not filling screen or controls hidden

**Solutions**:
- Rotate device to landscape
- Use full-screen mode
- Check browser zoom level
- Clear browser cache
- Update browser to latest version

## Related Documentation

- [Installation Guide](../getting-started/installation.md)
- [Admin GUI Manual](../admin/index.md) - Configure tracks and milestones
- [API Reference](../api/index.md) - Complete API documentation
- [Game Guide](game.md) - Kilometer challenge system
