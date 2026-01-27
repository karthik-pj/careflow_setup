# Careflow Setup

## Overview
Careflow is a Streamlit-based indoor positioning system designed for managing Careflow BLE Gateway devices and beacons. Its primary purpose is real-time location tracking using triangulation on uploaded floor plans. The system aims to provide accurate indoor positioning, enabling features like asset tracking, staff monitoring, and geofencing.

**Business Vision & Market Potential:** Careflow addresses the growing need for precise indoor location services in various sectors, including healthcare, logistics, and smart buildings. By offering a comprehensive solution from device management to real-time visualization and advanced analytics, Careflow aims to be a leading platform for indoor positioning.

**Key Capabilities:**
*   Manage buildings, floor plans, BLE gateways, and beacons.
*   Real-time beacon position tracking and visualization.
*   MQTT integration for signal ingestion and data publishing.
*   Advanced triangulation and signal processing for accuracy.
*   Features for historical playback, geofencing, and analytics.
*   Tools for gateway planning and calibration to optimize performance.

## User Preferences
I prefer detailed explanations and clear breakdowns of complex topics. I want an iterative development approach where I can review changes frequently. Please ask before making major changes or architectural decisions. Do not make changes to the `database/models.py` file without explicit instruction.

## System Architecture

### UI/UX Decisions
The application uses a Streamlit-based interface.
*   **Branding:** Careflow horizontal logo (attached_assets/CAREFLOW LOGO-Color_1764612034940.png) is displayed in the sidebar.
*   **Color Scheme:** Careflow Blue (`#2e5cbf`, `#008ed3`).
*   **Font:** Inter (Google Fonts).
*   **Live Tracking UX:** Auto-refresh is off by default to preserve zoom/pan state; a manual "Update Data" button is provided.

### Technical Implementations
*   **Core Application:** Built with Streamlit (`app.py`).
*   **Database:** SQLAlchemy ORM with context managers for session management.
    *   **Schema:** Includes tables for Buildings, Floors, Gateways, Beacons, RSSISignals, Positions, MQTTConfig, Zones, ZoneAlerts, CalibrationPoints, AlertZones, and CoverageZones.
*   **Background Processing:** A dedicated scheduler thread handles continuous position calculation, using Paho MQTT's internal thread for signal storage via callback. This uses a singleton pattern with `@st.cache_resource` and includes heartbeat monitoring.
*   **Triangulation Engine:**
    *   Utilizes Log-distance path loss model for RSSI to distance conversion.
    *   Employs Median RSSI filtering with IQR for robust signal aggregation.
    *   Applies Weighted trilateration, Kalman filtering, and Geometric intersection.
    *   Supports per-gateway calibration (`tx_power`, `path_loss_exponent`).
*   **Floor Plan Support:**
    *   GeoJSON-only workflow for architectural vector files (simplified from previous multi-format support).
    *   Consistent format used throughout for visualization, planning, and tracking.
*   **MQTT Publisher:** Thread-safe singleton with an async message queue for non-blocking publishing of beacon positions and zone alerts.
*   **Processing Settings:** Configurable refresh rate, signal window, RSSI smoothing, position smoothing (exponential), and stability threshold to prevent phantom drift.
*   **Security:** MQTT passwords are referenced by environment variables (e.g., `MQTT_PASSWORD`) and not stored in the database.

### Feature Specifications
*   **Building Management:** Create buildings and multi-story floor plans with GPS coordinates.
*   **Gateway Configuration:** Set up Careflow BLE gateways, including precise positioning and calibration.
*   **Beacon Registration:** Register BLE beacons with various resource types (Device, Staff, Asset).
*   **MQTT Integration:** Connect to an MQTT broker for real-time RSSI signal reception.
*   **Live Tracking:** Visualize beacon positions and movement vectors on floor plans.
*   **Signal Monitor:** Tool for debugging and monitoring incoming signals.
*   **Historical Playback:** Replay beacon movement patterns.
*   **Alert Zones:** Define geofencing zones with entry/exit/dwell time alerts. Supports polygon draw with room-snap functionality.
*   **Zones & Alerts:** Define geofencing zones with configurable alerts and acknowledgment.
*   **Analytics Dashboard:** Heatmaps, dwell time analysis, and traffic patterns.
*   **Import/Export:** Bulk import/export of configurations (JSON/CSV).
*   **Calibration Wizard:** Improve triangulation accuracy using known beacon positions.
*   **Gateway Planning:** Plan optimal gateway placement based on target accuracy, with auto-suggestion, coverage visualization, and export of installation guides.
*   **Coverage Zones:** Define polygonal areas on floor plans with specific target accuracy and priority levels. Supports polygon draw with room-snap functionality.
*   **Shared GeoJSON Renderer:** Consolidated utility (`utils/geojson_renderer.py`) for rendering floor plans, zones, gateways, and beacons across all views.

### System Design Choices
*   **Modularity:** The project is structured into `database`, `views`, and `utils` folders for clear separation of concerns.
*   **Scalability:** Background processing and async MQTT publishing are designed to handle real-time data streams without blocking the UI.
*   **Accuracy Focus:** Multiple triangulation algorithms and calibration features are integrated to achieve sub-meter accuracy with appropriate hardware.

## External Dependencies

*   **MQTT Broker:** For real-time RSSI signal ingestion and publishing of positions/alerts.
*   **Moko MKGW-mini03 Gateways (CFS/Careflow branded):** The system is configured to receive data from these specific BLE gateways.
*   **`paho-mqtt` library:** Used for MQTT client handling (subscription and publishing).
*   **Plotly:** For interactive data visualization in the UI (e.g., live tracking).
*   **Google Fonts (Inter):** For consistent typography.