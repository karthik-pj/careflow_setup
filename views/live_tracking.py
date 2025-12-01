import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, RSSISignal, MQTTConfig
from utils.triangulation import GatewayReading, trilaterate_2d, calculate_velocity, filter_outlier_readings
from utils.signal_processor import get_signal_processor
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
import time
import base64


def get_floor_plan_figure(floor, positions_data, gateways_data, show_trails=True):
    """Create a plotly figure with floor plan and positions"""
    
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
            st.warning(f"Could not load floor plan image: {e}")
    
    for gw in gateways_data:
        fig.add_trace(go.Scatter(
            x=[gw['x']],
            y=[gw['y']],
            mode='markers+text',
            marker=dict(size=15, color='blue', symbol='square'),
            text=[gw['name']],
            textposition='top center',
            name=f"Gateway: {gw['name']}",
            hoverinfo='text',
            hovertext=f"Gateway: {gw['name']}<br>Position: ({gw['x']:.1f}, {gw['y']:.1f})"
        ))
    
    colors = ['red', 'green', 'orange', 'purple', 'cyan', 'magenta', 'yellow', 'lime']
    
    for idx, (beacon_name, pos_list) in enumerate(positions_data.items()):
        color = colors[idx % len(colors)]
        
        if show_trails and len(pos_list) > 1:
            trail_x = [p['x'] for p in pos_list]
            trail_y = [p['y'] for p in pos_list]
            
            fig.add_trace(go.Scatter(
                x=trail_x,
                y=trail_y,
                mode='lines',
                line=dict(color=color, width=2, dash='dot'),
                name=f"{beacon_name} trail",
                opacity=0.5,
                showlegend=False
            ))
        
        if pos_list:
            latest = pos_list[-1]
            
            fig.add_trace(go.Scatter(
                x=[latest['x']],
                y=[latest['y']],
                mode='markers+text',
                marker=dict(size=12, color=color),
                text=[beacon_name],
                textposition='bottom center',
                name=beacon_name,
                hoverinfo='text',
                hovertext=f"{beacon_name}<br>Position: ({latest['x']:.1f}, {latest['y']:.1f})<br>Speed: {latest.get('speed', 0):.2f} m/s"
            ))
            
            if latest.get('velocity_x') and latest.get('velocity_y'):
                scale = 2
                fig.add_annotation(
                    x=latest['x'],
                    y=latest['y'],
                    ax=latest['x'] + latest['velocity_x'] * scale,
                    ay=latest['y'] + latest['velocity_y'] * scale,
                    xref='x',
                    yref='y',
                    axref='x',
                    ayref='y',
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    arrowwidth=2,
                    arrowcolor=color
                )
    
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
    st.title("Live Tracking")
    st.markdown("Real-time beacon position tracking on floor plans")
    
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
            st.subheader("View Settings")
            
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
            
            show_trails = st.checkbox("Show movement trails", value=True)
            trail_duration = st.slider("Trail duration (seconds)", 10, 300, 60)
            
            auto_refresh = st.checkbox("Auto-refresh", value=True)
            refresh_interval = st.slider("Refresh interval (seconds)", 1, 10, 2)
            
            st.markdown("---")
            st.subheader("Signal Processor")
            
            processor = get_signal_processor()
            
            if processor.is_running:
                st.success("Running")
                if st.button("Stop Processing"):
                    processor.stop()
                    st.rerun()
            else:
                st.warning("Stopped")
                if st.button("Start Processing", type="primary"):
                    if processor.start():
                        st.success("Started!")
                        st.rerun()
                    else:
                        st.error(processor.last_error or "Failed to start")
            
            if st.button("Manual Refresh"):
                st.rerun()
        
        with col2:
            floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
            
            gateways = session.query(Gateway).filter(
                Gateway.floor_id == selected_floor_id,
                Gateway.is_active == True
            ).all()
            
            gateways_data = [
                {'name': gw.name, 'x': gw.x_position, 'y': gw.y_position, 'id': gw.id}
                for gw in gateways
            ]
            
            cutoff_time = datetime.utcnow() - timedelta(seconds=trail_duration)
            
            recent_positions = session.query(Position).filter(
                Position.floor_id == selected_floor_id,
                Position.timestamp >= cutoff_time
            ).order_by(Position.timestamp.asc()).all()
            
            positions_data = {}
            for pos in recent_positions:
                beacon = session.query(Beacon).filter(Beacon.id == pos.beacon_id).first()
                if beacon:
                    if beacon.name not in positions_data:
                        positions_data[beacon.name] = []
                    positions_data[beacon.name].append({
                        'x': pos.x_position,
                        'y': pos.y_position,
                        'velocity_x': pos.velocity_x,
                        'velocity_y': pos.velocity_y,
                        'speed': pos.speed,
                        'timestamp': pos.timestamp
                    })
            
            st.subheader(f"Floor Plan: {floor.name or f'Floor {floor.floor_number}'}")
            
            fig = get_floor_plan_figure(floor, positions_data, gateways_data, show_trails)
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            
            col_stats1, col_stats2, col_stats3 = st.columns(3)
            
            with col_stats1:
                st.metric("Active Gateways", len(gateways))
            
            with col_stats2:
                st.metric("Tracked Beacons", len(positions_data))
            
            with col_stats3:
                total_positions = sum(len(p) for p in positions_data.values())
                st.metric("Position Updates", total_positions)
            
            if positions_data:
                st.subheader("Beacon Details")
                
                for beacon_name, pos_list in positions_data.items():
                    if pos_list:
                        latest = pos_list[-1]
                        with st.expander(f"📍 {beacon_name}", expanded=False):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                st.write(f"**Position:** ({latest['x']:.2f}, {latest['y']:.2f})")
                            with c2:
                                st.write(f"**Speed:** {latest.get('speed', 0):.2f} m/s")
                            with c3:
                                st.write(f"**Last Update:** {latest['timestamp'].strftime('%H:%M:%S')}")
            
            if auto_refresh:
                time.sleep(refresh_interval)
                st.rerun()
