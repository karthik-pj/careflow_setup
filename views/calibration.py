import streamlit as st
from database import get_db_session, Building, Floor, Gateway, Beacon, Position, CalibrationPoint
from utils.triangulation import rssi_to_distance, GatewayReading, trilaterate_2d
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image
import plotly.graph_objects as go
import numpy as np
import base64


def render():
    st.title("Calibration Wizard")
    st.markdown("Improve triangulation accuracy using known beacon positions")
    
    tab1, tab2, tab3 = st.tabs(["Calibration Points", "Run Calibration", "Accuracy Analysis"])
    
    with tab1:
        render_calibration_points()
    
    with tab2:
        render_run_calibration()
    
    with tab3:
        render_accuracy_analysis()


def render_calibration_points():
    with get_db_session() as session:
        st.subheader("Define Calibration Points")
        st.info("Place beacons at known positions to create calibration reference points")
        
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured.")
            return
        
        with st.form("add_calibration_point"):
            col1, col2 = st.columns(2)
            
            with col1:
                building_options = {b.name: b.id for b in buildings}
                selected_building = st.selectbox("Building", options=list(building_options.keys()))
                
                floors = session.query(Floor).filter(
                    Floor.building_id == building_options[selected_building]
                ).order_by(Floor.floor_number).all()
                
                if floors:
                    floor_options = {f"Floor {f.floor_number}": f.id for f in floors}
                    selected_floor = st.selectbox("Floor", options=list(floor_options.keys()))
                else:
                    st.warning("No floor plans available.")
                    st.form_submit_button("Add Calibration Point", disabled=True)
                    return
                
                beacons = session.query(Beacon).filter(Beacon.is_active == True).all()
                if beacons:
                    beacon_options = {f"{b.name} ({b.mac_address})": b.id for b in beacons}
                    selected_beacon = st.selectbox("Beacon", options=list(beacon_options.keys()))
                else:
                    st.warning("No active beacons.")
                    st.form_submit_button("Add Calibration Point", disabled=True)
                    return
            
            with col2:
                st.write("**Known Position (measured manually)**")
                known_x = st.number_input("X Position (meters)", value=0.0, min_value=0.0, step=0.1)
                known_y = st.number_input("Y Position (meters)", value=0.0, min_value=0.0, step=0.1)
            
            submitted = st.form_submit_button("Add Calibration Point", type="primary")
            
            if submitted:
                cal_point = CalibrationPoint(
                    floor_id=floor_options[selected_floor],
                    beacon_id=beacon_options[selected_beacon],
                    known_x=known_x,
                    known_y=known_y,
                    is_verified=False
                )
                session.add(cal_point)
                st.success("Calibration point added!")
                st.rerun()
        
        st.markdown("---")
        st.subheader("Existing Calibration Points")
        
        cal_points = session.query(CalibrationPoint).all()
        
        if cal_points:
            for cp in cal_points:
                beacon = session.query(Beacon).filter(Beacon.id == cp.beacon_id).first()
                floor = session.query(Floor).filter(Floor.id == cp.floor_id).first()
                
                status_icon = "✓" if cp.is_verified else "?"
                error_str = f"Error: {cp.error_distance:.2f}m" if cp.error_distance else "Not measured"
                
                with st.expander(f"[{status_icon}] {beacon.name if beacon else 'Unknown'} at ({cp.known_x}, {cp.known_y}) - {error_str}"):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        st.write(f"**Beacon:** {beacon.name if beacon else 'Unknown'}")
                        st.write(f"**Floor:** {floor.name if floor else 'Unknown'}")
                        st.write(f"**Known Position:** ({cp.known_x}, {cp.known_y})")
                    
                    with col2:
                        if cp.measured_x is not None:
                            st.write(f"**Measured Position:** ({cp.measured_x:.2f}, {cp.measured_y:.2f})")
                            st.write(f"**Error Distance:** {cp.error_distance:.2f} m")
                        else:
                            st.write("**Measured Position:** Not yet measured")
                        st.write(f"**Verified:** {'Yes' if cp.is_verified else 'No'}")
                    
                    with col3:
                        if st.button("Delete", key=f"del_cal_{cp.id}"):
                            session.delete(cp)
                            st.rerun()
        else:
            st.info("No calibration points defined yet.")


