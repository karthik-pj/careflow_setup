# Careflow Setup

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
    ├── mqtt_handler.py      # MQTT client handler (subscription)
    ├── mqtt_publisher.py    # MQTT publisher for positions/alerts
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

## MQTT Publishing
The system can publish beacon positions and zone alerts to MQTT for integration with other applications:

### Position Messages (Topic: careflow/positions/{beacon_mac})
```json
{
  "type": "position",
  "beacon": {"mac": "AA:BB:CC:DD:EE:FF", "name": "Beacon Name", "resource_type": "Staff"},
  "location": {"floor_id": 1, "floor_name": "Floor 1", "building_name": "Building A", "x": 10.5, "y": 20.3, "accuracy": 2.5},
  "movement": {"speed": 0.5, "heading": 45.0, "velocity_x": 0.3, "velocity_y": 0.4},
  "timestamp": "2025-12-02T14:00:00.000Z"
}
```

### Alert Messages (Topic: careflow/alerts/{alert_type}/{zone_id})
```json
{
  "type": "zone_alert",
  "alert_type": "entry",
  "beacon": {"mac": "AA:BB:CC:DD:EE:FF", "name": "Beacon Name", "resource_type": "Staff"},
  "zone": {"id": 1, "name": "Restricted Area", "floor_name": "Floor 1"},
  "position": {"x": 10.5, "y": 20.3},
  "timestamp": "2025-12-02T14:00:00.000Z"
}
```

### Publisher Architecture
- Thread-safe singleton with async message queue
- Separate paho-mqtt client from subscription handler
- Non-blocking publish calls (queue with 1000 message capacity)
- Automatic connection management with callbacks

## MQTT Subscription (Moko MKGW-mini03 Gateways)
The system is configured to receive data from Moko MKGW-mini03 gateways (CFS/Careflow branded):

### Gateway Topic Structure
- **Publish (gateway sends data)**: `/cfs1/{gateway_mac}/send` or `/cfs2/{gateway_mac}/send`
- **Subscribe (gateway receives commands)**: `/cfs1/{gateway_mac}/receive` or `/cfs2/{gateway_mac}/receive`

### Gateway Message Format
```json
{
  "msg_id": 3070,
  "device_info": {
    "mac": "00e04c006bf1"
  },
  "data": [
    {
      "timestamp": 1764768812262,
      "timezone": 0,
      "type_code": 0,
      "type": "ibeacon",
      "rssi": -61,
      "connectable": 0,
      "mac": "b081845989f1",
      "uuid": "00000000000000000000000000000000",
      "major": 0,
      "minor": 0,
      "rssi_1m": 0
    }
  ]
}
```

### Multiple Gateway Subscription
Use comma-separated topics to subscribe to multiple gateways:
```
/cfs1/+/send, /cfs2/+/send
```

## Technical Notes
- Database sessions use context managers to prevent connection leaks
- Signal processor runs in background thread for continuous data ingestion
- Triangulation uses weighted least squares for position calculation
- Path loss model: RSSI to distance conversion with configurable calibration
- Movement vectors calculated from sequential position updates
- Floor plans support image overlay with coordinate mapping
- MQTT passwords stored securely via environment variable references
- Zone alerts are deduplicated within 30-second windows
- MQTT publisher uses async queue to avoid blocking DB transactions
- MQTT handler supports both `beacons` and `data` arrays in gateway messages

## Security
- MQTT passwords are NOT stored in database
- Password is referenced by environment variable name (e.g., MQTT_PASSWORD)
- Set the actual password as a Secret in the Secrets tab

## Branding
- Logo: Careflow horizontal logo displayed in sidebar (attached_assets/CAREFLOW LOGO-Color_1764612034940.png)
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
- December 2025: Added MQTT publishing for beacon positions and zone alerts with async queue architecture
