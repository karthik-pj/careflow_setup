import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, Zone, ZoneAlert, CoverageZone
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
import base64
import json
import math
from utils.mqtt_publisher import get_mqtt_publisher


def point_in_zone(x, y, zone):
    """Check if a point is inside a zone rectangle (legacy for Zone model)"""
    return zone.x_min <= x <= zone.x_max and zone.y_min <= y <= zone.y_max


def point_in_polygon(x, y, polygon_coords):
    """Check if a point is inside a polygon using ray casting algorithm"""
    if isinstance(polygon_coords, str):
        try:
            polygon_coords = json.loads(polygon_coords)
        except:
            return False
    
    if not polygon_coords or len(polygon_coords) < 3:
        return False
    
    n = len(polygon_coords)
    inside = False
    
    j = n - 1
    for i in range(n):
        xi, yi = polygon_coords[i][0], polygon_coords[i][1]
        xj, yj = polygon_coords[j][0], polygon_coords[j][1]
        
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    
    return inside


def latlon_to_meters(lat, lon, origin_lat, origin_lon):
    """Convert lat/lon to local meter coordinates using equirectangular projection"""
    dx = (lon - origin_lon) * math.cos(math.radians(origin_lat)) * 111000
    dy = (lat - origin_lat) * 111000
    return dx, dy


def get_geojson_bounds(floor):
    """Calculate the actual coordinate bounds of the GeoJSON floor plan in meters"""
    if not floor.floor_plan_geojson or not floor.origin_lat or not floor.origin_lon:
        return None
    
    try:
        geojson_data = json.loads(floor.floor_plan_geojson)
        all_x = []
        all_y = []
        
        origin_lat = float(floor.origin_lat)
        origin_lon = float(floor.origin_lon)
        
        for feature in geojson_data.get('features', []):
            geom = feature.get('geometry', {})
            geom_type = geom.get('type', '')
            
            coords_list = []
            if geom_type == 'Polygon':
                coords_list = geom.get('coordinates', [[]])[0]
            elif geom_type == 'LineString':
                coords_list = geom.get('coordinates', [])
            elif geom_type == 'MultiPolygon':
                for poly in geom.get('coordinates', []):
                    if poly:
                        coords_list.extend(poly[0])
            
            for c in coords_list:
                if len(c) >= 2:
                    lon, lat = c[0], c[1]
                    x, y = latlon_to_meters(lat, lon, origin_lat, origin_lon)
                    all_x.append(x)
                    all_y.append(y)
        
        if all_x and all_y:
            return {
                'x_min': min(all_x),
                'x_max': max(all_x),
                'y_min': min(all_y),
                'y_max': max(all_y)
            }
    except Exception:
        pass
    
    return None


def render_geojson_floor_plan(fig, floor):
    """Render GeoJSON floor plan as Plotly traces in meter coordinates"""
    if not floor.floor_plan_geojson or not floor.origin_lat or not floor.origin_lon:
        return False
    
    try:
        geojson_data = json.loads(floor.floor_plan_geojson)
        
        for feature in geojson_data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            geom_type = props.get('geomType', '')
            
            if geom_type == 'room' and geom.get('type') == 'Polygon':
                coords = geom.get('coordinates', [[]])[0]
                if coords:
                    xs = []
                    ys = []
                    for c in coords:
                        lon, lat = c[0], c[1]
                        x, y = latlon_to_meters(lat, lon, float(floor.origin_lat), float(floor.origin_lon))
                        xs.append(x)
                        ys.append(y)
                    
                    name = props.get('name', 'Unnamed')
                    
                    fig.add_trace(go.Scatter(
                        x=xs,
                        y=ys,
                        fill='toself',
                        fillcolor='rgba(46, 92, 191, 0.15)',
                        line=dict(color='#2e5cbf', width=1),
                        name=name,
                        hovertemplate=f"<b>{name}</b><extra></extra>",
                        mode='lines',
                        showlegend=False
                    ))
                    
                    center_x = sum(xs) / len(xs)
                    center_y = sum(ys) / len(ys)
                    fig.add_annotation(
                        x=center_x,
                        y=center_y,
                        text=name[:12],
                        showarrow=False,
                        font=dict(size=8, color='#1a1a1a')
                    )
            
            elif geom_type == 'wall' and geom.get('type') == 'LineString':
                coords = geom.get('coordinates', [])
                if coords:
                    xs = []
                    ys = []
                    for c in coords:
                        lon, lat = c[0], c[1]
                        x, y = latlon_to_meters(lat, lon, float(floor.origin_lat), float(floor.origin_lon))
                        xs.append(x)
                        ys.append(y)
                    
                    wall_type = props.get('subType', 'inner')
                    line_width = 2 if wall_type == 'outer' else 1
                    
                    fig.add_trace(go.Scatter(
                        x=xs,
                        y=ys,
                        mode='lines',
                        line=dict(color='#333', width=line_width),
                        showlegend=False,
                        hoverinfo='skip'
                    ))
        
        return True
    except Exception:
        return False


