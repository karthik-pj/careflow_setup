import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, RSSISignal, MQTTConfig
from utils.signal_processor import get_signal_processor
from sqlalchemy import func
from datetime import datetime, timedelta


def render():
    st.title("Dashboard")
    st.markdown("Overview of your BLE Indoor Positioning System")
    
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
            st.subheader("Signal Processing Status")
            
            processor = get_signal_processor()
            
            if processor.is_running:
                st.success("Signal processor is running")
                stats = processor.stats
                st.write(f"**Signals received:** {stats['signals_received']}")
                st.write(f"**Signals stored:** {stats['signals_stored']}")
                st.write(f"**Positions calculated:** {stats['positions_calculated']}")
                if stats['errors'] > 0:
                    st.warning(f"Errors: {stats['errors']}")
            else:
                st.warning("Signal processor is not running")
                if processor.last_error:
                    st.error(f"Last error: {processor.last_error}")
                st.info("Go to Signal Monitor to start processing")
            
            st.markdown("---")
            st.subheader("Recent Activity")
            
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_signals = session.query(func.count(RSSISignal.id)).filter(
                RSSISignal.timestamp >= one_hour_ago
            ).scalar()
            
            recent_positions = session.query(func.count(Position.id)).filter(
                Position.timestamp >= one_hour_ago
            ).scalar()
            
            st.write(f"**Signals received (last hour):** {recent_signals}")
            st.write(f"**Positions calculated (last hour):** {recent_positions}")
            
            mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
            if mqtt_config:
                st.success(f"MQTT Broker: {mqtt_config.broker_host}:{mqtt_config.broker_port}")
            else:
                st.warning("No MQTT broker configured. Go to MQTT Configuration to set up.")
        
        with col_right:
            st.subheader("System Status")
            
            gateways = session.query(Gateway).filter(Gateway.is_active == True).limit(5).all()
            
            if gateways:
                for gw in gateways:
                    five_min_ago = datetime.utcnow() - timedelta(minutes=5)
                    recent = session.query(func.count(RSSISignal.id)).filter(
                        RSSISignal.gateway_id == gw.id,
                        RSSISignal.timestamp >= five_min_ago
                    ).scalar()
                    
                    status = "🟢" if recent > 0 else "🔴"
                    st.write(f"{status} **{gw.name}** - {recent} signals (5 min)")
            else:
                st.info("No gateways configured yet.")
        
        st.markdown("---")
        
        st.subheader("Quick Setup Guide")
        
        setup_steps = []
        
        if building_count == 0:
            setup_steps.append("1. Create a building and upload floor plans")
        else:
            setup_steps.append("~~1. Create a building and upload floor plans~~ ✓")
        
        if gateway_count == 0:
            setup_steps.append("2. Add your Careflow BLE Gateways with their positions")
        else:
            setup_steps.append("~~2. Add your Careflow BLE Gateways with their positions~~ ✓")
        
        if beacon_count == 0:
            setup_steps.append("3. Register your BLE Beacons")
        else:
            setup_steps.append("~~3. Register your BLE Beacons~~ ✓")
        
        if not mqtt_config:
            setup_steps.append("4. Configure the MQTT broker connection")
        else:
            setup_steps.append("~~4. Configure the MQTT broker connection~~ ✓")
        
        setup_steps.append("5. Start live tracking to see beacon positions")
        
        for step in setup_steps:
            st.markdown(step)
