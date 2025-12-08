import ezdxf
from typing import Dict, List, Tuple, Optional, Any
import json
import math
from io import BytesIO
import tempfile
import os


def apply_transform(entity_data: Dict[str, Any], transform: Dict[str, float]) -> Dict[str, Any]:
    """Apply transformation (offset, scale, rotation) to entity coordinates"""
    if not entity_data or 'coordinates' not in entity_data:
        return entity_data
    
    offset_x = transform.get('offset_x', 0)
    offset_y = transform.get('offset_y', 0)
    scale_x = transform.get('scale_x', 1.0)
    scale_y = transform.get('scale_y', 1.0)
    rotation = transform.get('rotation', 0)
    
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    
    transformed_coords = []
    for coord in entity_data['coordinates']:
        if isinstance(coord, (list, tuple)) and len(coord) >= 2:
            x = coord[0] * scale_x
            y = coord[1] * scale_y
            rx = x * cos_r - y * sin_r + offset_x
            ry = x * sin_r + y * cos_r + offset_y
            transformed_coords.append([rx, ry])
    
    result = entity_data.copy()
    result['coordinates'] = transformed_coords
    
    if 'center' in entity_data:
        cx, cy = entity_data['center']
        cx = cx * scale_x
        cy = cy * scale_y
        rx = cx * cos_r - cy * sin_r + offset_x
        ry = cx * sin_r + cy * cos_r + offset_y
        result['center'] = [rx, ry]
    
    return result


def parse_dxf_file(file_content: bytes) -> Dict[str, Any]:
    """
    Parse a DXF file and extract floor plan geometry.
    Expands BLOCK/INSERT references to capture nested geometry.
    
    Returns a dict with:
    - entities: List of geometric entities (walls, rooms, etc.)
    - bounds: Bounding box of the drawing
    - layers: List of layer names
    - units: Drawing units if specified
    """
    with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    
    try:
        doc = ezdxf.readfile(tmp_path)
        msp = doc.modelspace()
        
        entities = []
        all_x = []
        all_y = []
        layers = set()
        
        def process_entity(entity, transform_matrix=None):
            """Process an entity, optionally applying transformation"""
            nonlocal entities, all_x, all_y, layers
            
            layers.add(entity.dxf.layer)
            entity_data = extract_entity_geometry(entity)
            if entity_data:
                if transform_matrix is not None:
                    entity_data = apply_transform(entity_data, transform_matrix)
                entities.append(entity_data)
                coords = entity_data.get('coordinates', [])
                for coord in coords:
                    if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                        all_x.append(coord[0])
                        all_y.append(coord[1])
        
        def expand_insert(insert_entity):
            """Expand an INSERT (block reference) to its constituent entities"""
            try:
                block_name = insert_entity.dxf.name
                if block_name in doc.blocks:
                    block = doc.blocks[block_name]
                    insert_point = insert_entity.dxf.insert
                    scale_x = getattr(insert_entity.dxf, 'xscale', 1.0)
                    scale_y = getattr(insert_entity.dxf, 'yscale', 1.0)
                    rotation = getattr(insert_entity.dxf, 'rotation', 0.0)
                    
                    transform = {
                        'offset_x': insert_point.x,
                        'offset_y': insert_point.y,
                        'scale_x': scale_x,
                        'scale_y': scale_y,
                        'rotation': math.radians(rotation)
                    }
                    
                    for block_entity in block:
                        if block_entity.dxftype() == 'INSERT':
                            expand_insert(block_entity)
                        else:
                            process_entity(block_entity, transform)
            except Exception as e:
                pass
        
        for entity in msp:
            if entity.dxftype() == 'INSERT':
                expand_insert(entity)
            else:
                process_entity(entity)
        
        bounds = None
        if all_x and all_y:
            bounds = {
                'min_x': min(all_x),
                'max_x': max(all_x),
                'min_y': min(all_y),
                'max_y': max(all_y),
                'width': max(all_x) - min(all_x),
                'height': max(all_y) - min(all_y)
            }
        
        units_code = doc.header.get('$INSUNITS', 0)
        units_map = {
            0: 'Unitless',
            1: 'Inches',
            2: 'Feet',
            3: 'Miles',
            4: 'Millimeters',
            5: 'Centimeters',
            6: 'Meters',
            7: 'Kilometers'
        }
        units = units_map.get(units_code, 'Unknown')
        
        return {
            'entities': entities,
            'bounds': bounds,
            'layers': list(layers),
            'units': units,
            'entity_count': len(entities)
        }
        
    finally:
        os.unlink(tmp_path)


