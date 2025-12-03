import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, RSSISignal, MQTTConfig
from utils.triangulation import GatewayReading, trilaterate_2d, calculate_velocity, filter_outlier_readings
from utils.signal_processor import get_signal_processor
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
import numpy as np
import time
import base64
import json
import math


def latlon_to_meters(lat, lon, origin_lat, origin_lon):
    """Convert lat/lon to local meter coordinates using equirectangular projection"""
    dx = (lon - origin_lon) * math.cos(math.radians(origin_lat)) * 111000
    dy = (lat - origin_lat) * 111000
    return dx, dy


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
                        x, y = latlon_to_meters(lat, lon, floor.origin_lat, floor.origin_lon)
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
                        x, y = latlon_to_meters(lat, lon, floor.origin_lat, floor.origin_lon)
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
    except Exception as e:
        return False


def create_floor_plan_base(floor):
    """Create base figure with floor plan image or GeoJSON if available"""
    fig = go.Figure()
    
    has_floor_plan = False
    
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
            has_floor_plan = True
        except Exception as e:
            pass
    
    if not has_floor_plan and floor.floor_plan_geojson:
        has_floor_plan = render_geojson_floor_plan(fig, floor)
    
    fig.update_layout(
        xaxis=dict(
            range=[0, floor.width_meters],
            title="X (meters)",
            showgrid=not has_floor_plan,
            zeroline=False,
            constrain='domain'
        ),
        yaxis=dict(
            range=[0, floor.height_meters],
            title="Y (meters)",
            showgrid=not has_floor_plan,
            zeroline=False,
            scaleanchor="x",
            scaleratio=1
        ),
        showlegend=True,
        legend=dict(x=1.02, y=1, bgcolor='rgba(255,255,255,0.8)'),
        margin=dict(l=50, r=150, t=50, b=50),
        height=600,
        plot_bgcolor='rgba(240,240,240,0.3)' if not has_floor_plan else 'rgba(255,255,255,0)'
    )
    
    return fig, has_floor_plan


def add_gateways_to_figure(fig, gateways_data):
    """Add gateway markers to the figure"""
    for gw in gateways_data:
        fig.add_trace(go.Scatter(
            x=[gw['x']],
            y=[gw['y']],
            mode='markers+text',
            marker=dict(size=18, color='#2e5cbf', symbol='square', 
                       line=dict(width=2, color='white')),
            text=[gw['name']],
            textposition='top center',
            textfont=dict(size=10, color='#2e5cbf'),
            name=f"Gateway: {gw['name']}",
            hoverinfo='text',
            hovertext=f"<b>Gateway: {gw['name']}</b><br>Position: ({gw['x']:.1f}, {gw['y']:.1f})"
        ))


def create_current_location_figure(floor, positions_data, gateways_data, beacon_info):
    """Create figure showing current beacon locations"""
    fig, has_image = create_floor_plan_base(floor)
    add_gateways_to_figure(fig, gateways_data)
    
    colors = ['#e63946', '#2a9d8f', '#e76f51', '#9b59b6', '#3498db', '#f39c12', '#1abc9c', '#e74c3c']
    
    for idx, (beacon_name, pos_list) in enumerate(positions_data.items()):
        if not pos_list:
            continue
            
        color = colors[idx % len(colors)]
        latest = pos_list[-1]
        info = beacon_info.get(beacon_name, {})
        
        fig.add_trace(go.Scatter(
            x=[latest['x']],
            y=[latest['y']],
            mode='markers',
            marker=dict(size=16, color=color, symbol='circle',
                       line=dict(width=2, color='white')),
            name=beacon_name,
            hoverinfo='text',
            hovertext=f"<b>{beacon_name}</b><br>Type: {info.get('type', 'Unknown')}<br>Position: ({latest['x']:.1f}, {latest['y']:.1f})<br>Speed: {latest.get('speed', 0):.2f} m/s"
        ))
    
    fig.update_layout(title=dict(text="Current Locations", x=0.5, font=dict(size=16)))
    return fig


