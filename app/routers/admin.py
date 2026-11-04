from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import parse_uuid
from app.models import tables
from app.schemas import validations

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Administration Panel"],
)

ACTIVATABLE_ROLES = (tables.UserRole.WORKER, tables.UserRole.MANAGER)


def _as_summary(user: tables.User, db: Session) -> dict:
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


def _as_station_request(request: tables.StationRequest, manager_name: str | None) -> dict:
    return {
        "request_id": str(request.id),
        "name": request.name,
        "moto_brand": request.moto_brand,
        "initial_batteries": request.initial_batteries or 0,
        "landmark": request.landmark,
        "latitude": request.latitude,
        "longitude": request.longitude,
        "status": request.status.value,
        "manager_id": str(request.manager_id),
        "manager_name": manager_name,
        "station_id": str(request.station_id) if request.station_id else None,
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else None,
    }


@router.get("/workers", response_model=List[validations.UserStatusResponse])
def list_workers(db: Session = Depends(get_db)):
    """List every station staff account, pending approvals first."""
    workers = (
        db.query(tables.User)
        .filter(tables.User.role.in_(ACTIVATABLE_ROLES))
        .order_by(tables.User.is_activated.asc(), tables.User.full_name.asc())
        .all()
    )
    return [_as_summary(worker, db) for worker in workers]


@router.patch("/activate-worker", response_model=validations.UserStatusResponse)
def activate_worker(
    payload: validations.WorkerActivationUpdate,
    db: Session = Depends(get_db),
):
    """Approve or revoke a station staff account (workers and managers)."""
    worker = (
        db.query(tables.User)
        .filter(tables.User.id == parse_uuid(payload.worker_id, "worker"))
        .first()
    )
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker account not found.",
        )
    if worker.role not in ACTIVATABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only worker or manager accounts can be activated.",
        )

    worker.is_activated = payload.is_activated
    try:
        db.commit()
        db.refresh(worker)
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database update failed: {error}",
        )

    return _as_summary(worker, db)


@router.delete("/workers/{worker_id}")
def reject_pending_staff(
    worker_id: str,
    db: Session = Depends(get_db),
):
    """Delete a pending worker or manager registration the administrator does not accept."""
    staff = (
        db.query(tables.User)
        .filter(tables.User.id == parse_uuid(worker_id, "worker"))
        .first()
    )
    if staff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff account not found.",
        )
    if staff.role not in ACTIVATABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only worker or manager accounts can be rejected.",
        )
    if staff.is_activated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending accounts can be rejected. Deactivate active staff instead.",
        )

    try:
        db.query(tables.StationRequest).filter(
            tables.StationRequest.manager_id == staff.id
        ).delete(synchronize_session=False)
        db.delete(staff)
        db.commit()
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database delete failed: {error}",
        )

    return {"status": "rejected", "user_id": worker_id}


@router.get("/station-requests")
def list_station_requests(db: Session = Depends(get_db)):
    """List every station request, pending ones first."""
    rows = (
        db.query(tables.StationRequest, tables.User.full_name)
        .join(tables.User, tables.User.id == tables.StationRequest.manager_id)
        .order_by(
            case(
                (tables.StationRequest.status == tables.StationRequestStatus.PENDING, 0),
                else_=1,
            ),
            tables.StationRequest.created_at.desc(),
        )
        .all()
    )
    return [_as_station_request(request, manager_name) for request, manager_name in rows]


@router.patch("/station-requests/{request_id}")
def review_station_request(
    request_id: str,
    payload: validations.StationRequestReview,
    db: Session = Depends(get_db),
):
    """Approve a manager's station request (creating the station) or reject it."""
    station_request = (
        db.query(tables.StationRequest)
        .filter(tables.StationRequest.id == parse_uuid(request_id, "station request"))
        .first()
    )
    if station_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station request not found.",
        )
    if station_request.status != tables.StationRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This station request was already reviewed.",
        )

    if payload.is_approved:
        duplicate = (
            db.query(tables.Station)
            .filter(func.lower(tables.Station.name) == station_request.name.lower())
            .first()
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A station with this name already exists.",
            )

        station = tables.Station(
            name=station_request.name,
            moto_brand=station_request.moto_brand,
            available_batteries=station_request.initial_batteries or 0,
            current_queue=tables.QueueStatus.QUIET,
            landmark=station_request.landmark,
            latitude=station_request.latitude,
            longitude=station_request.longitude,
            manager_id=station_request.manager_id,
        )
        db.add(station)
        db.flush()
        station_request.station_id = station.id
        station_request.status = tables.StationRequestStatus.APPROVED
    else:
        station_request.status = tables.StationRequestStatus.REJECTED

    station_request.reviewed_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(station_request)
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database update failed: {error}",
        )

    manager_name = (
        db.query(tables.User.full_name)
        .filter(tables.User.id == station_request.manager_id)
        .scalar()
    )
    return _as_station_request(station_request, manager_name)


@router.get("/reports")
def list_driver_reports(db: Session = Depends(get_db)):
    """List driver-submitted station problems, newest first."""
    rows = (
        db.query(tables.DriverReport, tables.Station.name, tables.User.full_name)
        .join(tables.Station, tables.Station.id == tables.DriverReport.station_id)
        .join(tables.User, tables.User.id == tables.DriverReport.driver_id)
        .order_by(tables.DriverReport.created_at.desc())
        .all()
    )

    return [
        {
            "report_id": str(report.id),
            "station_name": station_name,
            "driver_name": driver_name,
            "issue_description": report.issue_description,
            "is_resolved": report.is_resolved,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }
        for report, station_name, driver_name in rows
    ]


@router.patch("/reports/{report_id}")
def resolve_driver_report(
    report_id: str,
    payload: validations.ReportResolutionUpdate,
    db: Session = Depends(get_db),
):
    """Mark a driver report as resolved (or reopen it)."""
    report = (
        db.query(tables.DriverReport)
        .filter(tables.DriverReport.id == parse_uuid(report_id, "report"))
        .first()
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver report not found.",
        )

    report.is_resolved = payload.is_resolved
    try:
        db.commit()
        db.refresh(report)
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database update failed: {error}",
        )

    return {
        "report_id": str(report.id),
        "is_resolved": report.is_resolved,
    }
