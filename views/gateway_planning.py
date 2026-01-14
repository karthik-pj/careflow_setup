import streamlit as st
import plotly.graph_objects as go
import numpy as np
import json
import base64
import math
from io import BytesIO
from PIL import Image
from database.models import (
    get_db_session, Building, Floor, Gateway, GatewayPlan, PlannedGateway, CoverageZone
)


def latlon_to_meters(lat, lon, origin_lat, origin_lon):
    """Convert lat/lon to local meter coordinates using equirectangular projection"""
    dx = (lon - origin_lon) * math.cos(math.radians(origin_lat)) * 111000
    dy = (lat - origin_lat) * 111000
    return dx, dy


def render_dxf_floor_plan(fig, floor):
    """Render DXF floor plan (stored as GeoJSON) in local meter coordinates"""
    if not floor.floor_plan_geojson:
        return False
    
    try:
        geojson_data = json.loads(floor.floor_plan_geojson)
        
        for feature in geojson_data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            geom_type = props.get('geomType', '')
            
            if geom.get('type') == 'Polygon':
                coords = geom.get('coordinates', [[]])[0]
                if coords:
                    xs = [c[0] for c in coords]
                    ys = [c[1] for c in coords]
                    
                    name = props.get('name', 'Unnamed')
                    
                    if geom_type == 'room':
                        fill_color = 'rgba(46, 92, 191, 0.15)'
                        line_color = '#2e5cbf'
                    else:
                        fill_color = 'rgba(200, 200, 200, 0.1)'
                        line_color = '#666'
                    
                    fig.add_trace(go.Scatter(
                        x=xs,
                        y=ys,
                        fill='toself',
                        fillcolor=fill_color,
                        line=dict(color=line_color, width=1),
                        name=name,
                        hovertemplate=f"<b>{name}</b><extra></extra>",
                        mode='lines',
                        showlegend=False
                    ))
            
            elif geom.get('type') == 'LineString':
                coords = geom.get('coordinates', [])
                if coords:
                    xs = [c[0] for c in coords]
                    ys = [c[1] for c in coords]
                    
                    if geom_type == 'wall':
                        line_width = 2
                        line_color = '#333'
                    else:
                        line_width = 1
                        line_color = '#666'
                    
                    fig.add_trace(go.Scatter(
                        x=xs,
                        y=ys,
                        mode='lines',
                        line=dict(color=line_color, width=line_width),
                        showlegend=False,
                        hoverinfo='skip'
                    ))
        
        return True
    except Exception as e:
        return False


def render_polygon_ring(fig, ring_coords, floor, props, is_building=False):
    """Render a single polygon ring (exterior or interior)"""
    if not ring_coords:
        return
    
    xs = []
    ys = []
    for c in ring_coords:
        if len(c) >= 2:
            lon, lat = c[0], c[1]
            x, y = latlon_to_meters(lat, lon, floor.origin_lat, floor.origin_lon)
            xs.append(x)
            ys.append(y)
    
    if not xs:
        return
    
    name = props.get('name', '')
    geom_type = props.get('geomType', '')
    
    if geom_type == 'room':
        fill_color = 'rgba(46, 92, 191, 0.15)'
        line_color = '#2e5cbf'
        line_width = 1
    elif geom_type == 'building':
        fill_color = 'rgba(200, 200, 200, 0.1)'
        line_color = '#444'
        line_width = 2
    else:
        fill_color = 'rgba(150, 150, 150, 0.1)'
        line_color = '#666'
        line_width = 1
    
    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        fill='toself',
        fillcolor=fill_color,
        line=dict(color=line_color, width=line_width),
        name=name if name else geom_type,
        hovertemplate=f"<b>{name or geom_type}</b><extra></extra>",
        mode='lines',
        showlegend=False
    ))
    
    if name and geom_type == 'room':
        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)
        fig.add_annotation(
            x=center_x,
            y=center_y,
            text=name[:12],
            showarrow=False,
            font=dict(size=8, color='#1a1a1a')
        )


