import streamlit as st
import plotly.graph_objects as go
import numpy as np
import json
import base64
from io import BytesIO
from database.models import (
    get_db_session, Building, Floor, Gateway, GatewayPlan, PlannedGateway
)


def calculate_recommended_gateways(floor_area: float, target_accuracy: float, signal_range: float = 15.0) -> dict:
    """Calculate recommended number of gateways based on floor area and target accuracy"""
    if target_accuracy <= 0.5:
        coverage_per_gateway = min(signal_range * 0.6, 8) ** 2 * np.pi * 0.3
        min_gateways = 4
        geometry_note = "Requires 4+ gateways in surrounding geometry with calibration"
    elif target_accuracy <= 1.0:
        coverage_per_gateway = min(signal_range * 0.7, 10) ** 2 * np.pi * 0.4
        min_gateways = 3
        geometry_note = "Requires 3+ gateways with good triangulation geometry"
    elif target_accuracy <= 2.0:
        coverage_per_gateway = min(signal_range * 0.8, 12) ** 2 * np.pi * 0.5
        min_gateways = 3
        geometry_note = "3+ gateways recommended for reliable 2D positioning"
    else:
        coverage_per_gateway = signal_range ** 2 * np.pi * 0.6
        min_gateways = 2
        geometry_note = "2+ gateways provide basic coverage"
    
    gateways_for_coverage = max(min_gateways, int(np.ceil(floor_area / coverage_per_gateway)))
    
    return {
        "recommended": gateways_for_coverage,
        "minimum": min_gateways,
        "coverage_radius": signal_range * (0.6 if target_accuracy <= 0.5 else 0.8),
        "geometry_note": geometry_note,
        "achievable": target_accuracy >= 0.5
    }


def evaluate_placement_quality(gateways: list, floor_width: float, floor_height: float, target_accuracy: float, signal_range: float = 15.0) -> dict:
    """Evaluate the quality of gateway placement"""
    if len(gateways) < 2:
        return {
            "score": 0,
            "status": "insufficient",
            "message": "At least 2 gateways required for any positioning",
            "coverage_percent": 0,
            "issues": ["Need minimum 2 gateways"]
        }
    
    positions = np.array([[g['x'], g['y']] for g in gateways])
    
    centroid = positions.mean(axis=0)
    floor_center = np.array([floor_width / 2, floor_height / 2])
    center_offset = np.linalg.norm(centroid - floor_center) / max(floor_width, floor_height)
    
    if len(gateways) >= 3:
        angles = []
        for i, pos in enumerate(positions):
            angle = np.arctan2(pos[1] - centroid[1], pos[0] - centroid[0])
            angles.append(angle)
        angles = sorted(angles)
        angle_gaps = []
        for i in range(len(angles)):
            gap = angles[(i + 1) % len(angles)] - angles[i]
            if gap < 0:
                gap += 2 * np.pi
            angle_gaps.append(gap)
        max_gap = max(angle_gaps)
        angular_distribution = 1.0 - (max_gap / (2 * np.pi))
    else:
        angular_distribution = 0.3
    
    distances = []
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            distances.append(np.linalg.norm(positions[i] - positions[j]))
    avg_distance = np.mean(distances)
    ideal_distance = max(floor_width, floor_height) * 0.4
    distance_score = 1.0 - min(1.0, abs(avg_distance - ideal_distance) / ideal_distance)
    
    grid_size = 1.0
    x_points = np.arange(0, floor_width, grid_size)
    y_points = np.arange(0, floor_height, grid_size)
    covered_points = 0
    total_points = len(x_points) * len(y_points)
    
    for x in x_points:
        for y in y_points:
            gateways_in_range = 0
            for pos in positions:
                dist = np.sqrt((x - pos[0])**2 + (y - pos[1])**2)
                if dist <= signal_range:
                    gateways_in_range += 1
            if target_accuracy <= 1.0:
                if gateways_in_range >= 3:
                    covered_points += 1
            else:
                if gateways_in_range >= 2:
                    covered_points += 1
    
    coverage_percent = (covered_points / total_points) * 100 if total_points > 0 else 0
    
    issues = []
    if len(gateways) < 3 and target_accuracy <= 2.0:
        issues.append(f"Need at least 3 gateways for {target_accuracy}m accuracy")
    if len(gateways) < 4 and target_accuracy <= 0.5:
        issues.append(f"Need 4+ calibrated gateways for sub-meter accuracy")
    if center_offset > 0.3:
        issues.append("Gateways are not centered over floor area")
    if angular_distribution < 0.6 and len(gateways) >= 3:
        issues.append("Gateways are clustered - spread them around the perimeter")
    if coverage_percent < 80:
        issues.append(f"Only {coverage_percent:.0f}% coverage - add more gateways")
    
    gateway_count_score = min(1.0, len(gateways) / (4 if target_accuracy <= 0.5 else 3))
    overall_score = (
        gateway_count_score * 0.3 +
        angular_distribution * 0.25 +
        distance_score * 0.2 +
        (coverage_percent / 100) * 0.25
    )
    
    if len(issues) == 0:
        status = "excellent"
        message = f"Placement meets requirements for ±{target_accuracy}m accuracy"
    elif overall_score >= 0.7:
        status = "good"
        message = "Placement is acceptable with minor improvements possible"
    elif overall_score >= 0.5:
        status = "fair"
        message = "Placement needs improvement for target accuracy"
    else:
        status = "poor"
        message = "Placement does not meet accuracy requirements"
    
    return {
        "score": overall_score,
        "status": status,
        "message": message,
        "coverage_percent": coverage_percent,
        "issues": issues,
        "details": {
            "gateway_count_score": gateway_count_score,
            "angular_distribution": angular_distribution,
            "distance_score": distance_score,
            "center_offset": center_offset
        }
    }


