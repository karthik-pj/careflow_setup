import streamlit as st
from database import get_db_session, Gateway, Beacon, RSSISignal, Position, MQTTConfig, Floor
from utils.triangulation import GatewayReading, trilaterate_2d, calculate_velocity, filter_outlier_readings
from utils.signal_processor import get_signal_processor
from datetime import datetime, timedelta
from sqlalchemy import func
import time


def render():
    st.title("Signal Monitor")
    st.markdown("Monitor incoming RSSI signals and process beacon positions")
    
    with get_db_session() as session:
        mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("MQTT Status")
            
            if mqtt_config:
                st.success(f"Broker: {mqtt_config.broker_host}:{mqtt_config.broker_port}")
                st.write(f"Topic: {mqtt_config.topic_prefix}#")
                
                processor = get_signal_processor()
                
                st.markdown("---")
                st.subheader("Signal Processor")
                
                if processor.is_running:
                    st.success("🟢 Running")
                    stats = processor.stats
                    st.write(f"**Signals received:** {stats['signals_received']}")
                    st.write(f"**Signals stored:** {stats['signals_stored']}")
                    st.write(f"**Positions calculated:** {stats['positions_calculated']}")
                    if stats['errors'] > 0:
                        st.warning(f"**Errors:** {stats['errors']}")
                    if processor.last_error:
                        st.error(f"Last error: {processor.last_error}")
                    
                    if st.button("Stop Processing"):
                        processor.stop()
                        st.rerun()
                else:
                    st.warning("🔴 Stopped")
                    if processor.last_error:
                        st.error(f"Error: {processor.last_error}")
                    
                    if st.button("Start Processing", type="primary"):
                        if processor.start():
                            st.success("Processor started!")
                            st.rerun()
                        else:
                            st.error(processor.last_error or "Failed to start")
            else:
                st.error("No MQTT broker configured")
                st.info("Go to MQTT Configuration to set up your broker")
            
        
        with col2:
            st.subheader("Recent Signals")
            
            one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
            recent_signals = session.query(RSSISignal).filter(
                RSSISignal.timestamp >= one_minute_ago
            ).order_by(RSSISignal.timestamp.desc()).limit(50).all()
            
            if recent_signals:
                signal_data = []
                for sig in recent_signals:
                    gateway = session.query(Gateway).filter(Gateway.id == sig.gateway_id).first()
                    beacon = session.query(Beacon).filter(Beacon.id == sig.beacon_id).first()
                    
                    signal_data.append({
                        'Time': sig.timestamp.strftime('%H:%M:%S'),
                        'Gateway': gateway.name if gateway else 'Unknown',
                        'Beacon': beacon.name if beacon else 'Unknown',
                        'RSSI': f"{sig.rssi} dBm",
                        'TX Power': f"{sig.tx_power or -59} dBm"
                    })
                
                st.dataframe(signal_data, use_container_width=True, height=300)
            else:
                st.info("No signals received in the last minute")
            
            st.markdown("---")
            st.subheader("Recent Positions")
            
            recent_positions = session.query(Position).order_by(
                Position.timestamp.desc()
            ).limit(20).all()
            
            if recent_positions:
                pos_data = []
                for pos in recent_positions:
                    beacon = session.query(Beacon).filter(Beacon.id == pos.beacon_id).first()
                    floor = session.query(Floor).filter(Floor.id == pos.floor_id).first()
                    
                    pos_data.append({
                        'Time': pos.timestamp.strftime('%H:%M:%S'),
                        'Beacon': beacon.name if beacon else 'Unknown',
                        'Floor': floor.name if floor else 'Unknown',
                        'X': f"{pos.x_position:.2f}m",
                        'Y': f"{pos.y_position:.2f}m",
                        'Speed': f"{pos.speed:.2f} m/s",
                        'Accuracy': f"±{pos.accuracy:.2f}m"
                    })
                
                st.dataframe(pos_data, use_container_width=True)
            else:
                st.info("No positions calculated yet")
        
        st.markdown("---")
        
        st.subheader("Signal Statistics")
        
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
        
        with col_stat1:
            total_signals = session.query(func.count(RSSISignal.id)).filter(
                RSSISignal.timestamp >= one_hour_ago
            ).scalar()
            st.metric("Signals (1 hour)", total_signals)
        
        with col_stat2:
            total_positions = session.query(func.count(Position.id)).filter(
                Position.timestamp >= one_hour_ago
            ).scalar()
            st.metric("Positions (1 hour)", total_positions)
        
        with col_stat3:
            active_gateways = session.query(func.count(func.distinct(RSSISignal.gateway_id))).filter(
                RSSISignal.timestamp >= one_minute_ago
            ).scalar()
            st.metric("Active Gateways", active_gateways)
        
        with col_stat4:
            active_beacons = session.query(func.count(func.distinct(RSSISignal.beacon_id))).filter(
                RSSISignal.timestamp >= one_minute_ago
            ).scalar()
            st.metric("Active Beacons", active_beacons)
        
        if st.button("Refresh Page"):
            st.rerun()
