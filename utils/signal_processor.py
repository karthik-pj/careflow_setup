import threading
import time
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import streamlit as st

from database import get_db_session, Gateway, Beacon, RSSISignal, Position, MQTTConfig, Floor, Building
from utils.mqtt_handler import MQTTHandler, MQTTMessage
from utils.triangulation import GatewayReading, trilaterate_2d, calculate_velocity, filter_outlier_readings
from utils.mqtt_publisher import get_mqtt_publisher


class SignalProcessor:
    """Background processor for MQTT signals and position calculation"""
    
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
        self._thread: Optional[threading.Thread] = None
        self._last_error: Optional[str] = None
        self._stats = {
            'signals_received': 0,
            'signals_stored': 0,
            'positions_calculated': 0,
            'positions_published': 0,
            'errors': 0
        }
        self._publisher = None
    
    @property
    def is_running(self) -> bool:
        return self._running and self._thread and self._thread.is_alive()
    
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
        """Start the signal processor with MQTT connection"""
        if self.is_running:
            return True
        
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
            
            if not self._mqtt_handler.connect():
                self._last_error = self._mqtt_handler.last_error or "Failed to connect to MQTT broker"
                return False
            
            self._publisher = get_mqtt_publisher()
            with get_db_session() as session:
                mqtt_config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
                if mqtt_config and getattr(mqtt_config, 'publish_enabled', False):
                    self._publisher.configure(mqtt_config)
            
            self._running = True
            
            self._thread = threading.Thread(target=self._process_loop, daemon=True)
            self._thread.start()
            
            self._last_error = None
            return True
            
        except Exception as e:
            self._last_error = str(e)
            return False
    
    def stop(self):
        """Stop the signal processor"""
        self._running = False
        
        if self._mqtt_handler:
            self._mqtt_handler.stop()
            self._mqtt_handler.disconnect()
            self._mqtt_handler = None
        
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
    
    def _process_loop(self):
        """Main processing loop running in background thread"""
        last_position_calc = datetime.utcnow()
        
        while self._running:
            try:
                if self._mqtt_handler:
                    messages = self._mqtt_handler.get_messages(max_count=100)
                    
                    for msg in messages:
                        self._stats['signals_received'] += 1
                        self._store_signal(msg)
                
                if (datetime.utcnow() - last_position_calc).total_seconds() >= 1:
                    self._calculate_positions()
                    last_position_calc = datetime.utcnow()
                
                time.sleep(0.1)
                
            except Exception as e:
                self._last_error = str(e)
                self._stats['errors'] += 1
                time.sleep(1)
    
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
                
                beacon = session.query(Beacon).filter(
                    Beacon.mac_address == msg.beacon_mac
                ).first()
                
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
                
                signal = RSSISignal(
                    gateway_id=gateway.id,
                    beacon_id=beacon.id,
                    rssi=msg.rssi,
                    tx_power=msg.tx_power,
                    timestamp=msg.timestamp,
                    raw_data=msg.raw_data
                )
                session.add(signal)
                self._stats['signals_stored'] += 1
                
        except Exception as e:
            self._last_error = f"Signal storage error: {e}"
            self._stats['errors'] += 1
    
    def _calculate_positions(self):
        """Calculate positions for all beacons with recent signals"""
        try:
            with get_db_session() as session:
                five_seconds_ago = datetime.utcnow() - timedelta(seconds=5)
                
                beacon_signals: Dict[int, Dict[int, RSSISignal]] = {}
                
                recent_signals = session.query(RSSISignal).filter(
                    RSSISignal.timestamp >= five_seconds_ago
                ).order_by(RSSISignal.timestamp.desc()).all()
                
                for signal in recent_signals:
                    beacon_id = signal.beacon_id
                    gateway_id = signal.gateway_id
                    
                    if beacon_id not in beacon_signals:
                        beacon_signals[beacon_id] = {}
                    
                    if gateway_id not in beacon_signals[beacon_id]:
                        beacon_signals[beacon_id][gateway_id] = signal
                
                for beacon_id, gateway_signals in beacon_signals.items():
                    beacon = session.query(Beacon).filter(
                        Beacon.id == beacon_id,
                        Beacon.is_active == True
                    ).first()
                    
                    if not beacon:
                        continue
                    
                    readings = []
                    floor_id = None
                    
                    for gateway_id, signal in gateway_signals.items():
                        gateway = session.query(Gateway).filter(
                            Gateway.id == gateway_id,
                            Gateway.is_active == True
                        ).first()
                        
                        if gateway:
                            readings.append(GatewayReading(
                                gateway_id=gateway.id,
                                x=gateway.x_position,
                                y=gateway.y_position,
                                rssi=signal.rssi,
                                tx_power=signal.tx_power or -59,
                                path_loss_exponent=gateway.path_loss_exponent or 2.0
                            ))
                            floor_id = gateway.floor_id
                    
                    if len(readings) >= 1 and floor_id:
                        readings = filter_outlier_readings(readings)
                        x, y, accuracy = trilaterate_2d(readings)
                        
                        previous_position = session.query(Position).filter(
                            Position.beacon_id == beacon_id
                        ).order_by(Position.timestamp.desc()).first()
                        
                        velocity_x, velocity_y, speed, heading = 0, 0, 0, 0
                        
                        if previous_position:
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
                            calculation_method='triangulation'
                        )
                        session.add(position)
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


def get_signal_processor() -> SignalProcessor:
    """Get the singleton signal processor instance"""
    return SignalProcessor()
