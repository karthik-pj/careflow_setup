import streamlit as st
from database import get_db_session, Building, Floor, Beacon
from datetime import datetime
import re


def show_pending_message():
    """Display any pending success message from session state"""
    if 'beacons_success_msg' in st.session_state:
        st.success(st.session_state['beacons_success_msg'])
        del st.session_state['beacons_success_msg']


def set_success_and_rerun(message):
    """Store success message in session state and rerun"""
    st.session_state['beacons_success_msg'] = message
    st.rerun()


def validate_mac_address(mac: str) -> bool:
    """Validate MAC address format"""
    pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
    return bool(pattern.match(mac))


def render():
    st.title("BLE Beacon Management")
    st.markdown("Register and manage BLE beacons for tracking")
    
    show_pending_message()
    
    with get_db_session() as session:
        st.subheader("Add New Beacon")
        
        with st.form("add_beacon"):
            col1, col2 = st.columns(2)
            
            with col1:
                mac_address = st.text_input(
                    "MAC Address*",
                    placeholder="AA:BB:CC:DD:EE:FF",
                    help="The MAC address of the BLE beacon"
                ).upper()
                
                name = st.text_input(
                    "Beacon Name*",
                    placeholder="e.g., Asset Tag #001"
                )
                
                uuid = st.text_input(
                    "UUID",
                    placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                    help="iBeacon UUID (optional)"
                )
            
            with col2:
                resource_type = st.selectbox(
                    "Resource Type*",
                    options=["Device", "Staff", "Asset", "Vehicle", "Equipment", "Other"],
                    help="What type of resource is this beacon attached to?"
                )
                
                assigned_to = st.text_input(
                    "Assigned To",
                    placeholder="e.g., John Smith, Forklift #3",
                    help="Person or item this beacon is attached to"
                )
                
                col2a, col2b = st.columns(2)
                with col2a:
                    major = st.number_input("Major", value=0, min_value=0, max_value=65535)
                with col2b:
                    minor = st.number_input("Minor", value=0, min_value=0, max_value=65535)
            
            description = st.text_area(
                "Description",
                placeholder="Additional details about this beacon..."
            )
            
            st.markdown("**Fixed Position (Optional)**")
            st.caption("If this beacon is stationary, you can set its fixed position for calibration")
            
            buildings = session.query(Building).order_by(Building.name).all()
            
            col3, col4 = st.columns(2)
            
            with col3:
                is_fixed = st.checkbox("This beacon has a fixed position")
            
            floor_id = None
            fixed_x = None
            fixed_y = None
            
            if is_fixed and buildings:
                with col4:
                    building_options = {b.name: b.id for b in buildings}
                    selected_building = st.selectbox(
                        "Building",
                        options=list(building_options.keys()),
                        key="beacon_building"
                    )
                    
                    floors = session.query(Floor).filter(
                        Floor.building_id == building_options[selected_building]
                    ).order_by(Floor.floor_number).all()
                    
                    if floors:
                        floor_options = {
                            f"{f.floor_number}: {f.name or 'Floor ' + str(f.floor_number)}": f.id 
                            for f in floors
                        }
                        selected_floor = st.selectbox(
                            "Floor",
                            options=list(floor_options.keys()),
                            key="beacon_floor"
                        )
                        floor_id = floor_options[selected_floor]
                
                col5, col6 = st.columns(2)
                with col5:
                    fixed_x = st.number_input("X Position (meters)", value=0.0, min_value=0.0)
                with col6:
                    fixed_y = st.number_input("Y Position (meters)", value=0.0, min_value=0.0)
            
            is_active = st.checkbox("Beacon is active", value=True)
            
            submitted = st.form_submit_button("Add Beacon", type="primary")
            
            if submitted:
                if not name:
                    st.error("Beacon name is required")
                elif not mac_address:
                    st.error("MAC address is required")
                elif not validate_mac_address(mac_address):
                    st.error("Invalid MAC address format. Use AA:BB:CC:DD:EE:FF")
                else:
                    existing = session.query(Beacon).filter(
                        Beacon.mac_address == mac_address
                    ).first()
                    
                    if existing:
                        st.error("A beacon with this MAC address already exists")
                    else:
                        beacon = Beacon(
                            mac_address=mac_address,
                            name=name,
                            uuid=uuid or None,
                            major=major if major > 0 else None,
                            minor=minor if minor > 0 else None,
                            description=description or None,
                            resource_type=resource_type,
                            assigned_to=assigned_to or None,
                            is_fixed=is_fixed,
                            floor_id=floor_id,
                            fixed_x=fixed_x,
                            fixed_y=fixed_y,
                            is_active=is_active
                        )
                        session.add(beacon)
                        session.commit()
                        set_success_and_rerun(f"Beacon '{name}' added successfully!")
        
        st.markdown("---")
        st.subheader("Registered Beacons")
        
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            filter_type = st.selectbox(
                "Filter by Type",
                options=["All", "Device", "Staff", "Asset", "Vehicle", "Equipment", "Other"]
            )
        with filter_col2:
            filter_active = st.selectbox(
                "Filter by Status",
                options=["All", "Active Only", "Inactive Only"]
            )
        
        query = session.query(Beacon)
        
        if filter_type != "All":
            query = query.filter(Beacon.resource_type == filter_type)
        
        if filter_active == "Active Only":
            query = query.filter(Beacon.is_active == True)
        elif filter_active == "Inactive Only":
            query = query.filter(Beacon.is_active == False)
        
        beacons = query.order_by(Beacon.name).all()
        
        if beacons:
            for beacon in beacons:
                status_icon = "🟢" if beacon.is_active else "🔴"
                type_icon = {
                    "Device": "📱",
                    "Staff": "👤",
                    "Asset": "📦",
                    "Vehicle": "🚗",
                    "Equipment": "🔧",
                    "Other": "📍"
                }.get(beacon.resource_type, "📍")
                
                with st.expander(
                    f"{status_icon} {type_icon} {beacon.name} ({beacon.mac_address})",
                    expanded=False
                ):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        st.write(f"**Type:** {beacon.resource_type}")
                        st.write(f"**Assigned To:** {beacon.assigned_to or 'Not assigned'}")
                        if beacon.uuid:
                            st.write(f"**UUID:** {beacon.uuid}")
                        if beacon.major or beacon.minor:
                            st.write(f"**Major/Minor:** {beacon.major or 0}/{beacon.minor or 0}")
                    
                    with col2:
                        if beacon.is_fixed:
                            floor = session.query(Floor).filter(Floor.id == beacon.floor_id).first()
                            st.write(f"**Fixed Position:** Yes")
                            if floor:
                                st.write(f"**Floor:** {floor.name}")
                            st.write(f"**Position:** ({beacon.fixed_x}m, {beacon.fixed_y}m)")
                        else:
                            st.write("**Fixed Position:** No (mobile)")
                        
                        if beacon.description:
                            st.write(f"**Description:** {beacon.description}")
                    
                    with col3:
                        if st.button("Toggle Active", key=f"toggle_beacon_{beacon.id}"):
                            beacon.is_active = not beacon.is_active
                            session.commit()
                            st.rerun()
                        
                        if st.button("Delete", key=f"del_beacon_{beacon.id}", type="secondary"):
                            beacon_name = beacon.name
                            session.delete(beacon)
                            session.commit()
                            set_success_and_rerun(f"Beacon '{beacon_name}' deleted")
            
            st.markdown("---")
            st.write(f"**Total beacons:** {len(beacons)}")
        else:
            st.info("No beacons registered yet. Add your first beacon above.")
