import uuid
from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base

# 1. Strict Enums to eliminate data entry typos
class UserRole(str, enum.Enum):
    DRIVER = "driver"
    WORKER = "worker"
    MANAGER = "manager"
    ADMIN = "admin"

class QueueStatus(str, enum.Enum):
    QUIET = "QUIET"
    MODERATE = "MODERATE"
    VERY_BUSY = "VERY_BUSY"

class StationRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

# 2. Users Table Schema Map
class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True) # Nullable only for accounts created before login existed
    role = Column(SQLEnum(UserRole), nullable=False)
    moto_brand = Column(String, nullable=True) # Nullable for staff roles
    station_id = Column(Uuid(as_uuid=True), nullable=True) # Worker's station; managers manage stations instead
    is_activated = Column(Boolean, default=False) # Access firewall for staff
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# 3. Stations Table Schema Map
class Station(Base):
    __tablename__ = "stations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    moto_brand = Column(String, nullable=False) # Strict 1:1 brand lock
    available_batteries = Column(Integer, default=0) # Single combined metric
    current_queue = Column(SQLEnum(QueueStatus), default=QueueStatus.QUIET)
    landmark = Column(String, nullable=True) # Human directions ("Opposite Kimironko market")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    manager_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    last_updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # Track who updated the station metrics
    last_updated_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)

# 4. Driver Reports Table Schema Map
class DriverReport(Base):
    __tablename__ = "driver_reports"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    station_id = Column(Uuid(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    issue_description = Column(String, nullable=False)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# 5. Station Requests Table Schema Map (managers propose stations, admins approve them)
class StationRequest(Base):
    __tablename__ = "station_requests"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    manager_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    moto_brand = Column(String, nullable=False)
    initial_batteries = Column(Integer, default=0)
    landmark = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(SQLEnum(StationRequestStatus), default=StationRequestStatus.PENDING)
    station_id = Column(Uuid(as_uuid=True), ForeignKey("stations.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