def extract_entity_geometry(entity) -> Optional[Dict[str, Any]]:
    """Extract geometry from a DXF entity."""
    dxftype = entity.dxftype()
    layer = entity.dxf.layer
    
    try:
        if dxftype == 'LINE':
            return {
                'type': 'line',
                'layer': layer,
                'coordinates': [
                    [entity.dxf.start.x, entity.dxf.start.y],
                    [entity.dxf.end.x, entity.dxf.end.y]
                ]
            }
        
        elif dxftype == 'LWPOLYLINE':
            coords = []
            for point in entity.get_points('xy'):
                coords.append([point[0], point[1]])
            if entity.closed and coords:
                coords.append(coords[0])
            return {
                'type': 'polyline',
                'layer': layer,
                'closed': entity.closed,
                'coordinates': coords
            }
        
        elif dxftype == 'POLYLINE':
            coords = []
            for vertex in entity.vertices:
                coords.append([vertex.dxf.location.x, vertex.dxf.location.y])
            if entity.is_closed and coords:
                coords.append(coords[0])
            return {
                'type': 'polyline',
                'layer': layer,
                'closed': entity.is_closed,
                'coordinates': coords
            }
        
        elif dxftype == 'CIRCLE':
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            coords = []
            for i in range(37):
                angle = 2 * math.pi * i / 36
                coords.append([cx + r * math.cos(angle), cy + r * math.sin(angle)])
            return {
                'type': 'circle',
                'layer': layer,
                'center': [cx, cy],
                'radius': r,
                'coordinates': coords
            }
        
        elif dxftype == 'ARC':
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            start_angle = math.radians(entity.dxf.start_angle)
            end_angle = math.radians(entity.dxf.end_angle)
            if end_angle < start_angle:
                end_angle += 2 * math.pi
            coords = []
            num_points = max(2, int((end_angle - start_angle) / (math.pi / 18)) + 1)
            for i in range(num_points):
                angle = start_angle + (end_angle - start_angle) * i / (num_points - 1)
                coords.append([cx + r * math.cos(angle), cy + r * math.sin(angle)])
            return {
                'type': 'arc',
                'layer': layer,
                'center': [cx, cy],
                'radius': r,
                'coordinates': coords
            }
        
        elif dxftype == 'ELLIPSE':
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            major_axis = entity.dxf.major_axis
            ratio = entity.dxf.ratio
            a = math.sqrt(major_axis.x**2 + major_axis.y**2)
            b = a * ratio
            rotation = math.atan2(major_axis.y, major_axis.x)
            coords = []
            for i in range(37):
                angle = 2 * math.pi * i / 36
                x = a * math.cos(angle)
                y = b * math.sin(angle)
                rx = x * math.cos(rotation) - y * math.sin(rotation) + cx
                ry = x * math.sin(rotation) + y * math.cos(rotation) + cy
                coords.append([rx, ry])
            return {
                'type': 'ellipse',
                'layer': layer,
                'center': [cx, cy],
                'coordinates': coords
            }
        
        elif dxftype == 'SPLINE':
            coords = []
            try:
                for point in entity.control_points:
                    coords.append([point.x, point.y])
            except:
                pass
            if coords:
                return {
                    'type': 'spline',
                    'layer': layer,
                    'coordinates': coords
                }
        
        elif dxftype == 'TEXT' or dxftype == 'MTEXT':
            try:
                if dxftype == 'TEXT':
                    insert = entity.dxf.insert
                    text = entity.dxf.text
                else:
                    insert = entity.dxf.insert
                    text = entity.text
                return {
                    'type': 'text',
                    'layer': layer,
                    'text': text,
                    'coordinates': [[insert.x, insert.y]]
                }
            except:
                pass
        
        elif dxftype == 'HATCH':
            coords = []
            try:
                for path in entity.paths:
                    path_coords = []
                    if hasattr(path, 'vertices'):
                        for vertex in path.vertices:
                            path_coords.append([vertex.x, vertex.y])
                    if path_coords:
                        coords.extend(path_coords)
            except:
                pass
            if coords:
                return {
                    'type': 'hatch',
                    'layer': layer,
                    'coordinates': coords
                }
        
        elif dxftype == 'INSERT':
            try:
                insert = entity.dxf.insert
                return {
                    'type': 'block_insert',
                    'layer': layer,
                    'block_name': entity.dxf.name,
                    'coordinates': [[insert.x, insert.y]]
                }
            except:
                pass
        
    except Exception as e:
        pass
    
    return None


