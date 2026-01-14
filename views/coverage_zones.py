import streamlit as st
import json
import plotly.graph_objects as go
from PIL import Image
from io import BytesIO
import base64
import numpy as np
from datetime import datetime, timedelta
from database import get_db_session, Floor, Building, CoverageZone, Zone, ZoneAlert, Beacon, Position, Gateway
from utils.mqtt_publisher import get_mqtt_publisher


def latlon_to_meters(lat, lon, origin_lat, origin_lon):
    """Convert lat/lon to meters relative to origin"""
    import math
    lat_diff = lat - origin_lat
    lon_diff = lon - origin_lon
    y = lat_diff * 111320
    x = lon_diff * 111320 * math.cos(math.radians(origin_lat))
    return x, y


def extract_building_footprint(floor):
    """Extract building footprint polygon from floor plan GeoJSON"""
    if not floor.floor_plan_geojson:
        return None
    
    try:
        geojson_data = json.loads(floor.floor_plan_geojson)
        
        for feature in geojson_data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            geom_type = props.get('geomType', '')
            
            if geom_type == 'building':
                geometry_type = geom.get('type', '')
                
                if geometry_type == 'Polygon':
                    coords = geom.get('coordinates', [[]])[0]
                    if coords and floor.origin_lat and floor.origin_lon:
                        converted = []
                        for c in coords:
                            if len(c) >= 2:
                                x, y = latlon_to_meters(c[1], c[0], floor.origin_lat, floor.origin_lon)
                                converted.append([x, y])
                        return converted
                    return coords
                
                elif geometry_type == 'MultiPolygon':
                    all_coords = []
                    for polygon in geom.get('coordinates', []):
                        if polygon and polygon[0]:
                            ring = polygon[0]
                            if floor.origin_lat and floor.origin_lon:
                                for c in ring:
                                    if len(c) >= 2:
                                        x, y = latlon_to_meters(c[1], c[0], floor.origin_lat, floor.origin_lon)
                                        all_coords.append([x, y])
                            else:
                                all_coords.extend(ring)
                    
                    if all_coords:
                        xs = [c[0] for c in all_coords]
                        ys = [c[1] for c in all_coords]
                        min_x, max_x = min(xs), max(xs)
                        min_y, max_y = min(ys), max(ys)
                        return [
                            [min_x, min_y],
                            [max_x, min_y],
                            [max_x, max_y],
                            [min_x, max_y],
                            [min_x, min_y]
                        ]
        
        return None
    except Exception:
        return None


def render_floor_plan(fig, floor):
    """Render floor plan on figure"""
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
                    opacity=0.9,
                    layer="below"
                )
            )
            return True
        except Exception:
            pass
    
    if floor.floor_plan_geojson:
        try:
            geojson_data = json.loads(floor.floor_plan_geojson)
            rendered = False
            
            for feature in geojson_data.get('features', []):
                props = feature.get('properties', {})
                geom = feature.get('geometry', {})
                geometry_type = geom.get('type', '')
                geom_type = props.get('geomType', '')
                
                if geometry_type in ['Polygon', 'MultiPolygon']:
                    if geometry_type == 'Polygon':
                        rings = [geom.get('coordinates', [[]])[0]]
                    else:
                        rings = [poly[0] for poly in geom.get('coordinates', []) if poly]
                    
                    for ring in rings:
                        xs = []
                        ys = []
                        for c in ring:
                            if len(c) >= 2:
                                if floor.origin_lat and floor.origin_lon:
                                    x, y = latlon_to_meters(c[1], c[0], floor.origin_lat, floor.origin_lon)
                                else:
                                    x, y = c[0], c[1]
                                xs.append(x)
                                ys.append(y)
                        
                        if xs:
                            fill_color = 'rgba(46, 92, 191, 0.1)' if geom_type == 'room' else 'rgba(200, 200, 200, 0.1)'
                            line_color = '#2e5cbf' if geom_type == 'room' else '#444'
                            
                            fig.add_trace(go.Scatter(
                                x=xs, y=ys,
                                fill='toself',
                                fillcolor=fill_color,
                                line=dict(color=line_color, width=1),
                                mode='lines',
                                showlegend=False,
                                hoverinfo='skip'
                            ))
                            rendered = True
                
                elif geometry_type == 'LineString':
                    coords = geom.get('coordinates', [])
                    xs = []
                    ys = []
                    for c in coords:
                        if len(c) >= 2:
                            if floor.origin_lat and floor.origin_lon:
                                x, y = latlon_to_meters(c[1], c[0], floor.origin_lat, floor.origin_lon)
                            else:
                                x, y = c[0], c[1]
                            xs.append(x)
                            ys.append(y)
                    
                    if xs:
                        fig.add_trace(go.Scatter(
                            x=xs, y=ys,
                            mode='lines',
                            line=dict(color='#333', width=1),
                            showlegend=False,
                            hoverinfo='skip'
                        ))
                        rendered = True
            
            return rendered
        except Exception:
            pass
    
    return False