def render_run_calibration():
    with get_db_session() as session:
        st.subheader("Run Calibration Measurement")
        
        buildings = session.query(Building).all()
        if not buildings:
            st.warning("No buildings configured.")
            return
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            building_options = {b.name: b.id for b in buildings}
            selected_building = st.selectbox("Building", options=list(building_options.keys()), key="cal_building")
            
            floors = session.query(Floor).filter(
                Floor.building_id == building_options[selected_building]
            ).order_by(Floor.floor_number).all()
            
            if not floors:
                st.warning("No floor plans.")
                return
            
            floor_options = {f"Floor {f.floor_number}": f.id for f in floors}
            selected_floor_name = st.selectbox("Floor", options=list(floor_options.keys()), key="cal_floor")
            selected_floor_id = floor_options[selected_floor_name]
            
            cal_points = session.query(CalibrationPoint).filter(
                CalibrationPoint.floor_id == selected_floor_id
            ).all()
            
            if not cal_points:
                st.warning("No calibration points on this floor. Add some in the 'Calibration Points' tab.")
                return
            
            st.write(f"**Calibration points on this floor:** {len(cal_points)}")
            
            measurement_duration = st.slider("Measurement Duration (seconds)", 5, 60, 15)
            
            if st.button("Start Calibration Measurement", type="primary"):
                st.session_state['calibration_running'] = True
                st.session_state['calibration_start'] = datetime.utcnow()
                st.session_state['calibration_duration'] = measurement_duration
                st.rerun()
        
        with col2:
            floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
            
            if st.session_state.get('calibration_running'):
                start_time = st.session_state['calibration_start']
                duration = st.session_state['calibration_duration']
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                
                if elapsed < duration:
                    progress = elapsed / duration
                    st.progress(progress, text=f"Measuring... {int(elapsed)}/{duration} seconds")
                    
                    import time
                    time.sleep(1)
                    st.rerun()
                else:
                    st.success("Measurement complete! Processing results...")
                    
                    end_time = datetime.utcnow()
                    
                    for cp in cal_points:
                        positions = session.query(Position).filter(
                            Position.beacon_id == cp.beacon_id,
                            Position.floor_id == cp.floor_id,
                            Position.timestamp >= start_time,
                            Position.timestamp <= end_time
                        ).all()
                        
                        if positions:
                            avg_x = np.mean([p.x_position for p in positions])
                            avg_y = np.mean([p.y_position for p in positions])
                            
                            error = np.sqrt((avg_x - cp.known_x)**2 + (avg_y - cp.known_y)**2)
                            
                            cp.measured_x = avg_x
                            cp.measured_y = avg_y
                            cp.error_distance = error
                            cp.timestamp = datetime.utcnow()
                            cp.is_verified = True
                    
                    st.session_state['calibration_running'] = False
                    st.rerun()
            else:
                gateways = session.query(Gateway).filter(
                    Gateway.floor_id == selected_floor_id,
                    Gateway.is_active == True
                ).all()
                
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
                                opacity=0.6,
                                layer="below"
                            )
                        )
                    except Exception:
                        pass
                
                for gw in gateways:
                    fig.add_trace(go.Scatter(
                        x=[gw.x_position],
                        y=[gw.y_position],
                        mode='markers',
                        marker=dict(size=12, color='blue', symbol='square'),
                        name=f"Gateway: {gw.name}"
                    ))
                
                for cp in cal_points:
                    beacon = session.query(Beacon).filter(Beacon.id == cp.beacon_id).first()
                    
                    fig.add_trace(go.Scatter(
                        x=[cp.known_x],
                        y=[cp.known_y],
                        mode='markers+text',
                        marker=dict(size=15, color='green', symbol='diamond'),
                        text=[beacon.name if beacon else 'Unknown'],
                        textposition='top center',
                        name=f"Known: {beacon.name if beacon else 'Unknown'}"
                    ))
                    
                    if cp.measured_x is not None:
                        fig.add_trace(go.Scatter(
                            x=[cp.measured_x],
                            y=[cp.measured_y],
                            mode='markers',
                            marker=dict(size=12, color='red', symbol='x'),
                            name=f"Measured: {beacon.name if beacon else 'Unknown'}"
                        ))
                        
                        fig.add_shape(
                            type="line",
                            x0=cp.known_x, y0=cp.known_y,
                            x1=cp.measured_x, y1=cp.measured_y,
                            line=dict(color="red", width=2, dash="dash")
                        )
                
                fig.update_layout(
                    xaxis=dict(range=[0, floor.width_meters], title="X (meters)"),
                    yaxis=dict(range=[0, floor.height_meters], title="Y (meters)", scaleanchor="x"),
                    height=500,
                    showlegend=True,
                    title="Calibration Points Map"
                )
                
                st.plotly_chart(fig, use_container_width=True)


