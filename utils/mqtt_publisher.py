import json
import os
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from utils.mqtt_handler import MQTTHandler
from database import get_db_session, MQTTConfig


class MQTTPublisher:
    """Singleton MQTT publisher for sending positions and alerts to external apps"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.handler: Optional[MQTTHandler] = None
        self.positions_topic: str = 'careflow/positions'
        self.alerts_topic: str = 'careflow/alerts'
        self.enabled: bool = False
        self._connected: bool = False
    
    def configure(self, config: MQTTConfig) -> bool:
        """Configure the publisher from MQTT config"""
        if not config.publish_enabled:
            self.enabled = False
            return True
        
        self.enabled = True
        self.positions_topic = config.publish_positions_topic or 'careflow/positions'
        self.alerts_topic = config.publish_alerts_topic or 'careflow/alerts'
        
        password = None
        if config.password_env_key:
            password = os.environ.get(config.password_env_key)
        
        try:
            if self.handler:
                try:
                    self.handler.stop()
                    self.handler.disconnect()
                except:
                    pass
            
            self.handler = MQTTHandler(
                broker_host=config.broker_host,
                broker_port=config.broker_port,
                username=config.username,
                password=password,
                topic_prefix='',
                use_tls=config.use_tls,
                ca_cert_path=config.ca_cert_path if config.use_tls else None
            )
            
            if self.handler.connect():
                self.handler.start()
                self._connected = True
                print(f"MQTT Publisher connected, publishing to {self.positions_topic} and {self.alerts_topic}")
                return True
            else:
                self._connected = False
                print(f"MQTT Publisher failed to connect: {self.handler.last_error}")
                return False
                
        except Exception as e:
            print(f"MQTT Publisher configuration error: {e}")
            self._connected = False
            return False
    
    def publish_position(self, beacon_mac: str, beacon_name: str, resource_type: str,
                         floor_id: int, floor_name: str, building_name: str,
                         x: float, y: float, accuracy: float,
                         speed: float = 0, heading: float = 0,
                         velocity_x: float = 0, velocity_y: float = 0) -> bool:
        """Publish beacon position to MQTT"""
        if not self.enabled or not self._connected or not self.handler:
            return False
        
        payload = {
            "type": "position",
            "beacon": {
                "mac": beacon_mac,
                "name": beacon_name,
                "resource_type": resource_type
            },
            "location": {
                "floor_id": floor_id,
                "floor_name": floor_name,
                "building_name": building_name,
                "x": round(x, 2),
                "y": round(y, 2),
                "accuracy": round(accuracy, 2)
            },
            "movement": {
                "speed": round(speed, 3),
                "heading": round(heading, 1),
                "velocity_x": round(velocity_x, 3),
                "velocity_y": round(velocity_y, 3)
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        topic = f"{self.positions_topic}/{beacon_mac.replace(':', '')}"
        return self.handler.publish(topic, payload)
    
    def publish_alert(self, alert_type: str, beacon_mac: str, beacon_name: str,
                      zone_id: int, zone_name: str, floor_name: str,
                      x: float, y: float, resource_type: str = None) -> bool:
        """Publish zone alert to MQTT"""
        if not self.enabled or not self._connected or not self.handler:
            return False
        
        payload = {
            "type": "zone_alert",
            "alert_type": alert_type,
            "beacon": {
                "mac": beacon_mac,
                "name": beacon_name,
                "resource_type": resource_type
            },
            "zone": {
                "id": zone_id,
                "name": zone_name,
                "floor_name": floor_name
            },
            "position": {
                "x": round(x, 2),
                "y": round(y, 2)
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        topic = f"{self.alerts_topic}/{alert_type}/{zone_id}"
        return self.handler.publish(topic, payload)
    
    def is_connected(self) -> bool:
        """Check if publisher is connected"""
        return self.enabled and self._connected and self.handler and self.handler.is_connected
    
    def disconnect(self):
        """Disconnect the publisher"""
        if self.handler:
            try:
                self.handler.stop()
                self.handler.disconnect()
            except:
                pass
        self._connected = False


def get_mqtt_publisher() -> MQTTPublisher:
    """Get the singleton MQTT publisher instance"""
    return MQTTPublisher()


def initialize_publisher() -> bool:
    """Initialize the publisher from database config"""
    publisher = get_mqtt_publisher()
    
    try:
        with get_db_session() as session:
            config = session.query(MQTTConfig).filter(MQTTConfig.is_active == True).first()
            if config and config.publish_enabled:
                return publisher.configure(config)
    except Exception as e:
        print(f"Failed to initialize MQTT publisher: {e}")
    
    return False
