import streamlit as st
from database import init_db
import base64
from pathlib import Path
from utils.translations import t, LANGUAGE_NAMES
from utils.auth import (
    is_logged_in, get_current_user, logout, ensure_demo_user,
    can_access_page, require_page_access
)

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
    
    /* Main app background - Dark */
    .stApp, .main, [data-testid="stAppViewContainer"] {
        background-color: #0e1117 !important;
    }
    
    .stApp > header {
        background-color: #0e1117 !important;
    }
    
    /* Main content text - Dark */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
    .stApp p, .stApp span, .stApp label, .stApp div {
        color: #fafafa !important;
    }
    
    .stApp .stMarkdown, .stApp [data-testid="stMarkdownContainer"] {
        color: #fafafa !important;
    }
    
    /* Sidebar styling - Dark */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f2e 0%, #0e1117 100%) !important;
        border-right: 1px solid #2d3748;
    }
    
    section[data-testid="stSidebar"] > div {
        background: transparent !important;
    }
    
    section[data-testid="stSidebar"] * {
        color: #fafafa !important;
    }
    
    /* Radio buttons (navigation) - Dark */
    section[data-testid="stSidebar"] .stRadio > div {
        background-color: transparent !important;
    }
    
    section[data-testid="stSidebar"] .stRadio label {
        color: #fafafa !important;
        background-color: transparent !important;
    }
    
    section[data-testid="stSidebar"] .stRadio label:hover {
        background-color: rgba(46, 92, 191, 0.2) !important;
    }
    
    section[data-testid="stSidebar"] .stRadio label[data-checked="true"] {
        background-color: rgba(46, 92, 191, 0.3) !important;
    }
    
    /* Input fields - Dark */
    .stTextInput input, .stSelectbox select, .stNumberInput input, .stTextArea textarea {
        background-color: #1a1f2e !important;
        color: #fafafa !important;
        border-color: #2d3748 !important;
    }
    
    /* Cards and containers - Dark */
    .stExpander, [data-testid="stExpander"] {
        background-color: #1a1f2e !important;
        border-color: #2d3748 !important;
    }
    
    /* Metrics - Dark */
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
        color: #fafafa !important;
    }
    
    /* Tables - Dark */
    .stDataFrame, .stTable {
        background-color: #1a1f2e !important;
    }
    
    /* Tabs - Dark */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        color: #a0aec0 !important;
    }
    
    .stTabs [aria-selected="true"] {
        color: #fafafa !important;
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
    
    /* Main app background - Light */
    .stApp, .main, [data-testid="stAppViewContainer"] {
        background-color: #ffffff !important;
    }
    
    .stApp > header {
        background-color: #ffffff !important;
    }
    
    /* Main content text - Light */
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
    .stApp p, .stApp span, .stApp label, .stApp div {
        color: #1e293b !important;
    }
    
    .stApp .stMarkdown, .stApp [data-testid="stMarkdownContainer"] {
        color: #1e293b !important;
    }
    
    /* Sidebar styling - Light */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%) !important;
        border-right: 1px solid #e2e8f0;
    }
    
    section[data-testid="stSidebar"] > div {
        background: transparent !important;
    }
    
    section[data-testid="stSidebar"] * {
        color: #1e293b !important;
    }
    
    /* Radio buttons (navigation) - Light */
    section[data-testid="stSidebar"] .stRadio > div {
        background-color: transparent !important;
    }
    
    section[data-testid="stSidebar"] .stRadio label {
        color: #1e293b !important;
        background-color: transparent !important;
    }
    
    section[data-testid="stSidebar"] .stRadio label:hover {
        background-color: rgba(37, 99, 235, 0.1) !important;
    }
    
    section[data-testid="stSidebar"] .stRadio label[data-checked="true"] {
        background-color: rgba(37, 99, 235, 0.15) !important;
    }
    
    /* Input fields - Light */
    .stTextInput input, .stSelectbox select, .stNumberInput input, .stTextArea textarea {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border-color: #e2e8f0 !important;
    }
    
    /* Cards and containers - Light */
    .stExpander, [data-testid="stExpander"] {
        background-color: #f8fafc !important;
        border-color: #e2e8f0 !important;
    }
    
    /* Metrics - Light */
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
        color: #1e293b !important;
    }
    
    /* Tables - Light */
    .stDataFrame, .stTable {
        background-color: #ffffff !important;
    }
    
    /* Tabs - Light */
    .stTabs [data-baseweb="tab-list"] {
        background-color: transparent !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        color: #64748b !important;
    }
    
    .stTabs [aria-selected="true"] {
        color: #1e293b !important;
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
        display: none !important;
    }
    
    section[data-testid="stSidebar"] > div {
        padding-top: 0 !important;
    }
    
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 0.5rem !important;
    }
    
    /* Logo container */
    .logo-container {
        padding: 0 0 4px 0;
        text-align: left;
        padding-left: 8px;
        margin-top: 0;
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
    
    /* Reduce top padding of main content */
    .main .block-container {
        padding-top: 0.5rem !important;
    }
    
    .stApp > header {
        height: 0 !important;
        min-height: 0 !important;
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
    ensure_demo_user()
except Exception as e:
    st.error(f"Database initialization error: {e}")

if not is_logged_in():
    from views import login
    login.render()
    st.stop()

# Signal processor is manually started from MQTT Configuration page
# This prevents auto-connection attempts that could slow down the app

# Header controls styling - fixed position in upper right (CareAlert style)
st.markdown("""
<style>
    .header-controls {
        position: fixed;
        top: 8px;
        right: 70px;
        z-index: 999999;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    
    .lang-selector-wrapper {
        display: flex;
        align-items: center;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        padding: 5px 10px;
        gap: 6px;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    
    .lang-selector-wrapper:hover {
        background: rgba(255, 255, 255, 0.08);
        border-color: rgba(255, 255, 255, 0.15);
    }
    
    .globe-icon {
        width: 14px;
        height: 14px;
        opacity: 0.7;
    }
    
    .header-controls select {
        background: transparent;
        border: none;
        padding: 0;
        padding-right: 14px;
        font-family: 'Inter', sans-serif;
        font-size: 0.8rem;
        font-weight: 400;
        color: var(--cf-text);
        cursor: pointer;
        appearance: none;
        -webkit-appearance: none;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='8' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: right 0 center;
        min-width: 60px;
    }
    
    .header-controls select:focus {
        outline: none;
    }
    
    .header-controls select option {
        background: #1a1f2e;
        color: #fafafa;
        padding: 6px;
    }
    
    .theme-toggle-btn {
        background: transparent;
        border: none;
        padding: 5px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
        opacity: 0.7;
    }
    
    .theme-toggle-btn:hover {
        opacity: 1;
    }
    
    .theme-toggle-btn svg {
        width: 16px;
        height: 16px;
    }
</style>
""", unsafe_allow_html=True)

# Language and theme controls in header
lang_options = list(LANGUAGE_NAMES.keys())
current_lang = st.session_state.language

# Build language options HTML
lang_options_html = "".join([
    f'<option value="{code}" {"selected" if code == current_lang else ""}>{LANGUAGE_NAMES[code]}</option>'
    for code in lang_options
])

# Globe SVG icon
globe_svg = '''<svg class="globe-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
    <circle cx="12" cy="12" r="10"/>
    <path d="M2 12h20"/>
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
</svg>'''

# Moon/Sun SVG icons
if st.session_state.dark_mode:
    theme_svg = '''<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>'''
else:
    theme_svg = '''<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="5"/>
        <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
    </svg>'''

st.markdown(f"""
<div class="header-controls">
    <div class="lang-selector-wrapper">
        {globe_svg}
        <select id="langSelect" onchange="handleLangChange(this.value)">
            {lang_options_html}
        </select>
    </div>
    <button class="theme-toggle-btn" onclick="handleThemeToggle()" title="Toggle Dark/Light Mode">
        {theme_svg}
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

st.sidebar.markdown('<div class="careflow-subtitle">SENSOR INFRASTRUCTURE</div>', unsafe_allow_html=True)

current_user = get_current_user()
if current_user:
    role_display = {'admin': 'Admin', 'operator': 'Operator', 'viewer': 'Viewer'}.get(current_user['role'], current_user['role'])
    st.sidebar.markdown(f"""
        <div style="background: rgba(46, 92, 191, 0.1); border: 1px solid rgba(46, 92, 191, 0.3); 
                    border-radius: 8px; padding: 10px 12px; margin: 8px 0;">
            <div style="font-size: 0.9em; font-weight: 500;">{current_user['full_name'] or current_user['username']}</div>
            <div style="font-size: 0.75em; opacity: 0.7;">{role_display}</div>
        </div>
    """, unsafe_allow_html=True)
    
    if st.sidebar.button("Logout", use_container_width=True):
        logout()
        st.rerun()

st.sidebar.markdown("---")

PAGE_ACCESS_MAP = {
    "Dashboard": "dashboard",
    "Buildings & Floor Plans": "buildings",
    "Alert Zones": "alert_zones",
    "Gateway Planning": "gateway_planning",
    "Gateways": "gateways",
    "Beacons": "beacons",
    "MQTT Configuration": "mqtt",
    "Live Monitoring": "live_tracking",
    "User Management": "user_management"
}

nav_items = [
    ("Dashboard", "nav_dashboard"),
    ("Buildings & Floor Plans", "nav_buildings"),
    ("Alert Zones", "nav_alert_zones"),
    ("Gateway Planning", "nav_gateway_planning"),
    ("Gateways", "nav_gateways"),
    ("Beacons", "nav_beacons"),
    ("MQTT Configuration", "nav_mqtt"),
    ("Live Monitoring", "nav_live_tracking")
]

if current_user and current_user['role'] == 'admin':
    nav_items.append(("User Management", "nav_user_management"))

filtered_nav_items = [
    item for item in nav_items
    if can_access_page(PAGE_ACCESS_MAP.get(item[0], item[0].lower().replace(' ', '_')))
]

if not filtered_nav_items:
    filtered_nav_items = [("Dashboard", "nav_dashboard")]

page = st.sidebar.radio(
    "Navigation",
    [item[0] for item in filtered_nav_items],
    format_func=lambda x: t(next(item[1] for item in filtered_nav_items if item[0] == x)),
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
            st.sidebar.markdown(f'<div style="background:#5ab5b0;color:white;padding:8px 12px;border-radius:4px;font-size:0.9em;"><span style="margin-right:6px;">●</span>{t("signal_processor_running")}</div>', unsafe_allow_html=True)
        elif heartbeat:
            st.sidebar.markdown(f'<div style="background:#e5a33d;color:white;padding:8px 12px;border-radius:4px;font-size:0.9em;"><span style="margin-right:6px;">●</span>{t("signal_processor_stale")} ({int((datetime.utcnow() - heartbeat).total_seconds())}s)</div>', unsafe_allow_html=True)
        else:
            st.sidebar.markdown(f'<div style="background:#5ab5b0;color:white;padding:8px 12px;border-radius:4px;font-size:0.9em;"><span style="margin-right:6px;">●</span>{t("signal_processor_running")}</div>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f'<div style="background:#c9553d;color:white;padding:8px 12px;border-radius:4px;font-size:0.9em;"><span style="margin-right:6px;">●</span>{t("signal_processor_stopped")}</div>', unsafe_allow_html=True)
except Exception:
    st.sidebar.markdown(f'<div style="background:#888;color:white;padding:8px 12px;border-radius:4px;font-size:0.9em;"><span style="margin-right:6px;">●</span>{t("signal_processor_not_init")}</div>', unsafe_allow_html=True)


page_id = PAGE_ACCESS_MAP.get(page, "dashboard")
if not can_access_page(page_id):
    st.error("You don't have permission to access this page.")
    st.stop()

if page == "Dashboard":
    from views import dashboard
    dashboard.render()
elif page == "Buildings & Floor Plans":
    from views import buildings
    buildings.render()
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
elif page == "Live Monitoring":
    from views import live_tracking
    live_tracking.render()
elif page == "User Management":
    from views import user_management
    user_management.render()
