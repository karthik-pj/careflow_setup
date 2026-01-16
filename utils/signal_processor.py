import threading
import time
import os
import atexit
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import streamlit as st

from database import get_db_session, Gateway, Beacon, RSSISignal, Position, MQTTConfig, Floor, Building
from utils.mqtt_handler import MQTTHandler, MQTTMessage
from utils.triangulation import GatewayReading, trilaterate_2d, calculate_velocity, filter_outlier_readings, smooth_position
from utils.mqtt_publisher import get_mqtt_publisher


def normalize_mac_address(mac: str) -> str:
    """Normalize MAC address to uppercase without colons for comparison"""
    if not mac:
        return ""
    return mac.upper().replace(":", "").replace("-", "")


def determine_floor_from_signals(gateway_signals: Dict[int, Any], session) -> Tuple[int, float]:
    """Determine the most likely floor for a beacon based on signal strengths from gateways.
    
    Only considers floors that actually contributed gateway readings.
    Uses weighted signal strength scoring to prevent floor hopping.
    
    Returns:
        Tuple of (floor_id, confidence) where confidence is 0-1
    """
    floor_scores: Dict[int, float] = {}
    floor_signal_counts: Dict[int, int] = {}
    floor_gateway_counts: Dict[int, int] = {}
    
    for gateway_id, signals in gateway_signals.items():
        gateway = session.query(Gateway).filter(Gateway.id == gateway_id).first()
        if not gateway or not signals:
            continue
        
        # Get average RSSI for this gateway
        avg_rssi = sum(s.rssi for s in signals) / len(signals)
        
        # Convert RSSI to a positive score (stronger signal = higher score)
        # RSSI typically ranges from -30 (excellent) to -100 (weak)
        signal_strength = max(0, 100 + avg_rssi)  # 0-70 range typically
        
        floor_id = gateway.floor_id
        
        if floor_id not in floor_scores:
            floor_scores[floor_id] = 0
            floor_signal_counts[floor_id] = 0
            floor_gateway_counts[floor_id] = 0
        
        floor_scores[floor_id] += signal_strength
        floor_signal_counts[floor_id] += len(signals)
        floor_gateway_counts[floor_id] += 1
    
    if not floor_scores:
        return None, 0
    
    # Normalize by gateway count and calculate average score per floor
    for floor_id in floor_scores:
        if floor_gateway_counts[floor_id] > 0:
            floor_scores[floor_id] /= floor_gateway_counts[floor_id]
    
    # Find best floor (only from floors that had readings)
    best_floor_id = max(floor_scores, key=floor_scores.get)
    best_score = floor_scores[best_floor_id]
    best_gateway_count = floor_gateway_counts.get(best_floor_id, 0)
    
    # Calculate confidence based on separation from second best and gateway count
    sorted_scores = sorted(floor_scores.values(), reverse=True)
    if len(sorted_scores) > 1:
        second_best = sorted_scores[1]
        # Confidence is higher when best floor is significantly stronger
        separation = (best_score - second_best) / max(best_score, 1)
        base_confidence = min(1.0, 0.5 + separation)
    else:
        # Only one floor has readings - confidence based on gateway count
        base_confidence = 1.0
    
    # Boost confidence based on gateway count (more gateways = more reliable)
    gateway_factor = min(1.0, best_gateway_count / 3.0)
    confidence = base_confidence * (0.7 + 0.3 * gateway_factor)
    
    return best_floor_id, confidence


