# MyCyclingCity Documentation

Welcome to the MyCyclingCity project documentation.

## Quick Start

- [Getting Started](getting-started/index.md) - Installation and setup guide
- [Admin GUI Manual](admin/index.md) - Django Admin interface guide
- [API Reference](api/index.md) - Complete API documentation

## Documentation Sections

### Getting Started

Learn how to set up and configure MyCyclingCity:

- [Installation Guide](getting-started/installation.md) - Set up the development environment
- [Configuration Guide](getting-started/configuration.md) - Configure the application

### Admin GUI Manual

Comprehensive guide to the Django Admin interface:

- [Admin GUI Manual](admin/index.md) - Manage cyclists, groups, devices, and more

### API Reference

Complete API documentation:

- [API Reference](api/index.md) - All API endpoints and models

### Guides

Detailed guides for specific features:

- [Live Map](guides/map.md) - Interactive map with real-time tracking
- [Game (Kilometer-Challenge)](guides/game.md) - Game room and challenge system
- [Kiosk Specification](guides/kiosk_specification.md) - Kiosk dashboard specification

## Project Overview

MyCyclingCity is a Django-based web application for tracking cycling activities, managing groups, and displaying leaderboards.

### Architecture

The project is organized into several Django apps:

- **api**: Core API and models for cyclists, groups, events, and mileage tracking
- **map**: OSM/Leaflet map visualization
- **ranking**: Ranking tables and statistical lists
- **leaderboard**: Animated high-score tiles and leaderboard displays
- **kiosk**: Kiosk device management
- **iot**: IoT device management
- **game**: Kilometer challenge game
- **mgmt**: Management and analytics

## Contributing

All code, comments, and documentation must be in English.

## Version

Current version: The project uses a version detection mechanism that:
- First checks for a `version.txt` file in the project root
- Falls back to `git describe --tags --always --dirty` if the file doesn't exist
- The version is accessible via Django settings: `settings.get_project_version()`
