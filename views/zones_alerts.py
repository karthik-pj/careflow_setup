import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, Zone, ZoneAlert
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
import base64


def point_in_zone(x, y, zone):
    """Check if a point is inside a zone rectangle"""
    return zone.x_min <= x <= zone.x_max and zone.y_min <= y <= zone.y_max


def get_zones_figure(floor, zones, gateways_data, beacon_positions=None):
    """Create a plotly figure with floor plan, zones, and current positions"""
    
    fig = go.Figure()
    
    if floor.floor_plan_image:
        try:
            image = Image.open(BytesIO(floor.floor_plan_image))
            
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            fig.add_layout_image(
                dict(
                    source=f"data:image/png;base64,{img_str}",
                    xref="x",
                    yref="y",
                    x=0,
                    y=floor.height_meters,
                    sizex=floor.width_meters,
                    sizey=floor.height_meters,
                    sizing="stretch",
                    opacity=0.8,
                    layer="below"
                )
            )
        except Exception:
            pass
    
    for zone in zones:
        fig.add_shape(
            type="rect",
            x0=zone.x_min,
            y0=zone.y_min,
            x1=zone.x_max,
            y1=zone.y_max,
            line=dict(color=zone.color, width=2),
            fillcolor=zone.color,
            opacity=0.3,
            name=zone.name
        )
        
        fig.add_annotation(
            x=(zone.x_min + zone.x_max) / 2,
            y=zone.y_max + 0.5,
            text=zone.name,
            showarrow=False,
            font=dict(size=12, color=zone.color)
        )
    
    for gw in gateways_data:
        fig.add_trace(go.Scatter(
            x=[gw['x']],
            y=[gw['y']],
            mode='markers',
            marker=dict(size=10, color='blue', symbol='square'),
            name=f"Gateway: {gw['name']}",
            showlegend=False
        ))
    
    if beacon_positions:
        colors = ['red', 'green', 'orange', 'purple', 'cyan', 'magenta']
        for idx, (beacon_name, pos) in enumerate(beacon_positions.items()):
            color = colors[idx % len(colors)]
            fig.add_trace(go.Scatter(
                x=[pos['x']],
                y=[pos['y']],
                mode='markers+text',
                marker=dict(size=12, color=color),
                text=[beacon_name],
                textposition='bottom center',
                name=beacon_name
            ))
    
    fig.update_layout(
        xaxis=dict(
            range=[0, floor.width_meters],
            title="X (meters)",
            constrain='domain'
        ),
        yaxis=dict(
            range=[0, floor.height_meters],
            title="Y (meters)",
            scaleanchor="x",
            scaleratio=1
        ),
        showlegend=True,
        legend=dict(x=1.02, y=1),
        margin=dict(l=50, r=150, t=50, b=50),
        height=500
    )
    
    return fig


def check_zone_transitions(session, floor_id):
    """Check for beacon zone entry/exit events"""
    zones = session.query(Zone).filter(
        Zone.floor_id == floor_id,
        Zone.is_active == True
    ).all()
    
    if not zones:
        return []
    
    alerts = []
    thirty_seconds_ago = datetime.utcnow() - timedelta(seconds=30)
    
    beacons = session.query(Beacon).filter(Beacon.is_active == True).all()
    
    for beacon in beacons:
        positions = session.query(Position).filter(
            Position.beacon_id == beacon.id,
            Position.floor_id == floor_id,
            Position.timestamp >= thirty_seconds_ago
        ).order_by(Position.timestamp.desc()).limit(2).all()
        
        if len(positions) < 2:
            continue
        
        current_pos = positions[0]
        prev_pos = positions[1]
        
        for zone in zones:
            was_in_zone = point_in_zone(prev_pos.x_position, prev_pos.y_position, zone)
            is_in_zone = point_in_zone(current_pos.x_position, current_pos.y_position, zone)
            
            if not was_in_zone and is_in_zone and zone.alert_on_enter:
                existing = session.query(ZoneAlert).filter(
                    ZoneAlert.zone_id == zone.id,
                    ZoneAlert.beacon_id == beacon.id,
                    ZoneAlert.alert_type == 'enter',
                    ZoneAlert.timestamp >= thirty_seconds_ago
                ).first()
                
                if not existing:
                    alert = ZoneAlert(
                        zone_id=zone.id,
                        beacon_id=beacon.id,
                        alert_type='enter',
                        x_position=current_pos.x_position,
                        y_position=current_pos.y_position,
                        timestamp=datetime.utcnow()
                    )
                    session.add(alert)
                    alerts.append({
                        'type': 'enter',
                        'zone': zone.name,
                        'beacon': beacon.name,
                        'time': datetime.utcnow()
                    })
            
            elif was_in_zone and not is_in_zone and zone.alert_on_exit:
                existing = session.query(ZoneAlert).filter(
                    ZoneAlert.zone_id == zone.id,
                    ZoneAlert.beacon_id == beacon.id,
                    ZoneAlert.alert_type == 'exit',
                    ZoneAlert.timestamp >= thirty_seconds_ago
                ).first()
                
                if not existing:
                    alert = ZoneAlert(
                        zone_id=zone.id,
                        beacon_id=beacon.id,
                        alert_type='exit',
                        x_position=current_pos.x_position,
                        y_position=current_pos.y_position,
                        timestamp=datetime.utcnow()
                    )
                    session.add(alert)
                    alerts.append({
                        'type': 'exit',
                        'zone': zone.name,
                        'beacon': beacon.name,
                        'time': datetime.utcnow()
                    })
    
    return alerts


