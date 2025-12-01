# BLE Indoor Positioning System

## Overview
A Streamlit-based indoor positioning system for managing Moko BLE to WiFi Gateway Mini 03 devices, BLE beacons, and real-time location tracking with triangulation on floor plans.

## Features
- **Building Management**: Create buildings with GPS coordinates and multi-story floor plans
- **Gateway Configuration**: Set up Moko BLE gateways with precise positioning and calibration
- **Beacon Registration**: Register BLE beacons with resource types (Device, Staff, Asset, etc.)
- **MQTT Integration**: Connect to MQTT broker for receiving real-time RSSI signals
- **Triangulation Engine**: Calculate beacon positions from multiple gateway signals using weighted least squares
- **Live Tracking**: Visualize beacon positions and movement vectors on floor plans
- **Signal Monitor**: Debug and monitor incoming signals with manual testing capability
- **Background Processing**: Automatic signal ingestion and position calculation in background thread

## Project Structure
```
├── app.py                    # Main Streamlit application
├── database/
│   ├── __init__.py          # Database exports
│   └── models.py            # SQLAlchemy models with context manager
├── pages/
│   ├── dashboard.py         # System overview
│   ├── buildings.py         # Building and floor plan management
│   ├── gateways.py          # Gateway configuration
│   ├── beacons.py           # Beacon registration
│   ├── mqtt_config.py       # MQTT broker settings
│   ├── live_tracking.py     # Real-time visualization
│   └── signal_monitor.py    # Signal debugging
└── utils/
    ├── triangulation.py     # Position calculation algorithms
    ├── mqtt_handler.py      # MQTT client handler
    └── signal_processor.py  # Background signal processing
```

## Database Schema
- **Buildings**: Building information with GPS coordinates
- **Floors**: Floor plans with dimensions and images
- **Gateways**: Moko BLE gateway configurations with positions
- **Beacons**: BLE beacon registrations with resource types
- **RSSISignals**: Raw RSSI signal data from gateways
- **Positions**: Calculated beacon positions with velocity vectors
- **MQTTConfig**: MQTT broker connection settings (password stored as env var reference)

## Setup Steps
1. Add a building with floor plans
2. Configure Moko BLE gateways with their positions on floor plans
3. Register BLE beacons to track
4. Configure MQTT broker connection (set password in Secrets tab)
5. Start signal processor and begin live tracking

## Technical Notes
- Database sessions use context managers to prevent connection leaks
- Signal processor runs in background thread for continuous data ingestion
- Triangulation uses weighted least squares for position calculation
- Path loss model: RSSI to distance conversion with configurable calibration
- Movement vectors calculated from sequential position updates
- Floor plans support image overlay with coordinate mapping
- MQTT passwords stored securely via environment variable references

## Security
- MQTT passwords are NOT stored in database
- Password is referenced by environment variable name (e.g., MQTT_PASSWORD)
- Set the actual password as a Secret in the Secrets tab

## Recent Changes
- December 2025: Initial implementation with full feature set
- December 2025: Fixed database session management with context managers
- December 2025: Added background signal processor for automatic data ingestion
- December 2025: Improved MQTT credential security using environment variables