class SignalProcessor:
    """Signal processor that stores signals via MQTT callback and calculates positions on demand.
    
    Key architecture: Uses Paho MQTT's internal thread for signal storage (persistent),
    while position calculation is triggered by Streamlit page loads (on-demand).
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._mqtt_handler: Optional[MQTTHandler] = None
        self._running = False
        self._last_error: Optional[str] = None
        self._stats = {
            'signals_received': 0,
            'signals_stored': 0,
            'positions_calculated': 0,
            'positions_published': 0,
            'errors': 0
        }
        self._publisher = None
        self._refresh_interval = 1.0
        self._signal_window_seconds = 30.0  # Increased to capture signals from multiple gateways
        self._rssi_smoothing_enabled = True
        self._position_smoothing_alpha = 0.4
        self._position_history: Dict[int, List[Tuple[float, float]]] = {}
        self._last_heartbeat: Optional[datetime] = None
        self._last_position_calc: Optional[datetime] = None
        self._signal_lock = threading.Lock()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._calc_lock = threading.Lock()
        atexit.register(self._cleanup)
    
    @property
    def is_running(self) -> bool:
        """Check if processor is running (MQTT handler connected and scheduler active)"""
        mqtt_ok = self._running and self._mqtt_handler and self._mqtt_handler.is_connected
        scheduler_ok = self._scheduler_thread and self._scheduler_thread.is_alive()
        return mqtt_ok and scheduler_ok
    
    @property
    def last_heartbeat(self) -> Optional[datetime]:
        return self._last_heartbeat
    
    def _cleanup(self):
        """Cleanup handler for atexit"""
        if self._running:
            self.stop()
    
    def check_and_restart(self) -> bool:
        """Check if the processor should be running but isn't, and restart if needed.
        Also starts the processor if it has never been started.
        Returns True if processor is now running, False if restart failed.
        """
        # If already running properly, nothing to do
        if self.is_running:
            return True
        
        needs_restart = False
        needs_start = False
        
        if self._running:
            # Was running but something is wrong
            if self._mqtt_handler and not self._mqtt_handler.is_connected:
                needs_restart = True
            if not self._scheduler_thread or not self._scheduler_thread.is_alive():
                needs_restart = True
        else:
            # Never started - start it now
            needs_start = True
        
        if needs_restart:
            print("[SignalProcessor] Restarting due to connection or thread issues")
            self.stop()
            return self.start()
        
        if needs_start:
            print("[SignalProcessor] Starting for the first time")
            return self.start()
        
        return self.is_running
    
    @property
    def stats(self) -> Dict[str, int]:
        return self._stats.copy()
    
    @property
    def last_error(self) -> Optional[str]:
        return self._last_error
    
    def _get_mqtt_password(self, password_env_key: Optional[str]) -> Optional[str]:
        """Retrieve MQTT password from environment variable"""
        if password_env_key:
            return os.environ.get(password_env_key)
        return None
    
    def start(self) -> bool:
        """Start the signal processor with MQTT connection.
        
        Uses Paho's internal thread for signal storage (via callback),
        which persists across Streamlit reruns.
        """
        if self.is_running:
            return True
        
        # Always stop existing handler to ensure clean state
        if self._mqtt_handler or self._scheduler_thread:
            print("[SignalProcessor] Cleaning up stale resources before start")
            self.stop()
        
        try:
            with get_db_session() as session:
                mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
                
                if not mqtt_config:
                    self._last_error = "No active MQTT configuration found"
                    return False
                
                password = self._get_mqtt_password(mqtt_config.password_env_key)
                
                ca_cert_path = getattr(mqtt_config, 'ca_cert_path', None)
                
                self._mqtt_handler = MQTTHandler(
                    broker_host=mqtt_config.broker_host,
                    broker_port=mqtt_config.broker_port,
                    username=mqtt_config.username,
                    password=password,
                    topic_prefix=mqtt_config.topic_prefix,
                    use_tls=mqtt_config.use_tls,
                    ca_cert_path=ca_cert_path
                )
            
            self._mqtt_handler.add_callback(self._on_mqtt_message)
            self._mqtt_handler.add_reconnect_callback(self._on_mqtt_reconnect)
            self._mqtt_handler.add_disconnect_callback(self._on_mqtt_disconnect)
            
            if not self._mqtt_handler.connect():
                self._last_error = self._mqtt_handler.last_error or "Failed to connect to MQTT broker"
                return False
            
            self._publisher = get_mqtt_publisher()
            with get_db_session() as session:
                mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
                if mqtt_config:
                    if getattr(mqtt_config, 'publish_enabled', False):
                        self._publisher.configure(mqtt_config)
                    self._refresh_interval = getattr(mqtt_config, 'refresh_interval', 1.0) or 1.0
                    self._signal_window_seconds = getattr(mqtt_config, 'signal_window_seconds', 30.0) or 30.0
                    self._rssi_smoothing_enabled = getattr(mqtt_config, 'rssi_smoothing_enabled', True)
                    self._position_smoothing_alpha = getattr(mqtt_config, 'position_smoothing_alpha', 0.4) or 0.4
            
            self._running = True
            self._last_heartbeat = datetime.utcnow()
            self._stop_event.clear()
            
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop, 
                daemon=False, 
                name="SignalProcessorScheduler"
            )
            self._scheduler_thread.start()
            
            print("[SignalProcessor] Started with callback-based signal storage and position scheduler")
            self._last_error = None
            return True
            
        except Exception as e:
            self._last_error = str(e)
            print(f"[SignalProcessor] Start error: {e}")
            return False
    
    def stop(self):
        """Stop the signal processor"""
        self._running = False
        self._stop_event.set()
        
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=5)
            self._scheduler_thread = None
        
        if self._mqtt_handler:
            self._mqtt_handler.stop()
            self._mqtt_handler.disconnect()
            self._mqtt_handler = None
    
    def _on_mqtt_message(self, msg: MQTTMessage):
        """Callback for MQTT messages - runs in Paho's thread.
        
        This is the key to persistence: Paho's internal thread survives
        Streamlit reruns, so signals are stored continuously.
        """
        with self._signal_lock:
            try:
                self._stats['signals_received'] += 1
                self._store_signal(msg)
                self._last_heartbeat = datetime.utcnow()
            except Exception as e:
                self._stats['errors'] += 1
                self._last_error = str(e)
    
    def _on_mqtt_reconnect(self):
        """Callback when MQTT reconnects - ensures processing resumes immediately"""
        print("[SignalProcessor] MQTT reconnected - resuming signal processing")
        self._last_heartbeat = datetime.utcnow()
        self._last_error = None
    
    def _on_mqtt_disconnect(self):
        """Callback when MQTT disconnects - log the event"""
        print("[SignalProcessor] MQTT disconnected - signals will not be stored until reconnection")
        self._last_error = "MQTT disconnected - awaiting reconnection"
    
    def _scheduler_loop(self):
        """Scheduler loop for position calculation - runs in dedicated thread.
        
        This thread calculates positions at fixed intervals independent of the UI.
        Uses Event.wait() for graceful shutdown.
        """
        print("[SignalProcessor] Scheduler thread started")
        last_heartbeat_log = datetime.utcnow()
        
        while self._running and not self._stop_event.is_set():
            try:
                if (datetime.utcnow() - last_heartbeat_log).total_seconds() >= 30:
                    stats = self._stats
                    print(f"[SignalProcessor] Heartbeat - Signals: {stats['signals_received']}, Stored: {stats['signals_stored']}, Positions: {stats['positions_calculated']}, Errors: {stats['errors']}")
                    last_heartbeat_log = datetime.utcnow()
                
                with self._calc_lock:
                    self._calculate_positions()
                    self._last_position_calc = datetime.utcnow()
                
                self._stop_event.wait(timeout=self._refresh_interval)
                
            except Exception as e:
                self._last_error = f"Scheduler error: {e}"
                self._stats['errors'] += 1
                print(f"[SignalProcessor] Scheduler error: {e}")
                self._stop_event.wait(timeout=1.0)
        
        print("[SignalProcessor] Scheduler thread stopped")
    
    def _store_signal(self, msg: MQTTMessage):
        """Store an RSSI signal in the database"""
        try:
            with get_db_session() as session:
                gateway = session.query(Gateway).filter(
                    Gateway.mac_address == msg.gateway_mac,
                    Gateway.is_active == True
                ).first()
                
                if not gateway:
                    return
                
                normalized_beacon_mac = normalize_mac_address(msg.beacon_mac)
                all_beacons = session.query(Beacon).all()
                beacon = None
                for b in all_beacons:
                    if normalize_mac_address(b.mac_address) == normalized_beacon_mac:
                        beacon = b
                        break
                
                if not beacon:
                    mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
                    if mqtt_config and mqtt_config.auto_discover_beacons:
                        beacon = Beacon(
                            mac_address=msg.beacon_mac,
                            name=f"Auto-{msg.beacon_mac[-8:]}",
                            resource_type="Device",
                            is_active=True
                        )
                        session.add(beacon)
                        session.flush()
                    else:
                        return
                
                if not beacon.is_active:
                    return
                
                signal = RSSISignal(
                    gateway_id=gateway.id,
                    beacon_id=beacon.id,
                    rssi=msg.rssi,
                    tx_power=msg.tx_power,
                    timestamp=msg.timestamp,
                    raw_data=msg.raw_data
                )
                session.add(signal)
                session.commit()
                self._stats['signals_stored'] += 1
                
        except Exception as e:
            error_str = str(e)
            if 'ForeignKeyViolation' in error_str or 'foreign key constraint' in error_str.lower():
                pass
            else:
                self._last_error = f"Signal storage error: {e}"
                self._stats['errors'] += 1
    
    def _calculate_positions(self):
        """Calculate positions for all beacons with recent signals"""
        try:
            with get_db_session() as session:
                window_start = datetime.utcnow() - timedelta(seconds=self._signal_window_seconds)
                
                beacon_signals: Dict[int, Dict[int, List[RSSISignal]]] = {}
                
                recent_signals = session.query(RSSISignal).filter(
                    RSSISignal.timestamp >= window_start
                ).order_by(RSSISignal.timestamp.desc()).all()
                
                for signal in recent_signals:
                    beacon_id = signal.beacon_id
                    gateway_id = signal.gateway_id
                    
                    if beacon_id not in beacon_signals:
                        beacon_signals[beacon_id] = {}
                    
                    if gateway_id not in beacon_signals[beacon_id]:
                        beacon_signals[beacon_id][gateway_id] = []
                    
                    beacon_signals[beacon_id][gateway_id].append(signal)
                
                for beacon_id, gateway_signals in beacon_signals.items():
                    beacon = session.query(Beacon).filter(
                        Beacon.id == beacon_id,
                        Beacon.is_active == True
                    ).first()
                    
                    if not beacon:
                        continue
                    
                    readings = []
                    
                    # Determine floor using multi-floor signal analysis
                    floor_id, floor_confidence = determine_floor_from_signals(gateway_signals, session)
                    
                    if not floor_id:
                        continue
                    
                    # Collect readings from all gateways, preferring those on the determined floor
                    primary_readings = []
                    secondary_readings = []
                    
                    for gateway_id, signals in gateway_signals.items():
                        gateway = session.query(Gateway).filter(
                            Gateway.id == gateway_id,
                            Gateway.is_active == True
                        ).first()
                        
                        if gateway and signals:
                            if self._rssi_smoothing_enabled and len(signals) > 1:
                                weights = []
                                rssi_values = []
                                for i, s in enumerate(signals):
                                    weight = 1.0 / (i + 1)
                                    weights.append(weight)
                                    rssi_values.append(s.rssi)
                                total_weight = sum(weights)
                                avg_rssi = sum(r * w for r, w in zip(rssi_values, weights)) / total_weight
                                rssi = int(round(avg_rssi))
                                tx_power = signals[0].tx_power or -59
                            else:
                                rssi = signals[0].rssi
                                tx_power = signals[0].tx_power or -59
                            
                            reading = GatewayReading(
                                gateway_id=gateway.id,
                                x=gateway.x_position,
                                y=gateway.y_position,
                                rssi=rssi,
                                tx_power=tx_power,
                                path_loss_exponent=gateway.path_loss_exponent or 2.5
                            )
                            
                            # Separate readings by floor
                            if gateway.floor_id == floor_id:
                                primary_readings.append(reading)
                            else:
                                secondary_readings.append(reading)
                    
                    # Use primary floor readings if enough, otherwise fall back to all readings
                    if len(primary_readings) >= 1:
                        readings = primary_readings
                    elif len(secondary_readings) >= 1:
                        # Use all readings if primary floor doesn't have enough
                        readings = primary_readings + secondary_readings
                        floor_confidence *= 0.6  # Reduce confidence when using mixed floors
                    
                    if len(readings) >= 1:
                        # Debug: Log which gateways are being used for triangulation
                        if beacon:
                            gw_info = [(r.gateway_id, r.rssi, round(r.x, 1), round(r.y, 1)) for r in readings]
                            print(f"[TRIANGULATION DEBUG] {beacon.name}: {len(readings)} gateways: {gw_info}")
                        
                        readings = filter_outlier_readings(readings)
                        x, y, accuracy = trilaterate_2d(readings, beacon_id=beacon_id)
                        
                        # Debug: Log calculated position
                        if beacon:
                            print(f"[TRIANGULATION DEBUG] {beacon.name}: Position=({x:.1f}, {y:.1f}), Accuracy={accuracy:.1f}m")
                        
                        if self._position_smoothing_alpha < 1.0 and beacon_id in self._position_history:
                            prev_positions = self._position_history[beacon_id]
                            if prev_positions:
                                x, y = smooth_position((x, y), prev_positions, self._position_smoothing_alpha)
                        
                        if beacon_id not in self._position_history:
                            self._position_history[beacon_id] = []
                        self._position_history[beacon_id].append((x, y))
                        if len(self._position_history[beacon_id]) > 5:
                            self._position_history[beacon_id] = self._position_history[beacon_id][-5:]
                        
                        previous_position = session.query(Position).filter(
                            Position.beacon_id == beacon_id
                        ).order_by(Position.timestamp.desc()).first()
                        
                        velocity_x, velocity_y, speed, heading = 0, 0, 0, 0
                        
                        STABILITY_THRESHOLD = 0.3
                        
                        if previous_position:
                            dx = x - previous_position.x_position
                            dy = y - previous_position.y_position
                            distance_moved = (dx**2 + dy**2) ** 0.5
                            
                            if distance_moved < STABILITY_THRESHOLD:
                                x = previous_position.x_position
                                y = previous_position.y_position
                                velocity_x = 0
                                velocity_y = 0
                                speed = 0
                                heading = previous_position.heading or 0
                            else:
                                time_delta = (datetime.utcnow() - previous_position.timestamp).total_seconds()
                                if 0 < time_delta < 60:
                                    velocity_x, velocity_y, speed, heading = calculate_velocity(
                                        (x, y),
                                        (previous_position.x_position, previous_position.y_position),
                                        time_delta
                                    )
                        
                        position = Position(
                            beacon_id=beacon_id,
                            floor_id=floor_id,
                            x_position=x,
                            y_position=y,
                            accuracy=accuracy,
                            velocity_x=velocity_x,
                            velocity_y=velocity_y,
                            speed=speed,
                            heading=heading,
                            timestamp=datetime.utcnow(),
                            calculation_method='triangulation',
                            floor_confidence=floor_confidence
                        )
                        session.add(position)
                        session.commit()
                        self._stats['positions_calculated'] += 1
                        
                        if self._publisher and self._publisher.is_connected():
                            floor = session.query(Floor).filter(Floor.id == floor_id).first()
                            building_name = ""
                            floor_name = ""
                            if floor:
                                floor_name = floor.name or f"Floor {floor.floor_number}"
                                if floor.building:
                                    building_name = floor.building.name
                            
                            if self._publisher.publish_position(
                                beacon_mac=beacon.mac_address,
                                beacon_name=beacon.name,
                                resource_type=beacon.resource_type or "Device",
                                floor_id=floor_id,
                                floor_name=floor_name,
                                building_name=building_name,
                                x=x,
                                y=y,
                                accuracy=accuracy,
                                speed=speed,
                                heading=heading,
                                velocity_x=velocity_x,
                                velocity_y=velocity_y
                            ):
                                self._stats['positions_published'] += 1
                
        except Exception as e:
            self._last_error = f"Position calculation error: {e}"
            self._stats['errors'] += 1


@st.cache_resource
def get_signal_processor() -> SignalProcessor:
    """Get the singleton signal processor instance.
    Using st.cache_resource keeps the processor alive across Streamlit reruns.
    """
    return SignalProcessor()
