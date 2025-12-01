import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
import base64
import time


def get_playback_figure(floor, positions_at_time, gateways_data, trail_positions=None):
    """Create a plotly figure with floor plan and positions at a specific time"""
    
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
                    y=floor.height_meters,
                    sizex=floor.width_meters,
                    sizey=floor.height_meters,
                    sizing="stretch",
                    opacity=0.8,
                    layer="below"
                )
            )
        except Exception as e:
            pass
    
    for gw in gateways_data:
        fig.add_trace(go.Scatter(
            x=[gw['x']],
            y=[gw['y']],
            mode='markers+text',
            marker=dict(size=12, color='blue', symbol='square'),
            text=[gw['name']],
            textposition='top center',
            name=f"Gateway: {gw['name']}",
            hoverinfo='text',
            hovertext=f"Gateway: {gw['name']}"
        ))
    
    colors = ['red', 'green', 'orange', 'purple', 'cyan', 'magenta', 'yellow', 'lime']
    
    for idx, (beacon_name, pos) in enumerate(positions_at_time.items()):
        color = colors[idx % len(colors)]
        
        if trail_positions and beacon_name in trail_positions:
            trail = trail_positions[beacon_name]
            if len(trail) > 1:
                trail_x = [p['x'] for p in trail]
                trail_y = [p['y'] for p in trail]
                
                fig.add_trace(go.Scatter(
                    x=trail_x,
                    y=trail_y,
                    mode='lines',
                    line=dict(color=color, width=2, dash='dot'),
                    opacity=0.5,
                    showlegend=False
                ))
        
        fig.add_trace(go.Scatter(
            x=[pos['x']],
            y=[pos['y']],
            mode='markers+text',
            marker=dict(size=14, color=color),
            text=[beacon_name],
            textposition='bottom center',
            name=beacon_name,
            hoverinfo='text',
            hovertext=f"{beacon_name}<br>Position: ({pos['x']:.1f}, {pos['y']:.1f})<br>Time: {pos['timestamp'].strftime('%H:%M:%S')}"
        ))
    
    fig.update_layout(
        xaxis=dict(
            range=[0, floor.width_meters],
            title="X (meters)",
            constrain='domain'
        ),
        yaxis=dict(
            range=[0, floor.height_meters],
            title="Y (meters)",
            scaleanchor="x",
            scaleratio=1
        ),
        showlegend=True,
        legend=dict(x=1.02, y=1),
        margin=dict(l=50, r=150, t=50, b=50),
        height=600
    )
    
    return fig


