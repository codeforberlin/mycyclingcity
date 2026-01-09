# MyCyclingCity Documentation

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

## Getting Started

### Installation

```bash
# Activate virtual environment (adjust path to your environment)
# Example: source /home/roland/venv_mcc/bin/activate
# Or: source venv/bin/activate (if using project-local venv)

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic
```

### Running the Development Server

```bash
python manage.py runserver
```

## API Reference

See [API Reference](api_reference.md) for detailed API documentation.

## Official Manual

For the complete user manual and detailed guides, visit the [Official Manual](https://sai-lab.github.io/mcc-web/).

## Contributing

All code, comments, and documentation must be in English.

## Version

Current version: The project uses a version detection mechanism that:
- First checks for a `version.txt` file in the project root
- Falls back to `git describe --tags --always --dirty` if the file doesn't exist
- The version is accessible via Django settings: `settings.get_project_version()`


