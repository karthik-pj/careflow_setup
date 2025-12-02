import streamlit as st
from database import init_db
import base64
from pathlib import Path

st.set_page_config(
    page_title="Careflow Setup",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    .careflow-subtitle {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        color: #666;
        margin-top: 5px;
        letter-spacing: 0.5px;
    }
    
    .stApp {
        font-family: 'Inter', sans-serif;
    }
    
    .stSidebar {
        background-color: #f8fafc;
    }
    
    .stSidebar .stRadio > label {
        font-family: 'Inter', sans-serif;
    }
    
    div[data-testid="stSidebarHeader"] {
        padding-top: 1rem;
    }
    
    .main-header {
        color: #2e5cbf;
        font-family: 'Inter', sans-serif;
    }
    
    .stButton > button {
        font-family: 'Inter', sans-serif;
    }
    
    .stMetric {
        background-color: #f8fafc;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #2e5cbf;
    }
    
    .logo-container {
        padding: 15px 0;
        margin-bottom: 5px;
        text-align: center;
    }
    
    .logo-container img {
        width: 100%;
        max-width: 200px;
        height: auto;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

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

logo_path = Path("attached_assets/CAREFLOW LOGO-Color_1764612034940.png")
if logo_path.exists():
    with open(logo_path, "rb") as f:
        logo_data = base64.b64encode(f.read()).decode()
    st.sidebar.markdown(
        f'<div class="logo-container"><img src="data:image/png;base64,{logo_data}" alt="Careflow"></div>',
        unsafe_allow_html=True
    )
else:
    st.sidebar.markdown(
        '<div style="font-family: Inter, sans-serif; font-size: 1.8rem; font-weight: 700; '
        'background: linear-gradient(135deg, #2e5cbf 0%, #008ed3 100%); '
        '-webkit-background-clip: text; -webkit-text-fill-color: transparent; '
        'background-clip: text; margin-bottom: 0.5rem;">CareFlow</div>',
        unsafe_allow_html=True
    )

st.sidebar.markdown('<div class="careflow-subtitle" style="font-weight: 700; text-transform: uppercase; text-align: center;">CAREFLOW SETUP</div>', unsafe_allow_html=True)
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
