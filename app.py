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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    :root {
        --cf-primary: #2e5cbf;
        --cf-primary-dark: #1d4ed8;
        --cf-primary-light: #3b82f6;
        --cf-accent: #008ed3;
        --cf-text: #fafafa;
        --cf-text-light: #a0aec0;
        --cf-bg: #0e1117;
        --cf-bg-subtle: #1a1f2e;
        --cf-border: #2d3748;
        --cf-success: #10b981;
        --cf-warning: #f59e0b;
        --cf-error: #ef4444;
    }
    
    .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f2e 0%, #0e1117 100%);
        border-right: 1px solid var(--cf-border);
    }
    
    section[data-testid="stSidebar"] * {
        color: var(--cf-text) !important;
    }
    
    section[data-testid="stSidebar"] .stRadio > label {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
    }
    
    div[data-testid="stSidebarHeader"] {
        padding-top: 1rem;
    }
    
    /* Logo container */
    .logo-container {
        padding: 10px 0;
        margin-bottom: 5px;
        text-align: center;
    }
    
    .logo-container img {
        width: 100%;
        max-width: 180px;
        height: auto;
        display: inline-block;
    }
    
    .careflow-subtitle {
        font-family: 'Inter', sans-serif;
        font-size: 0.7rem;
        color: var(--cf-text-light);
        margin-top: 8px;
        letter-spacing: 1.5px;
        font-weight: 600;
    }
    
    /* Headers */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        color: var(--cf-text);
        font-weight: 600;
    }
    
    h1 {
        font-size: 1.875rem;
        margin-bottom: 0.5rem;
    }
    
    /* Card styling */
    .cf-card {
        background: var(--cf-bg);
        border: 1px solid var(--cf-border);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        transition: box-shadow 0.2s ease;
    }
    
    .cf-card:hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    }
    
    .cf-card-header {
        font-family: 'Inter', sans-serif;
        font-size: 1rem;
        font-weight: 600;
        color: var(--cf-text);
        margin-bottom: 1rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid var(--cf-border);
    }
    
    /* Metric cards */
    .cf-metric {
        background: var(--cf-bg);
        border: 1px solid var(--cf-border);
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }
    
    .cf-metric-value {
        font-family: 'Inter', sans-serif;
        font-size: 2rem;
        font-weight: 700;
        color: var(--cf-primary);
        line-height: 1.2;
    }
    
    .cf-metric-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.8rem;
        color: var(--cf-text-light);
        font-weight: 500;
        margin-top: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Streamlit metric override */
    div[data-testid="stMetric"] {
        background: var(--cf-bg);
        border: 1px solid var(--cf-border);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }
    
    div[data-testid="stMetric"] label {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        color: var(--cf-text-light);
    }
    
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        color: var(--cf-primary);
    }
    
    /* Buttons */
    .stButton > button {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        border-radius: 8px;
        padding: 0.5rem 1.25rem;
        transition: all 0.2s ease;
        border: none;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
    }
    
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--cf-primary) 0%, var(--cf-primary-dark) 100%);
    }
    
    /* Form inputs */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > div {
        font-family: 'Inter', sans-serif;
        border-radius: 8px;
        border: 1px solid var(--cf-border);
    }
    
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus {
        border-color: var(--cf-primary);
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
    }
    
    /* Tables */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid var(--cf-border);
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        background: var(--cf-bg-subtle);
        border-radius: 8px;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        border-radius: 8px 8px 0 0;
        padding: 0.75rem 1.25rem;
    }
    
    /* Status indicators */
    .cf-status {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 20px;
        font-family: 'Inter', sans-serif;
        font-size: 0.8rem;
        font-weight: 500;
    }
    
    .cf-status-success {
        background: rgba(16, 185, 129, 0.1);
        color: var(--cf-success);
    }
    
    .cf-status-warning {
        background: rgba(245, 158, 11, 0.1);
        color: var(--cf-warning);
    }
    
    .cf-status-error {
        background: rgba(239, 68, 68, 0.1);
        color: var(--cf-error);
    }
    
    /* Dividers */
    hr {
        border: none;
        border-top: 1px solid var(--cf-border);
        margin: 1.5rem 0;
    }
    
    /* Info boxes */
    .stAlert {
        border-radius: 10px;
        font-family: 'Inter', sans-serif;
    }
    
    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--cf-bg-subtle);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--cf-border);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--cf-text-light);
    }
    
    /* Section headers */
    .cf-section-header {
        font-family: 'Inter', sans-serif;
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--cf-text);
        margin: 1.5rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid var(--cf-primary);
        display: inline-block;
    }
    
    /* Badge styling */
    .cf-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-family: 'Inter', sans-serif;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .cf-badge-primary {
        background: var(--cf-primary);
        color: white;
    }
    
    .cf-badge-secondary {
        background: var(--cf-bg-subtle);
        color: var(--cf-text-light);
        border: 1px solid var(--cf-border);
    }
</style>
""", unsafe_allow_html=True)

try:
    init_db()
except Exception as e:
    st.error(f"Database initialization error: {e}")

# Signal processor is manually started from MQTT Configuration page
# This prevents auto-connection attempts that could slow down the app

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
        "Coverage Zones",
        "Alert Zones",
        "Gateway Planning",
        "Gateways",
        "Beacons",
        "MQTT Configuration",
        "Live Tracking",
        "History Playback",
        "Import/Export",
        "Signal Monitor"
    ],
    index=0,
    key="main_navigation"
)

st.sidebar.markdown("---")

try:
    from utils.signal_processor import get_signal_processor
    from datetime import datetime, timedelta
    processor = get_signal_processor()
    processor.check_and_restart()
    if processor.is_running:
        heartbeat = processor.last_heartbeat
        if heartbeat and (datetime.utcnow() - heartbeat).total_seconds() < 10:
            st.sidebar.success("Signal Processor: Running")
        elif heartbeat:
            st.sidebar.warning(f"Signal Processor: Stale ({int((datetime.utcnow() - heartbeat).total_seconds())}s)")
        else:
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
elif page == "Coverage Zones":
    from views import coverage_zones
    coverage_zones.show()
elif page == "Alert Zones":
    from views import alert_zones
    alert_zones.render()
elif page == "Gateway Planning":
    from views import gateway_planning
    gateway_planning.render_gateway_planning()
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
elif page == "Import/Export":
    from views import import_export
    import_export.render()
elif page == "Signal Monitor":
    from views import signal_monitor
    signal_monitor.render()
