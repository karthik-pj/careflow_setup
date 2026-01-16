import streamlit as st
from database import get_db_session, get_session, Building, Floor, Gateway, RSSISignal
from datetime import datetime, timedelta
from sqlalchemy import func
import re
import json
import math
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events


def get_gateway_status(session, gateway_ids, timeout_minutes=2):
    """
    Get status for each gateway based on RSSI signal activity.
    Returns dict: {gateway_id: {'status': 'active'|'offline'|'installed', 'last_seen': datetime|None}}
    
    Status meanings:
    - 'active': Detected registered beacons within timeout period
    - 'offline': Previously detected beacons but not within timeout
    - 'installed': Never detected any registered beacons (may still be receiving other signals)
    """
    if not gateway_ids:
        return {}
    
    cutoff_time = datetime.utcnow() - timedelta(minutes=timeout_minutes)
    
    latest_signals = session.query(
        RSSISignal.gateway_id,
        func.max(RSSISignal.timestamp).label('last_seen')
    ).filter(
        RSSISignal.gateway_id.in_(gateway_ids)
    ).group_by(RSSISignal.gateway_id).all()
    
    signal_times = {sig.gateway_id: sig.last_seen for sig in latest_signals}
    
    status = {}
    for gw_id in gateway_ids:
        if gw_id not in signal_times:
            status[gw_id] = 'installed'
        elif signal_times[gw_id] >= cutoff_time:
            status[gw_id] = 'active'
        else:
            status[gw_id] = 'offline'
    
    return status


def get_gateway_last_seen(session, gateway_ids):
    """
    Get the last seen timestamp for each gateway.
    Returns dict: {gateway_id: datetime|None}
    """
    if not gateway_ids:
        return {}
    
    latest_signals = session.query(
        RSSISignal.gateway_id,
        func.max(RSSISignal.timestamp).label('last_seen')
    ).filter(
        RSSISignal.gateway_id.in_(gateway_ids)
    ).group_by(RSSISignal.gateway_id).all()
    
    return {sig.gateway_id: sig.last_seen for sig in latest_signals}


def meters_to_latlon(x, y, origin_lat, origin_lon):
    """Convert local meter coordinates back to lat/lon"""
    lat = origin_lat + (y / 111000)
    lon = origin_lon + (x / (math.cos(math.radians(origin_lat)) * 111000))
    return lat, lon


def validate_mac_address(mac: str) -> bool:
    """Validate MAC address format"""
    pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
    return bool(pattern.match(mac))


def show_pending_message():
    """Display any pending success message from session state"""
    if 'gateways_success_msg' in st.session_state:
        st.success(st.session_state['gateways_success_msg'])
        del st.session_state['gateways_success_msg']


def set_success_and_rerun(message):
    """Store success message in session state and rerun"""
    st.session_state['gateways_success_msg'] = message
    st.rerun()


def extract_rooms_from_geojson(geojson_str):
    """Extract room names and their center coordinates from GeoJSON"""
    rooms = []
    try:
        geojson_data = json.loads(geojson_str)
        for feature in geojson_data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            
            if props.get('geomType') == 'room':
                name = props.get('name', '')
                if name:
                    coords = geom.get('coordinates', [])
                    if coords and geom.get('type') == 'Polygon':
                        ring = coords[0] if coords else []
                        if ring:
                            lons = [c[0] for c in ring]
                            lats = [c[1] for c in ring]
                            center_lon = sum(lons) / len(lons)
                            center_lat = sum(lats) / len(lats)
                            rooms.append({
                                'name': name,
                                'type': props.get('subType', 'room'),
                                'center_lat': center_lat,
                                'center_lon': center_lon
                            })
    except:
        pass
    return rooms


