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
            if self.topic_prefix and self.topic_prefix.strip():
                topic = self.topic_prefix.strip()
                
                if ',' in topic:
                    topics = [t.strip() for t in topic.split(',') if t.strip()]
                    for t in topics:
                        try:
                            client.subscribe(t)
                            print(f"Subscribed to topic: {t}")
                        except ValueError as e:
                            print(f"Invalid subscription topic '{t}': {e}")
                else:
                    if '+' in topic or '#' in topic:
                        pass
                    elif not topic.endswith('/') and not topic.endswith('#'):
                        topic = f"{topic}/#"
                    elif topic.endswith('/'):
                        topic = f"{topic}#"
                    try:
                        client.subscribe(topic)
                        print(f"Connected to MQTT broker, subscribed to {topic}")
                    except ValueError as e:
                        print(f"Invalid subscription topic '{topic}': {e}")
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
                    except Exception:
                        pass
        except Exception:
            pass
    
    def _parse_message(self, topic: str, payload: bytes) -> Optional[MQTTMessage]:
        """
        Parse incoming MQTT message from Moko MKGW-mini03 gateway (CFS/Careflow).
        
        Topic format: /cfs1/{gateway_mac}/send or /cfs2/{gateway_mac}/send
        
        Moko MKGW-mini03 format (JSON):
        {
            "msg_id": "12345",
            "device_info": {
                "mac": "00E04C006BF1",  # gateway MAC (no colons)
                "timestamp": 1699999999
            },
            "beacons": [
                {
                    "type": "iBeacon",
                    "mac": "AABBCCDDEEFF",  # beacon MAC (no colons)
                    "rssi": -65,
                    "raw_data": "0201061AFF4C000215...",
                    "uuid": "FDA50693-A4E2-4FB1-AFCF-C6EB07647825",
                    "major": 100,
                    "minor": 1,
                    "tx_power": -59
                }
            ]
        }
        
        Also supports simple format:
        {
            "gatewayMac": "AA:BB:CC:DD:EE:FF",
            "mac": "11:22:33:44:55:66",
            "rssi": -65,
            "txPower": -59,
            "timestamp": 1699999999
        }
        """
        try:
            raw_data = payload.decode('utf-8')
            data = json.loads(raw_data)
            
            topic_parts = topic.split('/')
            gateway_mac_from_topic = ""
            for i, part in enumerate(topic_parts):
                if len(part) == 12 and all(c in '0123456789abcdefABCDEF' for c in part):
                    gateway_mac_from_topic = ':'.join(part[j:j+2].upper() for j in range(0, 12, 2))
                    break
            
            if 'device_info' in data and ('beacons' in data or 'data' in data):
                device_info = data.get('device_info', {})
                gateway_mac_raw = device_info.get('mac', '')
                if len(gateway_mac_raw) == 12:
                    gateway_mac = ':'.join(gateway_mac_raw[j:j+2].upper() for j in range(0, 12, 2))
                else:
                    gateway_mac = gateway_mac_raw.upper()
                
                if not gateway_mac and gateway_mac_from_topic:
                    gateway_mac = gateway_mac_from_topic
                
                device_timestamp = device_info.get('timestamp')
                if device_timestamp:
                    if isinstance(device_timestamp, (int, float)):
                        if device_timestamp > 1e12:
                            base_timestamp = datetime.fromtimestamp(device_timestamp / 1000)
                        else:
                            base_timestamp = datetime.fromtimestamp(device_timestamp)
                    else:
                        base_timestamp = datetime.utcnow()
                else:
                    base_timestamp = datetime.utcnow()
                
                beacons = data.get('beacons', []) or data.get('data', [])
                
                if not isinstance(beacons, list):
                    return None
                
                if not beacons:
                    return None
                
                # Debug: Log all beacon MACs in this message
                beacon_macs = [b.get('mac', 'unknown') for b in beacons if isinstance(b, dict)]
                if len(beacon_macs) > 0:
                    print(f"[MQTT DEBUG] Gateway {gateway_mac} sent {len(beacon_macs)} beacons: {beacon_macs}")
                
                messages = []
                for beacon in beacons:
                    if not isinstance(beacon, dict):
                        continue
                    beacon_mac_raw = beacon.get('mac', '')
                    if len(beacon_mac_raw) == 12:
                        beacon_mac = ':'.join(beacon_mac_raw[j:j+2].upper() for j in range(0, 12, 2))
                    else:
                        beacon_mac = beacon_mac_raw.upper().replace('-', ':')
                    
                    if not beacon_mac:
                        continue
                    
                    rssi = int(beacon.get('rssi', beacon.get('RSSI', -100)))
                    tx_power = int(beacon.get('tx_power', beacon.get('txPower', beacon.get('measured_power', -59))))
                    
                    msg = MQTTMessage(
                        gateway_mac=gateway_mac,
                        beacon_mac=beacon_mac,
                        rssi=rssi,
                        tx_power=tx_power,
                        timestamp=base_timestamp,
                        raw_data=json.dumps(beacon)
                    )
                    messages.append(msg)
                
                if messages:
                    for msg in messages[1:]:
                        try:
                            self.message_queue.put_nowait(msg)
                        except queue.Full:
                            self.message_queue.get()
                            self.message_queue.put_nowait(msg)
                        for callback in self.callbacks:
                            try:
                                callback(msg)
                            except Exception as e:
                                print(f"Callback error: {e}")
                    
                    return messages[0] if messages else None
                return None
            
            gateway_mac = data.get('gatewayMac') or data.get('gateway_mac', '')
            beacon_mac = data.get('mac') or data.get('bleMAC') or data.get('beacon_mac', '')
            
            if 'gatewayMac' not in data and 'gateway_mac' not in data:
                if 'type' in data and data.get('type') == 'Gateway':
                    gateway_mac = data.get('mac', '')
                    beacon_mac = data.get('bleMAC', '')
                elif gateway_mac_from_topic:
                    gateway_mac = gateway_mac_from_topic
            
            if not gateway_mac and gateway_mac_from_topic:
                gateway_mac = gateway_mac_from_topic
            
            rssi = int(data.get('rssi', data.get('RSSI', -100)))
            tx_power = int(data.get('txPower', data.get('txpower', data.get('tx_power', -59))))
            
            timestamp_val = data.get('timestamp') or data.get('time')
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
            
            if not beacon_mac:
                print(f"[MQTT DEBUG] No beacon MAC found in message: {raw_data[:200]}")
                return None
            
            return MQTTMessage(
                gateway_mac=gateway_mac.upper() if gateway_mac else "",
                beacon_mac=beacon_mac.upper(),
                rssi=rssi,
                tx_power=tx_power,
                timestamp=timestamp,
                raw_data=raw_data
            )
        except json.JSONDecodeError as e:
            print(f"[MQTT DEBUG] JSON decode error: {e}, payload: {payload[:200]}")
            return None
        except Exception as e:
            print(f"Parse error: {e}")
            import traceback
            traceback.print_exc()
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
            self.client.loop_start()
            
            import time
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if not self.is_connected:
                self.client.loop_stop()
                self.last_error = self.last_error or "Connection timeout - broker did not confirm connection"
                return False
            
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