def render_coverage_zones(fig, zones):
    """Render coverage zones on figure"""
    for zone in zones:
        try:
            coords = json.loads(zone.polygon_coords)
            if coords:
                xs = [c[0] for c in coords]
                ys = [c[1] for c in coords]
                
                if xs[0] != xs[-1] or ys[0] != ys[-1]:
                    xs.append(xs[0])
                    ys.append(ys[0])
                
                color = zone.color or '#2e5cbf'
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                
                fig.add_trace(go.Scatter(
                    x=xs, y=ys,
                    fill='toself',
                    fillcolor=f'rgba({r}, {g}, {b}, 0.2)',
                    line=dict(color=color, width=2),
                    mode='lines',
                    name=zone.name,
                    hovertemplate=f"<b>{zone.name}</b><br>Accuracy: ±{zone.target_accuracy}m<extra></extra>"
                ))
                
                center_x = sum(xs[:-1]) / len(xs[:-1])
                center_y = sum(ys[:-1]) / len(ys[:-1])
                fig.add_annotation(
                    x=center_x, y=center_y,
                    text=f"{zone.name}<br>±{zone.target_accuracy}m",
                    showarrow=False,
                    font=dict(size=10, color=color),
                    bgcolor='rgba(255,255,255,0.8)'
                )
        except Exception:
            pass


def point_in_zone(x, y, zone):
    """Check if a point is inside a zone rectangle"""
    return zone.x_min <= x <= zone.x_max and zone.y_min <= y <= zone.y_max


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
                    session.commit()
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
                    session.commit()
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


def show():
    st.title("Coverage Zones & Alerts")
    st.write("Define coverage areas and manage geofencing alerts for beacon tracking.")
    
    tab1, tab2, tab3 = st.tabs(["Coverage Zones", "Live Monitoring", "Alert History"])
    
    with tab1:
        render_coverage_zones_tab()
    
    with tab2:
        render_live_monitoring_tab()
    
    with tab3:
        render_alert_history_tab()


