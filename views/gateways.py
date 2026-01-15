import streamlit as st
from database import get_db_session, Building, Floor, Gateway
from datetime import datetime
import re
import json
import math
import plotly.graph_objects as go


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


def create_floor_plan_figure(floor, gateways=None, rooms=None):
    """Create a Plotly figure showing the floor plan with rooms and gateways"""
    fig = go.Figure()
    
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
    
    if gateways:
        gw_lons = []
        gw_lats = []
        gw_names = []
        for gw in gateways:
            if gw.latitude and gw.longitude:
                gw_lons.append(gw.longitude)
                gw_lats.append(gw.latitude)
                gw_names.append(gw.name)
        
        if gw_lons:
            fig.add_trace(go.Scatter(
                x=gw_lons,
                y=gw_lats,
                mode='markers+text',
                marker=dict(symbol='square', size=12, color='#e74c3c'),
                text=gw_names,
                textposition='top center',
                name='Gateways',
                hovertemplate="<b>%{text}</b><br>Gateway<extra></extra>"
            ))
    
    # Apply focus area if set (convert from meters to lat/lon)
    x_range = None
    y_range = None
    if floor.focus_min_x is not None and floor.origin_lat and floor.origin_lon:
        min_lat, min_lon = meters_to_latlon(floor.focus_min_x - 1, floor.focus_min_y - 1, floor.origin_lat, floor.origin_lon)
        max_lat, max_lon = meters_to_latlon(floor.focus_max_x + 1, floor.focus_max_y + 1, floor.origin_lat, floor.origin_lon)
        x_range = [min_lon, max_lon]
        y_range = [min_lat, max_lat]
    
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
        plot_bgcolor='white'
    )
    
    return fig


def render():
    st.title("Gateway Configuration")
    st.markdown("Configure Careflow BLE Gateway devices")
    
    show_pending_message()
    
    # Handle gateway deletion first (before main session)
    if 'delete_gateway_id' in st.session_state:
        gw_id = st.session_state.pop('delete_gateway_id')
        gw_name = st.session_state.pop('delete_gateway_name')
        with get_db_session() as del_session:
            gw_to_delete = del_session.query(Gateway).filter(Gateway.id == gw_id).first()
            if gw_to_delete:
                del_session.delete(gw_to_delete)
        st.success(f"Gateway '{gw_name}' deleted")
    
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
        
        floor_options = {f"{f.floor_number}: {f.name or 'Floor ' + str(f.floor_number)}": f.id for f in floors}
        selected_floor_key = st.selectbox("Select Floor*", options=list(floor_options.keys()))
        selected_floor_id = floor_options[selected_floor_key]
        
        selected_floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
        
        existing_gateways = session.query(Gateway).filter(
            Gateway.floor_id == selected_floor_id
        ).all()
        
        rooms = []
        if selected_floor and selected_floor.floor_plan_geojson:
            rooms = extract_rooms_from_geojson(selected_floor.floor_plan_geojson)
            
            st.markdown("#### Floor Plan - Select Room for Gateway Position")
            st.caption("View the floor plan below. Select a room from the dropdown to auto-fill coordinates.")
            
            fig = create_floor_plan_figure(selected_floor, existing_gateways, rooms)
            st.plotly_chart(fig, use_container_width=True, key="gateway_floor_plan")
        
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
        
        position_method = st.radio(
            "Position Method",
            ["Select Room", "Enter Coordinates Manually"],
            horizontal=True,
            help="Choose how to specify the gateway position"
        )
        
        latitude = 0.0
        longitude = 0.0
        x_position = 0.0
        y_position = 0.0
        
        if position_method == "Select Room" and rooms:
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
                        st.write(f"**Position:** ({gw.x_position:.1f}m, {gw.y_position:.1f}m)")
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
                        
                        if st.button("Delete", key=f"del_gw_{gw.id}", type="secondary"):
                            st.session_state['delete_gateway_id'] = gw.id
                            st.session_state['delete_gateway_name'] = gw.name
                            st.rerun()
        
        else:
            st.info("No gateways configured yet. Add your first gateway above.")
