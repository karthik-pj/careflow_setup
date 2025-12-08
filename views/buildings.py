import streamlit as st
from database import get_db_session, Building, Floor
from datetime import datetime
import base64
from io import BytesIO
from PIL import Image
import json
import re
from utils.dwg_parser import parse_dxf_file, dxf_to_geojson, get_dxf_dimensions, detect_dxf_scale


def show_pending_message():
    """Display any pending success message from session state"""
    if 'buildings_success_msg' in st.session_state:
        st.success(st.session_state['buildings_success_msg'])
        del st.session_state['buildings_success_msg']


def set_success_and_rerun(message):
    """Store success message in session state and rerun"""
    st.session_state['buildings_success_msg'] = message
    st.rerun()


def parse_gps_coordinates(coord_string):
    """
    Parse GPS coordinates in various formats:
    - "53.8578°,10.6712° 53.8580°,10.6706°" (pairs separated by space)
    - "53.8578,10.6712 53.8580,10.6706" (without degree symbols)
    - "53.8578°, 10.6712°; 53.8580°, 10.6706°" (semicolon separated)
    
    Returns list of (lat, lon) tuples and calculates centroid
    """
    if not coord_string or not coord_string.strip():
        return [], None, None
    
    cleaned = coord_string.replace('°', '').replace(';', ' ').strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    pairs = []
    parts = cleaned.split(' ')
    
    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if not part:
            i += 1
            continue
            
        if ',' in part:
            coords = part.split(',')
            if len(coords) == 2:
                try:
                    lat = float(coords[0].strip())
                    lon = float(coords[1].strip())
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        pairs.append((lat, lon))
                except ValueError:
                    pass
        i += 1
    
    if not pairs:
        return [], None, None
    
    avg_lat = sum(p[0] for p in pairs) / len(pairs)
    avg_lon = sum(p[1] for p in pairs) / len(pairs)
    
    return pairs, avg_lat, avg_lon


def format_coords_for_display(boundary_coords):
    """Format stored coordinates for display"""
    if not boundary_coords:
        return "Not set"
    try:
        coords = json.loads(boundary_coords)
        formatted = " ".join([f"{lat:.4f}°,{lon:.4f}°" for lat, lon in coords])
        return formatted
    except:
        return boundary_coords


def parse_geojson(content):
    """Parse and validate GeoJSON content"""
    try:
        data = json.loads(content)
        if data.get('type') != 'FeatureCollection':
            return None, "GeoJSON must be a FeatureCollection"
        if 'features' not in data:
            return None, "GeoJSON must contain features"
        return data, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {str(e)}"


def extract_geojson_bounds(geojson_data):
    """Extract bounding box from GeoJSON features"""
    min_lat, max_lat = 90, -90
    min_lon, max_lon = 180, -180
    
    def process_coords(coords):
        nonlocal min_lat, max_lat, min_lon, max_lon
        if isinstance(coords[0], (int, float)):
            lon, lat = coords[0], coords[1]
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)
        else:
            for c in coords:
                process_coords(c)
    
    for feature in geojson_data.get('features', []):
        geometry = feature.get('geometry', {})
        coords = geometry.get('coordinates', [])
        if coords:
            process_coords(coords)
    
    if min_lat == 90:
        return None
    
    return {
        'min_lat': min_lat,
        'max_lat': max_lat,
        'min_lon': min_lon,
        'max_lon': max_lon,
        'center_lat': (min_lat + max_lat) / 2,
        'center_lon': (min_lon + max_lon) / 2
    }


def extract_geojson_rooms(geojson_data):
    """Extract room names and types from GeoJSON"""
    rooms = []
    for feature in geojson_data.get('features', []):
        props = feature.get('properties', {})
        geom_type = props.get('geomType', '')
        name = props.get('name', '')
        sub_type = props.get('subType', '')
        
        if geom_type == 'room' and name:
            rooms.append({
                'name': name,
                'type': sub_type or 'room'
            })
    return rooms


