import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, RSSISignal, MQTTConfig
from utils.signal_processor import get_signal_processor
from sqlalchemy import func
from datetime import datetime, timedelta


def render():
    st.title("Dashboard")
    st.caption("Overview of your BLE Indoor Positioning System")
    
    with get_db_session() as session:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            building_count = session.query(func.count(Building.id)).scalar()
            st.metric("Buildings", building_count)
        
        with col2:
            gateway_count = session.query(func.count(Gateway.id)).scalar()
            active_gateways = session.query(func.count(Gateway.id)).filter(Gateway.is_active == True).scalar()
            st.metric("Gateways", f"{active_gateways}/{gateway_count}", help="Active/Total")
        
        with col3:
            beacon_count = session.query(func.count(Beacon.id)).scalar()
            active_beacons = session.query(func.count(Beacon.id)).filter(Beacon.is_active == True).scalar()
            st.metric("Beacons", f"{active_beacons}/{beacon_count}", help="Active/Total")
        
        with col4:
            floor_count = session.query(func.count(Floor.id)).scalar()
            st.metric("Floor Plans", floor_count)
        
        st.markdown("---")
        
        col_left, col_right = st.columns(2)
        
        with col_left:
            with st.container(border=True):
                st.subheader("Signal Processing Status")
                processor = get_signal_processor()
                
                if processor.is_running:
                    st.success("Running")
                    stats = processor.stats
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Received", stats['signals_received'])
                    col_b.metric("Stored", stats['signals_stored'])
                    col_c.metric("Positions", stats['positions_calculated'])
                    if stats['errors'] > 0:
                        st.warning(f"Errors: {stats['errors']}")
                else:
                    st.warning("Stopped")
                    if processor.last_error:
                        st.error(f"Last error: {processor.last_error}")
                    st.info("Go to Signal Monitor to start processing")
            
            with st.container(border=True):
                st.subheader("Recent Activity")
                
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                recent_signals = session.query(func.count(RSSISignal.id)).filter(
                    RSSISignal.timestamp >= one_hour_ago
                ).scalar()
                
                recent_positions = session.query(func.count(Position.id)).filter(
                    Position.timestamp >= one_hour_ago
                ).scalar()
                
                col_a, col_b = st.columns(2)
                col_a.metric("Signals (1h)", recent_signals)
                col_b.metric("Positions (1h)", recent_positions)
                
                mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
                if mqtt_config:
                    st.success(f"MQTT: {mqtt_config.broker_host}:{mqtt_config.broker_port}")
                else:
                    st.warning("No MQTT broker configured")
        
        with col_right:
            with st.container(border=True):
                st.subheader("Gateway Status")
                gateways = session.query(Gateway).filter(Gateway.is_active == True).limit(5).all()
                
                if gateways:
                    for gw in gateways:
                        five_min_ago = datetime.utcnow() - timedelta(minutes=5)
                        recent = session.query(func.count(RSSISignal.id)).filter(
                            RSSISignal.gateway_id == gw.id,
                            RSSISignal.timestamp >= five_min_ago
                        ).scalar()
                        
                        status = "🟢" if recent > 0 else "🔴"
                        st.write(f"{status} **{gw.name}** — {recent} signals (5 min)")
                else:
                    st.info("No gateways configured yet.")
        
        st.markdown("---")
        
        with st.container(border=True):
            st.subheader("Quick Setup Guide")
            
            if building_count == 0:
                st.write("1️⃣ Create a building and upload floor plans")
            else:
                st.write("~~1️⃣ Create a building and upload floor plans~~ ✅")
            
            if gateway_count == 0:
                st.write("2️⃣ Add your Careflow BLE Gateways")
            else:
                st.write("~~2️⃣ Add your Careflow BLE Gateways~~ ✅")
            
            if beacon_count == 0:
                st.write("3️⃣ Register your BLE Beacons")
            else:
                st.write("~~3️⃣ Register your BLE Beacons~~ ✅")
            
            if not mqtt_config:
                st.write("4️⃣ Configure the MQTT broker connection")
            else:
                st.write("~~4️⃣ Configure the MQTT broker connection~~ ✅")
            
            st.write("5️⃣ Start live tracking to see beacon positions")
