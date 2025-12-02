import streamlit as st
import os
from database import get_db_session, MQTTConfig
from utils.mqtt_handler import MQTTHandler
from utils.signal_processor import get_signal_processor
import time


def show_pending_message():
    """Display any pending success message from session state"""
    if 'mqtt_success_msg' in st.session_state:
        st.success(st.session_state['mqtt_success_msg'])
        del st.session_state['mqtt_success_msg']


def set_success_and_rerun(message):
    """Store success message in session state and rerun"""
    st.session_state['mqtt_success_msg'] = message
    st.rerun()


def render():
    st.title("MQTT Broker Configuration")
    st.markdown("Configure the connection to your MQTT broker for receiving gateway data")
    
    show_pending_message()
    
    with get_db_session() as session:
        existing_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
        
        st.subheader("Broker Settings")
        
        with st.form("mqtt_config"):
            col1, col2 = st.columns(2)
            
            with col1:
                broker_host = st.text_input(
                    "Broker Host*",
                    value=existing_config.broker_host if existing_config else "",
                    placeholder="e.g., mqtt.example.com or 192.168.1.100",
                    help="MQTT broker hostname or IP address"
                )
                
                broker_port = st.number_input(
                    "Broker Port*",
                    value=existing_config.broker_port if existing_config else 1883,
                    min_value=1,
                    max_value=65535,
                    help="Default: 1883 for non-TLS, 8883 for TLS"
                )
                
                topic_prefix = st.text_input(
                    "Topic Prefix",
                    value=existing_config.topic_prefix if existing_config else "ble/gateway/",
                    placeholder="ble/gateway/",
                    help="Prefix for MQTT topics from gateways"
                )
            
            with col2:
                username = st.text_input(
                    "Username",
                    value=existing_config.username if existing_config else "",
                    placeholder="Leave empty if not required"
                )
                
                password_env_key = st.text_input(
                    "Password Environment Variable Name",
                    value=existing_config.password_env_key if existing_config else "MQTT_PASSWORD",
                    placeholder="MQTT_PASSWORD",
                    help="Name of the secret/environment variable containing the password"
                )
                
                has_password = False
                if password_env_key:
                    has_password = os.environ.get(password_env_key) is not None
                
                if password_env_key:
                    if has_password:
                        st.success(f"Password is set in environment variable '{password_env_key}'")
                    else:
                        st.warning(f"Environment variable '{password_env_key}' is not set")
                
                use_tls = st.checkbox(
                    "Use TLS/SSL",
                    value=existing_config.use_tls if existing_config else False,
                    help="Enable secure connection (required for EMQ X Cloud on port 8883)"
                )
                
                ca_cert_path = st.text_input(
                    "CA Certificate Path",
                    value=existing_config.ca_cert_path if existing_config and existing_config.ca_cert_path else "certs/emqxsl-ca.crt",
                    placeholder="certs/emqxsl-ca.crt",
                    help="Path to CA certificate file for TLS (required for EMQ X Cloud)"
                )
                
                if ca_cert_path and os.path.exists(ca_cert_path):
                    st.success(f"CA certificate found: {ca_cert_path}")
                elif use_tls and ca_cert_path:
                    st.warning(f"CA certificate not found at: {ca_cert_path}")
            
            st.info("Set the MQTT password as a secret (via Secrets tab in Tools) using the environment variable name specified above. This keeps your password secure.")
            
            col3, col4 = st.columns(2)
            
            with col3:
                submitted = st.form_submit_button("Save Configuration", type="primary")
            
            with col4:
                test_connection = st.form_submit_button("Test Connection")
            
            if submitted:
                if not broker_host:
                    st.error("Broker host is required")
                else:
                    if existing_config:
                        existing_config.broker_host = broker_host
                        existing_config.broker_port = broker_port
                        existing_config.topic_prefix = topic_prefix
                        existing_config.username = username or None
                        existing_config.password_env_key = password_env_key or None
                        existing_config.use_tls = use_tls
                        existing_config.ca_cert_path = ca_cert_path or None
                    else:
                        config = MQTTConfig(
                            broker_host=broker_host,
                            broker_port=broker_port,
                            topic_prefix=topic_prefix,
                            username=username or None,
                            password_env_key=password_env_key or None,
                            use_tls=use_tls,
                            ca_cert_path=ca_cert_path or None,
                            is_active=True
                        )
                        session.add(config)
                    
                    session.commit()
                    
                    processor = get_signal_processor()
                    if processor.is_running:
                        processor.stop()
                        time.sleep(0.5)
                        processor.start()
                    
                    set_success_and_rerun("Configuration saved successfully!")
            
            if test_connection:
                if not broker_host:
                    st.error("Please enter broker host first")
                else:
                    with st.spinner("Testing connection..."):
                        try:
                            password = os.environ.get(password_env_key) if password_env_key else None
                            
                            st.info(f"Debug: Using env key '{password_env_key}', password exists: {password is not None}, length: {len(password) if password else 0}")
                            st.info(f"Debug: Host={broker_host}, Port={broker_port}, User={username}, TLS={use_tls}, CA={ca_cert_path}")
                            
                            handler = MQTTHandler(
                                broker_host=broker_host,
                                broker_port=broker_port,
                                username=username or None,
                                password=password,
                                topic_prefix=topic_prefix,
                                use_tls=use_tls,
                                ca_cert_path=ca_cert_path if use_tls else None
                            )
                            
                            if handler.connect():
                                handler.start()
                                time.sleep(2)
                                
                                if handler.is_connected:
                                    st.success("Connection successful!")
                                else:
                                    st.error(f"Connection failed: {handler.last_error}")
                                
                                handler.stop()
                                handler.disconnect()
                            else:
                                st.error(f"Failed to connect: {handler.last_error}")
                        except Exception as e:
                            st.error(f"Connection error: {str(e)}")
        
        st.markdown("---")
        st.subheader("Signal Processor Control")
        
        processor = get_signal_processor()
        
        col_proc1, col_proc2 = st.columns(2)
        
        with col_proc1:
            if processor.is_running:
                st.success("Signal Processor: Running")
                if st.button("Stop Processor"):
                    processor.stop()
                    st.rerun()
            else:
                st.warning("Signal Processor: Stopped")
                if processor.last_error:
                    st.error(f"Last error: {processor.last_error}")
                if st.button("Start Processor", type="primary"):
                    if processor.start():
                        st.success("Processor started!")
                        st.rerun()
                    else:
                        st.error(processor.last_error or "Failed to start")
        
        with col_proc2:
            if processor.is_running:
                stats = processor.stats
                st.write(f"**Signals received:** {stats['signals_received']}")
                st.write(f"**Signals stored:** {stats['signals_stored']}")
                st.write(f"**Positions calculated:** {stats['positions_calculated']}")
        
        st.markdown("---")
        st.subheader("Expected Message Format")
        
        st.markdown("""
        The system expects MQTT messages from Careflow gateways in JSON format:
        
        ```json
        {
            "gatewayMac": "AA:BB:CC:DD:EE:FF",
            "mac": "11:22:33:44:55:66",
            "rssi": -65,
            "txPower": -59,
            "timestamp": 1699999999
        }
        ```
        
        **Alternative format:**
        ```json
        {
            "type": "Gateway",
            "mac": "AA:BB:CC:DD:EE:FF",
            "bleMAC": "11:22:33:44:55:66",
            "rssi": -65,
            "rawData": "..."
        }
        ```
        
        **Topic Structure:**
        - Default topic pattern: `{prefix}#` (subscribes to all subtopics)
        - Example: `ble/gateway/entrance` or `ble/gateway/floor1/room1`
        """)
        
        st.markdown("---")
        st.subheader("Configuration History")
        
        all_configs = session.query(MQTTConfig).order_by(MQTTConfig.created_at.desc()).all()
        
        if all_configs:
            for config in all_configs:
                status = "🟢 Active" if config.is_active else "⚪ Inactive"
                with st.expander(f"{status} - {config.broker_host}:{config.broker_port}"):
                    st.write(f"**Topic Prefix:** {config.topic_prefix}")
                    st.write(f"**TLS:** {'Yes' if config.use_tls else 'No'}")
                    st.write(f"**Username:** {config.username or 'Not set'}")
                    st.write(f"**Password Env Key:** {config.password_env_key or 'Not set'}")
                    st.write(f"**Created:** {config.created_at}")
                    
                    if not config.is_active:
                        if st.button("Set Active", key=f"activate_{config.id}"):
                            for c in all_configs:
                                c.is_active = False
                            config.is_active = True
                            session.commit()
                            set_success_and_rerun("Configuration activated")
                        
                        if st.button("Delete", key=f"delete_{config.id}", type="secondary"):
                            session.delete(config)
                            session.commit()
                            set_success_and_rerun("Configuration deleted")
        else:
            st.info("No MQTT configurations saved yet.")