def render():
    st.title("Zones & Alerts")
    st.markdown("Define geofencing zones and monitor entry/exit alerts")
    
    tab1, tab2, tab3 = st.tabs(["Zone Management", "Live Monitoring", "Alert History"])
    
    with tab1:
        render_zone_management()
    
    with tab2:
        render_live_monitoring()
    
    with tab3:
        render_alert_history()


def render_zone_management():
    with get_db_session() as session:
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured. Please add a building first.")
            return
        
        st.subheader("Create New Zone")
        
        with st.form("create_zone"):
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox("Building", options=list(building_options.keys()))
            
            floors = session.query(Floor).filter(
                Floor.building_id == building_options[selected_building]
            ).order_by(Floor.floor_number).all()
            
            if not floors:
                st.warning("No floor plans for this building.")
                st.form_submit_button("Create Zone", disabled=True)
                return
            
            floor_options = {f"Floor {f.floor_number}: {f.name or ''}": f.id for f in floors}
            selected_floor = st.selectbox("Floor", options=list(floor_options.keys()))
            
            col1, col2 = st.columns(2)
            
            with col1:
                zone_name = st.text_input("Zone Name*", placeholder="e.g., Restricted Area")
                description = st.text_area("Description", placeholder="Zone description...")
                color = st.color_picker("Zone Color", "#FF0000")
            
            with col2:
                col2a, col2b = st.columns(2)
                with col2a:
                    x_min = st.number_input("X Min (m)", value=0.0, min_value=0.0)
                    y_min = st.number_input("Y Min (m)", value=0.0, min_value=0.0)
                with col2b:
                    x_max = st.number_input("X Max (m)", value=10.0, min_value=0.0)
                    y_max = st.number_input("Y Max (m)", value=10.0, min_value=0.0)
                
                alert_on_enter = st.checkbox("Alert on Enter", value=True)
                alert_on_exit = st.checkbox("Alert on Exit", value=True)
            
            submitted = st.form_submit_button("Create Zone", type="primary")
            
            if submitted:
                if not zone_name:
                    st.error("Zone name is required")
                elif x_max <= x_min or y_max <= y_min:
                    st.error("Max values must be greater than min values")
                else:
                    zone = Zone(
                        floor_id=floor_options[selected_floor],
                        name=zone_name,
                        description=description,
                        x_min=x_min,
                        y_min=y_min,
                        x_max=x_max,
                        y_max=y_max,
                        color=color,
                        alert_on_enter=alert_on_enter,
                        alert_on_exit=alert_on_exit,
                        is_active=True
                    )
                    session.add(zone)
                    st.success(f"Zone '{zone_name}' created!")
                    st.rerun()
        
        st.markdown("---")
        st.subheader("Existing Zones")
        
        zones = session.query(Zone).order_by(Zone.name).all()
        
        if zones:
            for zone in zones:
                floor = session.query(Floor).filter(Floor.id == zone.floor_id).first()
                status_icon = "🟢" if zone.is_active else "🔴"
                
                with st.expander(f"{status_icon} {zone.name}", expanded=False):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        st.write(f"**Floor:** {floor.name if floor else 'Unknown'}")
                        st.write(f"**Area:** ({zone.x_min}, {zone.y_min}) to ({zone.x_max}, {zone.y_max})")
                        st.write(f"**Description:** {zone.description or 'None'}")
                    
                    with col2:
                        st.write(f"**Alert on Enter:** {'Yes' if zone.alert_on_enter else 'No'}")
                        st.write(f"**Alert on Exit:** {'Yes' if zone.alert_on_exit else 'No'}")
                        st.markdown(f"**Color:** <span style='color:{zone.color}'>{zone.color}</span>", unsafe_allow_html=True)
                    
                    with col3:
                        if st.button("Toggle Active", key=f"toggle_zone_{zone.id}"):
                            zone.is_active = not zone.is_active
                            st.rerun()
                        
                        if st.button("Delete", key=f"del_zone_{zone.id}", type="secondary"):
                            session.delete(zone)
                            st.success(f"Zone '{zone.name}' deleted")
                            st.rerun()
        else:
            st.info("No zones created yet.")


