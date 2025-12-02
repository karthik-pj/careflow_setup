import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, RSSISignal, MQTTConfig
from utils.signal_processor import get_signal_processor
from sqlalchemy import func
from datetime import datetime, timedelta


def render():
    st.title("Dashboard")
    st.caption("Overview of your BLE Indoor Positioning System")
    
    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
    
    with get_db_session() as session:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            building_count = session.query(func.count(Building.id)).scalar()
            st.markdown(f"""
            <div class="cf-metric">
                <div class="cf-metric-value">{building_count}</div>
                <div class="cf-metric-label">Buildings</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            gateway_count = session.query(func.count(Gateway.id)).scalar()
            active_gateways = session.query(func.count(Gateway.id)).filter(Gateway.is_active == True).scalar()
            st.markdown(f"""
            <div class="cf-metric">
                <div class="cf-metric-value">{active_gateways}<span style="font-size: 1rem; color: #64748b;">/{gateway_count}</span></div>
                <div class="cf-metric-label">Gateways</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            beacon_count = session.query(func.count(Beacon.id)).scalar()
            active_beacons = session.query(func.count(Beacon.id)).filter(Beacon.is_active == True).scalar()
            st.markdown(f"""
            <div class="cf-metric">
                <div class="cf-metric-value">{active_beacons}<span style="font-size: 1rem; color: #64748b;">/{beacon_count}</span></div>
                <div class="cf-metric-label">Beacons</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            floor_count = session.query(func.count(Floor.id)).scalar()
            st.markdown(f"""
            <div class="cf-metric">
                <div class="cf-metric-value">{floor_count}</div>
                <div class="cf-metric-label">Floor Plans</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)
        
        col_left, col_right = st.columns(2)
        
        with col_left:
            processor = get_signal_processor()
            
            if processor.is_running:
                stats = processor.stats
                status_html = '<span class="cf-status cf-status-success">Running</span>'
                stats_html = f"""
                <div style="margin-top: 1rem; display: grid; gap: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #e2e8f0;">
                        <span style="color: #64748b;">Signals received</span>
                        <span style="font-weight: 600;">{stats['signals_received']}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #e2e8f0;">
                        <span style="color: #64748b;">Signals stored</span>
                        <span style="font-weight: 600;">{stats['signals_stored']}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0;">
                        <span style="color: #64748b;">Positions calculated</span>
                        <span style="font-weight: 600;">{stats['positions_calculated']}</span>
                    </div>
                </div>
                """
                processor_card = f"""
                <div class="cf-card">
                    <div class="cf-card-header">Signal Processing Status</div>
                    {status_html}
                    {stats_html}
                </div>
                """
                st.markdown(processor_card, unsafe_allow_html=True)
                if stats['errors'] > 0:
                    st.warning(f"Errors: {stats['errors']}")
            else:
                status_html = '<span class="cf-status cf-status-warning">Stopped</span>'
                processor_card = f"""
                <div class="cf-card">
                    <div class="cf-card-header">Signal Processing Status</div>
                    {status_html}
                    <p style="margin-top: 1rem; color: #64748b; font-size: 0.9rem;">Go to Signal Monitor to start processing</p>
                </div>
                """
                st.markdown(processor_card, unsafe_allow_html=True)
                if processor.last_error:
                    st.error(f"Last error: {processor.last_error}")
            
            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
            
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_signals = session.query(func.count(RSSISignal.id)).filter(
                RSSISignal.timestamp >= one_hour_ago
            ).scalar()
            
            recent_positions = session.query(func.count(Position.id)).filter(
                Position.timestamp >= one_hour_ago
            ).scalar()
            
            mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
            
            mqtt_html = ""
            if mqtt_config:
                mqtt_html = f"""
                <div style="margin-top: 1rem; padding: 0.75rem; background: rgba(16, 185, 129, 0.1); border-radius: 8px; display: flex; align-items: center; gap: 0.5rem;">
                    <span style="color: #10b981;">●</span>
                    <span style="color: #10b981; font-size: 0.875rem;">MQTT: {mqtt_config.broker_host}:{mqtt_config.broker_port}</span>
                </div>
                """
            
            activity_card = f"""
            <div class="cf-card">
                <div class="cf-card-header">Recent Activity</div>
                <div style="display: grid; gap: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid #e2e8f0;">
                        <span style="color: #64748b;">Signals (last hour)</span>
                        <span style="font-weight: 600;">{recent_signals}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 0.5rem 0;">
                        <span style="color: #64748b;">Positions (last hour)</span>
                        <span style="font-weight: 600;">{recent_positions}</span>
                    </div>
                </div>
                {mqtt_html}
            </div>
            """
            st.markdown(activity_card, unsafe_allow_html=True)
            
            if not mqtt_config:
                st.warning("No MQTT broker configured. Go to MQTT Configuration to set up.")
        
        with col_right:
            gateways = session.query(Gateway).filter(Gateway.is_active == True).limit(5).all()
            
            gateway_card_html = """
            <div class="cf-card">
                <div class="cf-card-header">Gateway Status</div>
            """
            
            if gateways:
                gateway_card_html += "<div style='display: grid; gap: 0.75rem;'>"
                for gw in gateways:
                    five_min_ago = datetime.utcnow() - timedelta(minutes=5)
                    recent = session.query(func.count(RSSISignal.id)).filter(
                        RSSISignal.gateway_id == gw.id,
                        RSSISignal.timestamp >= five_min_ago
                    ).scalar()
                    
                    status_color = "#10b981" if recent > 0 else "#ef4444"
                    status_bg = "rgba(16, 185, 129, 0.1)" if recent > 0 else "rgba(239, 68, 68, 0.1)"
                    
                    gateway_card_html += f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: {status_bg}; border-radius: 8px;">
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <span style="color: {status_color};">●</span>
                            <span style="font-weight: 500;">{gw.name}</span>
                        </div>
                        <span style="font-size: 0.8rem; color: #64748b;">{recent} signals</span>
                    </div>
                    """
                gateway_card_html += "</div>"
            else:
                gateway_card_html += "<p style='color: #64748b; font-size: 0.9rem;'>No gateways configured yet.</p>"
            
            gateway_card_html += "</div>"
            st.markdown(gateway_card_html, unsafe_allow_html=True)
        
        st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)
        
        steps_html = "<div style='display: grid; gap: 0.75rem;'>"
        
        if building_count == 0:
            steps_html += """
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0;">
                <span style="width: 24px; height: 24px; border-radius: 50%; background: #2563eb; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600;">1</span>
                <span>Create a building and upload floor plans</span>
            </div>
            """
        else:
            steps_html += """
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0; opacity: 0.6;">
                <span style="width: 24px; height: 24px; border-radius: 50%; background: #10b981; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem;">✓</span>
                <span style="text-decoration: line-through;">Create a building and upload floor plans</span>
            </div>
            """
        
        if gateway_count == 0:
            steps_html += """
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0;">
                <span style="width: 24px; height: 24px; border-radius: 50%; background: #2563eb; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600;">2</span>
                <span>Add your Careflow BLE Gateways</span>
            </div>
            """
        else:
            steps_html += """
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0; opacity: 0.6;">
                <span style="width: 24px; height: 24px; border-radius: 50%; background: #10b981; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem;">✓</span>
                <span style="text-decoration: line-through;">Add your Careflow BLE Gateways</span>
            </div>
            """
        
        if beacon_count == 0:
            steps_html += """
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0;">
                <span style="width: 24px; height: 24px; border-radius: 50%; background: #2563eb; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600;">3</span>
                <span>Register your BLE Beacons</span>
            </div>
            """
        else:
            steps_html += """
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0; opacity: 0.6;">
                <span style="width: 24px; height: 24px; border-radius: 50%; background: #10b981; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem;">✓</span>
                <span style="text-decoration: line-through;">Register your BLE Beacons</span>
            </div>
            """
        
        if not mqtt_config:
            steps_html += """
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0;">
                <span style="width: 24px; height: 24px; border-radius: 50%; background: #2563eb; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600;">4</span>
                <span>Configure the MQTT broker connection</span>
            </div>
            """
        else:
            steps_html += """
            <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0; opacity: 0.6;">
                <span style="width: 24px; height: 24px; border-radius: 50%; background: #10b981; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem;">✓</span>
                <span style="text-decoration: line-through;">Configure the MQTT broker connection</span>
            </div>
            """
        
        steps_html += """
        <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0;">
            <span style="width: 24px; height: 24px; border-radius: 50%; background: #2563eb; color: white; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 600;">5</span>
            <span>Start live tracking to see beacon positions</span>
        </div>
        """
        
        steps_html += "</div>"
        
        setup_card = f"""
        <div class="cf-card">
            <div class="cf-card-header">Quick Setup Guide</div>
            {steps_html}
        </div>
        """
        st.markdown(setup_card, unsafe_allow_html=True)
