from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, LargeBinary, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from contextlib import contextmanager
import os

Base = declarative_base()

_engine = None
_SessionLocal = None


class Building(Base):
    """Building information with GPS coordinates"""
    __tablename__ = 'buildings'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    address = Column(String(500))
    latitude = Column(Float)
    longitude = Column(Float)
    boundary_coords = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    floors = relationship("Floor", back_populates="building", cascade="all, delete-orphan")
    gateways = relationship("Gateway", back_populates="building", cascade="all, delete-orphan")


class Floor(Base):
    """Floor plan for each story of a building"""
    __tablename__ = 'floors'
    
    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey('buildings.id'), nullable=False)
    floor_number = Column(Integer, nullable=False)
    name = Column(String(255))
    floor_plan_image = Column(LargeBinary)
    floor_plan_filename = Column(String(255))
    floor_plan_geojson = Column(Text)
    floor_plan_type = Column(String(20), default='image')
    width_meters = Column(Float, default=50.0)
    height_meters = Column(Float, default=50.0)
    origin_lat = Column(Float)
    origin_lon = Column(Float)
    origin_x = Column(Float, default=0)
    origin_y = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    building = relationship("Building", back_populates="floors")
    gateways = relationship("Gateway", back_populates="floor", cascade="all, delete-orphan")
    beacons = relationship("Beacon", back_populates="floor", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="floor", cascade="all, delete-orphan")
    zones = relationship("Zone", back_populates="floor", cascade="all, delete-orphan")
    calibration_points = relationship("CalibrationPoint", back_populates="floor", cascade="all, delete-orphan")


class Gateway(Base):
    """Careflow BLE Gateway configuration"""
    __tablename__ = 'gateways'
    
    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey('buildings.id'), nullable=False)
    floor_id = Column(Integer, ForeignKey('floors.id'), nullable=False)
    mac_address = Column(String(17), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    x_position = Column(Float, nullable=False)
    y_position = Column(Float, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    mqtt_topic = Column(String(255))
    wifi_ssid = Column(String(255))
    is_active = Column(Boolean, default=True)
    signal_strength_calibration = Column(Float, default=-59)
    path_loss_exponent = Column(Float, default=2.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    building = relationship("Building", back_populates="gateways")
    floor = relationship("Floor", back_populates="gateways")
    rssi_signals = relationship("RSSISignal", back_populates="gateway", cascade="all, delete-orphan")


class Beacon(Base):
    """BLE Beacon configuration"""
    __tablename__ = 'beacons'
    
    id = Column(Integer, primary_key=True)
    floor_id = Column(Integer, ForeignKey('floors.id'))
    mac_address = Column(String(17), unique=True, nullable=False)
    uuid = Column(String(36))
    major = Column(Integer)
    minor = Column(Integer)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    resource_type = Column(String(100))
    assigned_to = Column(String(255))
    is_fixed = Column(Boolean, default=False)
    fixed_x = Column(Float)
    fixed_y = Column(Float)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    floor = relationship("Floor", back_populates="beacons")
    rssi_signals = relationship("RSSISignal", back_populates="beacon", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="beacon", cascade="all, delete-orphan")


class RSSISignal(Base):
    """Raw RSSI signal data received from gateways"""
    __tablename__ = 'rssi_signals'
    
    id = Column(Integer, primary_key=True)
    gateway_id = Column(Integer, ForeignKey('gateways.id'), nullable=False)
    beacon_id = Column(Integer, ForeignKey('beacons.id'), nullable=False)
    rssi = Column(Integer, nullable=False)
    tx_power = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    raw_data = Column(Text)
    
    gateway = relationship("Gateway", back_populates="rssi_signals")
    beacon = relationship("Beacon", back_populates="rssi_signals")


class Position(Base):
    """Calculated position from triangulation"""
    __tablename__ = 'positions'
    
    id = Column(Integer, primary_key=True)
    beacon_id = Column(Integer, ForeignKey('beacons.id'), nullable=False)
    floor_id = Column(Integer, ForeignKey('floors.id'), nullable=False)
    x_position = Column(Float, nullable=False)
    y_position = Column(Float, nullable=False)
    accuracy = Column(Float)
    velocity_x = Column(Float, default=0)
    velocity_y = Column(Float, default=0)
    speed = Column(Float, default=0)
    heading = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    calculation_method = Column(String(50), default='triangulation')
    
    beacon = relationship("Beacon", back_populates="positions")
    floor = relationship("Floor", back_populates="positions")


class MQTTConfig(Base):
    """MQTT Broker configuration"""
    __tablename__ = 'mqtt_config'
    
    id = Column(Integer, primary_key=True)
    broker_host = Column(String(255), nullable=False)
    broker_port = Column(Integer, default=1883)
    username = Column(String(255))
    password_env_key = Column(String(255))
    topic_prefix = Column(String(255), default='ble/gateway/')
    use_tls = Column(Boolean, default=False)
    ca_cert_path = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Zone(Base):
    """Geofencing zone definition"""
    __tablename__ = 'zones'
    
    id = Column(Integer, primary_key=True)
    floor_id = Column(Integer, ForeignKey('floors.id'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    zone_type = Column(String(50), default='rectangle')
    x_min = Column(Float, nullable=False)
    y_min = Column(Float, nullable=False)
    x_max = Column(Float, nullable=False)
    y_max = Column(Float, nullable=False)
    color = Column(String(20), default='#FF0000')
    alert_on_enter = Column(Boolean, default=True)
    alert_on_exit = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    floor = relationship("Floor", back_populates="zones")
    alerts = relationship("ZoneAlert", back_populates="zone", cascade="all, delete-orphan")


class ZoneAlert(Base):
    """Zone entry/exit alert events"""
    __tablename__ = 'zone_alerts'
    
    id = Column(Integer, primary_key=True)
    zone_id = Column(Integer, ForeignKey('zones.id'), nullable=False)
    beacon_id = Column(Integer, ForeignKey('beacons.id'), nullable=False)
    alert_type = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    x_position = Column(Float)
    y_position = Column(Float)
    acknowledged = Column(Boolean, default=False)
    
    zone = relationship("Zone", back_populates="alerts")


class CalibrationPoint(Base):
    """Calibration reference points for accuracy improvement"""
    __tablename__ = 'calibration_points'
    
    id = Column(Integer, primary_key=True)
    floor_id = Column(Integer, ForeignKey('floors.id'), nullable=False)
    beacon_id = Column(Integer, ForeignKey('beacons.id'), nullable=False)
    known_x = Column(Float, nullable=False)
    known_y = Column(Float, nullable=False)
    measured_x = Column(Float)
    measured_y = Column(Float)
    error_distance = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_verified = Column(Boolean, default=False)
    
    floor = relationship("Floor", back_populates="calibration_points")


def get_engine():
    """Create database engine from environment variables (singleton)"""
    global _engine
    if _engine is None:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is not set")
        _engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300)
    return _engine


def get_session_factory():
    """Get session factory (singleton)"""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(bind=engine)
    return _SessionLocal


@contextmanager
def get_db_session():
    """Context manager for database sessions - ensures proper cleanup"""
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session():
    """Create a new database session (legacy - use get_db_session context manager instead)"""
    SessionLocal = get_session_factory()
    return SessionLocal()


def init_db():
    """Initialize database tables"""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine
