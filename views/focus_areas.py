import streamlit as st
import json
from database import get_db_session, Building, Floor, FocusArea
from utils.geojson_renderer import (
    create_floor_plan_figure, render_zone_polygon, extract_rooms_from_geojson,
    find_nearest_room_corner, polygon_to_geojson, geojson_to_polygon_coords
)


def render():
    st.title("Focus Areas")
    st.write("Define areas of interest on your floor plans for coverage planning and alert zones.")
    
    with get_db_session() as session:
        buildings = session.query(Building).order_by(Building.name).all()
        
        if not buildings:
            st.warning("No buildings found. Please add a building first in 'Buildings & Floor Plans'.")
            return
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            st.subheader("Select Floor")
            
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox(
                "Building",
                options=list(building_options.keys()),
                key="fa_building"
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
                        key="fa_floor"
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
                st.subheader("Focus Areas")
                
                focus_areas = session.query(FocusArea).filter(
                    FocusArea.floor_id == selected_floor.id
                ).order_by(FocusArea.priority.desc()).all()
                
                if focus_areas:
                    for fa in focus_areas:
                        status_icon = "✓" if fa.is_active else "○"
                        with st.expander(f"{status_icon} {fa.name}", expanded=False):
                            st.write(f"**Type:** {fa.area_type}")
                            st.write(f"**Priority:** {fa.priority}")
                            if fa.description:
                                st.write(f"**Description:** {fa.description}")
                            
                            col_toggle, col_del = st.columns(2)
                            with col_toggle:
                                if st.button(
                                    "Deactivate" if fa.is_active else "Activate",
                                    key=f"toggle_fa_{fa.id}"
                                ):
                                    fa.is_active = not fa.is_active
                                    session.commit()
                                    st.rerun()
                            with col_del:
                                if st.button("Delete", key=f"del_fa_{fa.id}", type="secondary"):
                                    session.delete(fa)
                                    session.commit()
                                    st.success(f"Deleted focus area '{fa.name}'")
                                    st.rerun()
                else:
                    st.info("No focus areas defined yet.")
                
                st.divider()
                render_add_focus_area(session, selected_floor)
        
        with col2:
            if selected_floor:
                render_floor_plan_with_focus_areas(session, selected_floor)
            else:
                st.info("Select a building and floor to view the floor plan.")


def render_add_focus_area(session, floor):
    st.subheader("Add Focus Area")
    
    if 'fa_vertices' not in st.session_state:
        st.session_state.fa_vertices = []
    
    rooms = extract_rooms_from_geojson(floor)
    
    creation_method = st.radio(
        "Define area by:",
        ["Draw Custom Polygon", "Select Rooms", "Rectangle Bounds"],
        horizontal=True,
        key="fa_creation_method"
    )
    
    if creation_method == "Draw Custom Polygon":
        st.info("Add vertices by entering coordinates. Hover over the floor plan to see X/Y values.")
        
        if st.session_state.fa_vertices:
            st.write(f"**Vertices:** {len(st.session_state.fa_vertices)}")
            for i, v in enumerate(st.session_state.fa_vertices):
                st.caption(f"Point {i+1}: ({v[0]:.1f}, {v[1]:.1f}) m")
        
        with st.form(key="add_fa_vertex", clear_on_submit=True):
            col_x, col_y = st.columns(2)
            with col_x:
                new_x = st.number_input("X (m)", min_value=0.0, max_value=float(floor.width_meters), value=0.0, step=0.5, key="fa_vertex_x")
            with col_y:
                new_y = st.number_input("Y (m)", min_value=0.0, max_value=float(floor.height_meters), value=0.0, step=0.5, key="fa_vertex_y")
            
            snap_to_room = st.checkbox("Snap to nearest room corner", value=True, key="fa_snap")
            
            if st.form_submit_button("Add Point"):
                if snap_to_room and rooms:
                    snapped_x, snapped_y, room_name = find_nearest_room_corner(new_x, new_y, rooms)
                    st.session_state.fa_vertices.append([round(snapped_x, 2), round(snapped_y, 2)])
                    if room_name:
                        st.info(f"Snapped to corner of '{room_name}'")
                else:
                    st.session_state.fa_vertices.append([round(new_x, 2), round(new_y, 2)])
        
        col_undo, col_clear = st.columns(2)
        with col_undo:
            if st.button("Undo Last", disabled=len(st.session_state.fa_vertices) == 0):
                st.session_state.fa_vertices.pop()
                st.rerun()
        with col_clear:
            if st.button("Clear All", disabled=len(st.session_state.fa_vertices) == 0):
                st.session_state.fa_vertices = []
                st.rerun()
        
        if len(st.session_state.fa_vertices) >= 3:
            st.divider()
            with st.form(key="save_fa_polygon"):
                fa_name = st.text_input("Focus Area Name", value="", key="fa_name")
                fa_type = st.selectbox("Area Type", ["general", "critical", "restricted", "high_traffic"], key="fa_type")
                fa_priority = st.slider("Priority", 1, 10, 5, key="fa_priority")
                fa_color = st.color_picker("Color", "#2e5cbf", key="fa_color")
                fa_description = st.text_area("Description (optional)", key="fa_description")
                
                if st.form_submit_button("Create Focus Area", type="primary"):
                    if fa_name:
                        geojson_feature = polygon_to_geojson(
                            st.session_state.fa_vertices,
                            fa_name,
                            geom_type='focus_area',
                            properties={
                                'area_type': fa_type,
                                'priority': fa_priority,
                                'color': fa_color
                            }
                        )
                        
                        new_fa = FocusArea(
                            floor_id=floor.id,
                            name=fa_name,
                            description=fa_description,
                            geojson=json.dumps(geojson_feature),
                            area_type=fa_type,
                            priority=fa_priority,
                            color=fa_color,
                            is_active=True
                        )
                        session.add(new_fa)
                        session.commit()
                        st.session_state.fa_vertices = []
                        st.success(f"Created focus area '{fa_name}'")
                        st.rerun()
                    else:
                        st.error("Please enter a name for the focus area.")
    
    elif creation_method == "Select Rooms":
        if rooms:
            room_names = [r['name'] for r in rooms]
            selected_rooms = st.multiselect("Select rooms to include", room_names, key="fa_selected_rooms")
            
            if selected_rooms:
                with st.form(key="save_fa_rooms"):
                    fa_name = st.text_input("Focus Area Name", value="", key="fa_room_name")
                    fa_type = st.selectbox("Area Type", ["general", "critical", "restricted", "high_traffic"], key="fa_room_type")
                    fa_priority = st.slider("Priority", 1, 10, 5, key="fa_room_priority")
                    fa_color = st.color_picker("Color", "#2e5cbf", key="fa_room_color")
                    
                    if st.form_submit_button("Create Focus Area from Rooms", type="primary"):
                        if fa_name:
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
                                
                                geojson_feature = polygon_to_geojson(
                                    bounding_box,
                                    fa_name,
                                    geom_type='focus_area',
                                    properties={
                                        'area_type': fa_type,
                                        'priority': fa_priority,
                                        'color': fa_color,
                                        'source_rooms': selected_rooms
                                    }
                                )
                                
                                new_fa = FocusArea(
                                    floor_id=floor.id,
                                    name=fa_name,
                                    geojson=json.dumps(geojson_feature),
                                    area_type=fa_type,
                                    priority=fa_priority,
                                    color=fa_color,
                                    is_active=True
                                )
                                session.add(new_fa)
                                session.commit()
                                st.success(f"Created focus area '{fa_name}' from {len(selected_rooms)} room(s)")
                                st.rerun()
                        else:
                            st.error("Please enter a name for the focus area.")
        else:
            st.warning("No rooms found in the floor plan GeoJSON. Upload a floor plan with room definitions first.")
    
    elif creation_method == "Rectangle Bounds":
        with st.form(key="save_fa_rect"):
            col1, col2 = st.columns(2)
            with col1:
                x_min = st.number_input("X Min (m)", min_value=0.0, max_value=float(floor.width_meters), value=0.0, key="fa_x_min")
                y_min = st.number_input("Y Min (m)", min_value=0.0, max_value=float(floor.height_meters), value=0.0, key="fa_y_min")
            with col2:
                x_max = st.number_input("X Max (m)", min_value=0.0, max_value=float(floor.width_meters), value=float(floor.width_meters), key="fa_x_max")
                y_max = st.number_input("Y Max (m)", min_value=0.0, max_value=float(floor.height_meters), value=float(floor.height_meters), key="fa_y_max")
            
            fa_name = st.text_input("Focus Area Name", value="", key="fa_rect_name")
            fa_type = st.selectbox("Area Type", ["general", "critical", "restricted", "high_traffic"], key="fa_rect_type")
            fa_priority = st.slider("Priority", 1, 10, 5, key="fa_rect_priority")
            fa_color = st.color_picker("Color", "#2e5cbf", key="fa_rect_color")
            
            if st.form_submit_button("Create Rectangle Focus Area", type="primary"):
                if fa_name and x_max > x_min and y_max > y_min:
                    rect_coords = [
                        [x_min, y_min],
                        [x_max, y_min],
                        [x_max, y_max],
                        [x_min, y_max]
                    ]
                    
                    geojson_feature = polygon_to_geojson(
                        rect_coords,
                        fa_name,
                        geom_type='focus_area',
                        properties={
                            'area_type': fa_type,
                            'priority': fa_priority,
                            'color': fa_color
                        }
                    )
                    
                    new_fa = FocusArea(
                        floor_id=floor.id,
                        name=fa_name,
                        geojson=json.dumps(geojson_feature),
                        area_type=fa_type,
                        priority=fa_priority,
                        color=fa_color,
                        is_active=True
                    )
                    session.add(new_fa)
                    session.commit()
                    st.success(f"Created focus area '{fa_name}'")
                    st.rerun()
                else:
                    st.error("Please enter a valid name and ensure max > min for both X and Y.")


def render_floor_plan_with_focus_areas(session, floor):
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
                render_zone_polygon(fig, coords, fa.name, color=fa.color, opacity=0.3)
        except Exception:
            pass
    
    if st.session_state.get('fa_vertices'):
        vertices = st.session_state.fa_vertices
        if vertices:
            xs = [v[0] for v in vertices]
            ys = [v[1] for v in vertices]
            
            import plotly.graph_objects as go
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
    
    st.plotly_chart(fig, use_container_width=True, key="focus_area_floor_plan")
    
    st.caption(f"Floor dimensions: {floor.width_meters:.1f}m × {floor.height_meters:.1f}m")
    
    if focus_areas:
        st.success(f"{len(focus_areas)} active focus area(s) defined")
    else:
        st.info("No focus areas defined yet. Add focus areas to enable coverage zone and alert zone creation.")