def render_coverage_zones_tab():
    """Render the coverage zones management tab"""
    if 'drawing_vertices' not in st.session_state:
        st.session_state.drawing_vertices = []
    if 'drawing_mode' not in st.session_state:
        st.session_state.drawing_mode = False
    if 'viewport_bounds' not in st.session_state:
        st.session_state.viewport_bounds = None
    
    with get_db_session() as session:
        buildings = session.query(Building).order_by(Building.name).all()
        
        if not buildings:
            st.warning("No buildings found. Please add a building first.")
            return
        
        building_options = {b.name: b.id for b in buildings}
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Select Floor")
            
            selected_building = st.selectbox(
                "Building",
                options=list(building_options.keys()),
                key="cz_building"
            )
            
            if selected_building:
                floors = session.query(Floor).filter(
                    Floor.building_id == building_options[selected_building]
                ).order_by(Floor.floor_number).all()
                
                if floors:
                    floor_options = {f"{f.name} (Level {f.floor_number})": f.id for f in floors}
                    selected_floor_name = st.selectbox(
                        "Floor",
                        options=list(floor_options.keys()),
                        key="cz_floor"
                    )
                    selected_floor_id = floor_options.get(selected_floor_name)
                    selected_floor = session.query(Floor).get(selected_floor_id) if selected_floor_id else None
                else:
                    st.warning("No floors found for this building.")
                    selected_floor = None
            else:
                selected_floor = None
            
            st.divider()
            
            if selected_floor:
                st.subheader("Coverage Zones")
                
                zones = session.query(CoverageZone).filter(
                    CoverageZone.floor_id == selected_floor.id
                ).order_by(CoverageZone.priority.desc()).all()
                
                if zones:
                    for zone in zones:
                        with st.expander(f"🔷 {zone.name} (±{zone.target_accuracy}m)", expanded=False):
                            st.write(f"**Priority:** {zone.priority}")
                            st.write(f"**Active:** {'Yes' if zone.is_active else 'No'}")
                            if zone.description:
                                st.write(f"**Description:** {zone.description}")
                            
                            col_edit, col_del = st.columns(2)
                            with col_edit:
                                if st.button("Edit", key=f"edit_zone_{zone.id}"):
                                    st.session_state['editing_zone_id'] = zone.id
                                    st.rerun()
                            with col_del:
                                if st.button("Delete", key=f"del_zone_{zone.id}", type="secondary"):
                                    session.delete(zone)
                                    session.commit()
                                    st.success(f"Deleted zone '{zone.name}'")
                                    st.rerun()
                else:
                    st.info("No coverage zones defined yet.")
                
                st.divider()
                
                st.subheader("Add Zone")
                
                zone_creation_method = st.radio(
                    "How do you want to define the zone area?",
                    ["Draw Custom Shape", "Enter Rectangle Bounds", "Cover Entire Floor"],
                    horizontal=False,
                    help="Draw: enter vertex coordinates | Rectangle: enter X/Y min/max | Entire: full floor coverage",
                    key="zone_creation_method"
                )
                
                prev_method = st.session_state.get('prev_creation_method')
                if prev_method and prev_method != zone_creation_method:
                    st.session_state.drawing_vertices = []
                    st.session_state['pending_polygon'] = None
                    st.session_state['use_viewport'] = False
                    st.session_state['viewport_bounds'] = None
                st.session_state['prev_creation_method'] = zone_creation_method
                
                if zone_creation_method == "Draw Custom Shape":
                    st.info("📍 **Add points** using coordinates from the floor plan. Hover over the chart to see X/Y values, then enter them below.")
                    
                    if st.session_state.drawing_vertices:
                        st.write(f"**Vertices placed:** {len(st.session_state.drawing_vertices)}")
                        vertices_to_delete = []
                        for i, v in enumerate(st.session_state.drawing_vertices):
                            col_pt, col_del = st.columns([4, 1])
                            with col_pt:
                                st.caption(f"Point {i+1}: ({v[0]:.1f}, {v[1]:.1f}) m")
                            with col_del:
                                if st.button("❌", key=f"del_pt_{i}", help="Remove this point"):
                                    vertices_to_delete.append(i)
                        for idx in reversed(vertices_to_delete):
                            st.session_state.drawing_vertices.pop(idx)
                        if vertices_to_delete:
                            st.rerun()
                    
                    with st.form(key="add_vertex_form", clear_on_submit=True):
                        st.markdown("**Add vertex:**")
                        col_x, col_y = st.columns(2)
                        with col_x:
                            new_x = st.number_input("X (m)", min_value=0.0, max_value=float(selected_floor.width_meters) if selected_floor else 100.0, value=0.0, step=0.5, key="form_vertex_x")
                        with col_y:
                            new_y = st.number_input("Y (m)", min_value=0.0, max_value=float(selected_floor.height_meters) if selected_floor else 100.0, value=0.0, step=0.5, key="form_vertex_y")
                        
                        add_submitted = st.form_submit_button("Add Point", type="primary")
                        if add_submitted:
                            is_duplicate = any(
                                abs(v[0] - new_x) < 0.5 and abs(v[1] - new_y) < 0.5
                                for v in st.session_state.drawing_vertices
                            )
                            if not is_duplicate and (new_x > 0 or new_y > 0):
                                st.session_state.drawing_vertices.append([round(new_x, 2), round(new_y, 2)])
                    
                    col_draw1, col_draw2, col_draw3 = st.columns(3)
                    with col_draw1:
                        if st.button("Undo Last", disabled=len(st.session_state.drawing_vertices) == 0):
                            st.session_state.drawing_vertices.pop()
                    with col_draw2:
                        if st.button("Clear All", disabled=len(st.session_state.drawing_vertices) == 0):
                            st.session_state.drawing_vertices = []
                    with col_draw3:
                        can_complete = len(st.session_state.drawing_vertices) >= 3
                        complete_btn = st.button("Complete Polygon", type="primary", disabled=not can_complete)
                    
                    if can_complete and complete_btn:
                        st.session_state['pending_polygon'] = st.session_state.drawing_vertices.copy()
                        st.session_state.drawing_vertices = []
                
                elif zone_creation_method == "Enter Rectangle Bounds":
                    st.info("📐 Enter the corner coordinates to define a rectangular zone.")
                    
                    col_vp1, col_vp2 = st.columns(2)
                    with col_vp1:
                        vp_x_min = st.number_input("X Min (m)", min_value=0.0, max_value=float(selected_floor.width_meters), value=0.0, key="vp_x_min")
                        vp_y_min = st.number_input("Y Min (m)", min_value=0.0, max_value=float(selected_floor.height_meters), value=0.0, key="vp_y_min")
                    with col_vp2:
                        vp_x_max = st.number_input("X Max (m)", min_value=0.0, max_value=float(selected_floor.width_meters), value=float(selected_floor.width_meters), key="vp_x_max")
                        vp_y_max = st.number_input("Y Max (m)", min_value=0.0, max_value=float(selected_floor.height_meters), value=float(selected_floor.height_meters), key="vp_y_max")
                    
                    if st.button("Set Rectangle Bounds", type="primary"):
                        if vp_x_max > vp_x_min and vp_y_max > vp_y_min:
                            st.session_state['use_viewport'] = True
                            st.session_state['viewport_bounds'] = {
                                'x_min': vp_x_min,
                                'x_max': vp_x_max,
                                'y_min': vp_y_min,
                                'y_max': vp_y_max
                            }
                            st.rerun()
                        else:
                            st.error("Max values must be greater than min values.")
                
                zone_name = st.text_input("Zone Name*", placeholder="e.g., Main Area, Operating Room")
                zone_description = st.text_area("Description", placeholder="Optional description", height=68)
                
                col_acc, col_pri = st.columns(2)
                with col_acc:
                    target_accuracy = st.select_slider(
                        "Target Accuracy",
                        options=[0.5, 1.0, 2.0, 3.0, 5.0],
                        value=1.0,
                        format_func=lambda x: f"±{x}m"
                    )
                with col_pri:
                    priority = st.number_input("Priority", min_value=1, max_value=10, value=1, help="Higher priority zones take precedence")
                
                zone_color = st.color_picker("Zone Color", value="#2e5cbf")
                
                pending_polygon = st.session_state.get('pending_polygon')
                use_viewport = st.session_state.get('use_viewport')
                viewport_bounds = st.session_state.get('viewport_bounds')
                
                if zone_creation_method == "Cover Entire Floor":
                    if st.button("Create Zone", type="primary"):
                        if not zone_name:
                            st.error("Please enter a zone name")
                        else:
                            polygon_coords = json.dumps([
                                [0, 0],
                                [selected_floor.width_meters, 0],
                                [selected_floor.width_meters, selected_floor.height_meters],
                                [0, selected_floor.height_meters],
                                [0, 0]
                            ])
                            
                            new_zone = CoverageZone(
                                floor_id=selected_floor.id,
                                name=zone_name,
                                description=zone_description,
                                polygon_coords=polygon_coords,
                                target_accuracy=target_accuracy,
                                priority=priority,
                                color=zone_color,
                                is_active=True
                            )
                            session.add(new_zone)
                            session.commit()
                            st.success(f"Created zone '{zone_name}'")
                            st.rerun()
                
                elif pending_polygon:
                    st.success(f"Polygon ready with {len(pending_polygon)} vertices!")
                    if st.button("Save Zone", type="primary"):
                        if not zone_name:
                            st.error("Please enter a zone name")
                        else:
                            closed_polygon = pending_polygon.copy()
                            if closed_polygon[0] != closed_polygon[-1]:
                                closed_polygon.append(closed_polygon[0])
                            polygon_coords = json.dumps(closed_polygon)
                            new_zone = CoverageZone(
                                floor_id=selected_floor.id,
                                name=zone_name,
                                description=zone_description,
                                polygon_coords=polygon_coords,
                                target_accuracy=target_accuracy,
                                priority=priority,
                                color=zone_color,
                                is_active=True
                            )
                            session.add(new_zone)
                            session.commit()
                            st.session_state['pending_polygon'] = None
                            st.success(f"Created zone '{zone_name}'")
                            st.rerun()
                
                elif use_viewport and viewport_bounds:
                    x_min, x_max = viewport_bounds.get('x_min', 0), viewport_bounds.get('x_max', selected_floor.width_meters)
                    y_min, y_max = viewport_bounds.get('y_min', 0), viewport_bounds.get('y_max', selected_floor.height_meters)
                    st.success(f"Rectangle bounds set: ({x_min:.1f}, {y_min:.1f}) to ({x_max:.1f}, {y_max:.1f})")
                    if st.button("Save Zone", type="primary"):
                        if not zone_name:
                            st.error("Please enter a zone name")
                        else:
                            polygon_coords = json.dumps([
                                [x_min, y_min],
                                [x_max, y_min],
                                [x_max, y_max],
                                [x_min, y_max],
                                [x_min, y_min]
                            ])
                            new_zone = CoverageZone(
                                floor_id=selected_floor.id,
                                name=zone_name,
                                description=zone_description,
                                polygon_coords=polygon_coords,
                                target_accuracy=target_accuracy,
                                priority=priority,
                                color=zone_color,
                                is_active=True
                            )
                            session.add(new_zone)
                            session.commit()
                            st.session_state['use_viewport'] = False
                            st.session_state['viewport_bounds'] = None
                            st.success(f"Created zone '{zone_name}'")
                            st.rerun()
        
        with col2:
            st.subheader("Floor Plan Preview")
            
            if selected_floor:
                current_mode = st.session_state.get('zone_creation_method', 'Draw Custom Shape')
                
                zones = session.query(CoverageZone).filter(
                    CoverageZone.floor_id == selected_floor.id,
                    CoverageZone.is_active == True
                ).all()
                
                # Load focus area from database if available
                if selected_floor.focus_min_x is not None:
                    st.session_state['focus_area'] = {
                        'x_min': selected_floor.focus_min_x,
                        'x_max': selected_floor.focus_max_x,
                        'y_min': selected_floor.focus_min_y,
                        'y_max': selected_floor.focus_max_y
                    }
                    st.session_state['focus_x_min'] = selected_floor.focus_min_x
                    st.session_state['focus_x_max'] = selected_floor.focus_max_x
                    st.session_state['focus_y_min'] = selected_floor.focus_min_y
                    st.session_state['focus_y_max'] = selected_floor.focus_max_y
                elif 'focus_area' not in st.session_state:
                    st.session_state['focus_area'] = None
                
                with st.expander("🔍 Focus Area (set view bounds)", expanded=False):
                    st.caption("Set specific view bounds to focus on a region. This will be saved for Gateway Planning.")
                    
                    focus_col1, focus_col2 = st.columns(2)
                    with focus_col1:
                        focus_x_min = st.number_input("X Min", min_value=0.0, max_value=float(selected_floor.width_meters), 
                                                       value=float(st.session_state.get('focus_x_min', 0.0)), step=1.0, key="focus_x_min_input")
                        focus_y_min = st.number_input("Y Min", min_value=0.0, max_value=float(selected_floor.height_meters), 
                                                       value=float(st.session_state.get('focus_y_min', 0.0)), step=1.0, key="focus_y_min_input")
                    with focus_col2:
                        focus_x_max = st.number_input("X Max", min_value=0.0, max_value=float(selected_floor.width_meters), 
                                                       value=float(st.session_state.get('focus_x_max', selected_floor.width_meters)), step=1.0, key="focus_x_max_input")
                        focus_y_max = st.number_input("Y Max", min_value=0.0, max_value=float(selected_floor.height_meters), 
                                                       value=float(st.session_state.get('focus_y_max', selected_floor.height_meters)), step=1.0, key="focus_y_max_input")
                    
                    focus_btn_col1, focus_btn_col2, focus_btn_col3 = st.columns(3)
                    with focus_btn_col1:
                        if st.button("Save Focus Area", type="primary"):
                            if focus_x_max > focus_x_min and focus_y_max > focus_y_min:
                                selected_floor.focus_min_x = focus_x_min
                                selected_floor.focus_max_x = focus_x_max
                                selected_floor.focus_min_y = focus_y_min
                                selected_floor.focus_max_y = focus_y_max
                                session.commit()
                                st.session_state['focus_area'] = {
                                    'x_min': focus_x_min, 'x_max': focus_x_max,
                                    'y_min': focus_y_min, 'y_max': focus_y_max
                                }
                                st.session_state['focus_x_min'] = focus_x_min
                                st.session_state['focus_x_max'] = focus_x_max
                                st.session_state['focus_y_min'] = focus_y_min
                                st.session_state['focus_y_max'] = focus_y_max
                                st.success("Focus area saved!")
                            else:
                                st.error("Max must be greater than Min")
                    with focus_btn_col2:
                        if st.button("Clear Focus"):
                            selected_floor.focus_min_x = None
                            selected_floor.focus_max_x = None
                            selected_floor.focus_min_y = None
                            selected_floor.focus_max_y = None
                            session.commit()
                            st.session_state['focus_area'] = None
                            st.session_state['focus_x_min'] = 0.0
                            st.session_state['focus_x_max'] = selected_floor.width_meters
                            st.session_state['focus_y_min'] = 0.0
                            st.session_state['focus_y_max'] = selected_floor.height_meters
                            st.success("Focus area cleared")
                            st.rerun()
                    with focus_btn_col3:
                        if zones and st.button("Focus on Zones"):
                            all_xs, all_ys = [], []
                            for zone in zones:
                                try:
                                    coords = json.loads(zone.polygon_coords)
                                    for c in coords:
                                        all_xs.append(c[0])
                                        all_ys.append(c[1])
                                except:
                                    pass
                            if all_xs and all_ys:
                                margin = 2.0
                                new_focus_x_min = max(0, min(all_xs) - margin)
                                new_focus_x_max = min(selected_floor.width_meters, max(all_xs) + margin)
                                new_focus_y_min = max(0, min(all_ys) - margin)
                                new_focus_y_max = min(selected_floor.height_meters, max(all_ys) + margin)
                                selected_floor.focus_min_x = new_focus_x_min
                                selected_floor.focus_max_x = new_focus_x_max
                                selected_floor.focus_min_y = new_focus_y_min
                                selected_floor.focus_max_y = new_focus_y_max
                                session.commit()
                                st.session_state['focus_area'] = {
                                    'x_min': new_focus_x_min, 'x_max': new_focus_x_max,
                                    'y_min': new_focus_y_min, 'y_max': new_focus_y_max
                                }
                                st.session_state['focus_x_min'] = new_focus_x_min
                                st.session_state['focus_x_max'] = new_focus_x_max
                                st.session_state['focus_y_min'] = new_focus_y_min
                                st.session_state['focus_y_max'] = new_focus_y_max
                                # Update widget keys directly so input fields reflect new values
                                st.session_state['focus_x_min_input'] = new_focus_x_min
                                st.session_state['focus_x_max_input'] = new_focus_x_max
                                st.session_state['focus_y_min_input'] = new_focus_y_min
                                st.session_state['focus_y_max_input'] = new_focus_y_max
                                st.success("Focus area set to zones bounds")
                                st.rerun()
                    
                    if st.session_state.get('focus_area'):
                        fa = st.session_state['focus_area']
                        st.info(f"Focused: X [{fa['x_min']:.1f} - {fa['x_max']:.1f}], Y [{fa['y_min']:.1f} - {fa['y_max']:.1f}]")
                
                fig = go.Figure()
                
                has_floor_plan = render_floor_plan(fig, selected_floor)
                
                if not has_floor_plan:
                    fig.add_shape(
                        type="rect",
                        x0=0, y0=0,
                        x1=selected_floor.width_meters, y1=selected_floor.height_meters,
                        line=dict(color="#2e5cbf", width=2),
                        fillcolor="rgba(46, 92, 191, 0.05)"
                    )
                
                if zones:
                    render_coverage_zones(fig, zones)
                
                drawing_vertices = st.session_state.get('drawing_vertices', [])
                if drawing_vertices:
                    xs = [v[0] for v in drawing_vertices]
                    ys = [v[1] for v in drawing_vertices]
                    
                    fig.add_trace(go.Scatter(
                        x=xs, y=ys,
                        mode='markers+lines+text',
                        marker=dict(size=14, color='#ff6b35', symbol='circle'),
                        line=dict(color='#ff6b35', width=2, dash='dash'),
                        text=[f"{i+1}" for i in range(len(xs))],
                        textposition="top center",
                        textfont=dict(size=12, color='#ff6b35'),
                        name='Drawing Points',
                        hovertemplate='Point %{text}<br>X: %{x:.1f}m<br>Y: %{y:.1f}m<extra></extra>'
                    ))
                    
                    if len(drawing_vertices) >= 3:
                        fig.add_trace(go.Scatter(
                            x=xs + [xs[0]], y=ys + [ys[0]],
                            fill='toself',
                            fillcolor='rgba(255, 107, 53, 0.15)',
                            line=dict(color='rgba(255, 107, 53, 0.5)', width=1, dash='dot'),
                            mode='lines',
                            name='Preview',
                            showlegend=False,
                            hoverinfo='skip'
                        ))
                
                pending_polygon = st.session_state.get('pending_polygon')
                if pending_polygon:
                    xs = [v[0] for v in pending_polygon]
                    ys = [v[1] for v in pending_polygon]
                    fig.add_trace(go.Scatter(
                        x=xs + [xs[0]], y=ys + [ys[0]],
                        fill='toself',
                        fillcolor='rgba(46, 191, 92, 0.2)',
                        line=dict(color='#2ebf5c', width=3),
                        mode='lines',
                        name='Completed Polygon',
                        hovertemplate='Completed polygon ready to save<extra></extra>'
                    ))
                
                focus_area = st.session_state.get('focus_area')
                if focus_area:
                    x_axis_config = dict(
                        title="X (meters)",
                        range=[focus_area['x_min'], focus_area['x_max']],
                        scaleanchor="y",
                        scaleratio=1,
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)',
                        constrain='domain'
                    )
                    y_axis_config = dict(
                        title="Y (meters)",
                        range=[focus_area['y_min'], focus_area['y_max']],
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)',
                        constrain='domain'
                    )
                else:
                    x_axis_config = dict(
                        title="X (meters)",
                        range=[0, selected_floor.width_meters],
                        scaleanchor="y",
                        scaleratio=1,
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)',
                        constrain='domain'
                    )
                    y_axis_config = dict(
                        title="Y (meters)",
                        range=[0, selected_floor.height_meters],
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)',
                        constrain='domain'
                    )
                
                fig.update_layout(
                    height=600,
                    uirevision=f"floor_{selected_floor.id}_focus",
                    xaxis=x_axis_config,
                    yaxis=y_axis_config,
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    margin=dict(l=50, r=50, t=50, b=50),
                    plot_bgcolor='rgba(255,255,255,0.9)'
                )
                
                st.plotly_chart(fig, use_container_width=True, key="floor_plan_view")
                
                st.caption(f"Floor dimensions: {selected_floor.width_meters:.1f}m × {selected_floor.height_meters:.1f}m")
                
                if zones:
                    st.success(f"{len(zones)} coverage zone(s) defined")
                else:
                    st.info("No coverage zones defined. Gateways will be placed based on floor boundaries.")
            else:
                st.info("Select a building and floor to view the floor plan.")