def render():
    st.title("Buildings & Floor Plans")
    st.markdown("Manage buildings and upload architectural floor plans")
    
    show_pending_message()
    
    tab1, tab2 = st.tabs(["Buildings", "Floor Plans"])
    
    with tab1:
        render_buildings()
    
    with tab2:
        render_floor_plans()


def render_buildings():
    with get_db_session() as session:
        st.subheader("Add New Building")
        
        with st.form("add_building"):
            col1, col2 = st.columns(2)
            
            with col1:
                name = st.text_input("Building Name*", placeholder="e.g., Main Office")
                address = st.text_input("Address", placeholder="123 Main Street")
            
            with col2:
                st.markdown("**GPS Boundary Coordinates**")
                gps_coords = st.text_area(
                    "Enter GPS coordinates",
                    placeholder="53.8578°,10.6712° 53.8580°,10.6706°\n(lat,lon pairs separated by spaces)",
                    help="Enter latitude,longitude pairs with optional ° symbols. Pairs separated by spaces or semicolons. Example: 53.8578°,10.6712° 53.8580°,10.6706°",
                    height=100
                )
            
            description = st.text_area("Description", placeholder="Describe the building...")
            
            submitted = st.form_submit_button("Add Building", type="primary")
            
            if submitted:
                if name:
                    coord_pairs, center_lat, center_lon = parse_gps_coordinates(gps_coords)
                    
                    boundary_json = json.dumps(coord_pairs) if coord_pairs else None
                    
                    building = Building(
                        name=name,
                        description=description,
                        address=address,
                        latitude=center_lat,
                        longitude=center_lon,
                        boundary_coords=boundary_json
                    )
                    session.add(building)
                    session.commit()
                    
                    if coord_pairs:
                        set_success_and_rerun(f"Building '{name}' added with {len(coord_pairs)} boundary points!")
                    else:
                        set_success_and_rerun(f"Building '{name}' added successfully!")
                else:
                    st.error("Building name is required")
        
        st.markdown("---")
        st.subheader("Existing Buildings")
        
        buildings = session.query(Building).order_by(Building.name).all()
        
        if buildings:
            for building in buildings:
                with st.expander(f"📍 {building.name}", expanded=False):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        st.write(f"**Address:** {building.address or 'Not specified'}")
                        st.write(f"**Description:** {building.description or 'No description'}")
                    
                    with col2:
                        if building.latitude and building.longitude:
                            st.write(f"**Center GPS:** {building.latitude:.6f}, {building.longitude:.6f}")
                        else:
                            st.write("**GPS:** Not set")
                        
                        if building.boundary_coords:
                            try:
                                coords = json.loads(building.boundary_coords)
                                st.write(f"**Boundary Points:** {len(coords)}")
                            except:
                                pass
                        
                        floor_count = session.query(Floor).filter(Floor.building_id == building.id).count()
                        st.write(f"**Floors:** {floor_count}")
                    
                    with col3:
                        if st.button("Delete", key=f"del_building_{building.id}", type="secondary"):
                            building_name = building.name
                            session.delete(building)
                            session.commit()
                            set_success_and_rerun(f"Building '{building_name}' deleted")
                    
                    if building.boundary_coords:
                        with st.container():
                            st.write("**Boundary Coordinates:**")
                            st.code(format_coords_for_display(building.boundary_coords), language=None)
        else:
            st.info("No buildings added yet. Add your first building above.")


