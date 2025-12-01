import streamlit as st
from database import get_db_session, Building, Floor
from datetime import datetime
import base64
from io import BytesIO
from PIL import Image


def render():
    st.title("Buildings & Floor Plans")
    st.markdown("Manage buildings and upload architectural floor plans")
    
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
                latitude = st.number_input("Latitude (GPS)", value=0.0, format="%.6f", min_value=-90.0, max_value=90.0)
                longitude = st.number_input("Longitude (GPS)", value=0.0, format="%.6f", min_value=-180.0, max_value=180.0)
            
            description = st.text_area("Description", placeholder="Describe the building...")
            
            submitted = st.form_submit_button("Add Building", type="primary")
            
            if submitted:
                if name:
                    building = Building(
                        name=name,
                        description=description,
                        address=address,
                        latitude=latitude if latitude != 0 else None,
                        longitude=longitude if longitude != 0 else None
                    )
                    session.add(building)
                    st.success(f"Building '{name}' added successfully!")
                    st.rerun()
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
                            st.write(f"**GPS:** {building.latitude:.6f}, {building.longitude:.6f}")
                        else:
                            st.write("**GPS:** Not set")
                        
                        floor_count = session.query(Floor).filter(Floor.building_id == building.id).count()
                        st.write(f"**Floors:** {floor_count}")
                    
                    with col3:
                        if st.button("Delete", key=f"del_building_{building.id}", type="secondary"):
                            session.delete(building)
                            st.success(f"Building '{building.name}' deleted")
                            st.rerun()
        else:
            st.info("No buildings added yet. Add your first building above.")


def render_floor_plans():
    with get_db_session() as session:
        buildings = session.query(Building).order_by(Building.name).all()
        
        if not buildings:
            st.warning("Please add a building first before uploading floor plans.")
            return
        
        st.subheader("Upload Floor Plan")
        
        with st.form("add_floor"):
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox("Select Building*", options=list(building_options.keys()))
            
            col1, col2 = st.columns(2)
            
            with col1:
                floor_number = st.number_input("Floor Number*", value=0, step=1, help="Use 0 for ground floor, negative for basement")
                floor_name = st.text_input("Floor Name", placeholder="e.g., Ground Floor, Level 1")
            
            with col2:
                width_meters = st.number_input("Floor Width (meters)", value=50.0, min_value=1.0, max_value=1000.0)
                height_meters = st.number_input("Floor Height (meters)", value=50.0, min_value=1.0, max_value=1000.0)
            
            floor_plan_file = st.file_uploader(
                "Upload Floor Plan Image*",
                type=['png', 'jpg', 'jpeg'],
                help="Upload an architectural floor plan image"
            )
            
            submitted = st.form_submit_button("Add Floor Plan", type="primary")
            
            if submitted:
                if selected_building and floor_plan_file:
                    image_data = floor_plan_file.read()
                    
                    floor = Floor(
                        building_id=building_options[selected_building],
                        floor_number=floor_number,
                        name=floor_name or f"Floor {floor_number}",
                        floor_plan_image=image_data,
                        floor_plan_filename=floor_plan_file.name,
                        width_meters=width_meters,
                        height_meters=height_meters
                    )
                    session.add(floor)
                    st.success(f"Floor plan uploaded successfully!")
                    st.rerun()
                else:
                    st.error("Building selection and floor plan image are required")
        
        st.markdown("---")
        st.subheader("Existing Floor Plans")
        
        for building in buildings:
            floors = session.query(Floor).filter(
                Floor.building_id == building.id
            ).order_by(Floor.floor_number).all()
            
            if floors:
                st.write(f"**{building.name}**")
                
                for floor in floors:
                    with st.expander(f"Floor {floor.floor_number}: {floor.name or ''}", expanded=False):
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            if floor.floor_plan_image:
                                try:
                                    image = Image.open(BytesIO(floor.floor_plan_image))
                                    st.image(image, caption=f"{floor.name or f'Floor {floor.floor_number}'}", use_container_width=True)
                                except Exception as e:
                                    st.error(f"Error displaying image: {e}")
                        
                        with col2:
                            st.write(f"**Dimensions:** {floor.width_meters}m x {floor.height_meters}m")
                            st.write(f"**Filename:** {floor.floor_plan_filename}")
                            
                            if st.button("Delete", key=f"del_floor_{floor.id}", type="secondary"):
                                session.delete(floor)
                                st.success("Floor plan deleted")
                                st.rerun()
                
                st.markdown("---")