def create_floor_plan_figure(floor, gateways=None, rooms=None, for_click=False, gateway_statuses=None):
    """Create a Plotly figure showing the floor plan with rooms and gateways
    
    Args:
        floor: The floor object with floor_plan_geojson
        gateways: List of gateway objects to display
        rooms: List of room dictionaries
        for_click: If True, adds an invisible click layer for capturing clicks anywhere
        gateway_statuses: Dict mapping gateway_id to status ('installed', 'active', 'offline')
    """
    if gateway_statuses is None:
        gateway_statuses = {}
    fig = go.Figure()
    
    # Track bounds for click layer
    all_x = []
    all_y = []
    
    if floor.floor_plan_geojson:
        try:
            geojson_data = json.loads(floor.floor_plan_geojson)
            
            for feature in geojson_data.get('features', []):
                props = feature.get('properties', {})
                geom = feature.get('geometry', {})
                geom_type = props.get('geomType', '')
                
                if geom_type == 'room' and geom.get('type') == 'Polygon':
                    coords = geom.get('coordinates', [[]])[0]
                    if coords:
                        lons = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        all_x.extend(lons)
                        all_y.extend(lats)
                        name = props.get('name', 'Unnamed')
                        
                        fig.add_trace(go.Scatter(
                            x=lons,
                            y=lats,
                            fill='toself',
                            fillcolor='rgba(46, 92, 191, 0.2)',
                            line=dict(color='#2e5cbf', width=1),
                            name=name,
                            hovertemplate=f"<b>{name}</b><br>Click to place gateway here<extra></extra>",
                            mode='lines'
                        ))
                        
                        center_lon = sum(lons) / len(lons)
                        center_lat = sum(lats) / len(lats)
                        fig.add_annotation(
                            x=center_lon,
                            y=center_lat,
                            text=name[:15],
                            showarrow=False,
                            font=dict(size=8, color='#1a1a1a')
                        )
                
                elif geom_type == 'wall' and geom.get('type') == 'LineString':
                    coords = geom.get('coordinates', [])
                    if coords:
                        lons = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        all_x.extend(lons)
                        all_y.extend(lats)
                        wall_type = props.get('subType', 'inner')
                        line_width = 2 if wall_type == 'outer' else 1
                        
                        fig.add_trace(go.Scatter(
                            x=lons,
                            y=lats,
                            mode='lines',
                            line=dict(color='#333', width=line_width),
                            showlegend=False,
                            hoverinfo='skip'
                        ))
        except Exception as e:
            st.warning(f"Error rendering floor plan: {e}")
    
    # Add invisible click layer if enabled (for click-to-place functionality)
    if for_click and all_x and all_y:
        import numpy as np
        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        
        # Create a grid of invisible points for click detection
        grid_x = np.linspace(min_x, max_x, 20)
        grid_y = np.linspace(min_y, max_y, 20)
        click_x = []
        click_y = []
        for x in grid_x:
            for y in grid_y:
                click_x.append(x)
                click_y.append(y)
        
        fig.add_trace(go.Scatter(
            x=click_x,
            y=click_y,
            mode='markers',
            marker=dict(size=20, color='rgba(0,0,0,0)', line=dict(width=0)),
            hoverinfo='x+y',
            showlegend=False,
            name='click_layer'
        ))
    
    if gateways:
        status_colors = {
            'installed': '#2e5cbf',
            'active': '#27ae60',
            'offline': '#e74c3c'
        }
        status_labels = {
            'installed': 'Installed',
            'active': 'Active', 
            'offline': 'Offline'
        }
        
        for gw in gateways:
            if gw.latitude and gw.longitude:
                status = gateway_statuses.get(gw.id, 'installed')
                color = status_colors.get(status, '#2e5cbf')
                status_label = status_labels.get(status, 'Unknown')
                
                fig.add_trace(go.Scatter(
                    x=[gw.longitude],
                    y=[gw.latitude],
                    mode='markers+text',
                    marker=dict(symbol='square', size=12, color=color),
                    text=[gw.name],
                    textposition='top center',
                    name=gw.name,
                    showlegend=False,
                    hovertemplate=f"<b>{gw.name}</b><br>Status: {status_label}<extra></extra>"
                ))
            elif gw.x_position is not None and gw.y_position is not None:
                status = gateway_statuses.get(gw.id, 'installed')
                color = status_colors.get(status, '#2e5cbf')
                status_label = status_labels.get(status, 'Unknown')
                
                fig.add_trace(go.Scatter(
                    x=[gw.x_position],
                    y=[gw.y_position],
                    mode='markers+text',
                    marker=dict(symbol='square', size=12, color=color),
                    text=[gw.name],
                    textposition='top center',
                    name=gw.name,
                    showlegend=False,
                    hovertemplate=f"<b>{gw.name}</b><br>Status: {status_label}<extra></extra>"
                ))
    
    # Apply focus area if set
    x_range = None
    y_range = None
    if floor.focus_min_x is not None:
        # Check if floor uses GPS coordinates (non-zero origin) or meter coordinates (origin at 0,0)
        if floor.origin_lat and floor.origin_lon:
            # Convert from meters to lat/lon for GPS-based floors
            min_lat, min_lon = meters_to_latlon(floor.focus_min_x - 1, floor.focus_min_y - 1, floor.origin_lat, floor.origin_lon)
            max_lat, max_lon = meters_to_latlon(floor.focus_max_x + 1, floor.focus_max_y + 1, floor.origin_lat, floor.origin_lon)
            x_range = [min_lon, max_lon]
            y_range = [min_lat, max_lat]
        else:
            # Use meter coordinates directly for floors with origin at (0,0)
            x_range = [floor.focus_min_x - 1, floor.focus_max_x + 1]
            y_range = [floor.focus_min_y - 1, floor.focus_max_y + 1]
    
    xaxis_config = dict(
        scaleanchor='y',
        scaleratio=1,
        showgrid=False,
        zeroline=False,
        showticklabels=False,
        title='',
        constrain='domain'
    )
    yaxis_config = dict(
        showgrid=False,
        zeroline=False,
        showticklabels=False,
        title='',
        constrain='domain'
    )
    
    if x_range:
        xaxis_config['range'] = x_range
    if y_range:
        yaxis_config['range'] = y_range
    
    fig.update_layout(
        showlegend=False,
        xaxis=xaxis_config,
        yaxis=yaxis_config,
        margin=dict(l=10, r=10, t=10, b=10),
        height=400,
        plot_bgcolor='white',
        hovermode='closest',
        clickmode='event'
    )
    
    return fig


