import streamlit as st
from database import init_db

st.set_page_config(
    page_title="BLE Indoor Positioning System",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded"
)

try:
    init_db()
except Exception as e:
    st.error(f"Database initialization error: {e}")

if 'processor_init_attempted' not in st.session_state:
    st.session_state['processor_init_attempted'] = False

if not st.session_state['processor_init_attempted']:
    try:
        from utils.signal_processor import get_signal_processor
        from database import get_db_session, MQTTConfig
        
        with get_db_session() as session:
            mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
            if mqtt_config:
                processor = get_signal_processor()
                if not processor.is_running:
                    processor.start()
        
        st.session_state['processor_init_attempted'] = True
    except Exception as e:
        st.session_state['processor_init_attempted'] = True

st.sidebar.title("BLE Positioning System")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Buildings & Floor Plans",
        "Gateways",
        "Beacons",
        "MQTT Configuration",
        "Live Tracking",
        "History Playback",
        "Zones & Alerts",
        "Analytics",
        "Import/Export",
        "Calibration",
        "Signal Monitor"
    ],
    index=0
)

st.sidebar.markdown("---")

try:
    from utils.signal_processor import get_signal_processor
    processor = get_signal_processor()
    if processor.is_running:
        st.sidebar.success("Signal Processor: Running")
    else:
        st.sidebar.warning("Signal Processor: Stopped")
except Exception:
    st.sidebar.info("Signal Processor: Not initialized")

st.sidebar.markdown("---")
st.sidebar.info("Moko BLE Gateway Mini 03 Indoor Positioning System")

if page == "Dashboard":
    from views import dashboard
    dashboard.render()
elif page == "Buildings & Floor Plans":
    from views import buildings
    buildings.render()
elif page == "Gateways":
    from views import gateways
    gateways.render()
elif page == "Beacons":
    from views import beacons
    beacons.render()
elif page == "MQTT Configuration":
    from views import mqtt_config
    mqtt_config.render()
elif page == "Live Tracking":
    from views import live_tracking
    live_tracking.render()
elif page == "History Playback":
    from views import history_playback
    history_playback.render()
elif page == "Zones & Alerts":
    from views import zones_alerts
    zones_alerts.render()
elif page == "Analytics":
    from views import analytics
    analytics.render()
elif page == "Import/Export":
    from views import import_export
    import_export.render()
elif page == "Calibration":
    from views import calibration
    calibration.render()
elif page == "Signal Monitor":
    from views import signal_monitor
    signal_monitor.render()