def render_floor_plans():
    with get_db_session() as session:
        buildings = session.query(Building).order_by(Building.name).all()
        
        if not buildings:
            st.warning("Please add a building first before uploading floor plans.")
            return
        
        st.subheader("Upload Floor Plan")
        
        building_options = {b.name: b.id for b in buildings}
        
        plan_type = st.radio(
            "Floor Plan Type",
            ["Image (PNG/JPG)", "DXF (AutoCAD)", "GeoJSON"],
            horizontal=True,
            help="Choose between uploading an image, DXF CAD file, or GeoJSON architectural file",
            key="floor_plan_type_selector"
        )
        
        if plan_type == "Image (PNG/JPG)":
            with st.form("add_floor_image"):
                selected_building = st.selectbox("Select Building*", options=list(building_options.keys()), key="img_building")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    floor_number = st.number_input("Floor Number*", value=0, step=1, help="Use 0 for ground floor, negative for basement", key="img_floor_num")
                    floor_name = st.text_input("Floor Name", placeholder="e.g., Ground Floor, Level 1", key="img_floor_name")
                
                with col2:
                    width_meters = st.number_input("Floor Width (meters)", value=50.0, min_value=1.0, max_value=1000.0, key="img_width")
                    height_meters = st.number_input("Floor Height (meters)", value=50.0, min_value=1.0, max_value=1000.0, key="img_height")
                
                floor_plan_file = st.file_uploader(
                    "Upload Floor Plan Image*",
                    type=['png', 'jpg', 'jpeg'],
                    help="Upload an architectural floor plan image",
                    key="img_uploader"
                )
                
                submitted = st.form_submit_button("Add Floor Plan", type="primary")
                
                if submitted:
                    if not selected_building:
                        st.error("Please select a building")
                    elif not floor_plan_file:
                        st.error("Please upload a floor plan image")
                    else:
                        image_data = floor_plan_file.read()
                        
                        floor = Floor(
                            building_id=building_options[selected_building],
                            floor_number=floor_number,
                            name=floor_name or f"Floor {floor_number}",
                            floor_plan_image=image_data,
                            floor_plan_filename=floor_plan_file.name,
                            floor_plan_type='image',
                            width_meters=width_meters,
                            height_meters=height_meters
                        )
                        session.add(floor)
                        session.commit()
                        set_success_and_rerun("Floor plan image uploaded successfully!")
        
        elif plan_type == "DXF (AutoCAD)":
            st.info("Upload a DXF file exported from AutoCAD, ArchiCAD, or other CAD software. For DWG files, please export to DXF first (File → Save As → DXF in AutoCAD).")
            
            with st.form("add_floor_dxf"):
                selected_building = st.selectbox("Select Building*", options=list(building_options.keys()), key="dxf_building")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    floor_number = st.number_input("Floor Number*", value=0, step=1, help="Use 0 for ground floor, negative for basement", key="dxf_floor_num")
                    floor_name = st.text_input("Floor Name", placeholder="e.g., Ground Floor, Level 1", key="dxf_floor_name")
                
                with col2:
                    scale_option = st.selectbox(
                        "Scale",
                        ["Auto-detect", "Millimeters", "Centimeters", "Meters", "Inches", "Feet"],
                        help="Select the unit used in your DXF file",
                        key="dxf_scale"
                    )
                
                dxf_file = st.file_uploader(
                    "Upload DXF Floor Plan*",
                    type=['dxf'],
                    help="Upload a DXF file from AutoCAD or similar CAD software",
                    key="dxf_uploader"
                )
                
                with st.expander("Advanced Settings"):
                    wall_layers = st.text_input(
                        "Wall Layer Names (comma-separated)",
                        value="WALL,WALLS,A-WALL,S-WALL,PARTITION",
                        help="Layer names that contain walls"
                    )
                    room_layers = st.text_input(
                        "Room Layer Names (comma-separated)",
                        value="ROOM,ROOMS,A-AREA,A-ROOM,SPACE,ZONE",
                        help="Layer names that contain rooms/spaces"
                    )
                
                submitted = st.form_submit_button("Add Floor Plan", type="primary")
                
                if submitted:
                    if not selected_building:
                        st.error("Please select a building")
                    elif not dxf_file:
                        st.error("Please upload a DXF file")
                    else:
                        try:
                            dxf_content = dxf_file.read()
                            dxf_data = parse_dxf_file(dxf_content)
                            
                            if scale_option == "Auto-detect":
                                scale = detect_dxf_scale(dxf_data)
                            else:
                                scale_map = {
                                    "Millimeters": 0.001,
                                    "Centimeters": 0.01,
                                    "Meters": 1.0,
                                    "Inches": 0.0254,
                                    "Feet": 0.3048
                                }
                                scale = scale_map.get(scale_option, 1.0)
                            
                            wall_layer_list = [l.strip() for l in wall_layers.split(',')]
                            room_layer_list = [l.strip() for l in room_layers.split(',')]
                            
                            bounds = dxf_data.get('bounds')
                            origin_x = bounds['min_x'] if bounds else 0
                            origin_y = bounds['min_y'] if bounds else 0
                            
                            geojson_str = dxf_to_geojson(
                                dxf_data, 
                                scale=scale, 
                                origin_x=origin_x,
                                origin_y=origin_y,
                                wall_layers=wall_layer_list,
                                room_layers=room_layer_list
                            )
                            
                            width, height = get_dxf_dimensions(dxf_data, scale)
                            
                            floor = Floor(
                                building_id=building_options[selected_building],
                                floor_number=floor_number,
                                name=floor_name or f"Floor {floor_number}",
                                floor_plan_geojson=geojson_str,
                                floor_plan_filename=dxf_file.name,
                                floor_plan_type='dxf',
                                width_meters=round(width, 2),
                                height_meters=round(height, 2),
                                origin_lat=0,
                                origin_lon=0
                            )
                            session.add(floor)
                            session.commit()
                            
                            entity_count = dxf_data.get('entity_count', 0)
                            layers = dxf_data.get('layers', [])
                            set_success_and_rerun(f"DXF floor plan uploaded! Found {entity_count} entities across {len(layers)} layers. Dimensions: {width:.1f}m x {height:.1f}m")
                            
                        except Exception as e:
                            st.error(f"Error parsing DXF file: {str(e)}")
        
        else:
            selected_building = st.selectbox("Select Building*", options=list(building_options.keys()), key="geo_building")
            
            col1, col2 = st.columns(2)
            
            with col1:
                floor_number = st.number_input("Floor Number*", value=0, step=1, help="Use 0 for ground floor, negative for basement", key="geo_floor_num")
                floor_name = st.text_input("Floor Name", placeholder="e.g., Ground Floor, Level 1", key="geo_floor_name")
            
            with col2:
                st.info("Dimensions will be calculated from GeoJSON bounds")
            
            input_method = st.radio(
                "Input Method",
                ["Paste GeoJSON", "Upload File"],
                horizontal=True,
                help="Choose how to provide your GeoJSON floor plan"
            )
            
            geojson_content = None
            filename = "floor_plan.geojson"
            
            if input_method == "Paste GeoJSON":
                geojson_text = st.text_area(
                    "Paste GeoJSON Content*",
                    height=300,
                    placeholder='{"type": "FeatureCollection", "features": [...]}',
                    help="Paste the complete GeoJSON content here"
                )
                if geojson_text:
                    geojson_content = geojson_text.strip()
            else:
                geojson_file = st.file_uploader(
                    "Upload GeoJSON Floor Plan*",
                    type=None,
                    help="Upload a GeoJSON file (.geojson or .json)",
                    key="geo_uploader"
                )
                if geojson_file:
                    geojson_content = geojson_file.read().decode('utf-8')
                    filename = geojson_file.name
            
            if st.button("Add Floor Plan", type="primary", key="add_geojson_btn"):
                if not selected_building:
                    st.error("Please select a building")
                elif not geojson_content:
                    st.error("Please provide GeoJSON content (paste or upload)")
                else:
                    geojson_data, error = parse_geojson(geojson_content)
                    
                    if error:
                        st.error(f"GeoJSON Error: {error}")
                    else:
                        bounds = extract_geojson_bounds(geojson_data)
                        
                        if bounds:
                            lat_range = bounds['max_lat'] - bounds['min_lat']
                            lon_range = bounds['max_lon'] - bounds['min_lon']
                            calc_height = lat_range * 111000
                            calc_width = lon_range * 111000 * abs(cos_deg(bounds['center_lat']))
                            
                            floor = Floor(
                                building_id=building_options[selected_building],
                                floor_number=floor_number,
                                name=floor_name or f"Floor {floor_number}",
                                floor_plan_geojson=geojson_content,
                                floor_plan_filename=filename,
                                floor_plan_type='geojson',
                                width_meters=round(calc_width, 2),
                                height_meters=round(calc_height, 2),
                                origin_lat=bounds['min_lat'],
                                origin_lon=bounds['min_lon']
                            )
                            session.add(floor)
                            session.commit()
                            
                            rooms = extract_geojson_rooms(geojson_data)
                            room_count = len(rooms)
                            set_success_and_rerun(f"GeoJSON floor plan uploaded! Found {room_count} named rooms. Dimensions: {calc_width:.1f}m x {calc_height:.1f}m")
                        else:
                            st.error("Could not extract bounds from GeoJSON")
        
        st.markdown("---")
        st.subheader("Existing Floor Plans")
        
        for building in buildings:
            floors = session.query(Floor).filter(
                Floor.building_id == building.id
            ).order_by(Floor.floor_number).all()
            
            if floors:
                st.write(f"**{building.name}**")
                
                for floor in floors:
                    plan_type_label = f"[{floor.floor_plan_type or 'image'}]" if floor.floor_plan_type else ""
                    with st.expander(f"Floor {floor.floor_number}: {floor.name or ''} {plan_type_label}", expanded=False):
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            if floor.floor_plan_type == 'geojson' and floor.floor_plan_geojson:
                                render_geojson_preview(floor)
                            elif floor.floor_plan_image:
                                try:
                                    image = Image.open(BytesIO(floor.floor_plan_image))
                                    st.image(image, caption=f"{floor.name or f'Floor {floor.floor_number}'}", use_container_width=True)
                                except Exception as e:
                                    st.error(f"Error displaying image: {e}")
                        
                        with col2:
                            st.write(f"**Type:** {floor.floor_plan_type or 'image'}")
                            st.write(f"**Dimensions:** {floor.width_meters:.1f}m x {floor.height_meters:.1f}m")
                            st.write(f"**Filename:** {floor.floor_plan_filename}")
                            
                            if floor.origin_lat and floor.origin_lon:
                                st.write(f"**Origin:** {floor.origin_lat:.6f}, {floor.origin_lon:.6f}")
                            
                            if floor.floor_plan_type == 'geojson' and floor.floor_plan_geojson:
                                try:
                                    geojson_data = json.loads(floor.floor_plan_geojson)
                                    rooms = extract_geojson_rooms(geojson_data)
                                    if rooms:
                                        st.write(f"**Rooms:** {len(rooms)}")
                                        with st.popover("View Rooms"):
                                            for room in rooms[:20]:
                                                st.write(f"• {room['name']} ({room['type']})")
                                            if len(rooms) > 20:
                                                st.write(f"... and {len(rooms) - 20} more")
                                except:
                                    pass
                            
                            if st.button("Delete", key=f"del_floor_{floor.id}", type="secondary"):
                                session.delete(floor)
                                session.commit()
                                set_success_and_rerun("Floor plan deleted")
                
                st.markdown("---")