def render_accuracy_analysis():
    with get_db_session() as session:
        st.subheader("Accuracy Analysis & Recommendations")
        
        verified_points = session.query(CalibrationPoint).filter(
            CalibrationPoint.is_verified == True
        ).all()
        
        if not verified_points:
            st.info("No verified calibration measurements yet. Run calibration first.")
            return
        
        errors = [cp.error_distance for cp in verified_points if cp.error_distance]
        
        if not errors:
            st.warning("No error measurements available.")
            return
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Calibration Points", len(verified_points))
        
        with col2:
            avg_error = np.mean(errors)
            st.metric("Average Error", f"{avg_error:.2f} m")
        
        with col3:
            max_error = np.max(errors)
            st.metric("Max Error", f"{max_error:.2f} m")
        
        with col4:
            min_error = np.min(errors)
            st.metric("Min Error", f"{min_error:.2f} m")
        
        fig = go.Figure()
        
        beacon_names = []
        for cp in verified_points:
            beacon = session.query(Beacon).filter(Beacon.id == cp.beacon_id).first()
            beacon_names.append(beacon.name if beacon else f"Beacon {cp.beacon_id}")
        
        fig.add_trace(go.Bar(
            x=beacon_names,
            y=errors,
            marker_color=['green' if e < 2 else 'orange' if e < 5 else 'red' for e in errors]
        ))
        
        fig.update_layout(
            title="Error Distance by Calibration Point",
            xaxis_title="Calibration Point",
            yaxis_title="Error (meters)",
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("Calibration Recommendations")
        
        if avg_error > 5:
            st.error("High average error detected. Consider the following:")
            st.markdown("""
            - **Increase the number of gateways** - More gateways improve triangulation accuracy
            - **Adjust signal calibration values** - The TX power setting might be incorrect
            - **Check for signal interference** - Metal objects or walls can affect RSSI readings
            - **Increase path loss exponent** - Indoor environments typically need higher values (2.5-4.0)
            """)
        elif avg_error > 2:
            st.warning("Moderate accuracy. Improvements possible:")
            st.markdown("""
            - **Fine-tune path loss exponent** - Try values between 2.5 and 3.5
            - **Add more calibration points** - Better coverage improves overall accuracy
            - **Consider gateway placement** - Ensure good coverage without obstructions
            """)
        else:
            st.success("Good accuracy! Your system is well calibrated.")
            st.markdown("""
            - System is performing within acceptable parameters
            - Continue monitoring for any degradation over time
            - Consider adding more calibration points for even better accuracy
            """)
        
        st.markdown("---")
        st.subheader("Suggested Gateway Adjustments")
        
        gateways = session.query(Gateway).filter(Gateway.is_active == True).all()
        
        if gateways:
            for gw in gateways:
                with st.expander(f"Gateway: {gw.name}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Current Calibration:** {gw.signal_strength_calibration} dBm")
                        st.write(f"**Current Path Loss:** {gw.path_loss_exponent}")
                    
                    with col2:
                        new_calibration = st.number_input(
                            "Signal Calibration (dBm)",
                            value=float(gw.signal_strength_calibration),
                            min_value=-100.0,
                            max_value=0.0,
                            key=f"cal_{gw.id}"
                        )
                        
                        new_path_loss = st.number_input(
                            "Path Loss Exponent",
                            value=float(gw.path_loss_exponent),
                            min_value=1.0,
                            max_value=6.0,
                            step=0.1,
                            key=f"pl_{gw.id}"
                        )
                        
                        if st.button("Update", key=f"update_{gw.id}"):
                            gw.signal_strength_calibration = new_calibration
                            gw.path_loss_exponent = new_path_loss
                            st.success("Gateway updated!")
                            st.rerun()
