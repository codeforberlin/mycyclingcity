# Getting Started

Welcome to the MyCyclingCity project documentation.

## Project Overview

MyCyclingCity is a Django-based web application for tracking cycling activities, managing groups, and displaying leaderboards.

## Architecture

The project is organized into several Django apps:

- **api**: Core API and models for cyclists, groups, events, and mileage tracking
- **map**: OSM/Leaflet map visualization
- **ranking**: Ranking tables and statistical lists
- **leaderboard**: Animated high-score tiles and leaderboard displays
- **kiosk**: Kiosk device management
- **iot**: IoT device management
- **game**: Kilometer challenge game
- **mgmt**: Management and analytics

## Quick Links

- [Installation Guide](installation.md) - Set up the development environment
- [Configuration](configuration.md) - Configure the application
- [API Reference](../api/index.md) - Complete API documentation
- [Admin GUI Manual](../admin/index.md) - Django Admin interface guide

## Contributing

All code, comments, and documentation must be in English.

## Version

Current version: The project uses a version detection mechanism that:
- First checks for a `version.txt` file in the project root
- Falls back to `git describe --tags --always --dirty` if the file doesn't exist
- The version is accessible via Django settings: `settings.get_project_version()`