def cos_deg(degrees):
    """Calculate cosine of angle in degrees"""
    import math
    return math.cos(math.radians(degrees))


def render_geojson_preview(floor):
    """Render a preview of GeoJSON floor plan"""
    try:
        geojson_data = json.loads(floor.floor_plan_geojson)
        
        st.markdown("**GeoJSON Floor Plan Preview**")
        
        feature_count = len(geojson_data.get('features', []))
        rooms = extract_geojson_rooms(geojson_data)
        
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Features", feature_count)
        with col_b:
            st.metric("Named Rooms", len(rooms))
        with col_c:
            bounds = extract_geojson_bounds(geojson_data)
            if bounds:
                st.metric("Center", f"{bounds['center_lat']:.4f}, {bounds['center_lon']:.4f}")
        
        geom_types = {}
        for feature in geojson_data.get('features', []):
            props = feature.get('properties', {})
            geom_type = props.get('geomType', 'unknown')
            geom_types[geom_type] = geom_types.get(geom_type, 0) + 1
        
        if geom_types:
            st.write("**Feature Types:**")
            types_str = ", ".join([f"{k}: {v}" for k, v in geom_types.items()])
            st.write(types_str)
        
        with st.popover("View Raw GeoJSON"):
            st.json(geojson_data)
            
    except Exception as e:
        st.error(f"Error rendering GeoJSON: {e}")
