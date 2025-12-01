import streamlit as st
from database import get_db_session, Building, Floor, Gateway
from datetime import datetime
import re


def validate_mac_address(mac: str) -> bool:
    """Validate MAC address format"""
    pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
    return bool(pattern.match(mac))


def render():
    st.title("Gateway Configuration")
    st.markdown("Configure Moko BLE to WiFi Gateway Mini 03 devices")
    
    with get_db_session() as session:
        buildings = session.query(Building).order_by(Building.name).all()
        
        if not buildings:
            st.warning("Please add a building first before configuring gateways.")
            st.info("Go to 'Buildings & Floor Plans' to add a building.")
            return
        
        st.subheader("Add New Gateway")
        
        with st.form("add_gateway"):
            building_options = {b.name: b.id for b in buildings}
            selected_building_name = st.selectbox("Select Building*", options=list(building_options.keys()))
            selected_building_id = building_options[selected_building_name]
            
            floors = session.query(Floor).filter(
                Floor.building_id == selected_building_id
            ).order_by(Floor.floor_number).all()
            
            if not floors:
                st.warning("Please upload a floor plan for this building first.")
                st.form_submit_button("Add Gateway", disabled=True)
                return
            
            floor_options = {f"{f.floor_number}: {f.name or 'Floor ' + str(f.floor_number)}": f.id for f in floors}
            selected_floor = st.selectbox("Select Floor*", options=list(floor_options.keys()))
            
            col1, col2 = st.columns(2)
            
            with col1:
                mac_address = st.text_input(
                    "MAC Address*",
                    placeholder="AA:BB:CC:DD:EE:FF",
                    help="The MAC address of the Moko gateway"
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
                
                x_position = st.number_input(
                    "X Position (meters)*",
                    value=0.0,
                    min_value=0.0,
                    max_value=1000.0,
                    help="Position from left edge of floor plan"
                )
                
                y_position = st.number_input(
                    "Y Position (meters)*",
                    value=0.0,
                    min_value=0.0,
                    max_value=1000.0,
                    help="Position from top edge of floor plan"
                )
            
            col3, col4 = st.columns(2)
            
            with col3:
                latitude = st.number_input(
                    "Latitude (GPS)",
                    value=0.0,
                    format="%.6f",
                    min_value=-90.0,
                    max_value=90.0
                )
                
                signal_calibration = st.number_input(
                    "Signal Calibration (dBm)",
                    value=-59,
                    min_value=-100,
                    max_value=0,
                    help="RSSI at 1 meter distance"
                )
            
            with col4:
                longitude = st.number_input(
                    "Longitude (GPS)",
                    value=0.0,
                    format="%.6f",
                    min_value=-180.0,
                    max_value=180.0
                )
                
                path_loss = st.number_input(
                    "Path Loss Exponent",
                    value=2.0,
                    min_value=1.0,
                    max_value=6.0,
                    help="2.0 for free space, 2.5-4 for indoor"
                )
            
            description = st.text_area(
                "Description",
                placeholder="Describe the gateway location..."
            )
            
            is_active = st.checkbox("Gateway is active", value=True)
            
            submitted = st.form_submit_button("Add Gateway", type="primary")
            
            if submitted:
                if not name:
                    st.error("Gateway name is required")
                elif not mac_address:
                    st.error("MAC address is required")
                elif not validate_mac_address(mac_address):
                    st.error("Invalid MAC address format. Use AA:BB:CC:DD:EE:FF")
                else:
                    existing = session.query(Gateway).filter(
                        Gateway.mac_address == mac_address
                    ).first()
                    
                    if existing:
                        st.error("A gateway with this MAC address already exists")
                    else:
                        gateway = Gateway(
                            building_id=selected_building_id,
                            floor_id=floor_options[selected_floor],
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
                        st.success(f"Gateway '{name}' added successfully!")
                        st.rerun()
        
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
                        st.write(f"**Position:** ({gw.x_position}m, {gw.y_position}m)")
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
                            st.rerun()
                        
                        if st.button("Delete", key=f"del_gw_{gw.id}", type="secondary"):
                            session.delete(gw)
                            st.success(f"Gateway '{gw.name}' deleted")
                            st.rerun()
        else:
            st.info("No gateways configured yet. Add your first gateway above.")
