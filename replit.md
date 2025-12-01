# Careflow BLE Indoor Positioning System

## Overview
A Streamlit-based indoor positioning system for managing Careflow BLE Gateway devices, BLE beacons, and real-time location tracking with triangulation on floor plans.

## Features

### Core Features
- **Building Management**: Create buildings with GPS coordinates and multi-story floor plans
- **Gateway Configuration**: Set up Careflow BLE gateways with precise positioning and calibration
- **Beacon Registration**: Register BLE beacons with resource types (Device, Staff, Asset, etc.)
- **MQTT Integration**: Connect to MQTT broker for receiving real-time RSSI signals
- **Triangulation Engine**: Calculate beacon positions from multiple gateway signals using weighted least squares
- **Live Tracking**: Visualize beacon positions and movement vectors on floor plans
- **Signal Monitor**: Debug and monitor incoming signals with manual testing capability
- **Background Processing**: Automatic signal ingestion and position calculation in background thread

### Phase 2 Features
- **Historical Playback**: Replay beacon movement patterns from historical data with adjustable speed
- **Zones & Alerts**: Define geofencing zones and monitor entry/exit alerts with acknowledgment
- **Analytics Dashboard**: Heatmaps, dwell time analysis, and traffic patterns by hour
- **Import/Export**: Bulk import and export of gateway, beacon, and zone configurations (JSON/CSV)
- **Calibration Wizard**: Improve triangulation accuracy using known beacon positions

## Project Structure
```
├── app.py                    # Main Streamlit application
├── database/
│   ├── __init__.py          # Database exports
│   └── models.py            # SQLAlchemy models with context manager
├── views/                    # Named 'views' to avoid Streamlit multipage detection
│   ├── dashboard.py         # System overview
│   ├── buildings.py         # Building and floor plan management
│   ├── gateways.py          # Gateway configuration
│   ├── beacons.py           # Beacon registration
│   ├── mqtt_config.py       # MQTT broker settings
│   ├── live_tracking.py     # Real-time visualization
│   ├── history_playback.py  # Historical playback with timeline controls
│   ├── zones_alerts.py      # Geofencing zones and alert management
│   ├── analytics.py         # Heatmaps, dwell time, traffic patterns
│   ├── import_export.py     # Bulk import/export functionality
│   ├── calibration.py       # Calibration wizard and accuracy analysis
│   └── signal_monitor.py    # Signal debugging
└── utils/
    ├── triangulation.py     # Position calculation algorithms
    ├── mqtt_handler.py      # MQTT client handler
    └── signal_processor.py  # Background signal processing
```

## Database Schema
- **Buildings**: Building information with GPS coordinates
- **Floors**: Floor plans with dimensions and images
- **Gateways**: Careflow BLE gateway configurations with positions
- **Beacons**: BLE beacon registrations with resource types
- **RSSISignals**: Raw RSSI signal data from gateways
- **Positions**: Calculated beacon positions with velocity vectors
- **MQTTConfig**: MQTT broker connection settings (password stored as env var reference)
- **Zones**: Geofencing zone definitions with alert configuration
- **ZoneAlerts**: Zone entry/exit alert events with acknowledgment status
- **CalibrationPoints**: Reference points for accuracy improvement

## Setup Steps
1. Add a building with floor plans
2. Configure Careflow BLE gateways with their positions on floor plans
3. Register BLE beacons to track
4. Configure MQTT broker connection (set password in Secrets tab)
5. Start signal processor and begin live tracking
6. (Optional) Define zones for geofencing alerts
7. (Optional) Create calibration points to improve accuracy

## Technical Notes
- Database sessions use context managers to prevent connection leaks
- Signal processor runs in background thread for continuous data ingestion
- Triangulation uses weighted least squares for position calculation
- Path loss model: RSSI to distance conversion with configurable calibration
- Movement vectors calculated from sequential position updates
- Floor plans support image overlay with coordinate mapping
- MQTT passwords stored securely via environment variable references
- Zone alerts are deduplicated within 30-second windows

## Security
- MQTT passwords are NOT stored in database
- Password is referenced by environment variable name (e.g., MQTT_PASSWORD)
- Set the actual password as a Secret in the Secrets tab

## Branding
- Logo: Careflow logo displayed in sidebar (attached_assets/careflow_logo.png)
- Color Scheme: Careflow Blue (#2e5cbf, #008ed3)
- Font: Inter (Google Fonts)
- Theme configured in .streamlit/config.toml

## Recent Changes
- December 2025: Initial implementation with full feature set
- December 2025: Fixed database session management with context managers
- December 2025: Added background signal processor for automatic data ingestion
- December 2025: Improved MQTT credential security using environment variables
- December 2025: Added Phase 2 features (history playback, zones/alerts, analytics, import/export, calibration)
- December 2025: Updated branding from Moko to Careflow with logo and color scheme