def render_live_monitoring():
    with get_db_session() as session:
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured.")
            return
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            st.subheader("Settings")
            
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox("Building", options=list(building_options.keys()), key="monitor_building")
            
            floors = session.query(Floor).filter(
                Floor.building_id == building_options[selected_building]
            ).order_by(Floor.floor_number).all()
            
            if not floors:
                st.warning("No floor plans.")
                return
            
            floor_options = {f"Floor {f.floor_number}": f.id for f in floors}
            selected_floor_name = st.selectbox("Floor", options=list(floor_options.keys()), key="monitor_floor")
            selected_floor_id = floor_options[selected_floor_name]
            
            auto_refresh = st.checkbox("Auto-refresh", value=True, key="zone_auto_refresh")
            
            if st.button("Check for Alerts"):
                new_alerts = check_zone_transitions(session, selected_floor_id)
                if new_alerts:
                    for alert in new_alerts:
                        st.warning(f"{alert['beacon']} {alert['type']}ed {alert['zone']}")
                else:
                    st.info("No new zone transitions detected")
        
        with col2:
            floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
            
            zones = session.query(Zone).filter(
                Zone.floor_id == selected_floor_id,
                Zone.is_active == True
            ).all()
            
            gateways = session.query(Gateway).filter(
                Gateway.floor_id == selected_floor_id,
                Gateway.is_active == True
            ).all()
            
            gateways_data = [
                {'name': gw.name, 'x': gw.x_position, 'y': gw.y_position}
                for gw in gateways
            ]
            
            five_seconds_ago = datetime.utcnow() - timedelta(seconds=5)
            recent_positions = session.query(Position).filter(
                Position.floor_id == selected_floor_id,
                Position.timestamp >= five_seconds_ago
            ).order_by(Position.timestamp.desc()).all()
            
            beacon_positions = {}
            for pos in recent_positions:
                beacon = session.query(Beacon).filter(Beacon.id == pos.beacon_id).first()
                if beacon and beacon.name not in beacon_positions:
                    beacon_positions[beacon.name] = {
                        'x': pos.x_position,
                        'y': pos.y_position
                    }
            
            st.subheader(f"Zone Map: {floor.name or f'Floor {floor.floor_number}'}")
            
            fig = get_zones_figure(floor, zones, gateways_data, beacon_positions)
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("Current Zone Occupancy")
            
            if zones and beacon_positions:
                for zone in zones:
                    beacons_in_zone = []
                    for beacon_name, pos in beacon_positions.items():
                        if point_in_zone(pos['x'], pos['y'], zone):
                            beacons_in_zone.append(beacon_name)
                    
                    if beacons_in_zone:
                        st.write(f"**{zone.name}:** {', '.join(beacons_in_zone)}")
                    else:
                        st.write(f"**{zone.name}:** Empty")
            elif not zones:
                st.info("No zones defined for this floor.")
            else:
                st.info("No beacons currently tracked on this floor.")
            
            if auto_refresh:
                import time
                time.sleep(2)
                st.rerun()


def render_alert_history():
    with get_db_session() as session:
        st.subheader("Alert History")
        
        col1, col2 = st.columns(2)
        
        with col1:
            filter_type = st.selectbox(
                "Filter by Type",
                options=["All", "Enter", "Exit"]
            )
        
        with col2:
            filter_ack = st.selectbox(
                "Filter by Status",
                options=["All", "Unacknowledged", "Acknowledged"]
            )
        
        query = session.query(ZoneAlert).order_by(ZoneAlert.timestamp.desc())
        
        if filter_type != "All":
            query = query.filter(ZoneAlert.alert_type == filter_type.lower())
        
        if filter_ack == "Unacknowledged":
            query = query.filter(ZoneAlert.acknowledged == False)
        elif filter_ack == "Acknowledged":
            query = query.filter(ZoneAlert.acknowledged == True)
        
        alerts = query.limit(100).all()
        
        if alerts:
            st.write(f"**Total alerts shown:** {len(alerts)}")
            
            if st.button("Acknowledge All Visible"):
                for alert in alerts:
                    alert.acknowledged = True
                st.success("All alerts acknowledged")
                st.rerun()
            
            for alert in alerts:
                zone = session.query(Zone).filter(Zone.id == alert.zone_id).first()
                beacon = session.query(Beacon).filter(Beacon.id == alert.beacon_id).first()
                
                icon = "🚪" if alert.alert_type == "enter" else "🚶"
                ack_icon = "✓" if alert.acknowledged else "!"
                
                with st.expander(
                    f"{icon} [{ack_icon}] {beacon.name if beacon else 'Unknown'} {alert.alert_type}ed {zone.name if zone else 'Unknown'} - {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                    expanded=False
                ):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**Zone:** {zone.name if zone else 'Unknown'}")
                        st.write(f"**Beacon:** {beacon.name if beacon else 'Unknown'}")
                        st.write(f"**Position:** ({alert.x_position:.2f}, {alert.y_position:.2f})")
                        st.write(f"**Time:** {alert.timestamp}")
                    
                    with col2:
                        if not alert.acknowledged:
                            if st.button("Acknowledge", key=f"ack_{alert.id}"):
                                alert.acknowledged = True
                                st.rerun()
        else:
            st.info("No alerts recorded yet.")
