from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from enum import Enum

from app.core.phone import normalize_phone

class UserRole(str, Enum):
    DRIVER = "driver"
    WORKER = "worker"
    MANAGER = "manager"
    ADMIN = "admin"

# Validation model for incoming user registration payloads
class UserCreateInput(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    phone_number: str = Field(..., max_length=20)
    password: str = Field(..., min_length=6, max_length=72)
    role: UserRole
    moto_brand: Optional[str] = None # Strict constraint rule: Nullable for non-drivers
    station_id: Optional[str] = None # Required for workers, ignored for other roles

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: str) -> str:
        return normalize_phone(value)

    class Config:
        from_attributes = True


class LoginInput(BaseModel):
    phone_number: str = Field(..., max_length=20)
    password: str = Field(..., min_length=1, max_length=72)

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: str) -> str:
        return normalize_phone(value)


class LoginResponse(BaseModel):
    user_id: str
    full_name: str
    phone_number: str
    role: str
    moto_brand: Optional[str] = None
    station_id: Optional[str] = None
    station_name: Optional[str] = None
    is_activated: bool
# Validation schema model for sending clean station information to the mobile app
class StationResponse(BaseModel):
    id: str
    name: str
    moto_brand: str
    available_batteries: int
    current_queue: str
    landmark: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    class Config:
        from_attributes = True


class QueueStateInput(str, Enum):
    QUIET = "QUIET"
    MODERATE = "MODERATE"
    VERY_BUSY = "VERY_BUSY"


class StationMetricsUpdate(BaseModel):
    station_id: str
    worker_id: str
    available_batteries: int = Field(..., ge=0, le=500)
    current_queue: QueueStateInput


class DriverReportCreate(BaseModel):
    driver_id: str
    station_id: str
    issue_description: str = Field(..., min_length=3, max_length=500)


class WorkerActivationUpdate(BaseModel):
    worker_id: str
    is_activated: bool


class ReportResolutionUpdate(BaseModel):
    is_resolved: bool


class UserStatusResponse(BaseModel):
    user_id: str
    full_name: str
    phone_number: str
    role: str
    moto_brand: Optional[str] = None
    station_id: Optional[str] = None
    station_name: Optional[str] = None
    is_activated: bool


class StationRequestCreate(BaseModel):
    manager_id: str
    name: str = Field(..., min_length=2, max_length=100)
    moto_brand: str = Field(..., min_length=2, max_length=50)
    initial_batteries: int = Field(default=0, ge=0, le=500)
    landmark: Optional[str] = Field(default=None, max_length=160)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def check_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude, or neither.")
        return self


class StationRequestReview(BaseModel):
    is_approved: bool


class ManagerWorkerActivation(BaseModel):
    manager_id: str
    worker_id: str
    is_activated: bool


class ManagerReportResolution(BaseModel):
    manager_id: str
    is_resolved: bool


# Validation schema model for incoming station metric updates from workers
class StationUpdateInput(BaseModel):
    worker_id: str
    station_id: str
    available_batteries: int = Field(..., ge=0) # Enforces that battery numbers can never be negative
    queue_status: str # Must be QUIET, MODERATE, or VERY_BUSY

    class Config:
        from_attributes = True