def render_live_monitoring_tab():
    """Render the live zone monitoring tab"""
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
            
            auto_refresh = st.checkbox("Auto-refresh", value=False, key="zone_auto_refresh")
            
            if st.button("Check for Alerts"):
                new_alerts = check_zone_transitions(session, selected_floor_id)
                if new_alerts:
                    for alert in new_alerts:
                        st.warning(f"{alert['beacon']} {alert['type']}ed {alert['zone']}")
                else:
                    st.info("No new zone transitions detected")
            
            st.divider()
            st.subheader("Manage Alert Zones")
            
            existing_zones = session.query(Zone).filter(
                Zone.floor_id == selected_floor_id
            ).all()
            
            if existing_zones:
                zone_to_delete = st.selectbox(
                    "Select zone to delete",
                    options=[z.name for z in existing_zones],
                    key="zone_to_delete"
                )
                
                if st.button("Delete Zone", type="secondary"):
                    zone = session.query(Zone).filter(
                        Zone.floor_id == selected_floor_id,
                        Zone.name == zone_to_delete
                    ).first()
                    if zone:
                        session.query(ZoneAlert).filter(ZoneAlert.zone_id == zone.id).delete()
                        session.delete(zone)
                        session.commit()
                        st.success(f"Deleted zone '{zone_to_delete}' and its alerts")
                        st.rerun()
            else:
                st.info("No alert zones on this floor")
        
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
            
            fig = go.Figure()
            
            has_floor_plan = render_floor_plan(fig, floor)
            
            if not has_floor_plan:
                fig.add_shape(
                    type="rect",
                    x0=0, y0=0,
                    x1=float(floor.width_meters), y1=float(floor.height_meters),
                    line=dict(color="#2e5cbf", width=2),
                    fillcolor="rgba(46, 92, 191, 0.05)"
                )
            
            for zone in zones:
                fig.add_shape(
                    type="rect",
                    x0=float(zone.x_min), y0=float(zone.y_min),
                    x1=float(zone.x_max), y1=float(zone.y_max),
                    line=dict(color=zone.color, width=2),
                    fillcolor=zone.color,
                    opacity=0.3
                )
                fig.add_annotation(
                    x=(float(zone.x_min) + float(zone.x_max)) / 2,
                    y=float(zone.y_max) + 0.5,
                    text=zone.name,
                    showarrow=False,
                    font=dict(size=12, color=zone.color)
                )
            
            for gw in gateways:
                fig.add_trace(go.Scatter(
                    x=[float(gw.x_position)],
                    y=[float(gw.y_position)],
                    mode='markers',
                    marker=dict(size=10, color='blue', symbol='square'),
                    name=f"GW: {gw.name}",
                    showlegend=False
                ))
            
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
                height=500,
                xaxis=dict(
                    title="X (meters)",
                    range=[0, float(floor.width_meters)],
                    scaleanchor="y",
                    scaleratio=1
                ),
                yaxis=dict(
                    title="Y (meters)",
                    range=[0, float(floor.height_meters)]
                ),
                showlegend=True,
                margin=dict(l=50, r=50, t=50, b=50)
            )
            
            st.plotly_chart(fig, use_container_width=True, key="zone_monitoring_chart")
            
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
                st.info("No alert zones defined for this floor. Alert zones (rectangular areas with entry/exit triggers) are separate from coverage zones used for gateway planning.")
            else:
                st.info("No beacons currently tracked on this floor.")
            
            if auto_refresh:
                import time
                time.sleep(2)
                st.rerun()


def render_alert_history_tab():
    """Render the alert history tab"""
    with get_db_session() as session:
        st.subheader("Alert History")
        
        col1, col2 = st.columns(2)
        
        with col1:
            filter_type = st.selectbox(
                "Filter by Type",
                options=["All", "Enter", "Exit"],
                key="alert_filter_type"
            )
        
        with col2:
            filter_ack = st.selectbox(
                "Filter by Status",
                options=["All", "Unacknowledged", "Acknowledged"],
                key="alert_filter_ack"
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


if __name__ == "__main__":
    show()
