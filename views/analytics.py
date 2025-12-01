import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, Zone
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import pandas as pd
import base64


def render():
    st.title("Analytics Dashboard")
    st.markdown("Analyze movement patterns, traffic, and dwell times")
    
    tab1, tab2, tab3 = st.tabs(["Heatmap", "Dwell Time Analysis", "Traffic Patterns"])
    
    with tab1:
        render_heatmap()
    
    with tab2:
        render_dwell_analysis()
    
    with tab3:
        render_traffic_patterns()


def render_heatmap():
    with get_db_session() as session:
        st.subheader("Position Heatmap")
        
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured.")
            return
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox("Building", options=list(building_options.keys()), key="heat_building")
            
            floors = session.query(Floor).filter(
                Floor.building_id == building_options[selected_building]
            ).order_by(Floor.floor_number).all()
            
            if not floors:
                st.warning("No floor plans.")
                return
            
            floor_options = {f"Floor {f.floor_number}": f.id for f in floors}
            selected_floor_name = st.selectbox("Floor", options=list(floor_options.keys()), key="heat_floor")
            selected_floor_id = floor_options[selected_floor_name]
            
            today = datetime.now().date()
            
            col_date1, col_date2 = st.columns(2)
            with col_date1:
                start_date = st.date_input("Start", value=today - timedelta(days=7), key="heat_start")
            with col_date2:
                end_date = st.date_input("End", value=today, key="heat_end")
            
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
            
            resolution = st.slider("Grid Resolution", 5, 50, 20, key="heat_res")
            
            beacons = session.query(Beacon).filter(Beacon.is_active == True).all()
            beacon_options = ["All Beacons"] + [b.name for b in beacons]
            selected_beacon = st.selectbox("Filter Beacon", options=beacon_options, key="heat_beacon")
        
        with col2:
            floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
            
            floor_width = floor.width_meters if floor.width_meters else 50.0
            floor_height = floor.height_meters if floor.height_meters else 50.0
            
            query = session.query(Position).filter(
                Position.floor_id == selected_floor_id,
                Position.timestamp >= start_datetime,
                Position.timestamp <= end_datetime
            )
            
            if selected_beacon != "All Beacons":
                beacon = session.query(Beacon).filter(Beacon.name == selected_beacon).first()
                if beacon:
                    query = query.filter(Position.beacon_id == beacon.id)
            
            positions = query.all()
            
            if not positions:
                st.warning("No position data found for the selected period.")
                return
            
            heatmap_data = np.zeros((resolution, resolution))
            
            for pos in positions:
                x_idx = int((pos.x_position / floor_width) * (resolution - 1))
                y_idx = int((pos.y_position / floor_height) * (resolution - 1))
                
                x_idx = max(0, min(resolution - 1, x_idx))
                y_idx = max(0, min(resolution - 1, y_idx))
                
                heatmap_data[y_idx, x_idx] += 1
            
            fig = go.Figure()
            
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
                            y=floor_height,
                            sizex=floor_width,
                            sizey=floor_height,
                            sizing="stretch",
                            opacity=0.5,
                            layer="below"
                        )
                    )
                except Exception:
                    pass
            
            x_coords = np.linspace(0, floor_width, resolution)
            y_coords = np.linspace(0, floor_height, resolution)
            
            fig.add_trace(go.Heatmap(
                z=heatmap_data,
                x=x_coords,
                y=y_coords,
                colorscale='Hot',
                opacity=0.6,
                showscale=True,
                colorbar=dict(title="Visits")
            ))
            
            fig.update_layout(
                xaxis=dict(range=[0, floor_width], title="X (meters)"),
                yaxis=dict(range=[0, floor_height], title="Y (meters)", scaleanchor="x"),
                height=600,
                title=f"Position Heatmap - {len(positions)} data points"
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            col_stats1, col_stats2, col_stats3 = st.columns(3)
            with col_stats1:
                st.metric("Total Positions", len(positions))
            with col_stats2:
                unique_beacons = len(set(p.beacon_id for p in positions))
                st.metric("Unique Beacons", unique_beacons)
            with col_stats3:
                hot_spot = np.unravel_index(np.argmax(heatmap_data), heatmap_data.shape)
                hot_x = x_coords[hot_spot[1]]
                hot_y = y_coords[hot_spot[0]]
                st.metric("Hottest Spot", f"({hot_x:.1f}, {hot_y:.1f})")


def render_dwell_analysis():
    with get_db_session() as session:
        st.subheader("Dwell Time Analysis")
        
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured.")
            return
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox("Building", options=list(building_options.keys()), key="dwell_building")
            
            floors = session.query(Floor).filter(
                Floor.building_id == building_options[selected_building]
            ).order_by(Floor.floor_number).all()
            
            if not floors:
                st.warning("No floor plans.")
                return
            
            floor_options = {f"Floor {f.floor_number}": f.id for f in floors}
            selected_floor_name = st.selectbox("Floor", options=list(floor_options.keys()), key="dwell_floor")
            selected_floor_id = floor_options[selected_floor_name]
            
            today = datetime.now().date()
            start_date = st.date_input("Start Date", value=today - timedelta(days=7), key="dwell_start")
            end_date = st.date_input("End Date", value=today, key="dwell_end")
            
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
        
        with col2:
            zones = session.query(Zone).filter(
                Zone.floor_id == selected_floor_id,
                Zone.is_active == True
            ).all()
            
            if not zones:
                st.info("No zones defined for this floor. Create zones in 'Zones & Alerts' to analyze dwell times.")
                return
            
            positions = session.query(Position).filter(
                Position.floor_id == selected_floor_id,
                Position.timestamp >= start_datetime,
                Position.timestamp <= end_datetime
            ).order_by(Position.beacon_id, Position.timestamp).all()
            
            if not positions:
                st.warning("No position data found for the selected period.")
                return
            
            zone_dwell_times = {zone.name: [] for zone in zones}
            
            current_beacon_id = None
            zone_entry_times = {}
            last_zones = set()
            
            for pos in positions:
                if pos.beacon_id != current_beacon_id:
                    for zone_name, entry_time in zone_entry_times.items():
                        if entry_time:
                            zone_dwell_times[zone_name].append(0)
                    
                    current_beacon_id = pos.beacon_id
                    zone_entry_times = {zone.name: None for zone in zones}
                    last_zones = set()
                
                current_zones = set()
                for zone in zones:
                    in_zone = (zone.x_min <= pos.x_position <= zone.x_max and 
                              zone.y_min <= pos.y_position <= zone.y_max)
                    
                    if in_zone:
                        current_zones.add(zone.name)
                        
                        if zone.name not in last_zones:
                            zone_entry_times[zone.name] = pos.timestamp
                    else:
                        if zone.name in last_zones and zone_entry_times.get(zone.name):
                            dwell = (pos.timestamp - zone_entry_times[zone.name]).total_seconds()
                            zone_dwell_times[zone.name].append(dwell)
                            zone_entry_times[zone.name] = None
                
                last_zones = current_zones
            
            dwell_data = []
            for zone_name, times in zone_dwell_times.items():
                if times:
                    dwell_data.append({
                        'Zone': zone_name,
                        'Avg Dwell (s)': np.mean(times),
                        'Max Dwell (s)': np.max(times),
                        'Min Dwell (s)': np.min(times),
                        'Total Visits': len(times)
                    })
            
            if dwell_data:
                df = pd.DataFrame(dwell_data)
                
                fig = px.bar(df, x='Zone', y='Avg Dwell (s)', 
                            title='Average Dwell Time by Zone',
                            color='Total Visits',
                            color_continuous_scale='Viridis')
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("Dwell Time Statistics")
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No dwell time data calculated. Make sure there are position records within zone boundaries.")


def render_traffic_patterns():
    with get_db_session() as session:
        st.subheader("Traffic Patterns")
        
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured.")
            return
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox("Building", options=list(building_options.keys()), key="traffic_building")
            
            floors = session.query(Floor).filter(
                Floor.building_id == building_options[selected_building]
            ).order_by(Floor.floor_number).all()
            
            if not floors:
                st.warning("No floor plans.")
                return
            
            floor_options = {f"Floor {f.floor_number}": f.id for f in floors}
            selected_floor_name = st.selectbox("Floor", options=list(floor_options.keys()), key="traffic_floor")
            selected_floor_id = floor_options[selected_floor_name]
            
            today = datetime.now().date()
            analysis_date = st.date_input("Date", value=today, key="traffic_date")
            
            start_datetime = datetime.combine(analysis_date, datetime.min.time())
            end_datetime = datetime.combine(analysis_date, datetime.max.time())
        
        with col2:
            positions = session.query(Position).filter(
                Position.floor_id == selected_floor_id,
                Position.timestamp >= start_datetime,
                Position.timestamp <= end_datetime
            ).all()
            
            if not positions:
                st.warning("No position data found for the selected date.")
                return
            
            hourly_counts = {}
            unique_beacons_by_hour = {}
            
            for pos in positions:
                hour = pos.timestamp.hour
                if hour not in hourly_counts:
                    hourly_counts[hour] = 0
                    unique_beacons_by_hour[hour] = set()
                
                hourly_counts[hour] += 1
                unique_beacons_by_hour[hour].add(pos.beacon_id)
            
            hours = list(range(24))
            counts = [hourly_counts.get(h, 0) for h in hours]
            unique_counts = [len(unique_beacons_by_hour.get(h, set())) for h in hours]
            
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                x=hours,
                y=counts,
                name='Position Updates',
                marker_color='steelblue'
            ))
            
            fig.add_trace(go.Scatter(
                x=hours,
                y=unique_counts,
                name='Unique Beacons',
                mode='lines+markers',
                yaxis='y2',
                line=dict(color='orange', width=2)
            ))
            
            fig.update_layout(
                title=f'Traffic Pattern - {analysis_date}',
                xaxis=dict(title='Hour of Day', tickmode='linear', dtick=1),
                yaxis=dict(title='Position Updates', side='left'),
                yaxis2=dict(title='Unique Beacons', side='right', overlaying='y'),
                height=400,
                legend=dict(x=0.01, y=0.99)
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            
            with col_stat1:
                st.metric("Total Updates", len(positions))
            
            with col_stat2:
                peak_hour = max(hourly_counts, key=hourly_counts.get) if hourly_counts else 0
                st.metric("Peak Hour", f"{peak_hour}:00")
            
            with col_stat3:
                all_beacons = set(p.beacon_id for p in positions)
                st.metric("Total Beacons", len(all_beacons))
            
            with col_stat4:
                avg_speed = np.mean([p.speed for p in positions if p.speed])
                st.metric("Avg Speed", f"{avg_speed:.2f} m/s")
            
            st.subheader("Beacon Activity Summary")
            
            beacon_activity = {}
            for pos in positions:
                beacon = session.query(Beacon).filter(Beacon.id == pos.beacon_id).first()
                if beacon:
                    if beacon.name not in beacon_activity:
                        beacon_activity[beacon.name] = {
                            'positions': 0,
                            'avg_speed': [],
                            'total_distance': 0
                        }
                    beacon_activity[beacon.name]['positions'] += 1
                    if pos.speed:
                        beacon_activity[beacon.name]['avg_speed'].append(pos.speed)
            
            activity_data = []
            for name, data in beacon_activity.items():
                activity_data.append({
                    'Beacon': name,
                    'Positions': data['positions'],
                    'Avg Speed (m/s)': np.mean(data['avg_speed']) if data['avg_speed'] else 0
                })
            
            if activity_data:
                df = pd.DataFrame(activity_data)
                df = df.sort_values('Positions', ascending=False)
                st.dataframe(df, use_container_width=True)
