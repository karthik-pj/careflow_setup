import streamlit as st
from database import init_db
import base64
from pathlib import Path
from utils.translations import t, LANGUAGE_NAMES

st.set_page_config(
    page_title="Careflow Setup",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize theme and language in session state
if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = True
if 'language' not in st.session_state:
    st.session_state.language = "en"

# Theme-specific CSS variables
if st.session_state.dark_mode:
    theme_css = """
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
    
    /* Sidebar styling - Dark */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f2e 0%, #0e1117 100%);
        border-right: 1px solid var(--cf-border);
    }
    
    section[data-testid="stSidebar"] * {
        color: var(--cf-text) !important;
    }
    """
else:
    theme_css = """
    :root {
        --cf-primary: #2563eb;
        --cf-primary-dark: #1d4ed8;
        --cf-primary-light: #3b82f6;
        --cf-accent: #0ea5e9;
        --cf-text: #1e293b;
        --cf-text-light: #64748b;
        --cf-bg: #ffffff;
        --cf-bg-subtle: #f8fafc;
        --cf-border: #e2e8f0;
        --cf-success: #10b981;
        --cf-warning: #f59e0b;
        --cf-error: #ef4444;
    }
    
    /* Sidebar styling - Light */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        border-right: 1px solid var(--cf-border);
    }
    
    section[data-testid="stSidebar"] * {
        color: var(--cf-text) !important;
    }
    """

# Inject theme CSS first
st.markdown(f"<style>{theme_css}</style>", unsafe_allow_html=True)

# Common CSS (theme-independent)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
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
        padding: 16px 0 8px 0;
        text-align: left;
        padding-left: 8px;
    }
    
    .logo-container img {
        width: auto;
        max-width: 140px;
        height: auto;
        display: inline-block;
    }
    
    .careflow-subtitle {
        font-family: 'Inter', sans-serif;
        font-size: 0.65rem;
        color: var(--cf-text-light);
        margin-top: 4px;
        letter-spacing: 1px;
        font-weight: 500;
        text-align: left;
        padding-left: 8px;
        opacity: 0.7;
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

# Header controls styling - fixed position in upper right
st.markdown("""
<style>
    .header-controls {
        position: fixed;
        top: 14px;
        right: 60px;
        z-index: 999999;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    
    .header-controls select {
        background: transparent;
        border: 1px solid var(--cf-border);
        border-radius: 6px;
        padding: 6px 28px 6px 10px;
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        font-weight: 500;
        color: var(--cf-text);
        cursor: pointer;
        appearance: none;
        -webkit-appearance: none;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: right 8px center;
        min-width: 100px;
    }
    
    .header-controls select:hover {
        border-color: var(--cf-primary);
    }
    
    .header-controls select:focus {
        outline: none;
        border-color: var(--cf-primary);
        box-shadow: 0 0 0 2px rgba(46, 92, 191, 0.2);
    }
    
    .theme-toggle-btn {
        background: transparent;
        border: 1px solid var(--cf-border);
        border-radius: 6px;
        padding: 6px 10px;
        cursor: pointer;
        font-size: 1rem;
        color: var(--cf-text);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
    }
    
    .theme-toggle-btn:hover {
        border-color: var(--cf-primary);
        background: var(--cf-bg-subtle);
    }
</style>
""", unsafe_allow_html=True)

# Language and theme controls in header
lang_options = list(LANGUAGE_NAMES.keys())
current_lang = st.session_state.language
theme_icon = "🌙" if st.session_state.dark_mode else "☀️"

# Build language options HTML
lang_options_html = "".join([
    f'<option value="{code}" {"selected" if code == current_lang else ""}>{LANGUAGE_NAMES[code]}</option>'
    for code in lang_options
])

st.markdown(f"""
<div class="header-controls">
    <select id="langSelect" onchange="handleLangChange(this.value)">
        {lang_options_html}
    </select>
    <button class="theme-toggle-btn" onclick="handleThemeToggle()" title="Toggle Dark/Light Mode">
        {theme_icon}
    </button>
</div>
<script>
    function handleLangChange(lang) {{
        const params = new URLSearchParams(window.location.search);
        params.set('lang', lang);
        window.location.search = params.toString();
    }}
    function handleThemeToggle() {{
        const params = new URLSearchParams(window.location.search);
        params.set('toggle_theme', 'true');
        window.location.search = params.toString();
    }}
</script>
""", unsafe_allow_html=True)

# Handle URL parameters for language and theme changes
query_params = st.query_params
if 'lang' in query_params:
    new_lang = query_params['lang']
    if new_lang in lang_options and new_lang != st.session_state.language:
        st.session_state.language = new_lang
        st.query_params.clear()
        st.rerun()
    elif new_lang == st.session_state.language:
        st.query_params.clear()

if 'toggle_theme' in query_params:
    st.session_state.dark_mode = not st.session_state.dark_mode
    st.query_params.clear()
    st.rerun()

# Sidebar logo
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

# Navigation with translations
nav_items = [
    ("Dashboard", "nav_dashboard"),
    ("Buildings & Floor Plans", "nav_buildings"),
    ("Coverage Zones", "nav_coverage_zones"),
    ("Alert Zones", "nav_alert_zones"),
    ("Gateway Planning", "nav_gateway_planning"),
    ("Gateways", "nav_gateways"),
    ("Beacons", "nav_beacons"),
    ("MQTT Configuration", "nav_mqtt"),
    ("Live Tracking", "nav_live_tracking"),
    ("History Playback", "nav_history"),
    ("Import/Export", "nav_import_export"),
    ("Signal Monitor", "nav_signal_monitor")
]

page = st.sidebar.radio(
    "Navigation",
    [item[0] for item in nav_items],
    format_func=lambda x: t(next(item[1] for item in nav_items if item[0] == x)),
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
            st.sidebar.success(t("signal_processor_running"))
        elif heartbeat:
            st.sidebar.warning(f"{t('signal_processor_stale')} ({int((datetime.utcnow() - heartbeat).total_seconds())}s)")
        else:
            st.sidebar.success(t("signal_processor_running"))
    else:
        st.sidebar.warning(t("signal_processor_stopped"))
except Exception:
    st.sidebar.info(t("signal_processor_not_init"))


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