def get_zones_figure(floor, zones, gateways_data, beacon_positions=None, editable=False, new_zone=None, bounds=None):
    """Create a plotly figure with floor plan, zones, and current positions"""
    
    fig = go.Figure()
    has_floor_plan = False
    
    if bounds is None:
        bounds = get_geojson_bounds(floor)
    
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
                    y=float(floor.height_meters),
                    sizex=float(floor.width_meters),
                    sizey=float(floor.height_meters),
                    sizing="stretch",
                    opacity=0.9,
                    layer="below"
                )
            )
            has_floor_plan = True
        except Exception:
            pass
    
    if not has_floor_plan and floor.floor_plan_geojson:
        has_floor_plan = render_geojson_floor_plan(fig, floor)
    
    for zone in zones:
        # Check if zone is a CoverageZone (polygon) or Zone (rectangle)
        if hasattr(zone, 'polygon_coords') and zone.polygon_coords:
            # Render as polygon
            try:
                coords = json.loads(zone.polygon_coords) if isinstance(zone.polygon_coords, str) else zone.polygon_coords
                if coords and len(coords) >= 3:
                    xs = [c[0] for c in coords] + [coords[0][0]]
                    ys = [c[1] for c in coords] + [coords[0][1]]
                    
                    color = zone.color if zone.color else '#2e5cbf'
                    fig.add_trace(go.Scatter(
                        x=xs, y=ys,
                        fill='toself',
                        fillcolor=color.replace('#', 'rgba(') + ',0.25)' if color.startswith('#') else f'rgba(46,92,191,0.25)',
                        line=dict(color=color, width=2),
                        mode='lines',
                        name=zone.name,
                        showlegend=False,
                        hovertemplate=f'{zone.name}<extra></extra>'
                    ))
                    
                    center_x = sum([c[0] for c in coords]) / len(coords)
                    center_y = sum([c[1] for c in coords]) / len(coords)
                    fig.add_annotation(
                        x=center_x,
                        y=center_y,
                        text=zone.name,
                        showarrow=False,
                        font=dict(size=11, color=color)
                    )
            except:
                pass
        else:
            # Render as rectangle (legacy Zone model)
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
    
    if new_zone:
        fig.add_shape(
            type="rect",
            x0=new_zone['x_min'],
            y0=new_zone['y_min'],
            x1=new_zone['x_max'],
            y1=new_zone['y_max'],
            line=dict(color=new_zone.get('color', '#FF0000'), width=3, dash='dash'),
            fillcolor=new_zone.get('color', '#FF0000'),
            opacity=0.4,
            name="New Zone (Preview)"
        )
        
        fig.add_annotation(
            x=(new_zone['x_min'] + new_zone['x_max']) / 2,
            y=(new_zone['y_min'] + new_zone['y_max']) / 2,
            text=new_zone.get('name', 'New Zone'),
            showarrow=False,
            font=dict(size=14, color='white'),
            bgcolor=new_zone.get('color', '#FF0000'),
            bordercolor=new_zone.get('color', '#FF0000'),
            borderwidth=1
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
    
    if bounds:
        x_min_range = bounds['x_min'] - 2
        x_max_range = bounds['x_max'] + 2
        y_min_range = bounds['y_min'] - 2
        y_max_range = bounds['y_max'] + 2
        w = bounds['x_max'] - bounds['x_min']
        h = bounds['y_max'] - bounds['y_min']
    else:
        x_min_range = 0
        x_max_range = float(floor.width_meters)
        y_min_range = 0
        y_max_range = float(floor.height_meters)
        w = x_max_range
        h = y_max_range
    
    fig.update_layout(
        xaxis=dict(
            range=[x_min_range, x_max_range],
            title="X (meters)",
            showgrid=not has_floor_plan,
            zeroline=False,
            constrain='domain',
            dtick=max(1, int(w // 8))
        ),
        yaxis=dict(
            range=[y_min_range, y_max_range],
            title="Y (meters)",
            showgrid=not has_floor_plan,
            zeroline=False,
            scaleanchor="x",
            scaleratio=1,
            dtick=max(1, int(h // 8))
        ),
        showlegend=True,
        legend=dict(x=1.02, y=1, bgcolor='rgba(255,255,255,0.8)'),
        margin=dict(l=50, r=150, t=50, b=50),
        height=500,
        plot_bgcolor='rgba(240,240,240,0.3)' if not has_floor_plan else 'rgba(255,255,255,0)'
    )
    
    return fig


def check_zone_transitions(session, floor_id):
    """Check for beacon zone entry/exit events using CoverageZone polygons"""
    zones = session.query(CoverageZone).filter(
        CoverageZone.floor_id == floor_id,
        CoverageZone.is_active == True
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
            was_in_zone = point_in_polygon(prev_pos.x_position, prev_pos.y_position, zone.polygon_coords)
            is_in_zone = point_in_polygon(current_pos.x_position, current_pos.y_position, zone.polygon_coords)
            
            if not was_in_zone and is_in_zone and zone.alert_on_enter:
                alerts.append({
                    'type': 'enter',
                    'zone': zone.name,
                    'beacon': beacon.name,
                    'time': datetime.utcnow()
                })
                
                publisher = get_mqtt_publisher()
                if publisher.is_connected():
                    floor = session.query(Floor).filter(Floor.id == zone.floor_id).first()
                    floor_name = floor.name if floor else ""
                    publisher.publish_alert(
                        alert_type='enter',
                        beacon_mac=beacon.mac_address,
                        beacon_name=beacon.name,
                        zone_id=zone.id,
                        zone_name=zone.name,
                        floor_name=floor_name,
                        x=current_pos.x_position,
                        y=current_pos.y_position,
                        resource_type=beacon.resource_type
                    )
            
            elif was_in_zone and not is_in_zone and zone.alert_on_exit:
                alerts.append({
                    'type': 'exit',
                    'zone': zone.name,
                    'beacon': beacon.name,
                    'time': datetime.utcnow()
                })
                
                publisher = get_mqtt_publisher()
                if publisher.is_connected():
                    floor = session.query(Floor).filter(Floor.id == zone.floor_id).first()
                    floor_name = floor.name if floor else ""
                    publisher.publish_alert(
                        alert_type='exit',
                        beacon_mac=beacon.mac_address,
                        beacon_name=beacon.name,
                        zone_id=zone.id,
                        zone_name=zone.name,
                        floor_name=floor_name,
                        x=current_pos.x_position,
                        y=current_pos.y_position,
                        resource_type=beacon.resource_type
                    )
    
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
        
        building_options = {b.name: b.id for b in buildings}
        selected_building = st.selectbox("Building", options=list(building_options.keys()), key="zone_building")
        
        floors = session.query(Floor).filter(
            Floor.building_id == building_options[selected_building]
        ).order_by(Floor.floor_number).all()
        
        if not floors:
            st.warning("No floor plans for this building.")
            return
        
        floor_options = {f"Floor {f.floor_number}: {f.name or ''}": f.id for f in floors}
        selected_floor_key = st.selectbox("Floor", options=list(floor_options.keys()), key="zone_floor")
        selected_floor_id = floor_options[selected_floor_key]
        
        floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
        if not floor:
            st.warning("Floor not found.")
            return
        
        existing_zones = session.query(Zone).filter(Zone.floor_id == selected_floor_id).all()
        
        gateways = session.query(Gateway).filter(
            Gateway.floor_id == selected_floor_id,
            Gateway.is_active == True
        ).all()
        gateways_data = [{'name': gw.name, 'x': float(gw.x_position), 'y': float(gw.y_position)} for gw in gateways]
        
        col_form, col_preview = st.columns([1, 2])
        
        geojson_bounds = get_geojson_bounds(floor)
        
        if geojson_bounds:
            x_range_min = geojson_bounds['x_min']
            x_range_max = geojson_bounds['x_max']
            y_range_min = geojson_bounds['y_min']
            y_range_max = geojson_bounds['y_max']
            w = x_range_max - x_range_min
            h = y_range_max - y_range_min
        else:
            x_range_min = 0.0
            y_range_min = 0.0
            x_range_max = float(floor.width_meters)
            y_range_max = float(floor.height_meters)
            w = x_range_max
            h = y_range_max
        
        with col_form:
            st.markdown("#### Zone Settings")
            
            zone_name = st.text_input("Zone Name*", placeholder="e.g., Restricted Area", key="zone_name")
            description = st.text_area("Description", placeholder="Zone description...", key="zone_desc", height=68)
            color = st.color_picker("Zone Color", "#FF0000", key="zone_color")
            
            st.markdown("#### Zone Position")
            if geojson_bounds:
                st.caption(f"Floor area: X [{x_range_min:.1f} to {x_range_max:.1f}]m, Y [{y_range_min:.1f} to {y_range_max:.1f}]m")
            else:
                st.caption(f"Floor dimensions: {w:.1f}m x {h:.1f}m")
            
            preset = st.selectbox(
                "Quick Presets",
                options=["Custom", "Top-Left Quarter", "Top-Right Quarter", "Bottom-Left Quarter", 
                         "Bottom-Right Quarter", "Center", "Left Half", "Right Half", "Top Half", "Bottom Half"],
                key="zone_preset"
            )
            
            mid_x = (x_range_min + x_range_max) / 2
            mid_y = (y_range_min + y_range_max) / 2
            
            if preset == "Top-Left Quarter":
                default_x_min, default_y_min = x_range_min, mid_y
                default_x_max, default_y_max = mid_x, y_range_max
            elif preset == "Top-Right Quarter":
                default_x_min, default_y_min = mid_x, mid_y
                default_x_max, default_y_max = x_range_max, y_range_max
            elif preset == "Bottom-Left Quarter":
                default_x_min, default_y_min = x_range_min, y_range_min
                default_x_max, default_y_max = mid_x, mid_y
            elif preset == "Bottom-Right Quarter":
                default_x_min, default_y_min = mid_x, y_range_min
                default_x_max, default_y_max = x_range_max, mid_y
            elif preset == "Center":
                default_x_min, default_y_min = x_range_min + w/4, y_range_min + h/4
                default_x_max, default_y_max = x_range_max - w/4, y_range_max - h/4
            elif preset == "Left Half":
                default_x_min, default_y_min = x_range_min, y_range_min
                default_x_max, default_y_max = mid_x, y_range_max
            elif preset == "Right Half":
                default_x_min, default_y_min = mid_x, y_range_min
                default_x_max, default_y_max = x_range_max, y_range_max
            elif preset == "Top Half":
                default_x_min, default_y_min = x_range_min, mid_y
                default_x_max, default_y_max = x_range_max, y_range_max
            elif preset == "Bottom Half":
                default_x_min, default_y_min = x_range_min, y_range_min
                default_x_max, default_y_max = x_range_max, mid_y
            else:
                zone_w = min(10.0, w/3)
                zone_h = min(10.0, h/3)
                default_x_min = x_range_min + w/2 - zone_w/2
                default_y_min = y_range_min + h/2 - zone_h/2
                default_x_max = default_x_min + zone_w
                default_y_max = default_y_min + zone_h
            
            col2a, col2b = st.columns(2)
            with col2a:
                x_min = st.number_input("X Min (m)", value=default_x_min, min_value=x_range_min - 10, max_value=x_range_max + 10, step=0.5, key="x_min")
                y_min = st.number_input("Y Min (m)", value=default_y_min, min_value=y_range_min - 10, max_value=y_range_max + 10, step=0.5, key="y_min")
            with col2b:
                x_max = st.number_input("X Max (m)", value=default_x_max, min_value=x_range_min - 10, max_value=x_range_max + 10, step=0.5, key="x_max")
                y_max = st.number_input("Y Max (m)", value=default_y_max, min_value=y_range_min - 10, max_value=y_range_max + 10, step=0.5, key="y_max")
            
            st.markdown("#### Alerts")
            col_alert1, col_alert2 = st.columns(2)
            with col_alert1:
                alert_on_enter = st.checkbox("Alert on Enter", value=True, key="alert_enter")
            with col_alert2:
                alert_on_exit = st.checkbox("Alert on Exit", value=True, key="alert_exit")
            
            if st.button("Create Zone", type="primary", use_container_width=True):
                if not zone_name:
                    st.error("Zone name is required")
                elif x_max <= x_min or y_max <= y_min:
                    st.error("Max values must be greater than min values")
                else:
                    zone = Zone(
                        floor_id=selected_floor_id,
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
        
        with col_preview:
            st.markdown("#### Floor Plan Preview")
            st.caption("The dashed rectangle shows where your new zone will be placed")
            
            new_zone_preview = {
                'x_min': x_min,
                'y_min': y_min,
                'x_max': x_max,
                'y_max': y_max,
                'color': color,
                'name': zone_name or "New Zone"
            }
            
            fig = get_zones_figure(floor, existing_zones, gateways_data, new_zone=new_zone_preview, bounds=geojson_bounds)
            st.plotly_chart(fig, use_container_width=True, key="zone_preview_chart")
            
            if existing_zones:
                st.caption(f"Existing zones shown in solid colors ({len(existing_zones)} zones)")
        
        st.markdown("---")
        st.subheader("Existing Zones")
        
        editing_zone_id = st.session_state.get('editing_zone_id', None)
        
        if editing_zone_id:
            edit_zone = session.query(Zone).filter(Zone.id == editing_zone_id).first()
            if edit_zone:
                edit_floor = session.query(Floor).filter(Floor.id == edit_zone.floor_id).first()
                if edit_floor:
                    st.markdown(f"### Editing Zone: {edit_zone.name}")
                    
                    edit_bounds = get_geojson_bounds(edit_floor)
                    if edit_bounds:
                        ex_min, ex_max = edit_bounds['x_min'], edit_bounds['x_max']
                        ey_min, ey_max = edit_bounds['y_min'], edit_bounds['y_max']
                    else:
                        ex_min, ey_min = 0.0, 0.0
                        ex_max = float(edit_floor.width_meters)
                        ey_max = float(edit_floor.height_meters)
                    
                    edit_col1, edit_col2 = st.columns([1, 2])
                    
                    with edit_col1:
                        edit_name = st.text_input("Zone Name", value=edit_zone.name, key="edit_zone_name")
                        edit_desc = st.text_area("Description", value=edit_zone.description or "", key="edit_zone_desc", height=68)
                        edit_color = st.color_picker("Color", value=edit_zone.color, key="edit_zone_color")
                        
                        st.markdown("**Position**")
                        ecol1, ecol2 = st.columns(2)
                        with ecol1:
                            edit_x_min = st.number_input("X Min", value=float(edit_zone.x_min), min_value=ex_min - 20, max_value=ex_max + 20, step=0.5, key="edit_x_min")
                            edit_y_min = st.number_input("Y Min", value=float(edit_zone.y_min), min_value=ey_min - 20, max_value=ey_max + 20, step=0.5, key="edit_y_min")
                        with ecol2:
                            edit_x_max = st.number_input("X Max", value=float(edit_zone.x_max), min_value=ex_min - 20, max_value=ex_max + 20, step=0.5, key="edit_x_max")
                            edit_y_max = st.number_input("Y Max", value=float(edit_zone.y_max), min_value=ey_min - 20, max_value=ey_max + 20, step=0.5, key="edit_y_max")
                        
                        st.markdown("**Alerts**")
                        ecol3, ecol4 = st.columns(2)
                        with ecol3:
                            edit_alert_enter = st.checkbox("Alert on Enter", value=bool(edit_zone.alert_on_enter), key="edit_alert_enter")
                        with ecol4:
                            edit_alert_exit = st.checkbox("Alert on Exit", value=bool(edit_zone.alert_on_exit), key="edit_alert_exit")
                        
                        bcol1, bcol2, bcol3 = st.columns(3)
                        with bcol1:
                            if st.button("Save Changes", type="primary", key="save_edit"):
                                if not edit_name:
                                    st.error("Zone name is required")
                                elif edit_x_max <= edit_x_min or edit_y_max <= edit_y_min:
                                    st.error("Max values must be greater than min values")
                                else:
                                    edit_zone.name = edit_name
                                    edit_zone.description = edit_desc
                                    edit_zone.color = edit_color
                                    edit_zone.x_min = edit_x_min
                                    edit_zone.y_min = edit_y_min
                                    edit_zone.x_max = edit_x_max
                                    edit_zone.y_max = edit_y_max
                                    edit_zone.alert_on_enter = edit_alert_enter
                                    edit_zone.alert_on_exit = edit_alert_exit
                                    st.session_state['editing_zone_id'] = None
                                    st.success(f"Zone '{edit_name}' updated!")
                                    st.rerun()
                        with bcol2:
                            if st.button("Cancel", key="cancel_edit"):
                                st.session_state['editing_zone_id'] = None
                                st.rerun()
                        with bcol3:
                            if st.button("Delete Zone", type="secondary", key="delete_in_edit"):
                                session.delete(edit_zone)
                                st.session_state['editing_zone_id'] = None
                                st.success(f"Zone '{edit_zone.name}' deleted!")
                                st.rerun()
                    
                    with edit_col2:
                        st.markdown("**Preview**")
                        edit_gws = session.query(Gateway).filter(Gateway.floor_id == edit_floor.id, Gateway.is_active == True).all()
                        edit_gw_data = [{'name': gw.name, 'x': float(gw.x_position), 'y': float(gw.y_position)} for gw in edit_gws]
                        
                        edit_preview = {
                            'x_min': edit_x_min,
                            'y_min': edit_y_min,
                            'x_max': edit_x_max,
                            'y_max': edit_y_max,
                            'color': edit_color,
                            'name': edit_name or "Zone"
                        }
                        
                        other_zones = session.query(Zone).filter(Zone.floor_id == edit_floor.id, Zone.id != edit_zone.id).all()
                        edit_fig = get_zones_figure(edit_floor, other_zones, edit_gw_data, new_zone=edit_preview, bounds=edit_bounds)
                        st.plotly_chart(edit_fig, use_container_width=True, key="edit_zone_preview")
                    
                    st.markdown("---")
        
        zones = session.query(Zone).order_by(Zone.name).all()
        
        if zones:
            zones_by_floor = {}
            for zone in zones:
                floor_obj = session.query(Floor).filter(Floor.id == zone.floor_id).first()
                floor_key = f"{floor_obj.name or f'Floor {floor_obj.floor_number}'}" if floor_obj else "Unknown"
                if floor_key not in zones_by_floor:
                    zones_by_floor[floor_key] = []
                zones_by_floor[floor_key].append((zone, floor_obj))
            
            for floor_name, floor_zones in zones_by_floor.items():
                st.markdown(f"**{floor_name}**")
                
                for zone, floor_obj in floor_zones:
                    status_icon = "🟢" if zone.is_active else "🔴"
                    is_editing = editing_zone_id == zone.id
                    
                    with st.expander(f"{status_icon} {zone.name}" + (" (editing)" if is_editing else ""), expanded=is_editing):
                        col1, col2, col3 = st.columns([2, 2, 1])
                        
                        with col1:
                            st.write(f"**Area:** ({float(zone.x_min):.1f}, {float(zone.y_min):.1f}) to ({float(zone.x_max):.1f}, {float(zone.y_max):.1f})")
                            st.write(f"**Size:** {float(zone.x_max) - float(zone.x_min):.1f}m x {float(zone.y_max) - float(zone.y_min):.1f}m")
                            st.write(f"**Description:** {zone.description or 'None'}")
                        
                        with col2:
                            st.write(f"**Alert on Enter:** {'Yes' if zone.alert_on_enter else 'No'}")
                            st.write(f"**Alert on Exit:** {'Yes' if zone.alert_on_exit else 'No'}")
                            st.markdown(f"**Color:** <span style='background-color:{zone.color}; padding: 2px 10px; border-radius: 3px;'>&nbsp;</span> {zone.color}", unsafe_allow_html=True)
                        
                        with col3:
                            if st.button("Toggle Active", key=f"toggle_zone_{zone.id}"):
                                zone.is_active = not zone.is_active
                                st.rerun()
                            
                            if not is_editing:
                                if st.button("Edit", key=f"edit_zone_{zone.id}", type="primary"):
                                    st.session_state['editing_zone_id'] = zone.id
                                    st.rerun()
                            
                            if st.button("Delete", key=f"del_zone_{zone.id}", type="secondary"):
                                session.delete(zone)
                                if editing_zone_id == zone.id:
                                    st.session_state['editing_zone_id'] = None
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
            
            # Use CoverageZone (polygons) instead of Zone (rectangles)
            zones = session.query(CoverageZone).filter(
                CoverageZone.floor_id == selected_floor_id,
                CoverageZone.is_active == True
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
                        if point_in_polygon(pos['x'], pos['y'], zone.polygon_coords):
                            beacons_in_zone.append(beacon_name)
                    
                    if beacons_in_zone:
                        st.write(f"**{zone.name}:** {', '.join(beacons_in_zone)}")
                    else:
                        st.write(f"**{zone.name}:** Empty")
            elif not zones:
                st.info("No zones defined for this floor. Create zones in Coverage Zones.")
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
