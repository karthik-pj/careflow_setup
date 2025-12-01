import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class GatewayReading:
    """RSSI reading from a single gateway"""
    gateway_id: int
    x: float
    y: float
    rssi: int
    tx_power: int = -59
    path_loss_exponent: float = 2.0


def rssi_to_distance(rssi: int, tx_power: int = -59, path_loss_exponent: float = 2.0) -> float:
    """
    Convert RSSI value to estimated distance using the log-distance path loss model.
    
    Args:
        rssi: Received signal strength indicator (dBm)
        tx_power: Signal strength at 1 meter (dBm), typically -59 for BLE
        path_loss_exponent: Environment-specific path loss exponent (2.0 for free space)
    
    Returns:
        Estimated distance in meters
    """
    if rssi >= tx_power:
        return 0.1
    
    ratio = (tx_power - rssi) / (10 * path_loss_exponent)
    distance = pow(10, ratio)
    
    return max(0.1, min(distance, 100))


def trilaterate_2d(readings: List[GatewayReading]) -> Tuple[float, float, float]:
    """
    Calculate position using trilateration from multiple gateway readings.
    
    Uses weighted least squares optimization for better accuracy.
    
    Args:
        readings: List of gateway readings with positions and RSSI values
    
    Returns:
        Tuple of (x, y, accuracy) where accuracy is estimated error in meters
    """
    if len(readings) < 3:
        if len(readings) == 1:
            distance = rssi_to_distance(
                readings[0].rssi, 
                readings[0].tx_power, 
                readings[0].path_loss_exponent
            )
            return readings[0].x, readings[0].y, distance
        elif len(readings) == 2:
            d1 = rssi_to_distance(
                readings[0].rssi, 
                readings[0].tx_power, 
                readings[0].path_loss_exponent
            )
            d2 = rssi_to_distance(
                readings[1].rssi, 
                readings[1].tx_power, 
                readings[1].path_loss_exponent
            )
            weight1 = 1 / max(d1, 0.1)
            weight2 = 1 / max(d2, 0.1)
            total_weight = weight1 + weight2
            
            x = (readings[0].x * weight1 + readings[1].x * weight2) / total_weight
            y = (readings[0].y * weight1 + readings[1].y * weight2) / total_weight
            accuracy = (d1 + d2) / 2
            return x, y, accuracy
    
    positions = np.array([[r.x, r.y] for r in readings])
    distances = np.array([
        rssi_to_distance(r.rssi, r.tx_power, r.path_loss_exponent) 
        for r in readings
    ])
    
    weights = 1 / np.maximum(distances, 0.1)
    weights = weights / np.sum(weights)
    
    n = len(readings)
    A = np.zeros((n - 1, 2))
    b = np.zeros(n - 1)
    
    for i in range(n - 1):
        A[i, 0] = 2 * (positions[i, 0] - positions[n-1, 0])
        A[i, 1] = 2 * (positions[i, 1] - positions[n-1, 1])
        b[i] = (distances[n-1]**2 - distances[i]**2 + 
                positions[i, 0]**2 - positions[n-1, 0]**2 +
                positions[i, 1]**2 - positions[n-1, 1]**2)
    
    W = np.diag(weights[:-1])
    
    try:
        AtWA = A.T @ W @ A
        AtWb = A.T @ W @ b
        
        if np.linalg.det(AtWA) < 1e-10:
            x = np.sum(positions[:, 0] * weights)
            y = np.sum(positions[:, 1] * weights)
        else:
            result = np.linalg.solve(AtWA, AtWb)
            x, y = result[0], result[1]
    except np.linalg.LinAlgError:
        x = np.sum(positions[:, 0] * weights)
        y = np.sum(positions[:, 1] * weights)
    
    estimated_distances = np.sqrt((positions[:, 0] - x)**2 + (positions[:, 1] - y)**2)
    accuracy = np.sqrt(np.mean((estimated_distances - distances)**2))
    
    return float(x), float(y), float(accuracy)


def calculate_velocity(
    current_pos: Tuple[float, float],
    previous_pos: Tuple[float, float],
    time_delta_seconds: float
) -> Tuple[float, float, float, float]:
    """
    Calculate velocity vector and speed from two positions.
    
    Args:
        current_pos: Current (x, y) position
        previous_pos: Previous (x, y) position
        time_delta_seconds: Time difference in seconds
    
    Returns:
        Tuple of (velocity_x, velocity_y, speed, heading_degrees)
    """
    if time_delta_seconds <= 0:
        return 0.0, 0.0, 0.0, 0.0
    
    dx = current_pos[0] - previous_pos[0]
    dy = current_pos[1] - previous_pos[1]
    
    velocity_x = dx / time_delta_seconds
    velocity_y = dy / time_delta_seconds
    
    speed = np.sqrt(velocity_x**2 + velocity_y**2)
    
    heading = np.degrees(np.arctan2(dy, dx))
    if heading < 0:
        heading += 360
    
    return float(velocity_x), float(velocity_y), float(speed), float(heading)


def smooth_position(
    current_pos: Tuple[float, float],
    previous_positions: List[Tuple[float, float]],
    alpha: float = 0.3
) -> Tuple[float, float]:
    """
    Apply exponential smoothing to reduce position jitter.
    
    Args:
        current_pos: Current calculated position
        previous_positions: List of previous positions (most recent last)
        alpha: Smoothing factor (0-1), higher = more responsive
    
    Returns:
        Smoothed (x, y) position
    """
    if not previous_positions:
        return current_pos
    
    smoothed_x = current_pos[0]
    smoothed_y = current_pos[1]
    
    for prev_pos in reversed(previous_positions[-5:]):
        smoothed_x = alpha * smoothed_x + (1 - alpha) * prev_pos[0]
        smoothed_y = alpha * smoothed_y + (1 - alpha) * prev_pos[1]
    
    return smoothed_x, smoothed_y


def filter_outlier_readings(
    readings: List[GatewayReading],
    max_distance: float = 50.0
) -> List[GatewayReading]:
    """
    Filter out readings that suggest unrealistic distances.
    
    Args:
        readings: List of gateway readings
        max_distance: Maximum believable distance in meters
    
    Returns:
        Filtered list of readings
    """
    filtered = []
    for reading in readings:
        distance = rssi_to_distance(
            reading.rssi, 
            reading.tx_power, 
            reading.path_loss_exponent
        )
        if distance <= max_distance:
            filtered.append(reading)
    
    return filtered if filtered else readings