def dxf_to_geojson(dxf_data: Dict[str, Any], 
                   scale: float = 1.0,
                   origin_x: float = 0,
                   origin_y: float = 0,
                   wall_layers: Optional[List[str]] = None,
                   room_layers: Optional[List[str]] = None) -> str:
    """
    Convert parsed DXF data to GeoJSON format for floor plan display.
    
    Args:
        dxf_data: Parsed DXF data from parse_dxf_file()
        scale: Scale factor to convert DXF units to meters
        origin_x: X coordinate offset
        origin_y: Y coordinate offset
        wall_layers: Layer names to treat as walls (e.g., ['WALLS', 'A-WALL'])
        room_layers: Layer names to treat as rooms (e.g., ['ROOMS', 'A-AREA'])
    
    Returns:
        GeoJSON string
    """
    if wall_layers is None:
        wall_layers = ['WALL', 'WALLS', 'A-WALL', 'S-WALL', 'PARTITION']
    if room_layers is None:
        room_layers = ['ROOM', 'ROOMS', 'A-AREA', 'A-ROOM', 'SPACE', 'ZONE']
    
    wall_layers_lower = [l.lower() for l in wall_layers]
    room_layers_lower = [l.lower() for l in room_layers]
    
    features = []
    
    for entity in dxf_data.get('entities', []):
        layer = entity.get('layer', '').lower()
        coords = entity.get('coordinates', [])
        entity_type = entity.get('type', '')
        
        if not coords:
            continue
        
        scaled_coords = []
        for coord in coords:
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                scaled_coords.append([
                    (coord[0] - origin_x) * scale,
                    (coord[1] - origin_y) * scale
                ])
        
        if not scaled_coords:
            continue
        
        geom_type = 'wall'
        is_room = False
        
        for room_layer in room_layers_lower:
            if room_layer in layer:
                geom_type = 'room'
                is_room = True
                break
        
        if not is_room:
            for wall_layer in wall_layers_lower:
                if wall_layer in layer:
                    geom_type = 'wall'
                    break
        
        if is_room or entity.get('closed', False):
            if len(scaled_coords) >= 3:
                if scaled_coords[0] != scaled_coords[-1]:
                    scaled_coords.append(scaled_coords[0])
                feature = {
                    'type': 'Feature',
                    'properties': {
                        'name': entity.get('layer', 'Unknown'),
                        'geomType': geom_type,
                        'layer': entity.get('layer', ''),
                        'entityType': entity_type
                    },
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [scaled_coords]
                    }
                }
                features.append(feature)
        else:
            feature = {
                'type': 'Feature',
                'properties': {
                    'name': entity.get('layer', 'Unknown'),
                    'geomType': geom_type,
                    'subType': 'inner',
                    'layer': entity.get('layer', ''),
                    'entityType': entity_type
                },
                'geometry': {
                    'type': 'LineString',
                    'coordinates': scaled_coords
                }
            }
            features.append(feature)
    
    geojson = {
        'type': 'FeatureCollection',
        'features': features,
        'properties': {
            'units': dxf_data.get('units', 'Unknown'),
            'bounds': dxf_data.get('bounds'),
            'layers': dxf_data.get('layers', [])
        }
    }
    
    return json.dumps(geojson)


def get_dxf_dimensions(dxf_data: Dict[str, Any], scale: float = 1.0) -> Tuple[float, float]:
    """Get the width and height of the DXF drawing in meters."""
    bounds = dxf_data.get('bounds')
    if bounds:
        width = bounds['width'] * scale
        height = bounds['height'] * scale
        return max(1.0, width), max(1.0, height)
    return 100.0, 100.0


def detect_dxf_scale(dxf_data: Dict[str, Any]) -> float:
    """
    Attempt to detect the appropriate scale factor based on drawing units.
    Returns scale factor to convert to meters.
    Always returns at least 1.0 to avoid zero scaling.
    """
    units = dxf_data.get('units', 'Unknown')
    
    scale_factors = {
        'Millimeters': 0.001,
        'Centimeters': 0.01,
        'Meters': 1.0,
        'Inches': 0.0254,
        'Feet': 0.3048,
        'Kilometers': 1000.0,
        'Miles': 1609.34,
        'Unitless': 1.0,
        'Unknown': 1.0
    }
    
    scale = scale_factors.get(units, 1.0)
    return scale if scale > 0 else 1.0