def render_geojson_floor_plan(fig, floor):
    """Render GeoJSON floor plan as Plotly traces in meter coordinates.
    
    Handles all geometry types: Point, LineString, Polygon, MultiPolygon, etc.
    """
    if not floor.floor_plan_geojson or not floor.origin_lat or not floor.origin_lon:
        return False
    
    try:
        geojson_data = json.loads(floor.floor_plan_geojson)
        rendered_any = False
        
        for feature in geojson_data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            geometry_type = geom.get('type', '')
            geom_type = props.get('geomType', '')
            
            if geometry_type == 'Polygon':
                rings = geom.get('coordinates', [])
                if rings:
                    render_polygon_ring(fig, rings[0], floor, props)
                    rendered_any = True
            
            elif geometry_type == 'MultiPolygon':
                polygons = geom.get('coordinates', [])
                for polygon in polygons:
                    if polygon:
                        render_polygon_ring(fig, polygon[0], floor, props, is_building=True)
                        rendered_any = True
            
            elif geometry_type == 'LineString':
                coords = geom.get('coordinates', [])
                if coords:
                    xs = []
                    ys = []
                    for c in coords:
                        if len(c) >= 2:
                            lon, lat = c[0], c[1]
                            x, y = latlon_to_meters(lat, lon, floor.origin_lat, floor.origin_lon)
                            xs.append(x)
                            ys.append(y)
                    
                    if xs:
                        wall_type = props.get('subType', 'inner')
                        line_width = 2 if wall_type == 'outer' or geom_type == 'wall' else 1
                        
                        fig.add_trace(go.Scatter(
                            x=xs,
                            y=ys,
                            mode='lines',
                            line=dict(color='#333', width=line_width),
                            showlegend=False,
                            hoverinfo='skip'
                        ))
                        rendered_any = True
            
            elif geometry_type == 'MultiLineString':
                lines = geom.get('coordinates', [])
                for line_coords in lines:
                    if line_coords:
                        xs = []
                        ys = []
                        for c in line_coords:
                            if len(c) >= 2:
                                lon, lat = c[0], c[1]
                                x, y = latlon_to_meters(lat, lon, floor.origin_lat, floor.origin_lon)
                                xs.append(x)
                                ys.append(y)
                        
                        if xs:
                            fig.add_trace(go.Scatter(
                                x=xs,
                                y=ys,
                                mode='lines',
                                line=dict(color='#333', width=1),
                                showlegend=False,
                                hoverinfo='skip'
                            ))
                            rendered_any = True
        
        return rendered_any
    except Exception as e:
        return False


def create_floor_plan_figure(floor):
    """Create base figure with floor plan image or GeoJSON/DXF if available"""
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
    
    if not has_floor_plan and floor.floor_plan_type == 'dxf' and floor.floor_plan_geojson:
        has_floor_plan = render_dxf_floor_plan(fig, floor)
    
    if not has_floor_plan and floor.floor_plan_geojson:
        has_floor_plan = render_geojson_floor_plan(fig, floor)
    
    return fig, has_floor_plan


