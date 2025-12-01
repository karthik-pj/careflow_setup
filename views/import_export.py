import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Zone
import json
import csv
from io import StringIO
from datetime import datetime


def render():
    st.title("Import / Export")
    st.markdown("Bulk import and export gateway and beacon configurations")
    
    tab1, tab2 = st.tabs(["Export", "Import"])
    
    with tab1:
        render_export()
    
    with tab2:
        render_import()


def render_export():
    st.subheader("Export Configurations")
    
    with get_db_session() as session:
        export_type = st.selectbox(
            "What to Export",
            options=["Gateways", "Beacons", "Zones", "All Configurations"]
        )
        
        export_format = st.radio(
            "Format",
            options=["JSON", "CSV"],
            horizontal=True
        )
        
        if st.button("Generate Export", type="primary"):
            if export_type == "Gateways" or export_type == "All Configurations":
                gateways = session.query(Gateway).all()
                gateway_data = []
                for gw in gateways:
                    building = session.query(Building).filter(Building.id == gw.building_id).first()
                    floor = session.query(Floor).filter(Floor.id == gw.floor_id).first()
                    gateway_data.append({
                        'mac_address': gw.mac_address,
                        'name': gw.name,
                        'description': gw.description or '',
                        'building_name': building.name if building else '',
                        'floor_number': floor.floor_number if floor else 0,
                        'x_position': gw.x_position,
                        'y_position': gw.y_position,
                        'latitude': gw.latitude or '',
                        'longitude': gw.longitude or '',
                        'mqtt_topic': gw.mqtt_topic or '',
                        'wifi_ssid': gw.wifi_ssid or '',
                        'signal_calibration': gw.signal_strength_calibration,
                        'path_loss_exponent': gw.path_loss_exponent,
                        'is_active': gw.is_active
                    })
            
            if export_type == "Beacons" or export_type == "All Configurations":
                beacons = session.query(Beacon).all()
                beacon_data = []
                for b in beacons:
                    floor = session.query(Floor).filter(Floor.id == b.floor_id).first() if b.floor_id else None
                    beacon_data.append({
                        'mac_address': b.mac_address,
                        'name': b.name,
                        'uuid': b.uuid or '',
                        'major': b.major or 0,
                        'minor': b.minor or 0,
                        'description': b.description or '',
                        'resource_type': b.resource_type or '',
                        'assigned_to': b.assigned_to or '',
                        'is_fixed': b.is_fixed,
                        'floor_number': floor.floor_number if floor else '',
                        'fixed_x': b.fixed_x or '',
                        'fixed_y': b.fixed_y or '',
                        'is_active': b.is_active
                    })
            
            if export_type == "Zones" or export_type == "All Configurations":
                zones = session.query(Zone).all()
                zone_data = []
                for z in zones:
                    floor = session.query(Floor).filter(Floor.id == z.floor_id).first()
                    building = session.query(Building).filter(Building.id == floor.building_id).first() if floor else None
                    zone_data.append({
                        'name': z.name,
                        'description': z.description or '',
                        'building_name': building.name if building else '',
                        'floor_number': floor.floor_number if floor else 0,
                        'x_min': z.x_min,
                        'y_min': z.y_min,
                        'x_max': z.x_max,
                        'y_max': z.y_max,
                        'color': z.color,
                        'alert_on_enter': z.alert_on_enter,
                        'alert_on_exit': z.alert_on_exit,
                        'is_active': z.is_active
                    })
            
            if export_format == "JSON":
                if export_type == "All Configurations":
                    export_data = {
                        'export_date': datetime.utcnow().isoformat(),
                        'gateways': gateway_data,
                        'beacons': beacon_data,
                        'zones': zone_data
                    }
                elif export_type == "Gateways":
                    export_data = {'gateways': gateway_data}
                elif export_type == "Beacons":
                    export_data = {'beacons': beacon_data}
                else:
                    export_data = {'zones': zone_data}
                
                json_str = json.dumps(export_data, indent=2)
                st.download_button(
                    label="Download JSON",
                    data=json_str,
                    file_name=f"ble_config_{export_type.lower()}_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json"
                )
                
                st.json(export_data)
            
            else:
                if export_type == "Gateways":
                    data = gateway_data
                elif export_type == "Beacons":
                    data = beacon_data
                elif export_type == "Zones":
                    data = zone_data
                else:
                    st.warning("CSV export only supports single type. Please select Gateways, Beacons, or Zones.")
                    return
                
                if data:
                    output = StringIO()
                    writer = csv.DictWriter(output, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
                    csv_str = output.getvalue()
                    
                    st.download_button(
                        label="Download CSV",
                        data=csv_str,
                        file_name=f"ble_config_{export_type.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                    
                    st.text(csv_str[:2000] + "..." if len(csv_str) > 2000 else csv_str)
                else:
                    st.info(f"No {export_type.lower()} data to export.")


def render_import():
    st.subheader("Import Configurations")
    
    import_type = st.selectbox(
        "What to Import",
        options=["Gateways", "Beacons", "Zones"]
    )
    
    import_format = st.radio(
        "Format",
        options=["JSON", "CSV"],
        horizontal=True,
        key="import_format"
    )
    
    uploaded_file = st.file_uploader(
        f"Upload {import_format} File",
        type=['json'] if import_format == "JSON" else ['csv']
    )
    
    if uploaded_file:
        try:
            if import_format == "JSON":
                try:
                    content = uploaded_file.read().decode('utf-8')
                    data = json.loads(content)
                except json.JSONDecodeError as e:
                    st.error(f"Invalid JSON file: {str(e)}")
                    return
                
                if import_type == "Gateways":
                    items = data.get('gateways', data if isinstance(data, list) else [])
                elif import_type == "Beacons":
                    items = data.get('beacons', data if isinstance(data, list) else [])
                else:
                    items = data.get('zones', data if isinstance(data, list) else [])
            else:
                try:
                    content = uploaded_file.read().decode('utf-8')
                    reader = csv.DictReader(StringIO(content))
                    items = list(reader)
                except Exception as e:
                    st.error(f"Error parsing CSV file: {str(e)}")
                    return
            
            st.write(f"**Found {len(items)} items to import**")
            
            if items:
                st.json(items[:5])
                if len(items) > 5:
                    st.write(f"... and {len(items) - 5} more")
            
            col1, col2 = st.columns(2)
            
            with col1:
                skip_existing = st.checkbox("Skip existing (by MAC address)", value=True)
            
            with col2:
                update_existing = st.checkbox("Update existing entries", value=False)
            
            if st.button("Import Data", type="primary"):
                with get_db_session() as session:
                    imported = 0
                    skipped = 0
                    updated = 0
                    errors = []
                    
                    for item in items:
                        try:
                            if import_type == "Gateways":
                                mac = item.get('mac_address', '').upper()
                                existing = session.query(Gateway).filter(Gateway.mac_address == mac).first()
                                
                                if existing:
                                    if skip_existing and not update_existing:
                                        skipped += 1
                                        continue
                                    elif update_existing:
                                        existing.name = item.get('name', existing.name)
                                        existing.description = item.get('description') or existing.description
                                        existing.x_position = float(item.get('x_position', existing.x_position))
                                        existing.y_position = float(item.get('y_position', existing.y_position))
                                        existing.signal_strength_calibration = float(item.get('signal_calibration', existing.signal_strength_calibration))
                                        existing.path_loss_exponent = float(item.get('path_loss_exponent', existing.path_loss_exponent))
                                        updated += 1
                                        continue
                                
                                building_name = item.get('building_name', '')
                                floor_number = int(item.get('floor_number', 0))
                                
                                building = session.query(Building).filter(Building.name == building_name).first()
                                if not building:
                                    errors.append(f"Building '{building_name}' not found for gateway {mac}")
                                    continue
                                
                                floor = session.query(Floor).filter(
                                    Floor.building_id == building.id,
                                    Floor.floor_number == floor_number
                                ).first()
                                if not floor:
                                    errors.append(f"Floor {floor_number} not found in '{building_name}' for gateway {mac}")
                                    continue
                                
                                gateway = Gateway(
                                    building_id=building.id,
                                    floor_id=floor.id,
                                    mac_address=mac,
                                    name=item.get('name', ''),
                                    description=item.get('description'),
                                    x_position=float(item.get('x_position', 0)),
                                    y_position=float(item.get('y_position', 0)),
                                    latitude=float(item['latitude']) if item.get('latitude') else None,
                                    longitude=float(item['longitude']) if item.get('longitude') else None,
                                    mqtt_topic=item.get('mqtt_topic'),
                                    wifi_ssid=item.get('wifi_ssid'),
                                    signal_strength_calibration=float(item.get('signal_calibration', -59)),
                                    path_loss_exponent=float(item.get('path_loss_exponent', 2.0)),
                                    is_active=str(item.get('is_active', 'true')).lower() == 'true'
                                )
                                session.add(gateway)
                                imported += 1
                            
                            elif import_type == "Beacons":
                                mac = item.get('mac_address', '').upper()
                                existing = session.query(Beacon).filter(Beacon.mac_address == mac).first()
                                
                                if existing:
                                    if skip_existing and not update_existing:
                                        skipped += 1
                                        continue
                                    elif update_existing:
                                        existing.name = item.get('name', existing.name)
                                        existing.description = item.get('description') or existing.description
                                        existing.resource_type = item.get('resource_type') or existing.resource_type
                                        existing.assigned_to = item.get('assigned_to') or existing.assigned_to
                                        updated += 1
                                        continue
                                
                                floor_id = None
                                if item.get('floor_number'):
                                    floor = session.query(Floor).filter(
                                        Floor.floor_number == int(item.get('floor_number', 0))
                                    ).first()
                                    if floor:
                                        floor_id = floor.id
                                
                                beacon = Beacon(
                                    mac_address=mac,
                                    name=item.get('name', ''),
                                    uuid=item.get('uuid'),
                                    major=int(item['major']) if item.get('major') else None,
                                    minor=int(item['minor']) if item.get('minor') else None,
                                    description=item.get('description'),
                                    resource_type=item.get('resource_type'),
                                    assigned_to=item.get('assigned_to'),
                                    is_fixed=str(item.get('is_fixed', 'false')).lower() == 'true',
                                    floor_id=floor_id,
                                    fixed_x=float(item['fixed_x']) if item.get('fixed_x') else None,
                                    fixed_y=float(item['fixed_y']) if item.get('fixed_y') else None,
                                    is_active=str(item.get('is_active', 'true')).lower() == 'true'
                                )
                                session.add(beacon)
                                imported += 1
                            
                            elif import_type == "Zones":
                                building_name = item.get('building_name', '')
                                floor_number = int(item.get('floor_number', 0))
                                
                                building = session.query(Building).filter(Building.name == building_name).first()
                                if not building:
                                    errors.append(f"Building '{building_name}' not found for zone {item.get('name')}")
                                    continue
                                
                                floor = session.query(Floor).filter(
                                    Floor.building_id == building.id,
                                    Floor.floor_number == floor_number
                                ).first()
                                if not floor:
                                    errors.append(f"Floor {floor_number} not found in '{building_name}'")
                                    continue
                                
                                zone = Zone(
                                    floor_id=floor.id,
                                    name=item.get('name', ''),
                                    description=item.get('description'),
                                    x_min=float(item.get('x_min', 0)),
                                    y_min=float(item.get('y_min', 0)),
                                    x_max=float(item.get('x_max', 10)),
                                    y_max=float(item.get('y_max', 10)),
                                    color=item.get('color', '#FF0000'),
                                    alert_on_enter=str(item.get('alert_on_enter', 'true')).lower() == 'true',
                                    alert_on_exit=str(item.get('alert_on_exit', 'true')).lower() == 'true',
                                    is_active=str(item.get('is_active', 'true')).lower() == 'true'
                                )
                                session.add(zone)
                                imported += 1
                        
                        except Exception as e:
                            errors.append(f"Error processing item: {str(e)}")
                    
                    st.success(f"Import complete: {imported} imported, {updated} updated, {skipped} skipped")
                    
                    if errors:
                        st.warning(f"Errors encountered: {len(errors)}")
                        with st.expander("View Errors"):
                            for error in errors:
                                st.write(f"- {error}")
        
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
    
    st.markdown("---")
    st.subheader("Import Templates")
    
    st.markdown("""
    **Gateway CSV Template:**
    ```
    mac_address,name,description,building_name,floor_number,x_position,y_position,latitude,longitude,mqtt_topic,wifi_ssid,signal_calibration,path_loss_exponent,is_active
    AA:BB:CC:DD:EE:FF,Gateway 1,Main entrance,Main Building,0,5.0,10.0,,,ble/gateway/1,Office_WiFi,-59,2.0,true
    ```
    
    **Beacon CSV Template:**
    ```
    mac_address,name,uuid,major,minor,description,resource_type,assigned_to,is_fixed,floor_number,fixed_x,fixed_y,is_active
    11:22:33:44:55:66,Asset Tag 1,,0,0,Forklift,Asset,Warehouse Team,false,,,true
    ```
    
    **Zone CSV Template:**
    ```
    name,description,building_name,floor_number,x_min,y_min,x_max,y_max,color,alert_on_enter,alert_on_exit,is_active
    Restricted Area,No unauthorized access,Main Building,0,0,0,10,10,#FF0000,true,true,true
    ```
    """)
