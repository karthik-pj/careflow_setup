import streamlit as st
from utils.auth import authenticate_user, is_logged_in, logout
from utils.translations import t


def render():
    st.markdown("""
        <style>
        .login-container {
            max-width: 400px;
            margin: 0 auto;
            padding: 2rem;
        }
        .login-title {
            text-align: center;
            color: #2e5cbf;
            margin-bottom: 2rem;
        }
        .demo-box {
            background: #f0f4f8;
            border: 1px solid #d0d7de;
            border-radius: 8px;
            padding: 1rem;
            margin-top: 1.5rem;
            font-size: 0.9em;
        }
        </style>
    """, unsafe_allow_html=True)
    
    if is_logged_in():
        user = st.session_state.user
        st.success(f"Logged in as **{user['full_name'] or user['username']}** ({user['role']})")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Go to Dashboard", type="primary", use_container_width=True):
                st.session_state.page = "dashboard"
                st.rerun()
        with col2:
            if st.button("Logout", use_container_width=True):
                logout()
                st.rerun()
        return
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("attached_assets/CAREFLOW LOGO-Color_1764612034940.png", use_container_width=True)
    
    st.markdown('<h2 class="login-title">Login</h2>', unsafe_allow_html=True)
    
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            submit = st.form_submit_button("Login", type="primary", use_container_width=True)
    
    if submit:
        if not username or not password:
            st.error("Please enter both username and password.")
        else:
            user = authenticate_user(username, password)
            if user:
                st.session_state.user = user
                st.session_state.page = "dashboard"
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
    
    # Footer
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("---")
    dark_mode = st.session_state.get('dark_mode', True)
    footer_color = "#a0aec0" if dark_mode else "#64748b"
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem 0; color: {footer_color}; font-size: 0.8rem;">
        ©2026 CareFlow Systems GmbH, CareSet V 1.1.0
    </div>
    """, unsafe_allow_html=True)
