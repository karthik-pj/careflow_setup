import streamlit as st
import json
import plotly.graph_objects as go
from PIL import Image
from io import BytesIO
import base64
import numpy as np
from database import get_db_session, Floor, Building, CoverageZone
from streamlit_plotly_events import plotly_events


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


def show():
    st.title("Coverage Zone Editor")
    st.write("Define coverage areas on floor plans for gateway planning. Gateways will only be placed within defined zones.")
    
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
                    "Creation Method",
                    ["Draw on Floor Plan", "Use Current Viewport", "Use Building Footprint", "Use Full Floor"],
                    horizontal=False,
                    help="Choose how to define the zone boundaries",
                    key="zone_creation_method"
                )
                
                prev_method = st.session_state.get('prev_creation_method')
                if prev_method and prev_method != zone_creation_method:
                    st.session_state.drawing_vertices = []
                    st.session_state['pending_polygon'] = None
                    st.session_state['use_viewport'] = False
                    st.session_state['viewport_bounds'] = None
                st.session_state['prev_creation_method'] = zone_creation_method
                
                if zone_creation_method == "Draw on Floor Plan":
                    st.info("📍 **Click on the floor plan** to place polygon vertices. Add at least 3 points, then click 'Complete Polygon'.")
                    
                    if st.session_state.drawing_vertices:
                        st.write(f"**Vertices placed:** {len(st.session_state.drawing_vertices)}")
                        for i, v in enumerate(st.session_state.drawing_vertices):
                            st.caption(f"Point {i+1}: ({v[0]:.1f}, {v[1]:.1f})")
                    
                    col_draw1, col_draw2, col_draw3 = st.columns(3)
                    with col_draw1:
                        if st.button("Undo Last", disabled=len(st.session_state.drawing_vertices) == 0):
                            st.session_state.drawing_vertices.pop()
                            st.rerun()
                    with col_draw2:
                        if st.button("Clear All", disabled=len(st.session_state.drawing_vertices) == 0):
                            st.session_state.drawing_vertices = []
                            st.rerun()
                    with col_draw3:
                        can_complete = len(st.session_state.drawing_vertices) >= 3
                        complete_btn = st.button("Complete Polygon", type="primary", disabled=not can_complete)
                    
                    if can_complete and complete_btn:
                        st.session_state['pending_polygon'] = st.session_state.drawing_vertices.copy()
                        st.session_state.drawing_vertices = []
                
                elif zone_creation_method == "Use Current Viewport":
                    st.info("📐 Enter the viewport bounds to define a rectangular zone.")
                    
                    col_vp1, col_vp2 = st.columns(2)
                    with col_vp1:
                        vp_x_min = st.number_input("X Min (m)", min_value=0.0, max_value=float(selected_floor.width_meters), value=0.0, key="vp_x_min")
                        vp_y_min = st.number_input("Y Min (m)", min_value=0.0, max_value=float(selected_floor.height_meters), value=0.0, key="vp_y_min")
                    with col_vp2:
                        vp_x_max = st.number_input("X Max (m)", min_value=0.0, max_value=float(selected_floor.width_meters), value=float(selected_floor.width_meters), key="vp_x_max")
                        vp_y_max = st.number_input("Y Max (m)", min_value=0.0, max_value=float(selected_floor.height_meters), value=float(selected_floor.height_meters), key="vp_y_max")
                    
                    if st.button("Set Viewport Bounds", type="primary"):
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
                
                if zone_creation_method in ["Use Building Footprint", "Use Full Floor"]:
                    if st.button("Create Zone", type="primary"):
                        if not zone_name:
                            st.error("Please enter a zone name")
                        else:
                            if zone_creation_method == "Use Building Footprint":
                                footprint = extract_building_footprint(selected_floor)
                                if footprint:
                                    polygon_coords = json.dumps(footprint)
                                else:
                                    polygon_coords = json.dumps([
                                        [0, 0],
                                        [selected_floor.width_meters, 0],
                                        [selected_floor.width_meters, selected_floor.height_meters],
                                        [0, selected_floor.height_meters],
                                        [0, 0]
                                    ])
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
                    st.success(f"Viewport captured: ({x_min:.1f}, {y_min:.1f}) to ({x_max:.1f}, {y_max:.1f})")
                    if st.button("Save Zone from Viewport", type="primary"):
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
                
                zones = session.query(CoverageZone).filter(
                    CoverageZone.floor_id == selected_floor.id,
                    CoverageZone.is_active == True
                ).all()
                
                if zones:
                    render_coverage_zones(fig, zones)
                
                drawing_vertices = st.session_state.get('drawing_vertices', [])
                if drawing_vertices:
                    xs = [v[0] for v in drawing_vertices]
                    ys = [v[1] for v in drawing_vertices]
                    
                    fig.add_trace(go.Scatter(
                        x=xs, y=ys,
                        mode='markers+lines',
                        marker=dict(size=12, color='#ff6b35', symbol='circle'),
                        line=dict(color='#ff6b35', width=2, dash='dash'),
                        name='Drawing',
                        hovertemplate='Point %{pointNumber+1}<br>(%{x:.1f}, %{y:.1f})<extra></extra>'
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
                
                fig.update_layout(
                    height=600,
                    xaxis=dict(
                        title="X (meters)",
                        range=[-5, selected_floor.width_meters + 5],
                        scaleanchor="y",
                        scaleratio=1,
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)'
                    ),
                    yaxis=dict(
                        title="Y (meters)",
                        range=[-5, selected_floor.height_meters + 5],
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)'
                    ),
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    margin=dict(l=50, r=50, t=50, b=50),
                    plot_bgcolor='rgba(255,255,255,0.9)',
                    clickmode='event'
                )
                
                click_events = plotly_events(
                    fig, 
                    click_event=True, 
                    select_event=False,
                    key="floor_plan_click"
                )
                
                current_mode = st.session_state.get('zone_creation_method', 'Use Building Footprint')
                if current_mode == "Draw on Floor Plan" and click_events and len(click_events) > 0:
                    click_data = click_events[0]
                    x_clicked = click_data.get('x')
                    y_clicked = click_data.get('y')
                    
                    if x_clicked is not None and y_clicked is not None:
                        x_clicked = round(float(x_clicked), 2)
                        y_clicked = round(float(y_clicked), 2)
                        
                        is_duplicate = any(
                            abs(v[0] - x_clicked) < 0.5 and abs(v[1] - y_clicked) < 0.5
                            for v in st.session_state.drawing_vertices
                        )
                        
                        if not is_duplicate:
                            st.session_state.drawing_vertices.append([x_clicked, y_clicked])
                            st.rerun()
                
                st.caption(f"Floor dimensions: {selected_floor.width_meters:.1f}m × {selected_floor.height_meters:.1f}m")
                
                if zones:
                    st.success(f"{len(zones)} coverage zone(s) defined")
                else:
                    st.info("No coverage zones defined. Gateways will be placed based on floor boundaries.")
            else:
                st.info("Select a building and floor to view the floor plan.")


if __name__ == "__main__":
    show()
