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
    from pages import dashboard
    dashboard.render()
elif page == "Buildings & Floor Plans":
    from pages import buildings
    buildings.render()
elif page == "Gateways":
    from pages import gateways
    gateways.render()
elif page == "Beacons":
    from pages import beacons
    beacons.render()
elif page == "MQTT Configuration":
    from pages import mqtt_config
    mqtt_config.render()
elif page == "Live Tracking":
    from pages import live_tracking
    live_tracking.render()
elif page == "Signal Monitor":
    from pages import signal_monitor
    signal_monitor.render()