def calculate_recommended_gateways(floor_area: float, target_accuracy: float, signal_range: float = 15.0, floor=None) -> dict:
    """Calculate recommended number of gateways based on floor area and target accuracy.
    
    Optimizes for minimum gateways while ensuring overlapping coverage for triangulation.
    For perimeter placement, gateways only need to cover inward, reducing the count needed.
    """
    if floor:
        bounds = extract_building_bounds(floor)
        actual_area = bounds['width'] * bounds['height']
        actual_width = bounds['width']
        actual_height = bounds['height']
    else:
        actual_area = floor_area
        actual_width = np.sqrt(floor_area)
        actual_height = np.sqrt(floor_area)
    
    effective_range = signal_range * 0.8
    
    if target_accuracy <= 0.5:
        min_gateways = 4
        overlap_factor = 0.5
        geometry_note = "4 gateways in corners provide surrounding geometry for sub-meter accuracy"
    elif target_accuracy <= 1.0:
        min_gateways = 3
        overlap_factor = 0.6
        geometry_note = "3 gateways in triangle formation for meter-level accuracy"
    elif target_accuracy <= 2.0:
        min_gateways = 3
        overlap_factor = 0.7
        geometry_note = "3 gateways for reliable 2D positioning"
    else:
        min_gateways = 2
        overlap_factor = 0.8
        geometry_note = "2 gateways for basic zone-level coverage"
    
    coverage_diameter = effective_range * 2 * overlap_factor
    
    gw_along_width = max(2, int(np.ceil(actual_width / coverage_diameter)))
    gw_along_height = max(2, int(np.ceil(actual_height / coverage_diameter)))
    
    if actual_width <= coverage_diameter * 1.5 and actual_height <= coverage_diameter * 1.5:
        gateways_for_coverage = min_gateways
    elif actual_width <= coverage_diameter * 2 and actual_height <= coverage_diameter * 2:
        gateways_for_coverage = max(min_gateways, 4)
    else:
        perimeter_gateways = 2 * (gw_along_width + gw_along_height) - 4
        gateways_for_coverage = max(min_gateways, perimeter_gateways)
    
    if gateways_for_coverage > 12:
        geometry_note = f"{gateways_for_coverage} gateways needed for full coverage - consider zone-based approach"
    
    return {
        "recommended": gateways_for_coverage,
        "minimum": min_gateways,
        "coverage_radius": effective_range,
        "geometry_note": geometry_note,
        "achievable": target_accuracy >= 0.5,
        "actual_building_area": actual_area
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


def coords_look_like_latlon(all_coords, floor=None):
    """Detect if coordinates are lat/lon (degrees) vs meters.
    
    Decision logic:
    1. If floor_plan_type is 'dxf', coordinates are in meters
    2. If floor has origin_lat/origin_lon AND floor_plan_type is 'geojson', likely lat/lon
    3. Otherwise, check coordinate ranges (lat/lon has much smaller range than meters)
    """
    if not all_coords:
        return False
    
    if floor:
        if floor.floor_plan_type == 'dxf':
            return False
        if floor.floor_plan_type == 'geojson' and floor.origin_lat and floor.origin_lon:
            return True
    
    xs = [c[0] for c in all_coords if len(c) >= 2]
    ys = [c[1] for c in all_coords if len(c) >= 2]
    
    if not xs or not ys:
        return False
    
    x_range = max(xs) - min(xs)
    y_range = max(ys) - min(ys)
    
    if x_range < 1 and y_range < 1:
        all_x_in_lon_range = all(-180 <= x <= 180 for x in xs)
        all_y_in_lat_range = all(-90 <= y <= 90 for y in ys)
        if all_x_in_lon_range and all_y_in_lat_range:
            return True
    
    return False


def extract_coords_from_geometry(geom):
    """Extract all coordinates from a GeoJSON geometry, handling all types."""
    coords = []
    geom_type = geom.get('type', '')
    
    if geom_type == 'Point':
        coords.append(geom.get('coordinates', []))
    elif geom_type == 'LineString':
        coords.extend(geom.get('coordinates', []))
    elif geom_type == 'Polygon':
        for ring in geom.get('coordinates', []):
            coords.extend(ring)
    elif geom_type == 'MultiPoint':
        coords.extend(geom.get('coordinates', []))
    elif geom_type == 'MultiLineString':
        for line in geom.get('coordinates', []):
            coords.extend(line)
    elif geom_type == 'MultiPolygon':
        for polygon in geom.get('coordinates', []):
            for ring in polygon:
                coords.extend(ring)
    
    return coords


def extract_building_bounds(floor):
    """Extract actual building boundaries from floor plan geometry.
    
    Handles:
    - DXF plans: coordinates already in meters
    - GeoJSON lat/lon: converted to meters using floor origin (detected by small ranges)
    - GeoJSON meters: used directly (detected by large ranges)
    - All geometry types: Point, LineString, Polygon, MultiPolygon, etc.
    """
    min_x, max_x, min_y, max_y = None, None, None, None
    
    if floor.floor_plan_geojson:
        try:
            geojson_data = json.loads(floor.floor_plan_geojson)
            all_coords = []
            
            for feature in geojson_data.get('features', []):
                geom = feature.get('geometry', {})
                feature_coords = extract_coords_from_geometry(geom)
                all_coords.extend(feature_coords)
            
            if all_coords:
                is_latlon = coords_look_like_latlon(all_coords, floor)
                has_origin = floor.origin_lat is not None and floor.origin_lon is not None
                
                if is_latlon and has_origin:
                    xs = []
                    ys = []
                    for c in all_coords:
                        if len(c) >= 2:
                            lon, lat = c[0], c[1]
                            x, y = latlon_to_meters(lat, lon, floor.origin_lat, floor.origin_lon)
                            xs.append(x)
                            ys.append(y)
                else:
                    xs = [c[0] for c in all_coords if len(c) >= 2]
                    ys = [c[1] for c in all_coords if len(c) >= 2]
                
                if xs and ys:
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)
        except Exception:
            pass
    
    width = (max_x - min_x) if min_x is not None else 0
    height = (max_y - min_y) if min_y is not None else 0
    
    if min_x is None or width < 5 or height < 5:
        min_x, max_x = 0, floor.width_meters
        min_y, max_y = 0, floor.height_meters
    
    return {
        'min_x': min_x, 'max_x': max_x,
        'min_y': min_y, 'max_y': max_y,
        'width': max_x - min_x,
        'height': max_y - min_y,
        'center_x': (min_x + max_x) / 2,
        'center_y': (min_y + max_y) / 2
    }