def suggest_gateway_positions(floor_width: float, floor_height: float, num_gateways: int, margin: float = 2.0) -> list:
    """Suggest optimal gateway positions for a rectangular floor"""
    suggestions = []
    
    fw = float(floor_width)
    fh = float(floor_height)
    m = float(margin)
    
    if num_gateways == 3:
        suggestions = [
            {"x": m, "y": m, "name": "GW-1 (Corner SW)"},
            {"x": fw - m, "y": m, "name": "GW-2 (Corner SE)"},
            {"x": fw / 2, "y": fh - m, "name": "GW-3 (Center N)"},
        ]
    elif num_gateways == 4:
        suggestions = [
            {"x": m, "y": m, "name": "GW-1 (Corner SW)"},
            {"x": fw - m, "y": m, "name": "GW-2 (Corner SE)"},
            {"x": fw - m, "y": fh - m, "name": "GW-3 (Corner NE)"},
            {"x": m, "y": fh - m, "name": "GW-4 (Corner NW)"},
        ]
    elif num_gateways == 5:
        suggestions = [
            {"x": m, "y": m, "name": "GW-1 (Corner SW)"},
            {"x": fw - m, "y": m, "name": "GW-2 (Corner SE)"},
            {"x": fw - m, "y": fh - m, "name": "GW-3 (Corner NE)"},
            {"x": m, "y": fh - m, "name": "GW-4 (Corner NW)"},
            {"x": fw / 2, "y": fh / 2, "name": "GW-5 (Center)"},
        ]
    elif num_gateways >= 6:
        suggestions = [
            {"x": m, "y": m, "name": "GW-1 (Corner SW)"},
            {"x": fw - m, "y": m, "name": "GW-2 (Corner SE)"},
            {"x": fw - m, "y": fh - m, "name": "GW-3 (Corner NE)"},
            {"x": m, "y": fh - m, "name": "GW-4 (Corner NW)"},
            {"x": fw / 2, "y": m, "name": "GW-5 (Mid S)"},
            {"x": fw / 2, "y": fh - m, "name": "GW-6 (Mid N)"},
        ]
        for i in range(6, num_gateways):
            angle = (i - 6) * 2 * np.pi / max(1, (num_gateways - 6))
            radius = min(fw, fh) * 0.3
            x = float(fw / 2 + radius * np.cos(angle))
            y = float(fh / 2 + radius * np.sin(angle))
            suggestions.append({"x": round(x, 2), "y": round(y, 2), "name": f"GW-{i+1}"})
    else:
        for i in range(num_gateways):
            angle = i * 2 * np.pi / max(1, num_gateways)
            radius = min(fw, fh) * 0.35
            x = float(fw / 2 + radius * np.cos(angle))
            y = float(fh / 2 + radius * np.sin(angle))
            suggestions.append({"x": round(x, 2), "y": round(y, 2), "name": f"GW-{i+1}"})
    
    return suggestions


