import streamlit as st
import json
from database import get_db_session, Building, Floor, FocusArea, AlertZone
from utils.geojson_renderer import (
    create_floor_plan_figure, render_zone_polygon, extract_rooms_from_geojson,
    find_nearest_room_corner, polygon_to_geojson, geojson_to_polygon_coords
)
import plotly.graph_objects as go


def render():
    st.title("Alert Zones")
    st.write("Define geofencing zones for entry/exit alerts and dwell time monitoring.")
    
    with get_db_session() as session:
        buildings = session.query(Building).order_by(Building.name).all()
        
        if not buildings:
            st.warning("No buildings found. Please add a building first.")
            return
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            st.subheader("Select Floor")
            
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox(
                "Building",
                options=list(building_options.keys()),
                key="az_building"
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
                        key="az_floor"
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
                st.subheader("Alert Zones")
                
                alert_zones = session.query(AlertZone).filter(
                    AlertZone.floor_id == selected_floor.id
                ).order_by(AlertZone.name).all()
                
                if alert_zones:
                    for az in alert_zones:
                        status_icon = "✓" if az.is_active else "○"
                        alerts_info = []
                        if az.alert_on_enter:
                            alerts_info.append("Enter")
                        if az.alert_on_exit:
                            alerts_info.append("Exit")
                        if az.dwell_time_alert:
                            alerts_info.append(f"Dwell>{az.dwell_time_threshold_seconds}s")
                        
                        with st.expander(f"{status_icon} {az.name}", expanded=False):
                            st.write(f"**Alerts:** {', '.join(alerts_info) if alerts_info else 'None'}")
                            if az.description:
                                st.write(f"**Description:** {az.description}")
                            
                            col_toggle, col_del = st.columns(2)
                            with col_toggle:
                                if st.button(
                                    "Deactivate" if az.is_active else "Activate",
                                    key=f"toggle_az_{az.id}"
                                ):
                                    az.is_active = not az.is_active
                                    session.commit()
                                    st.rerun()
                            with col_del:
                                if st.button("Delete", key=f"del_az_{az.id}", type="secondary"):
                                    session.delete(az)
                                    session.commit()
                                    st.success(f"Deleted alert zone '{az.name}'")
                                    st.rerun()
                else:
                    st.info("No alert zones defined yet.")
                
                st.divider()
                render_add_alert_zone(session, selected_floor)
        
        with col2:
            if selected_floor:
                render_floor_plan_with_alert_zones(session, selected_floor)
            else:
                st.info("Select a building and floor to view the floor plan.")


def render_add_alert_zone(session, floor):
    st.subheader("Add Alert Zone")
    
    if 'az_vertices' not in st.session_state:
        st.session_state.az_vertices = []
    
    rooms = extract_rooms_from_geojson(floor)
    focus_areas = session.query(FocusArea).filter(
        FocusArea.floor_id == floor.id,
        FocusArea.is_active == True
    ).all()
    
    creation_method = st.radio(
        "Define zone by:",
        ["Draw Custom Polygon", "Select Rooms", "From Focus Area", "Rectangle Bounds"],
        horizontal=True,
        key="az_creation_method"
    )
    
    if creation_method == "Draw Custom Polygon":
        st.info("Add vertices by entering coordinates. Use 'Snap to room corner' for precise alignment.")
        
        if st.session_state.az_vertices:
            st.write(f"**Vertices:** {len(st.session_state.az_vertices)}")
            for i, v in enumerate(st.session_state.az_vertices):
                st.caption(f"Point {i+1}: ({v[0]:.1f}, {v[1]:.1f}) m")
        
        with st.form(key="add_az_vertex", clear_on_submit=True):
            col_x, col_y = st.columns(2)
            with col_x:
                new_x = st.number_input("X (m)", min_value=0.0, max_value=float(floor.width_meters), value=0.0, step=0.5, key="az_vertex_x")
            with col_y:
                new_y = st.number_input("Y (m)", min_value=0.0, max_value=float(floor.height_meters), value=0.0, step=0.5, key="az_vertex_y")
            
            snap_to_room = st.checkbox("Snap to nearest room corner", value=True, key="az_snap")
            
            if st.form_submit_button("Add Point"):
                if snap_to_room and rooms:
                    snapped_x, snapped_y, room_name = find_nearest_room_corner(new_x, new_y, rooms)
                    st.session_state.az_vertices.append([round(snapped_x, 2), round(snapped_y, 2)])
                    if room_name:
                        st.info(f"Snapped to corner of '{room_name}'")
                else:
                    st.session_state.az_vertices.append([round(new_x, 2), round(new_y, 2)])
        
        col_undo, col_clear = st.columns(2)
        with col_undo:
            if st.button("Undo Last", disabled=len(st.session_state.az_vertices) == 0, key="az_undo"):
                st.session_state.az_vertices.pop()
                st.rerun()
        with col_clear:
            if st.button("Clear All", disabled=len(st.session_state.az_vertices) == 0, key="az_clear"):
                st.session_state.az_vertices = []
                st.rerun()
        
        if len(st.session_state.az_vertices) >= 3:
            st.divider()
            render_alert_zone_form(session, floor, st.session_state.az_vertices, "polygon")
    
    elif creation_method == "Select Rooms":
        if rooms:
            room_names = [r['name'] for r in rooms]
            selected_rooms = st.multiselect("Select rooms to include", room_names, key="az_selected_rooms")
            
            if selected_rooms:
                all_coords = []
                for room in rooms:
                    if room['name'] in selected_rooms:
                        all_coords.extend(room['coords'])
                
                if all_coords:
                    xs = [c[0] for c in all_coords]
                    ys = [c[1] for c in all_coords]
                    bounding_box = [
                        [min(xs), min(ys)],
                        [max(xs), min(ys)],
                        [max(xs), max(ys)],
                        [min(xs), max(ys)]
                    ]
                    render_alert_zone_form(session, floor, bounding_box, "rooms", source_rooms=selected_rooms)
        else:
            st.warning("No rooms found in the floor plan. Upload a floor plan with room definitions.")
    
    elif creation_method == "From Focus Area":
        if focus_areas:
            fa_options = {fa.name: fa.id for fa in focus_areas}
            selected_fa_name = st.selectbox("Select Focus Area", options=list(fa_options.keys()), key="az_focus_area")
            
            if selected_fa_name:
                selected_fa = next((fa for fa in focus_areas if fa.name == selected_fa_name), None)
                if selected_fa:
                    try:
                        geojson_feature = json.loads(selected_fa.geojson)
                        coords = geojson_to_polygon_coords(geojson_feature)
                        if coords:
                            render_alert_zone_form(session, floor, coords, "focus_area", focus_area_id=selected_fa.id)
                    except:
                        st.error("Could not parse focus area geometry.")
        else:
            st.warning("No focus areas defined yet. Create focus areas first in 'Focus Areas'.")
    
    elif creation_method == "Rectangle Bounds":
        col1, col2 = st.columns(2)
        with col1:
            x_min = st.number_input("X Min (m)", min_value=0.0, max_value=float(floor.width_meters), value=0.0, key="az_x_min")
            y_min = st.number_input("Y Min (m)", min_value=0.0, max_value=float(floor.height_meters), value=0.0, key="az_y_min")
        with col2:
            x_max = st.number_input("X Max (m)", min_value=0.0, max_value=float(floor.width_meters), value=float(floor.width_meters), key="az_x_max")
            y_max = st.number_input("Y Max (m)", min_value=0.0, max_value=float(floor.height_meters), value=float(floor.height_meters), key="az_y_max")
        
        if x_max > x_min and y_max > y_min:
            rect_coords = [
                [x_min, y_min],
                [x_max, y_min],
                [x_max, y_max],
                [x_min, y_max]
            ]
            render_alert_zone_form(session, floor, rect_coords, "rectangle")


def render_alert_zone_form(session, floor, coords, zone_type, source_rooms=None, focus_area_id=None):
    with st.form(key=f"save_az_{zone_type}"):
        az_name = st.text_input("Alert Zone Name", value="", key=f"az_name_{zone_type}")
        az_color = st.color_picker("Zone Color", "#FF5722", key=f"az_color_{zone_type}")
        az_description = st.text_area("Description (optional)", key=f"az_desc_{zone_type}")
        
        st.subheader("Alert Settings")
        col1, col2 = st.columns(2)
        with col1:
            alert_on_enter = st.checkbox("Alert on Entry", value=True, key=f"az_enter_{zone_type}")
            alert_on_exit = st.checkbox("Alert on Exit", value=True, key=f"az_exit_{zone_type}")
        with col2:
            dwell_time_alert = st.checkbox("Dwell Time Alert", value=False, key=f"az_dwell_{zone_type}")
            dwell_threshold = st.number_input("Dwell Threshold (seconds)", min_value=30, max_value=3600, value=300, key=f"az_dwell_threshold_{zone_type}")
        
        if st.form_submit_button("Create Alert Zone", type="primary"):
            if az_name:
                properties = {
                    'zone_type': zone_type,
                    'color': az_color
                }
                if source_rooms:
                    properties['source_rooms'] = source_rooms
                
                geojson_feature = polygon_to_geojson(
                    coords,
                    az_name,
                    geom_type='alert_zone',
                    properties=properties
                )
                
                new_az = AlertZone(
                    floor_id=floor.id,
                    focus_area_id=focus_area_id,
                    name=az_name,
                    description=az_description,
                    geojson=json.dumps(geojson_feature),
                    zone_type=zone_type,
                    color=az_color,
                    alert_on_enter=alert_on_enter,
                    alert_on_exit=alert_on_exit,
                    dwell_time_alert=dwell_time_alert,
                    dwell_time_threshold_seconds=dwell_threshold if dwell_time_alert else 300,
                    is_active=True
                )
                session.add(new_az)
                session.commit()
                
                if 'az_vertices' in st.session_state:
                    st.session_state.az_vertices = []
                
                st.success(f"Created alert zone '{az_name}'")
                st.rerun()
            else:
                st.error("Please enter a name for the alert zone.")


def render_floor_plan_with_alert_zones(session, floor):
    st.subheader(f"Floor Plan: {floor.name or f'Level {floor.floor_number}'}")
    
    fig, has_floor_plan = create_floor_plan_figure(floor)
    
    focus_areas = session.query(FocusArea).filter(
        FocusArea.floor_id == floor.id,
        FocusArea.is_active == True
    ).all()
    
    for fa in focus_areas:
        try:
            geojson_feature = json.loads(fa.geojson)
            coords = geojson_to_polygon_coords(geojson_feature)
            if coords:
                render_zone_polygon(fig, coords, fa.name, color=fa.color, opacity=0.15, show_label=False)
        except:
            pass
    
    alert_zones = session.query(AlertZone).filter(
        AlertZone.floor_id == floor.id,
        AlertZone.is_active == True
    ).all()
    
    for az in alert_zones:
        try:
            geojson_feature = json.loads(az.geojson)
            coords = geojson_to_polygon_coords(geojson_feature)
            if coords:
                render_zone_polygon(fig, coords, az.name, color=az.color, opacity=0.35)
        except:
            pass
    
    if st.session_state.get('az_vertices'):
        vertices = st.session_state.az_vertices
        if vertices:
            xs = [v[0] for v in vertices]
            ys = [v[1] for v in vertices]
            
            fig.add_trace(go.Scatter(
                x=xs + [xs[0]] if len(xs) >= 3 else xs,
                y=ys + [ys[0]] if len(ys) >= 3 else ys,
                mode='lines+markers',
                line=dict(color='#FF5722', width=2, dash='dash'),
                marker=dict(size=10, color='#FF5722'),
                name='Drawing...',
                showlegend=True
            ))
    
    fig.update_layout(
        height=600,
        xaxis=dict(
            title="X (meters)",
            range=[0, float(floor.width_meters)],
            scaleanchor="y",
            scaleratio=1,
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)'
        ),
        yaxis=dict(
            title="Y (meters)",
            range=[0, float(floor.height_meters)],
            showgrid=True,
            gridcolor='rgba(0,0,0,0.1)'
        ),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=50, b=50),
        plot_bgcolor='rgba(255,255,255,0.9)'
    )
    
    st.plotly_chart(fig, use_container_width=True, key="alert_zone_floor_plan")
    
    st.caption(f"Floor dimensions: {floor.width_meters:.1f}m × {floor.height_meters:.1f}m")
    
    col1, col2 = st.columns(2)
    with col1:
        if focus_areas:
            st.info(f"{len(focus_areas)} focus area(s) shown (light shading)")
    with col2:
        if alert_zones:
            st.success(f"{len(alert_zones)} alert zone(s) active")
