import streamlit as st
import io
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, RSSISignal, MQTTConfig
from utils.signal_processor import get_signal_processor, normalize_mac_address
from utils.translations import t
from utils.mqtt_handler import get_gateway_mqtt_activity
from sqlalchemy import func
from datetime import datetime, timedelta


def generate_diagnostic_report(session) -> str:
    """Generate a comprehensive diagnostic report showing data flow funnel."""
    now = datetime.utcnow()
    report_lines = []
    
    report_lines.append("=" * 80)
    report_lines.append("CAREFLOW SYSTEM DIAGNOSTIC REPORT")
    report_lines.append(f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    # Section 1: System Overview
    report_lines.append("SECTION 1: SYSTEM OVERVIEW")
    report_lines.append("-" * 40)
    
    building_count = session.query(func.count(Building.id)).scalar()
    floor_count = session.query(func.count(Floor.id)).scalar()
    gateway_count = session.query(func.count(Gateway.id)).scalar()
    active_gateways = session.query(func.count(Gateway.id)).filter(Gateway.is_active == True).scalar()
    beacon_count = session.query(func.count(Beacon.id)).scalar()
    active_beacons = session.query(func.count(Beacon.id)).filter(Beacon.is_active == True).scalar()
    
    report_lines.append(f"Buildings: {building_count}")
    report_lines.append(f"Floor Plans: {floor_count}")
    report_lines.append(f"Gateways: {active_gateways}/{gateway_count} active")
    report_lines.append(f"Beacons: {active_beacons}/{beacon_count} active")
    report_lines.append("")
    
    # Section 2: MQTT Configuration
    report_lines.append("SECTION 2: MQTT CONFIGURATION")
    report_lines.append("-" * 40)
    
    mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
    if mqtt_config:
        report_lines.append(f"Broker: {mqtt_config.broker_host}:{mqtt_config.broker_port}")
        report_lines.append(f"Topic Prefix: {mqtt_config.topic_prefix}")
        report_lines.append(f"Auto-discover Beacons: {'ON' if mqtt_config.auto_discover_beacons else 'OFF'}")
    else:
        report_lines.append("WARNING: No active MQTT configuration!")
    report_lines.append("")
    
    # Section 3: Signal Processor Status
    report_lines.append("SECTION 3: SIGNAL PROCESSOR STATUS")
    report_lines.append("-" * 40)
    
    processor = get_signal_processor()
    report_lines.append(f"Status: {'RUNNING' if processor.is_running else 'STOPPED'}")
    stats = processor.stats
    report_lines.append(f"Signals Received: {stats['signals_received']}")
    report_lines.append(f"Signals Stored: {stats['signals_stored']}")
    report_lines.append(f"Positions Calculated: {stats['positions_calculated']}")
    report_lines.append(f"Errors: {stats['errors']}")
    if processor.last_error:
        report_lines.append(f"Last Error: {processor.last_error}")
    report_lines.append("")
    
    # Section 4: Gateway Status
    report_lines.append("SECTION 4: GATEWAY STATUS")
    report_lines.append("-" * 40)
    
    gateways = session.query(Gateway).filter(Gateway.is_active == True).all()
    mqtt_activity = get_gateway_mqtt_activity()
    two_min_ago = now - timedelta(minutes=2)
    five_min_ago = now - timedelta(minutes=5)
    
    for gw in gateways:
        gw_mac = gw.mac_address.upper() if gw.mac_address else ''
        mqtt_last_seen = mqtt_activity.get(gw_mac)
        
        recent = session.query(func.count(RSSISignal.id)).filter(
            RSSISignal.gateway_id == gw.id,
            RSSISignal.timestamp >= five_min_ago
        ).scalar()
        
        floor = session.query(Floor).filter(Floor.id == gw.floor_id).first()
        floor_name = floor.name if floor else "Not assigned"
        
        if recent > 0:
            status = "ACTIVE"
        elif mqtt_last_seen and mqtt_last_seen >= two_min_ago:
            status = "CONNECTED (no stored signals)"
        elif mqtt_last_seen:
            status = "OFFLINE"
        else:
            status = "INSTALLED (never seen)"
        
        report_lines.append(f"{gw.name}:")
        report_lines.append(f"  MAC: {gw.mac_address}")
        report_lines.append(f"  Floor: {floor_name}")
        report_lines.append(f"  Status: {status}")
        report_lines.append(f"  Signals (5min): {recent}")
        if mqtt_last_seen:
            report_lines.append(f"  Last MQTT Activity: {mqtt_last_seen.strftime('%H:%M:%S')}")
        report_lines.append("")
    
    # Section 5: Registered Beacons
    report_lines.append("SECTION 5: REGISTERED BEACONS")
    report_lines.append("-" * 40)
    
    beacons = session.query(Beacon).all()
    active_macs = set()
    for b in beacons:
        status = "Active" if b.is_active else "Inactive"
        report_lines.append(f"{b.name}: {b.mac_address} ({b.resource_type}) - {status}")
        if b.is_active:
            active_macs.add(normalize_mac_address(b.mac_address))
    report_lines.append("")
    
    # Section 6: Data Flow Funnel
    report_lines.append("=" * 80)
    report_lines.append("DATA FLOW FUNNEL ANALYSIS")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)
    
    total_signals_1h = session.query(func.count(RSSISignal.id)).filter(
        RSSISignal.timestamp >= one_hour_ago
    ).scalar()
    
    total_signals_24h = session.query(func.count(RSSISignal.id)).filter(
        RSSISignal.timestamp >= one_day_ago
    ).scalar()
    
    total_positions_1h = session.query(func.count(Position.id)).filter(
        Position.timestamp >= one_hour_ago
    ).scalar()
    
    total_positions_24h = session.query(func.count(Position.id)).filter(
        Position.timestamp >= one_day_ago
    ).scalar()
    
    report_lines.append("STAGE 1: MQTT Messages Received")
    report_lines.append(f"  └─ Total received this session: {stats['signals_received']}")
    report_lines.append("")
    
    report_lines.append("STAGE 2: Gateway Matching")
    report_lines.append(f"  └─ Registered gateways: {gateway_count}")
    report_lines.append(f"  └─ Active gateways: {active_gateways}")
    report_lines.append("  └─ Filter: Only messages from registered gateways pass")
    report_lines.append("")
    
    report_lines.append("STAGE 3: Beacon Filtering")
    report_lines.append(f"  └─ Registered beacons: {beacon_count}")
    report_lines.append(f"  └─ Active beacons: {active_beacons}")
    auto_disc = "ON - All beacons pass" if (mqtt_config and mqtt_config.auto_discover_beacons) else "OFF - Only registered beacons pass"
    report_lines.append(f"  └─ Auto-discover: {auto_disc}")
    report_lines.append("")
    
    report_lines.append("STAGE 4: Signals Stored in Database")
    report_lines.append(f"  └─ Stored this session: {stats['signals_stored']}")
    report_lines.append(f"  └─ Last 1 hour: {total_signals_1h}")
    report_lines.append(f"  └─ Last 24 hours: {total_signals_24h}")
    report_lines.append("")
    
    report_lines.append("STAGE 5: Position Calculation")
    report_lines.append("  └─ Requires: 3+ gateways detecting same beacon")
    report_lines.append(f"  └─ Calculated this session: {stats['positions_calculated']}")
    report_lines.append(f"  └─ Last 1 hour: {total_positions_1h}")
    report_lines.append(f"  └─ Last 24 hours: {total_positions_24h}")
    report_lines.append("")
    
    # Calculate drop-off rates
    report_lines.append("FUNNEL DROP-OFF ANALYSIS:")
    report_lines.append("-" * 40)
    
    if stats['signals_received'] > 0:
        store_rate = (stats['signals_stored'] / stats['signals_received']) * 100
        report_lines.append(f"  Received → Stored: {store_rate:.1f}%")
        
        if store_rate < 1:
            report_lines.append("  ⚠️ LOW STORAGE RATE - Possible causes:")
            report_lines.append("     • Detected beacons not registered in system")
            report_lines.append("     • Auto-discover is OFF")
            report_lines.append("     • Gateway MAC addresses don't match database")
    else:
        report_lines.append("  No signals received yet")
    
    if stats['signals_stored'] > 0:
        pos_rate = (stats['positions_calculated'] / stats['signals_stored']) * 100
        report_lines.append(f"  Stored → Positions: {pos_rate:.1f}%")
    report_lines.append("")
    
    # Section 7: Database State
    report_lines.append("SECTION 7: DATABASE STATE")
    report_lines.append("-" * 40)
    
    total_signals = session.query(func.count(RSSISignal.id)).scalar()
    total_positions = session.query(func.count(Position.id)).scalar()
    latest_signal = session.query(func.max(RSSISignal.timestamp)).scalar()
    latest_position = session.query(func.max(Position.timestamp)).scalar()
    
    report_lines.append(f"Total Signals: {total_signals}")
    report_lines.append(f"Total Positions: {total_positions}")
    if latest_signal:
        report_lines.append(f"Latest Signal: {latest_signal.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        report_lines.append("Latest Signal: None")
    if latest_position:
        report_lines.append(f"Latest Position: {latest_position.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        report_lines.append("Latest Position: None")
    report_lines.append("")
    
    # Section 8: Recommendations
    report_lines.append("=" * 80)
    report_lines.append("RECOMMENDATIONS")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    issues = []
    
    if not mqtt_config:
        issues.append("• Configure MQTT broker connection")
    
    if not processor.is_running:
        issues.append("• Start the signal processor")
    
    if stats['signals_received'] > 0 and stats['signals_stored'] == 0:
        issues.append("• Detected beacons don't match registered beacons")
        if mqtt_config and not mqtt_config.auto_discover_beacons:
            issues.append("• Consider enabling auto-discover temporarily to see detected beacons")
        issues.append("• Verify your registered beacons are powered on and transmitting")
    
    # Check for silent gateways
    for gw in gateways:
        gw_mac = gw.mac_address.upper() if gw.mac_address else ''
        mqtt_last_seen = mqtt_activity.get(gw_mac)
        recent = session.query(func.count(RSSISignal.id)).filter(
            RSSISignal.gateway_id == gw.id,
            RSSISignal.timestamp >= five_min_ago
        ).scalar()
        
        if not mqtt_last_seen:
            issues.append(f"• Gateway {gw.name} has never sent MQTT data - check gateway configuration")
        elif mqtt_last_seen < two_min_ago and recent == 0:
            issues.append(f"• Gateway {gw.name} is offline - check power and network")
    
    if issues:
        for issue in issues:
            report_lines.append(issue)
    else:
        report_lines.append("✓ System appears to be functioning correctly")
    
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("END OF REPORT")
    report_lines.append("=" * 80)
    
    return "\n".join(report_lines)


def render_signal_monitor(session):
    """Render the signal monitor section within dashboard."""
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("##### MQTT Status")
        mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
        
        if mqtt_config:
            st.markdown(f'<div style="background:#008ed3;color:white;padding:8px 12px;border-radius:4px;margin-bottom:8px;">Broker: {mqtt_config.broker_host}:{mqtt_config.broker_port}</div>', unsafe_allow_html=True)
            st.caption(f"Topic: {mqtt_config.topic_prefix}#")
            
            processor = get_signal_processor()
            
            st.markdown("---")
            st.markdown("##### Signal Processor")
            
            if processor.is_running:
                st.markdown('<div style="background:#5ab5b0;color:white;padding:8px 12px;border-radius:4px;margin-bottom:8px;">● Running</div>', unsafe_allow_html=True)
                stats = processor.stats
                st.write(f"**Signals received:** {stats['signals_received']}")
                st.write(f"**Signals stored:** {stats['signals_stored']}")
                st.write(f"**Positions calculated:** {stats['positions_calculated']}")
                if stats['errors'] > 0:
                    st.markdown(f'<div style="background:#e5a33d;color:white;padding:6px 10px;border-radius:4px;font-size:0.9em;">Errors: {stats["errors"]}</div>', unsafe_allow_html=True)
                
                if st.button("Stop Processing", key="dash_stop_proc"):
                    processor.stop()
                    st.rerun()
            else:
                st.markdown('<div style="background:#c9553d;color:white;padding:8px 12px;border-radius:4px;margin-bottom:8px;">● Stopped</div>', unsafe_allow_html=True)
                if processor.last_error:
                    st.markdown(f'<div style="background:#c9553d;color:white;padding:6px 10px;border-radius:4px;font-size:0.85em;margin-bottom:8px;">{processor.last_error}</div>', unsafe_allow_html=True)
                
                if st.button("Start Processing", type="primary", key="dash_start_proc"):
                    if processor.start():
                        st.rerun()
                    else:
                        st.error(processor.last_error or "Failed to start")
        else:
            st.markdown('<div style="background:#666;color:white;padding:8px 12px;border-radius:4px;">No MQTT broker configured</div>', unsafe_allow_html=True)
            st.caption("Go to MQTT Configuration to set up your broker")
    
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
    # Reduce top padding to move content upward
    st.markdown("""
        <style>
        .block-container { padding-top: 1rem !important; }
        </style>
    """, unsafe_allow_html=True)
    
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
                    st.markdown('<div style="background:#5ab5b0;color:white;padding:6px 12px;border-radius:4px;display:inline-block;">● ' + t("running") + '</div>', unsafe_allow_html=True)
                    stats = processor.stats
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric(t("received"), stats['signals_received'])
                    col_b.metric(t("stored"), stats['signals_stored'])
                    col_c.metric(t("positions"), stats['positions_calculated'])
                    if stats['errors'] > 0:
                        st.markdown(f'<div style="background:#e5a33d;color:white;padding:4px 10px;border-radius:4px;font-size:0.9em;margin-top:8px;">{t("error")}: {stats["errors"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div style="background:#c9553d;color:white;padding:6px 12px;border-radius:4px;display:inline-block;">● ' + t("stopped") + '</div>', unsafe_allow_html=True)
                    if processor.last_error:
                        st.markdown(f'<div style="background:#c9553d;color:white;padding:4px 10px;border-radius:4px;font-size:0.85em;margin-top:8px;">{processor.last_error}</div>', unsafe_allow_html=True)
                    st.caption("Expand Signal Monitor below to start processing")
            
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
                            color = "#5ab5b0"  # Teal - active
                            status_text = f"{recent} {t('signals')} (5 min)"
                        elif mqtt_last_seen and mqtt_last_seen >= two_min_ago:
                            color = "#008ed3"  # CareFlow Blue - connected
                            status_text = t("connected")
                        elif mqtt_last_seen:
                            color = "#c9553d"  # Red - offline
                            status_text = t("offline")
                        else:
                            color = "#888"  # Gray - installed
                            status_text = t("installed")
                        
                        st.markdown(f'<div style="display:flex;align-items:center;margin-bottom:6px;"><span style="display:inline-block;width:10px;height:10px;background:{color};border-radius:50%;margin-right:8px;"></span><strong>{gw.name}</strong><span style="color:#888;margin-left:8px;">— {status_text}</span></div>', unsafe_allow_html=True)
                else:
                    st.info(t("no_gateways"))
        
        st.markdown("---")
        
        with st.expander("📡 Signal Monitor", expanded=False):
            render_signal_monitor(session)
        
        with st.expander("🔍 System Diagnostics", expanded=False):
            st.markdown("##### Data Flow Diagnostic Tool")
            st.caption("Generate a detailed report showing the complete data flow funnel from MQTT to positions")
            
            if st.button("📊 Generate Diagnostic Report", type="primary", key="generate_diag"):
                with st.spinner("Generating report..."):
                    report = generate_diagnostic_report(session)
                    
                    # Store in session state
                    st.session_state['diagnostic_report'] = report
                    st.session_state['diagnostic_timestamp'] = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            
            if 'diagnostic_report' in st.session_state:
                report = st.session_state['diagnostic_report']
                timestamp = st.session_state.get('diagnostic_timestamp', 'report')
                
                col_dl, col_view = st.columns([1, 1])
                
                with col_dl:
                    st.download_button(
                        label="⬇️ Download Report",
                        data=report,
                        file_name=f"careflow_diagnostic_{timestamp}.txt",
                        mime="text/plain",
                        key="download_diag"
                    )
                
                with col_view:
                    if st.button("🗑️ Clear Report", key="clear_diag"):
                        del st.session_state['diagnostic_report']
                        if 'diagnostic_timestamp' in st.session_state:
                            del st.session_state['diagnostic_timestamp']
                        st.rerun()
                
                st.markdown("---")
                st.markdown("##### Report Preview")
                st.text_area(
                    label="Diagnostic Report",
                    value=report,
                    height=400,
                    label_visibility="collapsed"
                )
        