def point_in_polygon(x, y, polygon):
    """Ray casting algorithm to check if point is inside polygon.
    
    Args:
        x, y: Point coordinates
        polygon: List of [x, y] coordinates forming the polygon
    
    Returns:
        True if point is inside polygon
    """
    n = len(polygon)
    inside = False
    
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]
        
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    
    return inside


def get_coverage_zone_bounds(zone):
    """Extract bounds from a coverage zone polygon"""
    try:
        coords = json.loads(zone.polygon_coords)
        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            return {
                'min_x': min(xs), 'max_x': max(xs),
                'min_y': min(ys), 'max_y': max(ys),
                'width': max(xs) - min(xs),
                'height': max(ys) - min(ys),
                'center_x': (min(xs) + max(xs)) / 2,
                'center_y': (min(ys) + max(ys)) / 2,
                'polygon': coords
            }
    except Exception:
        pass
    return None


def calculate_gateways_for_zone(zone):
    """Calculate how many gateways are needed for a coverage zone based on its target accuracy."""
    bounds = get_coverage_zone_bounds(zone)
    if not bounds:
        return 3  # Default
    
    zone_area = bounds['width'] * bounds['height']
    target_accuracy = zone.target_accuracy or 1.0
    
    # Use same logic as calculate_recommended_gateways
    if target_accuracy <= 0.5:
        min_gateways = 4
    elif target_accuracy <= 1.0:
        min_gateways = 3
    elif target_accuracy <= 2.0:
        min_gateways = 3
    else:
        min_gateways = 2
    
    # For small zones, fewer gateways may suffice
    if zone_area < 50:  # Small zone < 50 sq meters
        return max(2, min_gateways - 1)
    elif zone_area < 200:  # Medium zone
        return min_gateways
    else:  # Large zone
        # Add more gateways for larger areas
        extra = int(zone_area / 200)
        return min(min_gateways + extra, 8)


