from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.core.utils import parse_uuid
from app.models import tables
from app.schemas import validations

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication Engine Mappings"]
)

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(payload: validations.UserCreateInput, db: Session = Depends(get_db)):
    """
    Unified User Registration Processing Endpoint.
    Screens input metrics and inserts records into the PostgreSQL database backend ledger.
    """
    # 1. Integrity check: Verify that the phone profile doesn't already exist in your system tables
    existing_user = db.query(tables.User).filter(tables.User.phone_number == payload.phone_number).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration Error: This phone number is already registered in the system."
        )

    # 2. Admin accounts can only be created by an existing administrator,
    # never through the public self-registration route. Managers may request
    # an account but stay pending until an admin approves them.
    if payload.role == validations.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts are provisioned by an administrator, not self-registered."
        )

    # 3. Strict business rule enforcement mapping: Drivers MUST declare a motorcycle brand
    if payload.role == validations.UserRole.DRIVER and not payload.moto_brand:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business Logic Conflict: Drivers must specify their motorcycle brand selection type."
        )

    # 4. Workers must pick the station they will work at; its manager reviews the request.
    station = None
    if payload.role == validations.UserRole.WORKER:
        if not payload.station_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please choose the station you will work at.",
            )
        station = (
            db.query(tables.Station)
            .filter(tables.Station.id == parse_uuid(payload.station_id, "station"))
            .first()
        )
        if station is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The selected station does not exist.",
            )

    # 5. Secure access initialization loop: Workers and managers default to is_activated = False
    # Drivers can log in automatically since they don't modify station metrics data profiles
    auto_activate = payload.role == validations.UserRole.DRIVER

    # 6. Map the inputs to our physical schema ledger record layout
    new_user = tables.User(
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        moto_brand=payload.moto_brand if payload.role == validations.UserRole.DRIVER else None,
        station_id=station.id if station is not None else None,
        is_activated=auto_activate
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return {
            "status": "success",
            "message": f"Account profile successfully initialized for role: {payload.role.value}",
            "user_id": str(new_user.id),
            "is_activated": new_user.is_activated
        }
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database Ledger Write Exception: {str(error)}"
        )


def _profile_payload(user: tables.User, db: Session) -> dict:
    station = None
    if user.station_id is not None:
        station = (
            db.query(tables.Station)
            .filter(tables.Station.id == user.station_id)
            .first()
        )

    return {
        "user_id": str(user.id),
        "full_name": user.full_name,
        "phone_number": user.phone_number,
        "role": user.role.value,
        "moto_brand": user.moto_brand,
        "station_id": str(user.station_id) if user.station_id else None,
        "station_name": station.name if station else None,
        "is_activated": user.is_activated,
    }


@router.post("/login", response_model=validations.LoginResponse)
def login(payload: validations.LoginInput, db: Session = Depends(get_db)):
    """Validate phone number + password and return the profile the app needs to route the user."""
    user = (
        db.query(tables.User)
        .filter(tables.User.phone_number == payload.phone_number)
        .first()
    )

    # Same message for unknown phone and wrong password so accounts cannot be enumerated.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password.",
        )

    return _profile_payload(user, db)


@router.get("/user/{user_id}", response_model=validations.UserStatusResponse)
def get_user_status(user_id: str, db: Session = Depends(get_db)):
    """Return the current profile state for session restore and worker activation checks."""
    user = (
        db.query(tables.User)
        .filter(tables.User.id == parse_uuid(user_id, "user"))
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found.",
        )

    return _profile_payload(user, db)