def render_gateway_planning():
    """Render the gateway planning interface"""
    st.header("Gateway Planning")
    st.markdown("Plan optimal gateway placement before physical installation to achieve your target accuracy.")
    
    with get_db_session() as session:
        buildings = session.query(Building).all()
        
        if not buildings:
            st.warning("Please add a building with floor plans first in the Buildings section.")
            return
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Plan Configuration")
            
            building_options = {b.id: b.name for b in buildings}
            selected_building_id = st.selectbox(
                "Select Building",
                options=list(building_options.keys()),
                format_func=lambda x: building_options[x],
                key="plan_building"
            )
            
            selected_building = session.query(Building).filter(Building.id == selected_building_id).first()
            floors = selected_building.floors if selected_building else []
            
            if not floors:
                st.warning("No floors defined for this building. Please add floor plans first.")
                return
            
            floor_options = {f.id: f"{f.name or f'Floor {f.floor_number}'}" for f in floors}
            selected_floor_id = st.selectbox(
                "Select Floor",
                options=list(floor_options.keys()),
                format_func=lambda x: floor_options[x],
                key="plan_floor"
            )
            
            selected_floor = session.query(Floor).filter(Floor.id == selected_floor_id).first()
            
            st.divider()
            
            st.markdown("**Target Accuracy**")
            target_accuracy = st.select_slider(
                "Desired positioning accuracy",
                options=[0.5, 1.0, 2.0, 3.0, 5.0],
                value=1.0,
                format_func=lambda x: f"±{x}m",
                key="target_accuracy"
            )
            
            if target_accuracy <= 0.5:
                st.info("Sub-meter accuracy requires 4+ calibrated gateways with optimal geometry, or consider UWB technology.")
            elif target_accuracy <= 1.0:
                st.info("1-meter accuracy requires 3+ gateways with good triangulation geometry.")
            
            signal_range = st.slider(
                "Expected signal range (meters)",
                min_value=5.0,
                max_value=30.0,
                value=15.0,
                step=1.0,
                help="Typical BLE range is 10-20m indoors depending on environment"
            )
            
            floor_area = selected_floor.width_meters * selected_floor.height_meters
            recommendations = calculate_recommended_gateways(floor_area, target_accuracy, signal_range)
            
            st.divider()
            st.markdown("**Recommendations**")
            st.metric("Recommended Gateways", recommendations["recommended"])
            st.caption(recommendations["geometry_note"])
            
            if not recommendations["achievable"]:
                st.warning("Sub-0.5m accuracy is at the limit of BLE technology. Consider UWB for better results.")
            
            st.divider()
            
            existing_plans = session.query(GatewayPlan).filter(
                GatewayPlan.floor_id == selected_floor_id
            ).all()
            
            plan_options = {"new": "Create New Plan"}
            for plan in existing_plans:
                plan_options[plan.id] = f"{plan.name} (±{plan.target_accuracy}m)"
            
            selected_plan_key = st.selectbox(
                "Gateway Plan",
                options=list(plan_options.keys()),
                format_func=lambda x: plan_options[x],
                key="selected_plan"
            )
            
            if selected_plan_key == "new":
                plan_name = st.text_input("Plan Name", value=f"Plan for {floor_options[selected_floor_id]}")
                if st.button("Create Plan", type="primary"):
                    new_plan = GatewayPlan(
                        floor_id=selected_floor_id,
                        name=plan_name,
                        target_accuracy=target_accuracy,
                        signal_range=signal_range
                    )
                    session.add(new_plan)
                    session.commit()
                    st.success(f"Created plan: {plan_name}")
                    st.rerun()
                current_plan = None
            else:
                current_plan = session.query(GatewayPlan).filter(GatewayPlan.id == selected_plan_key).first()
                
                if current_plan:
                    st.caption(f"Plan configuration: ±{current_plan.target_accuracy}m accuracy, {current_plan.signal_range}m signal range")
                    if st.button("Delete Plan", type="secondary"):
                        session.delete(current_plan)
                        session.commit()
                        st.success("Plan deleted")
                        st.rerun()
        
        with col2:
            st.subheader("Floor Plan & Gateway Placement")
            
            if selected_floor:
                effective_target_accuracy = current_plan.target_accuracy if current_plan and current_plan.target_accuracy else target_accuracy
                effective_signal_range = current_plan.signal_range if current_plan and current_plan.signal_range else signal_range
                
                floor_area = selected_floor.width_meters * selected_floor.height_meters
                effective_recommendations = calculate_recommended_gateways(floor_area, effective_target_accuracy, effective_signal_range)
                
                fig = go.Figure()
                
                floor_width = selected_floor.width_meters
                floor_height = selected_floor.height_meters
                
                if selected_floor.floor_plan_image:
                    try:
                        img_base64 = base64.b64encode(selected_floor.floor_plan_image).decode()
                        img_src = f"data:image/{selected_floor.floor_plan_filename.split('.')[-1] if selected_floor.floor_plan_filename else 'png'};base64,{img_base64}"
                        
                        fig.add_layout_image(
                            dict(
                                source=img_src,
                                xref="x",
                                yref="y",
                                x=0,
                                y=floor_height,
                                sizex=floor_width,
                                sizey=floor_height,
                                sizing="stretch",
                                opacity=0.7,
                                layer="below"
                            )
                        )
                    except Exception:
                        pass
                elif selected_floor.floor_plan_geojson:
                    try:
                        geojson_data = json.loads(selected_floor.floor_plan_geojson)
                        if 'features' in geojson_data:
                            for feature in geojson_data['features']:
                                if feature['geometry']['type'] == 'Polygon':
                                    coords = feature['geometry']['coordinates'][0]
                                    x_coords = [c[0] for c in coords]
                                    y_coords = [c[1] for c in coords]
                                    fig.add_trace(go.Scatter(
                                        x=x_coords,
                                        y=y_coords,
                                        mode='lines',
                                        line=dict(color='#666666', width=1),
                                        fill='toself',
                                        fillcolor='rgba(200,200,200,0.3)',
                                        showlegend=False,
                                        hoverinfo='skip'
                                    ))
                                elif feature['geometry']['type'] == 'LineString':
                                    coords = feature['geometry']['coordinates']
                                    x_coords = [c[0] for c in coords]
                                    y_coords = [c[1] for c in coords]
                                    fig.add_trace(go.Scatter(
                                        x=x_coords,
                                        y=y_coords,
                                        mode='lines',
                                        line=dict(color='#444444', width=1),
                                        showlegend=False,
                                        hoverinfo='skip'
                                    ))
                    except Exception:
                        pass
                
                fig.add_shape(
                    type="rect",
                    x0=0, y0=0,
                    x1=floor_width, y1=floor_height,
                    line=dict(color="#2e5cbf", width=2),
                    fillcolor="rgba(46, 92, 191, 0.05)"
                )
                
                planned_gateways = []
                if current_plan:
                    db_planned_gateways = session.query(PlannedGateway).filter(
                        PlannedGateway.plan_id == current_plan.id
                    ).order_by(PlannedGateway.id).all()
                    for pg in db_planned_gateways:
                        planned_gateways.append({
                            'id': pg.id,
                            'name': pg.name,
                            'x': pg.x_position,
                            'y': pg.y_position,
                            'is_installed': pg.is_installed
                        })
                
                for gw in planned_gateways:
                    theta = np.linspace(0, 2*np.pi, 50)
                    r = effective_signal_range
                    x_circle = gw['x'] + r * np.cos(theta)
                    y_circle = gw['y'] + r * np.sin(theta)
                    
                    color = 'rgba(0, 142, 211, 0.15)' if not gw['is_installed'] else 'rgba(46, 191, 92, 0.15)'
                    
                    fig.add_trace(go.Scatter(
                        x=x_circle.tolist(),
                        y=y_circle.tolist(),
                        mode='lines',
                        line=dict(color='#008ed3' if not gw['is_installed'] else '#2ebf5c', width=1, dash='dot'),
                        fill='toself',
                        fillcolor=color,
                        name=f"{gw['name']} coverage",
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                
                if planned_gateways:
                    fig.add_trace(go.Scatter(
                        x=[gw['x'] for gw in planned_gateways if not gw['is_installed']],
                        y=[gw['y'] for gw in planned_gateways if not gw['is_installed']],
                        mode='markers+text',
                        marker=dict(size=20, color='#008ed3', symbol='diamond'),
                        text=[gw['name'] for gw in planned_gateways if not gw['is_installed']],
                        textposition='top center',
                        textfont=dict(size=10),
                        name='Planned Gateways',
                        hovertemplate='<b>%{text}</b><br>Position: (%{x:.1f}m, %{y:.1f}m)<extra></extra>'
                    ))
                    
                    installed = [gw for gw in planned_gateways if gw['is_installed']]
                    if installed:
                        fig.add_trace(go.Scatter(
                            x=[gw['x'] for gw in installed],
                            y=[gw['y'] for gw in installed],
                            mode='markers+text',
                            marker=dict(size=20, color='#2ebf5c', symbol='diamond'),
                            text=[gw['name'] for gw in installed],
                            textposition='top center',
                            textfont=dict(size=10),
                            name='Installed Gateways',
                            hovertemplate='<b>%{text}</b><br>Position: (%{x:.1f}m, %{y:.1f}m)<br>INSTALLED<extra></extra>'
                        ))
                
                existing_gateways = session.query(Gateway).filter(
                    Gateway.floor_id == selected_floor_id,
                    Gateway.is_active == True
                ).all()
                
                if existing_gateways:
                    fig.add_trace(go.Scatter(
                        x=[gw.x_position for gw in existing_gateways],
                        y=[gw.y_position for gw in existing_gateways],
                        mode='markers+text',
                        marker=dict(size=16, color='#ff6b35', symbol='square'),
                        text=[gw.name for gw in existing_gateways],
                        textposition='top center',
                        textfont=dict(size=9),
                        name='Active Gateways',
                        hovertemplate='<b>%{text}</b><br>Position: (%{x:.1f}m, %{y:.1f}m)<br>ACTIVE<extra></extra>'
                    ))
                
                fig.update_layout(
                    height=600,
                    xaxis=dict(
                        title="X (meters)",
                        range=[-2, floor_width + 2],
                        scaleanchor="y",
                        scaleratio=1,
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)'
                    ),
                    yaxis=dict(
                        title="Y (meters)",
                        range=[-2, floor_height + 2],
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)'
                    ),
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    margin=dict(l=50, r=50, t=50, b=50),
                    plot_bgcolor='white'
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                if current_plan:
                    quality = evaluate_placement_quality(
                        planned_gateways, floor_width, floor_height, 
                        effective_target_accuracy, effective_signal_range
                    )
                    
                    status_colors = {
                        "excellent": "green",
                        "good": "blue", 
                        "fair": "orange",
                        "poor": "red",
                        "insufficient": "red"
                    }
                    
                    col_q1, col_q2, col_q3 = st.columns(3)
                    with col_q1:
                        st.metric("Placement Score", f"{quality['score']*100:.0f}%")
                    with col_q2:
                        st.metric("Coverage", f"{quality['coverage_percent']:.0f}%")
                    with col_q3:
                        color = status_colors.get(quality['status'], 'gray')
                        st.markdown(f"**Status:** :{color}[{quality['status'].upper()}]")
                    
                    if quality['issues']:
                        with st.expander("Placement Issues", expanded=True):
                            for issue in quality['issues']:
                                st.warning(issue)
                    else:
                        st.success(quality['message'])
        
        if current_plan:
            st.divider()
            st.subheader("Manage Planned Gateways")
            
            col_add1, col_add2, col_add3, col_add4 = st.columns([2, 1, 1, 1])
            
            with col_add1:
                new_gw_name = st.text_input("Gateway Name", value=f"GW-{len(planned_gateways)+1}", key="new_gw_name")
            with col_add2:
                new_gw_x = st.number_input("X Position (m)", min_value=0.0, max_value=floor_width, value=floor_width/2, key="new_gw_x")
            with col_add3:
                new_gw_y = st.number_input("Y Position (m)", min_value=0.0, max_value=floor_height, value=floor_height/2, key="new_gw_y")
            with col_add4:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Add Gateway", type="primary", key="add_gw"):
                    new_planned_gw = PlannedGateway(
                        plan_id=current_plan.id,
                        name=new_gw_name,
                        x_position=float(new_gw_x),
                        y_position=float(new_gw_y)
                    )
                    session.add(new_planned_gw)
                    session.commit()
                    st.success(f"Added {new_gw_name}")
                    st.rerun()
            
            suggestions = suggest_gateway_positions(floor_width, floor_height, effective_recommendations["recommended"])
            if st.button(f"Auto-suggest {effective_recommendations['recommended']} gateway positions"):
                existing_gws = session.query(PlannedGateway).filter(
                    PlannedGateway.plan_id == current_plan.id
                ).all()
                added_count = 0
                for suggestion in suggestions:
                    exists = any(
                        abs(pg.x_position - float(suggestion['x'])) < 1 and abs(pg.y_position - float(suggestion['y'])) < 1
                        for pg in existing_gws
                    )
                    if not exists:
                        new_planned_gw = PlannedGateway(
                            plan_id=current_plan.id,
                            name=suggestion['name'],
                            x_position=float(suggestion['x']),
                            y_position=float(suggestion['y'])
                        )
                        session.add(new_planned_gw)
                        added_count += 1
                session.commit()
                st.success(f"Added {added_count} suggested gateway positions")
                st.rerun()
            
            if planned_gateways:
                st.markdown("**Current Planned Gateways**")
                
                for gw in planned_gateways:
                    with st.container():
                        cols = st.columns([3, 2, 2, 1, 1])
                        with cols[0]:
                            st.markdown(f"**{gw['name']}**")
                        with cols[1]:
                            st.caption(f"X: {gw['x']:.1f}m")
                        with cols[2]:
                            st.caption(f"Y: {gw['y']:.1f}m")
                        with cols[3]:
                            if gw['is_installed']:
                                st.markdown(":green[Installed]")
                            else:
                                st.markdown(":blue[Planned]")
                        with cols[4]:
                            if st.button("Delete", key=f"del_gw_{gw['id']}"):
                                pg = session.query(PlannedGateway).filter(PlannedGateway.id == gw['id']).first()
                                if pg:
                                    session.delete(pg)
                                    session.commit()
                                    st.rerun()
            
            st.divider()
            st.subheader("Export Plan")
            
            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                if st.button("Export as Installation Guide"):
                    export_gateways = session.query(PlannedGateway).filter(
                        PlannedGateway.plan_id == current_plan.id
                    ).order_by(PlannedGateway.id).all()
                    guide_text = f"""# Gateway Installation Guide
## {current_plan.name}
### Floor: {floor_options[selected_floor_id]}
### Target Accuracy: ±{current_plan.target_accuracy}m

## Planned Gateway Positions

| Gateway | X Position | Y Position | Notes |
|---------|------------|------------|-------|
"""
                    for pg in export_gateways:
                        guide_text += f"| {pg.name} | {pg.x_position:.1f}m | {pg.y_position:.1f}m | {pg.notes or ''} |\n"
                    
                    guide_text += f"""
## Installation Notes

1. Position each gateway as close to the planned coordinates as possible
2. Ensure line-of-sight between gateways where possible
3. Mount gateways at 2-3 meters height for optimal coverage
4. Avoid placing near metal objects or water pipes
5. After installation, use the Calibration Wizard to fine-tune accuracy

## Coverage Requirements

- Signal Range: {current_plan.signal_range}m
- Minimum {effective_recommendations['minimum']} gateways required
- {effective_recommendations['geometry_note']}
"""
                    
                    st.download_button(
                        "Download Installation Guide",
                        guide_text,
                        file_name=f"gateway_installation_guide_{current_plan.name.replace(' ', '_')}.md",
                        mime="text/markdown"
                    )
            
            with col_exp2:
                if st.button("Export as JSON"):
                    json_export_gateways = session.query(PlannedGateway).filter(
                        PlannedGateway.plan_id == current_plan.id
                    ).order_by(PlannedGateway.id).all()
                    export_data = {
                        "plan_name": current_plan.name,
                        "floor": floor_options[selected_floor_id],
                        "floor_dimensions": {
                            "width_m": float(floor_width),
                            "height_m": float(floor_height)
                        },
                        "target_accuracy_m": float(current_plan.target_accuracy),
                        "signal_range_m": float(current_plan.signal_range),
                        "gateways": [
                            {
                                "name": pg.name,
                                "x_m": float(pg.x_position),
                                "y_m": float(pg.y_position),
                                "is_installed": pg.is_installed
                            }
                            for pg in json_export_gateways
                        ]
                    }
                    
                    st.download_button(
                        "Download JSON",
                        json.dumps(export_data, indent=2),
                        file_name=f"gateway_plan_{current_plan.name.replace(' ', '_')}.json",
                        mime="application/json"
                    )
