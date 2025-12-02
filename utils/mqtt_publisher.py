import json
import os
import threading
import queue
from datetime import datetime
from typing import Optional, Dict, Any
import paho.mqtt.client as mqtt
import ssl
from database import get_db_session, MQTTConfig


class MQTTPublisher:
    """Thread-safe singleton MQTT publisher for sending positions and alerts to external apps"""
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._client: Optional[mqtt.Client] = None
        self._publish_lock = threading.Lock()
        self._config_lock = threading.Lock()
        self.positions_topic: str = 'careflow/positions'
        self.alerts_topic: str = 'careflow/alerts'
        self.enabled: bool = False
        self._connected: bool = False
        self._publish_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._publish_thread: Optional[threading.Thread] = None
        self._running: bool = False
    
    def configure(self, config: MQTTConfig) -> bool:
        """Configure the publisher from MQTT config (thread-safe)"""
        with self._config_lock:
            if not config.publish_enabled:
                self.enabled = False
                self._stop_publish_thread()
                return True
            
            self.enabled = True
            self.positions_topic = config.publish_positions_topic or 'careflow/positions'
            self.alerts_topic = config.publish_alerts_topic or 'careflow/alerts'
            
            password = None
            if config.password_env_key:
                password = os.environ.get(config.password_env_key)
            
            try:
                if self._client:
                    try:
                        self._client.loop_stop()
                        self._client.disconnect()
                    except:
                        pass
                
                self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                self._client.on_connect = self._on_connect
                self._client.on_disconnect = self._on_disconnect
                
                if config.username and password:
                    self._client.username_pw_set(config.username, password)
                
                if config.use_tls:
                    ca_cert_path = config.ca_cert_path
                    if ca_cert_path and os.path.exists(ca_cert_path):
                        self._client.tls_set(
                            ca_certs=ca_cert_path,
                            cert_reqs=ssl.CERT_REQUIRED,
                            tls_version=ssl.PROTOCOL_TLSv1_2
                        )
                    else:
                        self._client.tls_set(
                            cert_reqs=ssl.CERT_REQUIRED,
                            tls_version=ssl.PROTOCOL_TLS
                        )
                    self._client.tls_insecure_set(False)
                
                self._client.connect(config.broker_host, config.broker_port, keepalive=60)
                self._client.loop_start()
                self._start_publish_thread()
                print(f"MQTT Publisher configured, publishing to {self.positions_topic} and {self.alerts_topic}")
                return True
                    
            except Exception as e:
                print(f"MQTT Publisher configuration error: {e}")
                self._connected = False
                return False
    
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback when connected to broker"""
        if reason_code == 0:
            self._connected = True
            print("MQTT Publisher connected to broker")
        else:
            self._connected = False
            print(f"MQTT Publisher connection failed: {reason_code}")
    
    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Callback when disconnected from broker"""
        self._connected = False
        if reason_code != 0:
            print(f"MQTT Publisher disconnected unexpectedly: {reason_code}")
    
    def _start_publish_thread(self):
        """Start the async publish thread"""
        if not self._running:
            self._running = True
            self._publish_thread = threading.Thread(target=self._publish_loop, daemon=True)
            self._publish_thread.start()
    
    def _stop_publish_thread(self):
        """Stop the async publish thread"""
        self._running = False
        if self._publish_thread:
            self._publish_thread.join(timeout=2)
            self._publish_thread = None
    
    def _publish_loop(self):
        """Background thread for publishing messages asynchronously"""
        while self._running:
            try:
                msg = self._publish_queue.get(timeout=1)
                if msg and self._connected and self._client:
                    with self._publish_lock:
                        try:
                            result = self._client.publish(msg['topic'], json.dumps(msg['payload']))
                            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                                print(f"MQTT Publish failed for topic {msg['topic']}: rc={result.rc}")
                        except Exception as e:
                            print(f"MQTT Publish error: {e}")
            except queue.Empty:
                continue
            except Exception as e:
                print(f"MQTT Publish loop error: {e}")
    
    def _enqueue_message(self, topic: str, payload: Dict[str, Any]) -> bool:
        """Enqueue a message for async publishing (non-blocking)"""
        if not self.enabled:
            return False
        
        try:
            self._publish_queue.put_nowait({'topic': topic, 'payload': payload})
            return True
        except queue.Full:
            print(f"MQTT Publish queue full, dropping message for topic: {topic}")
            return False
    
    def publish_position(self, beacon_mac: str, beacon_name: str, resource_type: str,
                         floor_id: int, floor_name: str, building_name: str,
                         x: float, y: float, accuracy: float,
                         speed: float = 0, heading: float = 0,
                         velocity_x: float = 0, velocity_y: float = 0) -> bool:
        """Publish beacon position to MQTT (async, non-blocking)"""
        if not self.enabled:
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
        return self._enqueue_message(topic, payload)
    
    def publish_alert(self, alert_type: str, beacon_mac: str, beacon_name: str,
                      zone_id: int, zone_name: str, floor_name: str,
                      x: float, y: float, resource_type: str = None) -> bool:
        """Publish zone alert to MQTT (async, non-blocking)"""
        if not self.enabled:
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
        return self._enqueue_message(topic, payload)
    
    def is_connected(self) -> bool:
        """Check if publisher is connected"""
        return self.enabled and self._connected and self._client is not None
    
    def disconnect(self):
        """Disconnect the publisher"""
        self._stop_publish_thread()
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
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
