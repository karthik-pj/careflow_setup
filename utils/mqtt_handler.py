import json
import os
import threading
import time
import ssl
from datetime import datetime
from typing import Callable, Optional, Dict, Any
import paho.mqtt.client as mqtt
from dataclasses import dataclass
import queue


@dataclass
class MQTTMessage:
    """Parsed MQTT message from gateway"""
    gateway_mac: str
    beacon_mac: str
    rssi: int
    tx_power: int
    timestamp: datetime
    raw_data: str


class MQTTHandler:
    """MQTT client handler for receiving BLE gateway data"""
    
    def __init__(
        self,
        broker_host: str,
        broker_port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        topic_prefix: str = "ble/gateway/",
        use_tls: bool = False,
        ca_cert_path: Optional[str] = None
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.topic_prefix = topic_prefix
        self.use_tls = use_tls
        self.ca_cert_path = ca_cert_path
        
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        if username and password:
            self.client.username_pw_set(username, password)
        
        if use_tls:
            if ca_cert_path and os.path.exists(ca_cert_path):
                self.client.tls_set(
                    ca_certs=ca_cert_path,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLSv1_2
                )
            else:
                self.client.tls_set(
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS
                )
            self.client.tls_insecure_set(False)
        
        self.is_connected = False
        self.message_queue = queue.Queue(maxsize=10000)
        self.callbacks: list[Callable[[MQTTMessage], None]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.last_error: Optional[str] = None
    
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback when connected to broker"""
        if reason_code == 0:
            self.is_connected = True
            self.last_error = None
            if self.topic_prefix:
                topic = f"{self.topic_prefix}#"
                client.subscribe(topic)
                print(f"Connected to MQTT broker, subscribed to {topic}")
            else:
                print(f"Connected to MQTT broker (no subscription - publish only)")
        else:
            self.is_connected = False
            self.last_error = f"Connection failed with code: {reason_code}"
            print(f"Failed to connect: {reason_code}")
    
    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Callback when disconnected from broker"""
        self.is_connected = False
        if reason_code != 0:
            self.last_error = f"Unexpected disconnection: {reason_code}"
            print(f"Disconnected unexpectedly: {reason_code}")
    
    def _on_message(self, client, userdata, msg):
        """Callback when message received"""
        try:
            parsed_message = self._parse_message(msg.topic, msg.payload)
            if parsed_message:
                try:
                    self.message_queue.put_nowait(parsed_message)
                except queue.Full:
                    self.message_queue.get()
                    self.message_queue.put_nowait(parsed_message)
                
                for callback in self.callbacks:
                    try:
                        callback(parsed_message)
                    except Exception as e:
                        print(f"Callback error: {e}")
        except Exception as e:
            print(f"Message parsing error: {e}")
    
    def _parse_message(self, topic: str, payload: bytes) -> Optional[MQTTMessage]:
        """
        Parse incoming MQTT message from Careflow gateway.
        
        Expected message format (JSON):
        {
            "mac": "AA:BB:CC:DD:EE:FF",
            "gatewayMac": "11:22:33:44:55:66",
            "rssi": -65,
            "txPower": -59,
            "timestamp": 1699999999
        }
        
        Alternative format:
        {
            "type": "Gateway",
            "mac": "11:22:33:44:55:66",
            "bleName": "...",
            "bleMAC": "AA:BB:CC:DD:EE:FF",
            "rssi": -65,
            "rawData": "..."
        }
        """
        try:
            data = json.loads(payload.decode('utf-8'))
            raw_data = payload.decode('utf-8')
            
            gateway_mac = data.get('gatewayMac') or data.get('mac', '')
            beacon_mac = data.get('mac') or data.get('bleMAC', '')
            
            if 'gatewayMac' not in data and 'type' in data:
                gateway_mac = data.get('mac', '')
                beacon_mac = data.get('bleMAC', '')
            
            rssi = int(data.get('rssi', -100))
            tx_power = int(data.get('txPower', data.get('txpower', -59)))
            
            timestamp_val = data.get('timestamp')
            if timestamp_val:
                if isinstance(timestamp_val, (int, float)):
                    if timestamp_val > 1e12:
                        timestamp = datetime.fromtimestamp(timestamp_val / 1000)
                    else:
                        timestamp = datetime.fromtimestamp(timestamp_val)
                else:
                    timestamp = datetime.utcnow()
            else:
                timestamp = datetime.utcnow()
            
            if not gateway_mac or not beacon_mac:
                parts = topic.replace(self.topic_prefix, '').split('/')
                if parts and not gateway_mac:
                    gateway_mac = parts[0]
            
            return MQTTMessage(
                gateway_mac=gateway_mac.upper(),
                beacon_mac=beacon_mac.upper(),
                rssi=rssi,
                tx_power=tx_power,
                timestamp=timestamp,
                raw_data=raw_data
            )
        except json.JSONDecodeError:
            hex_data = payload.hex()
            return None
        except Exception as e:
            print(f"Parse error: {e}")
            return None
    
    def add_callback(self, callback: Callable[[MQTTMessage], None]):
        """Add a callback function to be called on each message"""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[MQTTMessage], None]):
        """Remove a callback function"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def connect(self, timeout: int = 10) -> bool:
        """Connect to the MQTT broker with timeout"""
        try:
            self.client.connect(self.broker_host, self.broker_port, keepalive=60)
            return True
        except ssl.SSLCertVerificationError as e:
            self.last_error = f"SSL certificate error: {e}. Try enabling 'Use TLS/SSL' in config."
            print(f"SSL error: {e}")
            return False
        except ConnectionRefusedError as e:
            self.last_error = f"Connection refused. Check host/port and firewall settings."
            print(f"Connection refused: {e}")
            return False
        except OSError as e:
            if "timed out" in str(e).lower():
                self.last_error = f"Connection timed out. Ensure broker is reachable and port {self.broker_port} is correct."
            else:
                self.last_error = f"Network error: {e}"
            print(f"Connection error: {e}")
            return False
        except Exception as e:
            self.last_error = str(e)
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the broker"""
        self._running = False
        self.client.disconnect()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
    
    def start(self):
        """Start the MQTT client in a background thread"""
        if not self._running:
            self._running = True
            self.client.loop_start()
    
    def stop(self):
        """Stop the MQTT client"""
        self._running = False
        self.client.loop_stop()
    
    def get_messages(self, max_count: int = 100) -> list[MQTTMessage]:
        """Get pending messages from the queue"""
        messages = []
        while len(messages) < max_count:
            try:
                msg = self.message_queue.get_nowait()
                messages.append(msg)
            except queue.Empty:
                break
        return messages
    
    def publish(self, topic: str, payload: Dict[str, Any]) -> bool:
        """Publish a message to a topic"""
        try:
            result = self.client.publish(topic, json.dumps(payload))
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            print(f"Publish error: {e}")
            return False


def create_mqtt_handler_from_config(config: dict) -> MQTTHandler:
    """Create an MQTT handler from configuration dictionary"""
    return MQTTHandler(
        broker_host=config.get('broker_host', 'localhost'),
        broker_port=config.get('broker_port', 1883),
        username=config.get('username'),
        password=config.get('password'),
        topic_prefix=config.get('topic_prefix', 'ble/gateway/'),
        use_tls=config.get('use_tls', False),
        ca_cert_path=config.get('ca_cert_path')
    )