def render():
    st.title("Gateway Configuration")
    st.markdown("Configure Careflow BLE Gateway devices")
    
    show_pending_message()
    
    with get_db_session() as session:
        buildings = session.query(Building).order_by(Building.name).all()
        
        if not buildings:
            st.warning("Please add a building first before configuring gateways.")
            st.info("Go to 'Buildings & Floor Plans' to add a building.")
            return
        
        st.subheader("Add New Gateway")
        
        building_options = {b.name: b.id for b in buildings}
        selected_building_name = st.selectbox("Select Building*", options=list(building_options.keys()))
        selected_building_id = building_options[selected_building_name]
        
        floors = session.query(Floor).filter(
            Floor.building_id == selected_building_id
        ).order_by(Floor.floor_number).all()
        
        if not floors:
            st.warning("Please upload a floor plan for this building first.")
            return
        
        floor_options = {f"{f.name or 'Floor ' + str(f.floor_number)} (Level {f.floor_number})": f.id for f in floors}
        selected_floor_key = st.selectbox("Select Floor*", options=list(floor_options.keys()))
        selected_floor_id = floor_options[selected_floor_key]
        
        # Clear clicked position when floor changes to prevent stale coordinates
        if 'gw_last_floor_id' not in st.session_state:
            st.session_state['gw_last_floor_id'] = selected_floor_id
        elif st.session_state['gw_last_floor_id'] != selected_floor_id:
            # Floor changed - clear clicked coordinates
            st.session_state['gw_last_floor_id'] = selected_floor_id
            if 'gw_clicked_x' in st.session_state:
                del st.session_state['gw_clicked_x']
            if 'gw_clicked_y' in st.session_state:
                del st.session_state['gw_clicked_y']
            if 'gw_has_clicked' in st.session_state:
                del st.session_state['gw_has_clicked']
        
        selected_floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
        
        existing_gateways = session.query(Gateway).filter(
            Gateway.floor_id == selected_floor_id
        ).all()
        
        gateway_ids = [gw.id for gw in existing_gateways]
        gateway_statuses = get_gateway_status(session, gateway_ids)
        
        rooms = []
        if selected_floor and selected_floor.floor_plan_geojson:
            rooms = extract_rooms_from_geojson(selected_floor.floor_plan_geojson)
            
            st.markdown("#### Floor Plan - Click to Place Gateway")
            st.caption("👆 **Click on the floor plan** to select the exact gateway position, or use the options below.")
            
            fig = create_floor_plan_figure(selected_floor, existing_gateways, rooms, for_click=True, gateway_statuses=gateway_statuses)
            
            # Use plotly_events to capture click position
            # override_height is required for reliable click detection
            click_data = plotly_events(fig, click_event=True, key="gateway_click_map", override_height=400)
            
            # Process click data
            if click_data and len(click_data) > 0:
                clicked_x = click_data[0].get('x')
                clicked_y = click_data[0].get('y')
                if clicked_x is not None and clicked_y is not None:
                    # Store clicked position in session state with floor-scoped keys
                    st.session_state['gw_clicked_x'] = clicked_x
                    st.session_state['gw_clicked_y'] = clicked_y
                    st.session_state['gw_has_clicked'] = True
            
            # Display clicked position if available
            if 'gw_clicked_x' in st.session_state and 'gw_clicked_y' in st.session_state:
                clicked_x = st.session_state['gw_clicked_x']
                clicked_y = st.session_state['gw_clicked_y']
                
                # Determine if coordinates are in meters or lat/lon
                if selected_floor.origin_lat and selected_floor.origin_lon:
                    # Floor uses GPS coordinates - clicked values are lat/lon
                    st.success(f"📍 Selected position: Lat {clicked_y:.6f}, Lon {clicked_x:.6f}")
                else:
                    # Floor uses meter coordinates directly
                    st.success(f"📍 Selected position: X = {clicked_x:.2f}m, Y = {clicked_y:.2f}m")
        
        col1, col2 = st.columns(2)
        
        with col1:
            mac_address = st.text_input(
                "MAC Address*",
                placeholder="AA:BB:CC:DD:EE:FF",
                help="The MAC address of the Careflow gateway"
            ).upper()
            
            name = st.text_input(
                "Gateway Name*",
                placeholder="e.g., Entrance Gateway"
            )
            
            wifi_ssid = st.text_input(
                "WiFi SSID",
                placeholder="Network name the gateway connects to"
            )
        
        with col2:
            mqtt_topic = st.text_input(
                "MQTT Topic",
                placeholder="ble/gateway/entrance",
                help="Custom MQTT topic for this gateway"
            )
            
            signal_calibration = st.number_input(
                "Signal Calibration (dBm)",
                value=-59,
                min_value=-100,
                max_value=0,
                help="RSSI at 1 meter distance"
            )
            
            path_loss = st.number_input(
                "Path Loss Exponent",
                value=2.0,
                min_value=1.0,
                max_value=6.0,
                help="2.0 for free space, 2.5-4 for indoor"
            )
        
        st.markdown("#### Gateway Position")
        
        # Determine available position methods
        position_options = ["Click on Floor Plan", "Select Room", "Enter Coordinates Manually"]
        if not rooms:
            position_options = ["Click on Floor Plan", "Enter Coordinates Manually"]
        
        position_method = st.radio(
            "Position Method",
            position_options,
            horizontal=True,
            help="Choose how to specify the gateway position"
        )
        
        latitude = 0.0
        longitude = 0.0
        x_position = 0.0
        y_position = 0.0
        
        # Handle "Click on Floor Plan" position method
        has_clicked = st.session_state.get('gw_has_clicked', False)
        
        if position_method == "Click on Floor Plan":
            if has_clicked and 'gw_clicked_x' in st.session_state and 'gw_clicked_y' in st.session_state:
                clicked_x = st.session_state['gw_clicked_x']
                clicked_y = st.session_state['gw_clicked_y']
                
                # Check if floor uses GPS or meter coordinates
                if selected_floor.origin_lat and selected_floor.origin_lon:
                    # Floor uses GPS - clicked values are lat/lon
                    latitude = clicked_y
                    longitude = clicked_x
                    # Calculate meter positions from origin
                    lat_diff = latitude - selected_floor.origin_lat
                    lon_diff = longitude - selected_floor.origin_lon
                    y_position = lat_diff * 111000
                    x_position = lon_diff * 111000 * abs(math.cos(math.radians(latitude)))
                else:
                    # Floor uses meter coordinates directly
                    x_position = clicked_x
                    y_position = clicked_y
                    # Convert meters to lat/lon if origin is set (even if 0)
                    if selected_floor.origin_lat is not None and selected_floor.origin_lon is not None:
                        latitude, longitude = meters_to_latlon(x_position, y_position, 
                                                               selected_floor.origin_lat, selected_floor.origin_lon)
                
                st.info(f"Position: X = {x_position:.2f}m, Y = {y_position:.2f}m")
                if latitude != 0 or longitude != 0:
                    st.info(f"GPS: {latitude:.6f}, {longitude:.6f}")
            else:
                st.warning("👆 Click on the floor plan above to select a position")
        
        elif position_method == "Select Room" and rooms:
            room_options = ["-- Select a room --"] + [r['name'] for r in rooms]
            selected_room = st.selectbox("Select Room*", options=room_options)
            
            if selected_room != "-- Select a room --":
                room_data = next((r for r in rooms if r['name'] == selected_room), None)
                if room_data:
                    latitude = room_data['center_lat']
                    longitude = room_data['center_lon']
                    
                    if selected_floor.origin_lat and selected_floor.origin_lon:
                        import math
                        lat_diff = latitude - selected_floor.origin_lat
                        lon_diff = longitude - selected_floor.origin_lon
                        y_position = lat_diff * 111000
                        x_position = lon_diff * 111000 * abs(math.cos(math.radians(latitude)))
                    
                    st.info(f"Room center: {latitude:.6f}, {longitude:.6f}")
        
        elif position_method == "Select Room" and not rooms:
            st.warning("No rooms found in floor plan. Please enter coordinates manually.")
            position_method = "Enter Coordinates Manually"
        
        if position_method == "Enter Coordinates Manually":
            col3, col4 = st.columns(2)
            
            with col3:
                latitude = st.number_input(
                    "Latitude (GPS)*",
                    value=selected_floor.origin_lat if selected_floor and selected_floor.origin_lat else 0.0,
                    format="%.6f",
                    min_value=-90.0,
                    max_value=90.0
                )
                
                x_position = st.number_input(
                    "X Position (meters)",
                    value=0.0,
                    min_value=0.0,
                    max_value=1000.0,
                    help="Position from left edge of floor plan"
                )
            
            with col4:
                longitude = st.number_input(
                    "Longitude (GPS)*",
                    value=selected_floor.origin_lon if selected_floor and selected_floor.origin_lon else 0.0,
                    format="%.6f",
                    min_value=-180.0,
                    max_value=180.0
                )
                
                y_position = st.number_input(
                    "Y Position (meters)",
                    value=0.0,
                    min_value=0.0,
                    max_value=1000.0,
                    help="Position from bottom edge of floor plan"
                )
        
        # Installation height
        st.markdown("#### Installation Height")
        z_position = st.number_input(
            "Installation Height (meters)",
            value=2.5,
            min_value=0.0,
            max_value=10.0,
            step=0.1,
            help="Height of the gateway/anchor installation from the floor level (typically 2-3m)"
        )
        
        description = st.text_area(
            "Description",
            placeholder="Describe the gateway location..."
        )
        
        is_active = st.checkbox("Gateway is active", value=True)
        
        if st.button("Add Gateway", type="primary"):
            if not name:
                st.error("Gateway name is required")
            elif not mac_address:
                st.error("MAC address is required")
            elif not validate_mac_address(mac_address):
                st.error("Invalid MAC address format. Use AA:BB:CC:DD:EE:FF")
            elif position_method == "Select Room" and (latitude == 0 and longitude == 0):
                st.error("Please select a room for the gateway position")
            elif position_method == "Click on Floor Plan" and not has_clicked:
                st.error("Please click on the floor plan to select a position")
            else:
                existing = session.query(Gateway).filter(
                    Gateway.mac_address == mac_address
                ).first()
                
                if existing:
                    st.error("A gateway with this MAC address already exists")
                else:
                    gateway = Gateway(
                        building_id=selected_building_id,
                        floor_id=selected_floor_id,
                        mac_address=mac_address,
                        name=name,
                        description=description,
                        x_position=x_position,
                        y_position=y_position,
                        z_position=z_position,
                        latitude=latitude if latitude != 0 else None,
                        longitude=longitude if longitude != 0 else None,
                        mqtt_topic=mqtt_topic or None,
                        wifi_ssid=wifi_ssid or None,
                        is_active=is_active,
                        signal_strength_calibration=signal_calibration,
                        path_loss_exponent=path_loss
                    )
                    session.add(gateway)
                    session.commit()
                    # Clear clicked position from session state
                    if 'gw_clicked_x' in st.session_state:
                        del st.session_state['gw_clicked_x']
                    if 'gw_clicked_y' in st.session_state:
                        del st.session_state['gw_clicked_y']
                    if 'gw_has_clicked' in st.session_state:
                        del st.session_state['gw_has_clicked']
                    set_success_and_rerun(f"Gateway '{name}' added successfully!")
        
        st.markdown("---")
        st.subheader("Configured Gateways")
        
        gateways = session.query(Gateway).order_by(Gateway.name).all()
        
        if gateways:
            for gw in gateways:
                floor = session.query(Floor).filter(Floor.id == gw.floor_id).first()
                building = session.query(Building).filter(Building.id == gw.building_id).first()
                
                status_icon = "🟢" if gw.is_active else "🔴"
                
                with st.expander(f"{status_icon} {gw.name} ({gw.mac_address})", expanded=False):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        st.write(f"**Building:** {building.name if building else 'Unknown'}")
                        st.write(f"**Floor:** {floor.name if floor else 'Unknown'}")
                        z_height = gw.z_position if gw.z_position else 2.5
                        st.write(f"**Position:** ({gw.x_position:.1f}m, {gw.y_position:.1f}m, H: {z_height:.1f}m)")
                        if gw.latitude and gw.longitude:
                            st.write(f"**GPS:** {gw.latitude:.6f}, {gw.longitude:.6f}")
                        if gw.wifi_ssid:
                            st.write(f"**WiFi:** {gw.wifi_ssid}")
                    
                    with col2:
                        st.write(f"**MQTT Topic:** {gw.mqtt_topic or 'Default'}")
                        st.write(f"**Calibration:** {gw.signal_strength_calibration} dBm")
                        st.write(f"**Path Loss:** {gw.path_loss_exponent}")
                        if gw.description:
                            st.write(f"**Description:** {gw.description}")
                    
                    with col3:
                        if st.button("Toggle Active", key=f"toggle_gw_{gw.id}"):
                            gw.is_active = not gw.is_active
                            session.commit()
                            st.rerun()
                        
                        if st.button("🗑️ Delete", key=f"del_gw_{gw.id}", type="secondary"):
                            st.session_state['pending_delete_gw_id'] = gw.id
                            st.session_state['pending_delete_gw_name'] = gw.name
            
        # Show delete confirmation outside the gateway loop but inside gateways block
        if 'pending_delete_gw_id' in st.session_state:
            pending_id = st.session_state['pending_delete_gw_id']
            pending_name = st.session_state.get('pending_delete_gw_name', 'Gateway')
            st.warning(f"⚠️ Are you sure you want to delete gateway '{pending_name}'?")
            col_yes, col_no, _ = st.columns([1, 1, 4])
            with col_yes:
                if st.button("✅ Yes, Delete", key="confirm_delete_yes", type="primary"):
                    # Delete using direct SQL - first delete related signals
                    from sqlalchemy import text
                    try:
                        # Delete related RSSI signals first
                        session.execute(text(f"DELETE FROM rssi_signals WHERE gateway_id = {pending_id}"))
                        # Then delete the gateway
                        session.execute(text(f"DELETE FROM gateways WHERE id = {pending_id}"))
                        session.commit()
                        st.session_state['gateways_success_msg'] = f"Gateway '{pending_name}' deleted (including related signals)"
                        del st.session_state['pending_delete_gw_id']
                        if 'pending_delete_gw_name' in st.session_state:
                            del st.session_state['pending_delete_gw_name']
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
            with col_no:
                if st.button("❌ Cancel", key="confirm_delete_no"):
                    del st.session_state['pending_delete_gw_id']
                    if 'pending_delete_gw_name' in st.session_state:
                        del st.session_state['pending_delete_gw_name']
                    st.rerun()
        
        else:
            st.info("No gateways configured yet. Add your first gateway above.")