def create_spaghetti_figure(floor, positions_data, gateways_data, beacon_info):
    """Create spaghetti map showing movement trails"""
    fig, has_image = create_floor_plan_base(floor)
    add_gateways_to_figure(fig, gateways_data)
    
    colors = ['#e63946', '#2a9d8f', '#e76f51', '#9b59b6', '#3498db', '#f39c12', '#1abc9c', '#e74c3c']
    
    for idx, (beacon_name, pos_list) in enumerate(positions_data.items()):
        if not pos_list or len(pos_list) < 2:
            continue
            
        color = colors[idx % len(colors)]
        info = beacon_info.get(beacon_name, {})
        
        trail_x = [p['x'] for p in pos_list]
        trail_y = [p['y'] for p in pos_list]
        
        fig.add_trace(go.Scatter(
            x=trail_x,
            y=trail_y,
            mode='lines',
            line=dict(color=color, width=3),
            name=f"{beacon_name} path",
            opacity=0.7,
            hoverinfo='text',
            hovertext=f"<b>{beacon_name}</b><br>Type: {info.get('type', 'Unknown')}<br>Points: {len(pos_list)}"
        ))
        
        if pos_list:
            fig.add_trace(go.Scatter(
                x=[trail_x[0]],
                y=[trail_y[0]],
                mode='markers',
                marker=dict(size=10, color=color, symbol='circle-open', line=dict(width=2)),
                name=f"{beacon_name} start",
                showlegend=False,
                hoverinfo='text',
                hovertext=f"<b>{beacon_name} START</b><br>Time: {pos_list[0]['timestamp'].strftime('%H:%M:%S')}"
            ))
            
            fig.add_trace(go.Scatter(
                x=[trail_x[-1]],
                y=[trail_y[-1]],
                mode='markers',
                marker=dict(size=14, color=color, symbol='circle',
                           line=dict(width=2, color='white')),
                name=f"{beacon_name} current",
                showlegend=False,
                hoverinfo='text',
                hovertext=f"<b>{beacon_name} CURRENT</b><br>Time: {pos_list[-1]['timestamp'].strftime('%H:%M:%S')}"
            ))
    
    fig.update_layout(title=dict(text="Spaghetti Map - Movement Trails", x=0.5, font=dict(size=16)))
    return fig


def create_heatmap_figure(floor, positions_data, gateways_data):
    """Create heatmap showing dwell time density"""
    fig, has_image = create_floor_plan_base(floor)
    
    all_x = []
    all_y = []
    for beacon_name, pos_list in positions_data.items():
        for p in pos_list:
            all_x.append(p['x'])
            all_y.append(p['y'])
    
    if all_x and all_y:
        grid_size = 30
        x_bins = np.linspace(0, floor.width_meters, grid_size + 1)
        y_bins = np.linspace(0, floor.height_meters, grid_size + 1)
        
        heatmap_data, x_edges, y_edges = np.histogram2d(
            all_x, all_y, bins=[x_bins, y_bins]
        )
        
        heatmap_data = heatmap_data.T
        
        x_centers = (x_edges[:-1] + x_edges[1:]) / 2
        y_centers = (y_edges[:-1] + y_edges[1:]) / 2
        
        heatmap_data_masked = np.where(heatmap_data > 0, heatmap_data, np.nan)
        
        fig.add_trace(go.Heatmap(
            x=x_centers,
            y=y_centers,
            z=heatmap_data_masked,
            colorscale=[
                [0, 'rgba(255,255,0,0.3)'],
                [0.25, 'rgba(255,200,0,0.5)'],
                [0.5, 'rgba(255,100,0,0.6)'],
                [0.75, 'rgba(255,50,0,0.7)'],
                [1, 'rgba(255,0,0,0.8)']
            ],
            showscale=True,
            colorbar=dict(title="Density", x=1.15),
            hovertemplate='X: %{x:.1f}m<br>Y: %{y:.1f}m<br>Count: %{z}<extra></extra>',
            zsmooth='best'
        ))
    
    add_gateways_to_figure(fig, gateways_data)
    
    fig.update_layout(title=dict(text="Heatmap - Dwell Time Density", x=0.5, font=dict(size=16)))
    return fig