def suggest_gateway_positions_for_zone(zone_bounds, num_gateways, signal_range=15.0):
    """Suggest gateway positions within a coverage zone polygon."""
    suggestions = []
    
    bx_min, bx_max = zone_bounds['min_x'], zone_bounds['max_x']
    by_min, by_max = zone_bounds['min_y'], zone_bounds['max_y']
    bw = zone_bounds['width']
    bh = zone_bounds['height']
    cx, cy = zone_bounds['center_x'], zone_bounds['center_y']
    polygon = zone_bounds.get('polygon', [])
    
    wall_offset = 1.5
    
    if num_gateways <= 2:
        candidates = [
            {"x": bx_min + wall_offset, "y": cy, "name": "GW-1 (West)"},
            {"x": bx_max - wall_offset, "y": cy, "name": "GW-2 (East)"},
        ]
    elif num_gateways == 3:
        candidates = [
            {"x": bx_min + wall_offset, "y": by_min + bh * 0.3, "name": "GW-1 (SW)"},
            {"x": bx_max - wall_offset, "y": by_min + bh * 0.3, "name": "GW-2 (SE)"},
            {"x": cx, "y": by_max - wall_offset, "name": "GW-3 (N)"},
        ]
    elif num_gateways == 4:
        candidates = [
            {"x": bx_min + wall_offset, "y": by_min + wall_offset, "name": "GW-1 (SW)"},
            {"x": bx_max - wall_offset, "y": by_min + wall_offset, "name": "GW-2 (SE)"},
            {"x": bx_max - wall_offset, "y": by_max - wall_offset, "name": "GW-3 (NE)"},
            {"x": bx_min + wall_offset, "y": by_max - wall_offset, "name": "GW-4 (NW)"},
        ]
    else:
        candidates = []
        perimeter = 2 * (bw + bh)
        spacing = perimeter / num_gateways
        current_dist = spacing / 2
        gw_num = 1
        
        sides = [
            ('S', bx_min, by_min + wall_offset, bx_max, by_min + wall_offset, bw),
            ('E', bx_max - wall_offset, by_min, bx_max - wall_offset, by_max, bh),
            ('N', bx_max, by_max - wall_offset, bx_min, by_max - wall_offset, bw),
            ('W', bx_min + wall_offset, by_max, bx_min + wall_offset, by_min, bh),
        ]
        
        cumulative = 0
        for side_name, x1, y1, x2, y2, length in sides:
            while current_dist < cumulative + length and gw_num <= num_gateways:
                t = (current_dist - cumulative) / length
                x = x1 + t * (x2 - x1)
                y = y1 + t * (y2 - y1)
                candidates.append({"x": x, "y": y, "name": f"GW-{gw_num} ({side_name})"})
                gw_num += 1
                current_dist += spacing
            cumulative += length
    
    for c in candidates:
        if polygon:
            if point_in_polygon(c['x'], c['y'], polygon):
                suggestions.append({
                    "x": round(float(c['x']), 2),
                    "y": round(float(c['y']), 2),
                    "name": c['name']
                })
            else:
                suggestions.append({
                    "x": round(float(cx), 2),
                    "y": round(float(cy), 2),
                    "name": c['name'] + " (adjusted)"
                })
        else:
            suggestions.append({
                "x": round(float(c['x']), 2),
                "y": round(float(c['y']), 2),
                "name": c['name']
            })
    
    return suggestions


