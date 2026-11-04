from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import parse_uuid
from app.models import tables
from app.schemas import validations

router = APIRouter(
    prefix="/api/v1/updates",
    tags=["Station Metrics Updates"],
)

ALLOWED_STAFF_ROLES = (
    tables.UserRole.WORKER,
    tables.UserRole.MANAGER,
    tables.UserRole.ADMIN,
)


@router.patch("/metrics", response_model=validations.StationResponse)
def update_station_metrics(
    payload: validations.StationMetricsUpdate,
    db: Session = Depends(get_db),
):
    """Overwrite a station's battery inventory and queue state from the worker app."""
    staff = (
        db.query(tables.User)
        .filter(tables.User.id == parse_uuid(payload.worker_id, "worker"))
        .first()
    )
    if staff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station staff account not found.",
        )
    if staff.role not in ALLOWED_STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only station staff can update station metrics.",
        )
    if staff.role == tables.UserRole.WORKER and not staff.is_activated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This worker account is still pending activation.",
        )

    station = (
        db.query(tables.Station)
        .filter(tables.Station.id == parse_uuid(payload.station_id, "station"))
        .first()
    )
    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found.",
        )

    # Workers may only touch the station their request was approved for;
    # managers may only touch the stations assigned to them.
    if staff.role == tables.UserRole.WORKER and staff.station_id != station.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update the station you were approved to work at.",
        )
    if staff.role == tables.UserRole.MANAGER and station.manager_id != staff.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update stations assigned to you.",
        )

    station.available_batteries = payload.available_batteries
    station.current_queue = tables.QueueStatus[payload.current_queue.value]
    station.last_updated_by = staff.id

    try:
        db.commit()
        db.refresh(station)
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database update failed: {error}",
        )

    return {
        "id": str(station.id),
        "name": station.name,
        "moto_brand": station.moto_brand,
        "available_batteries": station.available_batteries,
        "current_queue": station.current_queue.value,
    }