def render():
    st.title("Live Tracking")
    st.markdown("Real-time beacon position tracking with floor plan visualization")
    
    with get_db_session() as session:
        mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
        
        if not mqtt_config:
            st.warning("No MQTT broker configured. Please configure MQTT settings first.")
            return
        
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured. Please add a building first.")
            return
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            st.subheader("Location")
            
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox("Building", options=list(building_options.keys()))
            
            floors = session.query(Floor).filter(
                Floor.building_id == building_options[selected_building]
            ).order_by(Floor.floor_number).all()
            
            if not floors:
                st.warning("No floor plans for this building.")
                return
            
            floor_options = {f"Floor {f.floor_number}: {f.name or ''}": f.id for f in floors}
            selected_floor_name = st.selectbox("Floor", options=list(floor_options.keys()))
            selected_floor_id = floor_options[selected_floor_name]
            
            st.markdown("---")
            st.subheader("View Mode")
            
            view_mode = st.radio(
                "Visualization",
                options=["Current Location", "Spaghetti Map", "Heatmap"],
                index=0,
                help="Choose how to display beacon data",
                key="live_tracking_view_mode"
            )
            
            st.markdown("---")
            st.subheader("Time Frame")
            
            time_presets = {
                "Last 5 minutes": 5,
                "Last 15 minutes": 15,
                "Last 30 minutes": 30,
                "Last 1 hour": 60,
                "Last 2 hours": 120,
                "Last 4 hours": 240
            }
            
            time_selection = st.selectbox(
                "Time Range",
                options=list(time_presets.keys()),
                index=1,
                key="live_tracking_time_range"
            )
            time_minutes = time_presets[time_selection]
            
            st.caption(f"Data from last {time_minutes} min")
            
            st.markdown("---")
            st.subheader("Beacons")
            
            all_beacons = session.query(Beacon).order_by(Beacon.name).all()
            
            resource_types = list(set([b.resource_type for b in all_beacons if b.resource_type]))
            resource_types.sort()
            
            if resource_types:
                filter_by_type = st.multiselect(
                    "Filter by Type",
                    options=resource_types,
                    default=[],
                    help="Filter beacons by resource type"
                )
                
                if filter_by_type:
                    filtered_beacons = [b for b in all_beacons if b.resource_type in filter_by_type]
                else:
                    filtered_beacons = all_beacons
            else:
                filtered_beacons = all_beacons
            
            beacon_options = {f"{b.name} ({b.mac_address[-8:]})": b.id for b in filtered_beacons}
            
            select_all = st.checkbox("Select All Beacons", value=True, key="live_tracking_select_all")
            
            if select_all:
                selected_beacon_ids = [b.id for b in filtered_beacons]
            else:
                selected_beacon_names = st.multiselect(
                    "Select Beacons",
                    options=list(beacon_options.keys()),
                    default=[],
                    key="live_tracking_beacon_select"
                )
                selected_beacon_ids = [beacon_options[name] for name in selected_beacon_names]
            
            st.caption(f"{len(selected_beacon_ids)} beacon(s) selected")
            
            st.markdown("---")
            st.subheader("Controls")
            
            auto_refresh = st.checkbox("Auto-refresh", value=view_mode == "Current Location")
            if auto_refresh:
                refresh_interval = st.slider("Refresh (sec)", 2, 10, 3)
            
            processor = get_signal_processor()
            if processor.is_running:
                st.success("Processor: Running")
            else:
                st.warning("Processor: Stopped")
                if st.button("Start Processor", type="primary"):
                    if processor.start():
                        st.rerun()
            
            if st.button("Refresh Now"):
                st.rerun()
        
        with col2:
            floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
            
            if not floor.floor_plan_image and not floor.floor_plan_geojson:
                st.warning("No floor plan uploaded for this floor. Please upload a floor plan in the Buildings section.")
                st.info(f"Current floor dimensions: {floor.width_meters:.1f}m x {floor.height_meters:.1f}m")
            
            gateways = session.query(Gateway).filter(
                Gateway.floor_id == selected_floor_id,
                Gateway.is_active == True
            ).all()
            
            gateways_data = [
                {'name': gw.name, 'x': gw.x_position, 'y': gw.y_position, 'id': gw.id}
                for gw in gateways
            ]
            
            cutoff_time = datetime.utcnow() - timedelta(minutes=time_minutes)
            
            if selected_beacon_ids:
                beacons_map = {b.id: b for b in session.query(Beacon).filter(
                    Beacon.id.in_(selected_beacon_ids)
                ).all()}
                
                positions_query = session.query(Position).filter(
                    Position.floor_id == selected_floor_id,
                    Position.timestamp >= cutoff_time,
                    Position.beacon_id.in_(selected_beacon_ids)
                ).order_by(Position.timestamp.asc())
                
                max_points = 5000
                recent_positions = positions_query.limit(max_points).all()
            else:
                beacons_map = {}
                recent_positions = []
            
            positions_data = {}
            beacon_info = {}
            for pos in recent_positions:
                beacon = beacons_map.get(pos.beacon_id)
                if beacon:
                    if beacon.name not in positions_data:
                        positions_data[beacon.name] = []
                        beacon_info[beacon.name] = {
                            'mac': beacon.mac_address,
                            'type': beacon.resource_type,
                            'id': beacon.id
                        }
                    positions_data[beacon.name].append({
                        'x': pos.x_position,
                        'y': pos.y_position,
                        'velocity_x': pos.velocity_x,
                        'velocity_y': pos.velocity_y,
                        'speed': pos.speed,
                        'timestamp': pos.timestamp
                    })
            
            st.subheader(f"{floor.name or f'Floor {floor.floor_number}'}")
            
            if view_mode == "Current Location":
                fig = create_current_location_figure(floor, positions_data, gateways_data, beacon_info)
            elif view_mode == "Spaghetti Map":
                fig = create_spaghetti_figure(floor, positions_data, gateways_data, beacon_info)
            else:
                fig = create_heatmap_figure(floor, positions_data, gateways_data)
            
            st.plotly_chart(fig, key="floor_plan_chart")
            
            col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
            
            with col_stats1:
                st.metric("Gateways", len(gateways))
            
            with col_stats2:
                st.metric("Beacons Visible", len(positions_data))
            
            with col_stats3:
                total_points = sum(len(p) for p in positions_data.values())
                st.metric("Data Points", total_points)
            
            with col_stats4:
                st.metric("Time Window", f"{time_minutes}m")
            
            if positions_data and view_mode == "Current Location":
                st.markdown("---")
                st.subheader("Beacon Details")
                
                for beacon_name, pos_list in positions_data.items():
                    if pos_list:
                        latest = pos_list[-1]
                        info = beacon_info.get(beacon_name, {})
                        resource_icon = {
                            'Staff': '👤', 'Patient': '🏥', 'Asset': '📦',
                            'Device': '📱', 'Vehicle': '🚗', 'Equipment': '🔧'
                        }.get(info.get('type', ''), '📍')
                        
                        with st.expander(f"{resource_icon} {beacon_name}", expanded=False):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                st.write(f"**Position:** ({latest['x']:.1f}, {latest['y']:.1f})")
                            with c2:
                                st.write(f"**Speed:** {latest.get('speed', 0):.2f} m/s")
                            with c3:
                                st.write(f"**Updated:** {latest['timestamp'].strftime('%H:%M:%S')}")
            
            elif not positions_data:
                if selected_beacon_ids:
                    st.info("No position data found for the selected beacons in this time frame. Make sure the signal processor is running.")
                else:
                    st.info("Select beacons to display on the floor plan.")
            
            if auto_refresh:
                time.sleep(refresh_interval)
                st.rerun()