def suggest_gateway_positions(floor_width: float, floor_height: float, num_gateways: int, 
                              signal_range: float = 15.0, floor=None) -> list:
    """Suggest optimal gateway positions inside the actual building footprint.
    
    Places gateways along the building perimeter (near walls) with positions
    optimized for triangulation coverage while minimizing the number of gateways.
    """
    suggestions = []
    
    if floor:
        bounds = extract_building_bounds(floor)
        bx_min, bx_max = bounds['min_x'], bounds['max_x']
        by_min, by_max = bounds['min_y'], bounds['max_y']
        bw = bounds['width']
        bh = bounds['height']
        cx, cy = bounds['center_x'], bounds['center_y']
    else:
        bx_min, by_min = 0, 0
        bx_max, bw = float(floor_width), float(floor_width)
        by_max, bh = float(floor_height), float(floor_height)
        cx, cy = bw / 2, bh / 2
    
    wall_offset = 1.5
    
    if num_gateways <= 2:
        suggestions = [
            {"x": round(bx_min + wall_offset, 2), "y": round(cy, 2), "name": "GW-1 (West Wall)"},
            {"x": round(bx_max - wall_offset, 2), "y": round(cy, 2), "name": "GW-2 (East Wall)"},
        ]
    elif num_gateways == 3:
        suggestions = [
            {"x": round(bx_min + wall_offset, 2), "y": round(by_min + bh * 0.3, 2), "name": "GW-1 (West)"},
            {"x": round(bx_max - wall_offset, 2), "y": round(by_min + bh * 0.3, 2), "name": "GW-2 (East)"},
            {"x": round(cx, 2), "y": round(by_max - wall_offset, 2), "name": "GW-3 (North)"},
        ]
    elif num_gateways == 4:
        suggestions = [
            {"x": round(bx_min + wall_offset, 2), "y": round(by_min + wall_offset, 2), "name": "GW-1 (SW Corner)"},
            {"x": round(bx_max - wall_offset, 2), "y": round(by_min + wall_offset, 2), "name": "GW-2 (SE Corner)"},
            {"x": round(bx_max - wall_offset, 2), "y": round(by_max - wall_offset, 2), "name": "GW-3 (NE Corner)"},
            {"x": round(bx_min + wall_offset, 2), "y": round(by_max - wall_offset, 2), "name": "GW-4 (NW Corner)"},
        ]
    else:
        perimeter = 2 * (bw + bh)
        spacing = perimeter / num_gateways
        
        current_dist = spacing / 2
        gw_num = 1
        
        sides = [
            ('S', bx_min, by_min + wall_offset, bx_max, by_min + wall_offset, bw),
            ('E', bx_max - wall_offset, by_min, bx_max - wall_offset, by_max, bh),
            ('N', bx_max, by_max - wall_offset, bx_min, by_max - wall_offset, bw),
            ('W', bx_min + wall_offset, by_max, bx_min + wall_offset, by_min, bh),
        ]
        
        cumulative = 0
        for side_name, x1, y1, x2, y2, length in sides:
            while current_dist < cumulative + length and gw_num <= num_gateways:
                t = (current_dist - cumulative) / length
                x = x1 + t * (x2 - x1)
                y = y1 + t * (y2 - y1)
                
                suggestions.append({
                    "x": round(float(x), 2),
                    "y": round(float(y), 2),
                    "name": f"GW-{gw_num} ({side_name} Wall)"
                })
                gw_num += 1
                current_dist += spacing
            
            cumulative += length
    
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
            
            # Detect building change and clear floor/plan selections
            if "gateway_planning_last_building_id" not in st.session_state:
                st.session_state.gateway_planning_last_building_id = selected_building_id
            elif st.session_state.gateway_planning_last_building_id != selected_building_id:
                st.session_state.gateway_planning_last_building_id = selected_building_id
                # Clear floor and plan selections when building changes
                for key in ["plan_floor", "selected_plan", "gateway_planning_last_floor_id"]:
                    if key in st.session_state:
                        del st.session_state[key]
                for key in list(st.session_state.keys()):
                    if key.startswith("gateway_plan_"):
                        del st.session_state[key]
                st.rerun()
            
            selected_building = session.query(Building).filter(Building.id == selected_building_id).first()
            floors = selected_building.floors if selected_building else []
            
            if not floors:
                st.warning("No floors defined for this building. Please add floor plans first.")
                return
            
            # Use same naming format as Coverage Zones for consistency
            floor_options = {f.id: f"{f.name} (Level {f.floor_number})" for f in floors}
            selected_floor_id = st.selectbox(
                "Select Floor",
                options=list(floor_options.keys()),
                format_func=lambda x: floor_options[x],
                key="plan_floor"
            )
            
            # Detect floor change and clear plan selection to avoid showing wrong floor's plan
            if "gateway_planning_last_floor_id" not in st.session_state:
                st.session_state.gateway_planning_last_floor_id = selected_floor_id
            elif st.session_state.gateway_planning_last_floor_id != selected_floor_id:
                # Floor changed - clear plan selection and any cached data
                st.session_state.gateway_planning_last_floor_id = selected_floor_id
                for key in list(st.session_state.keys()):
                    if key.startswith("selected_plan") or key.startswith("gateway_plan_"):
                        del st.session_state[key]
                st.rerun()
            
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
            recommendations = calculate_recommended_gateways(floor_area, target_accuracy, signal_range, floor=selected_floor)
            
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
                
                # Validate plan belongs to selected floor - if not, reset selection
                if current_plan and current_plan.floor_id != selected_floor_id:
                    if "selected_plan" in st.session_state:
                        del st.session_state["selected_plan"]
                    st.rerun()
                
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
                effective_recommendations = calculate_recommended_gateways(floor_area, effective_target_accuracy, effective_signal_range, floor=selected_floor)
                
                floor_width = selected_floor.width_meters
                floor_height = selected_floor.height_meters
                
                fig, has_floor_plan = create_floor_plan_figure(selected_floor)
                
                if not has_floor_plan:
                    fig.add_shape(
                        type="rect",
                        x0=0, y0=0,
                        x1=floor_width, y1=floor_height,
                        line=dict(color="#2e5cbf", width=2),
                        fillcolor="rgba(46, 92, 191, 0.05)"
                    )
                
                coverage_zones = session.query(CoverageZone).filter(
                    CoverageZone.floor_id == selected_floor_id,
                    CoverageZone.is_active == True
                ).order_by(CoverageZone.priority.desc()).all()
                
                for cz in coverage_zones:
                    try:
                        coords = json.loads(cz.polygon_coords)
                        if coords:
                            xs = [c[0] for c in coords]
                            ys = [c[1] for c in coords]
                            
                            if xs[0] != xs[-1] or ys[0] != ys[-1]:
                                xs.append(xs[0])
                                ys.append(ys[0])
                            
                            zone_color = cz.color or '#2e5cbf'
                            r, g, b = int(zone_color[1:3], 16), int(zone_color[3:5], 16), int(zone_color[5:7], 16)
                            
                            fig.add_trace(go.Scatter(
                                x=xs, y=ys,
                                fill='toself',
                                fillcolor=f'rgba({r}, {g}, {b}, 0.15)',
                                line=dict(color=zone_color, width=2, dash='dash'),
                                mode='lines',
                                name=f"{cz.name} (±{cz.target_accuracy}m)",
                                hovertemplate=f"<b>{cz.name}</b><br>Target: ±{cz.target_accuracy}m<extra></extra>"
                            ))
                    except Exception:
                        pass
                
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
                
                # Use focus area from database if set, otherwise show full floor
                if selected_floor.focus_min_x is not None:
                    x_range = [selected_floor.focus_min_x - 1, selected_floor.focus_max_x + 1]
                    y_range = [selected_floor.focus_min_y - 1, selected_floor.focus_max_y + 1]
                else:
                    x_range = [-2, floor_width + 2]
                    y_range = [-2, floor_height + 2]
                
                fig.update_layout(
                    height=600,
                    xaxis=dict(
                        title="X (meters)",
                        range=x_range,
                        scaleanchor="y",
                        scaleratio=1,
                        showgrid=not has_floor_plan,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)',
                        zeroline=False,
                        constrain='domain'
                    ),
                    yaxis=dict(
                        title="Y (meters)",
                        range=y_range,
                        showgrid=not has_floor_plan,
                        gridwidth=1,
                        gridcolor='rgba(0,0,0,0.1)',
                        zeroline=False,
                        constrain='domain'
                    ),
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1,
                        bgcolor='rgba(255,255,255,0.8)'
                    ),
                    margin=dict(l=50, r=50, t=50, b=50),
                    plot_bgcolor='rgba(240,240,240,0.3)' if not has_floor_plan else 'rgba(255,255,255,0)'
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Show focus area indicator
                if selected_floor.focus_min_x is not None:
                    fa_width = selected_floor.focus_max_x - selected_floor.focus_min_x
                    fa_height = selected_floor.focus_max_y - selected_floor.focus_min_y
                    st.caption(f"🔍 **Focus Area active**: X [{selected_floor.focus_min_x:.1f} - {selected_floor.focus_max_x:.1f}], Y [{selected_floor.focus_min_y:.1f} - {selected_floor.focus_max_y:.1f}] ({fa_width:.1f}m x {fa_height:.1f}m) - Set in Coverage Zones")
                
                if coverage_zones:
                    st.info(f"📍 **{len(coverage_zones)} coverage zone(s) defined** - Gateways will be placed within these areas.")
                else:
                    st.caption("💡 Tip: Define coverage zones to specify which areas need positioning. Go to **Coverage Zones** in the sidebar.")
                
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
                    position_valid = True
                    zone_name_matched = None
                    
                    if coverage_zones:
                        position_valid = False
                        for cz in coverage_zones:
                            try:
                                coords = json.loads(cz.polygon_coords)
                                if coords and point_in_polygon(float(new_gw_x), float(new_gw_y), coords):
                                    position_valid = True
                                    zone_name_matched = cz.name
                                    break
                            except Exception:
                                continue
                    
                    if position_valid:
                        new_planned_gw = PlannedGateway(
                            plan_id=current_plan.id,
                            name=new_gw_name,
                            x_position=float(new_gw_x),
                            y_position=float(new_gw_y)
                        )
                        session.add(new_planned_gw)
                        session.commit()
                        zone_msg = f" (in {zone_name_matched})" if zone_name_matched else ""
                        st.success(f"Added {new_gw_name}{zone_msg}")
                        st.rerun()
                    else:
                        st.error("Position is outside all coverage zones. Gateways must be placed within defined coverage areas.")
            
            # Auto-suggest gateways based on coverage zones
            if coverage_zones:
                st.markdown("**Auto-suggest by Coverage Zone**")
                
                # Show summary of zones and gateway requirements
                total_suggested = 0
                zone_gateway_counts = []
                for cz in coverage_zones:
                    gw_count = calculate_gateways_for_zone(cz)
                    zone_gateway_counts.append((cz, gw_count))
                    total_suggested += gw_count
                
                with st.expander("Zone Gateway Requirements", expanded=False):
                    for cz, count in zone_gateway_counts:
                        st.write(f"**{cz.name}** (±{cz.target_accuracy}m): {count} gateways")
                
                if st.button(f"Auto-suggest {total_suggested} gateways for all zones", type="primary"):
                    existing_gws = session.query(PlannedGateway).filter(
                        PlannedGateway.plan_id == current_plan.id
                    ).all()
                    added_count = 0
                    gw_num = len(existing_gws) + 1
                    
                    for cz, num_gateways in zone_gateway_counts:
                        zone_bounds = get_coverage_zone_bounds(cz)
                        if zone_bounds:
                            zone_suggestions = suggest_gateway_positions_for_zone(
                                zone_bounds, num_gateways, signal_range=effective_signal_range
                            )
                            for i, suggestion in enumerate(zone_suggestions):
                                exists = any(
                                    abs(pg.x_position - float(suggestion['x'])) < 1 and abs(pg.y_position - float(suggestion['y'])) < 1
                                    for pg in existing_gws
                                )
                                if not exists:
                                    new_planned_gw = PlannedGateway(
                                        plan_id=current_plan.id,
                                        name=f"GW-{gw_num} ({cz.name})",
                                        x_position=float(suggestion['x']),
                                        y_position=float(suggestion['y'])
                                    )
                                    session.add(new_planned_gw)
                                    existing_gws.append(new_planned_gw)
                                    added_count += 1
                                    gw_num += 1
                    
                    session.commit()
                    st.success(f"Added {added_count} gateway positions across {len(coverage_zones)} zone(s)")
                    st.rerun()
            else:
                # Fallback to floor-based suggestion if no coverage zones
                suggestions = suggest_gateway_positions(
                    floor_width, floor_height, effective_recommendations["recommended"],
                    signal_range=effective_signal_range, floor=selected_floor
                )
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