def render():
    st.title("Historical Playback")
    st.markdown("Replay beacon movement patterns from historical data")
    
    with get_db_session() as session:
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured. Please add a building first.")
            return
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            st.subheader("Playback Settings")
            
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
            st.subheader("Time Range")
            
            today = datetime.now().date()
            
            col_date1, col_date2 = st.columns(2)
            with col_date1:
                start_date = st.date_input("Start Date", value=today - timedelta(days=1))
            with col_date2:
                end_date = st.date_input("End Date", value=today)
            
            col_time1, col_time2 = st.columns(2)
            with col_time1:
                start_time = st.time_input("Start Time", value=datetime.strptime("00:00", "%H:%M").time())
            with col_time2:
                end_time = st.time_input("End Time", value=datetime.strptime("23:59", "%H:%M").time())
            
            start_datetime = datetime.combine(start_date, start_time)
            end_datetime = datetime.combine(end_date, end_time)
            
            st.markdown("---")
            st.subheader("Playback Controls")
            
            playback_speed = st.select_slider(
                "Speed",
                options=["0.5x", "1x", "2x", "5x", "10x", "50x"],
                value="1x"
            )
            
            speed_multiplier = {
                "0.5x": 0.5,
                "1x": 1,
                "2x": 2,
                "5x": 5,
                "10x": 10,
                "50x": 50
            }[playback_speed]
            
            show_trail = st.checkbox("Show movement trail", value=True)
            trail_length = st.slider("Trail length (points)", 5, 100, 20) if show_trail else 0
            
            beacons = session.query(Beacon).filter(Beacon.is_active == True).all()
            beacon_options = ["All Beacons"] + [b.name for b in beacons]
            selected_beacon_filter = st.selectbox("Filter Beacon", options=beacon_options)
        
        with col2:
            floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
            
            gateways = session.query(Gateway).filter(
                Gateway.floor_id == selected_floor_id,
                Gateway.is_active == True
            ).all()
            
            gateways_data = [
                {'name': gw.name, 'x': gw.x_position, 'y': gw.y_position}
                for gw in gateways
            ]
            
            query = session.query(Position).filter(
                Position.floor_id == selected_floor_id,
                Position.timestamp >= start_datetime,
                Position.timestamp <= end_datetime
            )
            
            if selected_beacon_filter != "All Beacons":
                beacon = session.query(Beacon).filter(Beacon.name == selected_beacon_filter).first()
                if beacon:
                    query = query.filter(Position.beacon_id == beacon.id)
            
            all_positions = query.order_by(Position.timestamp.asc()).all()
            
            if not all_positions:
                st.warning("No position data found for the selected time range and filters.")
                st.info("Try expanding the date range or check if the signal processor has been running.")
                
                fig = get_playback_figure(floor, {}, gateways_data)
                st.plotly_chart(fig, use_container_width=True)
                return
            
            positions_by_time = {}
            for pos in all_positions:
                beacon = session.query(Beacon).filter(Beacon.id == pos.beacon_id).first()
                if beacon:
                    time_key = pos.timestamp.replace(microsecond=0)
                    if time_key not in positions_by_time:
                        positions_by_time[time_key] = {}
                    positions_by_time[time_key][beacon.name] = {
                        'x': pos.x_position,
                        'y': pos.y_position,
                        'speed': pos.speed,
                        'timestamp': pos.timestamp
                    }
            
            sorted_times = sorted(positions_by_time.keys())
            
            if not sorted_times:
                st.warning("No valid position data to display.")
                return
            
            st.subheader(f"Playback: {floor.name or f'Floor {floor.floor_number}'}")
            
            total_frames = len(sorted_times)
            st.write(f"**Data points:** {total_frames} | **Time span:** {sorted_times[0].strftime('%Y-%m-%d %H:%M')} to {sorted_times[-1].strftime('%Y-%m-%d %H:%M')}")
            
            if 'playback_frame' not in st.session_state:
                st.session_state['playback_frame'] = 0
            if 'is_playing' not in st.session_state:
                st.session_state['is_playing'] = False
            
            col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns(4)
            
            with col_ctrl1:
                if st.button("⏮️ Start"):
                    st.session_state['playback_frame'] = 0
                    st.session_state['is_playing'] = False
            
            with col_ctrl2:
                if st.session_state['is_playing']:
                    if st.button("⏸️ Pause"):
                        st.session_state['is_playing'] = False
                else:
                    if st.button("▶️ Play"):
                        st.session_state['is_playing'] = True
            
            with col_ctrl3:
                if st.button("⏭️ End"):
                    st.session_state['playback_frame'] = total_frames - 1
                    st.session_state['is_playing'] = False
            
            with col_ctrl4:
                step_size = st.number_input("Step", min_value=1, max_value=100, value=1, label_visibility="collapsed")
            
            current_frame = st.slider(
                "Timeline",
                min_value=0,
                max_value=total_frames - 1,
                value=st.session_state['playback_frame'],
                key="timeline_slider"
            )
            st.session_state['playback_frame'] = current_frame
            
            current_time = sorted_times[current_frame]
            st.write(f"**Current time:** {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            positions_at_time = positions_by_time[current_time]
            
            trail_positions = {}
            if show_trail:
                start_idx = max(0, current_frame - trail_length)
                for i in range(start_idx, current_frame + 1):
                    frame_time = sorted_times[i]
                    for beacon_name, pos in positions_by_time[frame_time].items():
                        if beacon_name not in trail_positions:
                            trail_positions[beacon_name] = []
                        trail_positions[beacon_name].append(pos)
            
            fig = get_playback_figure(floor, positions_at_time, gateways_data, trail_positions if show_trail else None)
            st.plotly_chart(fig, use_container_width=True)
            
            if positions_at_time:
                st.subheader("Beacon Status at Current Time")
                
                cols = st.columns(min(len(positions_at_time), 4))
                for idx, (beacon_name, pos) in enumerate(positions_at_time.items()):
                    with cols[idx % 4]:
                        st.metric(
                            beacon_name,
                            f"({pos['x']:.1f}, {pos['y']:.1f})",
                            f"{pos['speed']:.2f} m/s" if pos.get('speed') else None
                        )
            
            if st.session_state['is_playing']:
                next_frame = current_frame + int(step_size * speed_multiplier)
                if next_frame < total_frames:
                    st.session_state['playback_frame'] = next_frame
                    time.sleep(0.5 / speed_multiplier)
                    st.rerun()
                else:
                    st.session_state['is_playing'] = False
                    st.session_state['playback_frame'] = total_frames - 1
