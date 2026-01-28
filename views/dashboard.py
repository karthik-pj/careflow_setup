import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, RSSISignal, MQTTConfig
from utils.signal_processor import get_signal_processor
from utils.translations import t
from utils.mqtt_handler import get_gateway_mqtt_activity
from sqlalchemy import func
from datetime import datetime, timedelta


def render_signal_monitor(session):
    """Render the signal monitor section within dashboard."""
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("##### MQTT Status")
        mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
        
        if mqtt_config:
            st.success(f"Broker: {mqtt_config.broker_host}:{mqtt_config.broker_port}")
            st.caption(f"Topic: {mqtt_config.topic_prefix}#")
            
            processor = get_signal_processor()
            
            st.markdown("---")
            st.markdown("##### Signal Processor")
            
            if processor.is_running:
                st.success("🟢 Running")
                stats = processor.stats
                st.write(f"**Signals received:** {stats['signals_received']}")
                st.write(f"**Signals stored:** {stats['signals_stored']}")
                st.write(f"**Positions calculated:** {stats['positions_calculated']}")
                if stats['errors'] > 0:
                    st.warning(f"**Errors:** {stats['errors']}")
                
                if st.button("Stop Processing", key="dash_stop_proc"):
                    processor.stop()
                    st.rerun()
            else:
                st.warning("🔴 Stopped")
                if processor.last_error:
                    st.error(f"Error: {processor.last_error}")
                
                if st.button("Start Processing", type="primary", key="dash_start_proc"):
                    if processor.start():
                        st.success("Processor started!")
                        st.rerun()
                    else:
                        st.error(processor.last_error or "Failed to start")
        else:
            st.error("No MQTT broker configured")
            st.info("Go to MQTT Configuration to set up your broker")
    
    with col2:
        st.markdown("##### Recent Signals")
        
        one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
        recent_signals = session.query(RSSISignal).filter(
            RSSISignal.timestamp >= one_minute_ago
        ).order_by(RSSISignal.timestamp.desc()).limit(30).all()
        
        if recent_signals:
            signal_data = []
            for sig in recent_signals:
                gateway = session.query(Gateway).filter(Gateway.id == sig.gateway_id).first()
                beacon = session.query(Beacon).filter(Beacon.id == sig.beacon_id).first()
                
                signal_data.append({
                    'Time': sig.timestamp.strftime('%H:%M:%S'),
                    'Gateway': gateway.name if gateway else 'Unknown',
                    'Beacon': beacon.name if beacon else 'Unknown',
                    'RSSI': f"{sig.rssi} dBm"
                })
            
            st.dataframe(signal_data, use_container_width=True, height=200)
        else:
            st.info("No signals received in the last minute")
        
        st.markdown("---")
        st.markdown("##### Recent Positions")
        
        recent_positions = session.query(Position).order_by(
            Position.timestamp.desc()
        ).limit(10).all()
        
        if recent_positions:
            pos_data = []
            for pos in recent_positions:
                beacon = session.query(Beacon).filter(Beacon.id == pos.beacon_id).first()
                floor = session.query(Floor).filter(Floor.id == pos.floor_id).first()
                
                pos_data.append({
                    'Time': pos.timestamp.strftime('%H:%M:%S'),
                    'Beacon': beacon.name if beacon else 'Unknown',
                    'Floor': floor.name if floor else 'Unknown',
                    'X': f"{pos.x_position:.1f}m",
                    'Y': f"{pos.y_position:.1f}m"
                })
            
            st.dataframe(pos_data, use_container_width=True, height=150)
        else:
            st.info("No positions calculated yet")
    
    if st.button("🔄 Refresh", key="dash_refresh_signals"):
        st.rerun()


def render():
    st.title(t("dashboard_title"))
    st.caption(t("dashboard_subtitle"))
    
    with get_db_session() as session:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            building_count = session.query(func.count(Building.id)).scalar()
            st.metric(t("buildings"), building_count)
        
        with col2:
            gateway_count = session.query(func.count(Gateway.id)).scalar()
            active_gateways = session.query(func.count(Gateway.id)).filter(Gateway.is_active == True).scalar()
            st.metric(t("gateways"), f"{active_gateways}/{gateway_count}", help="Active/Total")
        
        with col3:
            beacon_count = session.query(func.count(Beacon.id)).scalar()
            active_beacons = session.query(func.count(Beacon.id)).filter(Beacon.is_active == True).scalar()
            st.metric(t("beacons"), f"{active_beacons}/{beacon_count}", help="Active/Total")
        
        with col4:
            floor_count = session.query(func.count(Floor.id)).scalar()
            st.metric(t("floor_plans"), floor_count)
        
        st.markdown("---")
        
        col_left, col_right = st.columns(2)
        
        with col_left:
            with st.container(border=True):
                st.subheader(t("signal_processing_status"))
                processor = get_signal_processor()
                
                if processor.is_running:
                    st.success(t("running"))
                    stats = processor.stats
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric(t("received"), stats['signals_received'])
                    col_b.metric(t("stored"), stats['signals_stored'])
                    col_c.metric(t("positions"), stats['positions_calculated'])
                    if stats['errors'] > 0:
                        st.warning(f"{t('error')}: {stats['errors']}")
                else:
                    st.warning(t("stopped"))
                    if processor.last_error:
                        st.error(f"{t('error')}: {processor.last_error}")
                    st.info("Go to Signal Monitor to start processing")
            
            with st.container(border=True):
                st.subheader(t("signals") + " (1h)")
                
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                recent_signals = session.query(func.count(RSSISignal.id)).filter(
                    RSSISignal.timestamp >= one_hour_ago
                ).scalar()
                
                recent_positions = session.query(func.count(Position.id)).filter(
                    Position.timestamp >= one_hour_ago
                ).scalar()
                
                col_a, col_b = st.columns(2)
                col_a.metric(t("signals"), recent_signals)
                col_b.metric(t("positions"), recent_positions)
                
                mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
                if mqtt_config:
                    st.success(f"MQTT: {mqtt_config.broker_host}:{mqtt_config.broker_port}")
                else:
                    st.warning("No MQTT broker configured")
        
        with col_right:
            with st.container(border=True):
                st.subheader(t("gateway_status"))
                gateways = session.query(Gateway).filter(Gateway.is_active == True).all()
                
                if gateways:
                    mqtt_activity = get_gateway_mqtt_activity()
                    two_min_ago = datetime.utcnow() - timedelta(minutes=2)
                    five_min_ago = datetime.utcnow() - timedelta(minutes=5)
                    
                    for gw in gateways:
                        gw_mac = gw.mac_address.upper() if gw.mac_address else ''
                        mqtt_last_seen = mqtt_activity.get(gw_mac)
                        
                        recent = session.query(func.count(RSSISignal.id)).filter(
                            RSSISignal.gateway_id == gw.id,
                            RSSISignal.timestamp >= five_min_ago
                        ).scalar()
                        
                        if recent > 0:
                            status = "🟢"
                            status_text = f"{recent} {t('signals')} (5 min)"
                        elif mqtt_last_seen and mqtt_last_seen >= two_min_ago:
                            status = "🔵"
                            status_text = t("connected")
                        elif mqtt_last_seen:
                            status = "🔴"
                            status_text = t("offline")
                        else:
                            status = "⚪"
                            status_text = t("installed")
                        
                        st.write(f"{status} **{gw.name}** — {status_text}")
                else:
                    st.info(t("no_gateways"))
        
        st.markdown("---")
        
        with st.expander("📡 Signal Monitor", expanded=False):
            render_signal_monitor(session)
        
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
