from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import parse_uuid
from app.models import tables
from app.schemas import validations

router = APIRouter(
    prefix="/api/v1/manager",
    tags=["Manager Panel"],
)


def _require_manager(manager_id: str, db: Session) -> tables.User:
    manager = (
        db.query(tables.User)
        .filter(tables.User.id == parse_uuid(manager_id, "manager"))
        .first()
    )
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager account not found.",
        )
    if manager.role != tables.UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only manager accounts can use this panel.",
        )
    if not manager.is_activated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This manager account is waiting for administrator approval.",
        )
    return manager


def _station_payload(station: tables.Station) -> dict:
    return {
        "id": str(station.id),
        "name": station.name,
        "moto_brand": station.moto_brand,
        "available_batteries": station.available_batteries,
        "current_queue": station.current_queue.value if station.current_queue else "QUIET",
        "landmark": station.landmark,
        "latitude": station.latitude,
        "longitude": station.longitude,
    }


def _worker_payload(worker: tables.User, station_name: str | None) -> dict:
    return {
        "user_id": str(worker.id),
        "full_name": worker.full_name,
        "phone_number": worker.phone_number,
        "role": worker.role.value,
        "station_id": str(worker.station_id) if worker.station_id else None,
        "station_name": station_name,
        "is_activated": worker.is_activated,
    }


def _request_payload(request: tables.StationRequest) -> dict:
    return {
        "request_id": str(request.id),
        "name": request.name,
        "moto_brand": request.moto_brand,
        "initial_batteries": request.initial_batteries or 0,
        "landmark": request.landmark,
        "latitude": request.latitude,
        "longitude": request.longitude,
        "status": request.status.value,
        "station_id": str(request.station_id) if request.station_id else None,
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else None,
    }


@router.get("/overview")
def get_overview(manager_id: str, db: Session = Depends(get_db)):
    """Everything the manager dashboard shows: stations, workers, requests and reports."""
    manager = _require_manager(manager_id, db)

    stations = (
        db.query(tables.Station)
        .filter(tables.Station.manager_id == manager.id)
        .order_by(tables.Station.name.asc())
        .all()
    )
    station_ids = [station.id for station in stations]
    station_names = {str(station.id): station.name for station in stations}

    workers = []
    if station_ids:
        staff = (
            db.query(tables.User)
            .filter(
                tables.User.role == tables.UserRole.WORKER,
                tables.User.station_id.in_(station_ids),
            )
            .order_by(tables.User.is_activated.asc(), tables.User.full_name.asc())
            .all()
        )
        workers = [
            _worker_payload(worker, station_names.get(str(worker.station_id)))
            for worker in staff
        ]

    requests = (
        db.query(tables.StationRequest)
        .filter(tables.StationRequest.manager_id == manager.id)
        .order_by(
            case(
                (tables.StationRequest.status == tables.StationRequestStatus.PENDING, 0),
                else_=1,
            ),
            tables.StationRequest.created_at.desc(),
        )
        .all()
    )

    reports = []
    if station_ids:
        rows = (
            db.query(tables.DriverReport, tables.Station.name, tables.User.full_name)
            .join(tables.Station, tables.Station.id == tables.DriverReport.station_id)
            .join(tables.User, tables.User.id == tables.DriverReport.driver_id)
            .filter(tables.Station.manager_id == manager.id)
            .order_by(tables.DriverReport.created_at.desc())
            .all()
        )
        reports = [
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

    return {
        "manager": {
            "user_id": str(manager.id),
            "full_name": manager.full_name,
        },
        "stations": [_station_payload(station) for station in stations],
        "workers": workers,
        "station_requests": [_request_payload(request) for request in requests],
        "reports": reports,
    }


@router.patch("/workers/activation")
def activate_station_worker(
    payload: validations.ManagerWorkerActivation,
    db: Session = Depends(get_db),
):
    """Approve or revoke a worker who registered for one of the manager's stations."""
    manager = _require_manager(payload.manager_id, db)

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
    if worker.role != tables.UserRole.WORKER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only worker accounts can be approved here.",
        )
    if worker.station_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This worker did not choose a station.",
        )

    station = (
        db.query(tables.Station)
        .filter(tables.Station.id == worker.station_id)
        .first()
    )
    if station is None or station.manager_id != manager.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This worker is not assigned to one of your stations.",
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

    return _worker_payload(worker, station.name)


@router.delete("/workers/{worker_id}")
def reject_station_worker(
    worker_id: str,
    manager_id: str,
    db: Session = Depends(get_db),
):
    """Delete a pending worker registration for one of the manager's stations."""
    manager = _require_manager(manager_id, db)

    worker = (
        db.query(tables.User)
        .filter(tables.User.id == parse_uuid(worker_id, "worker"))
        .first()
    )
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker account not found.",
        )
    if worker.role != tables.UserRole.WORKER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only worker accounts can be rejected here.",
        )
    if worker.is_activated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending workers can be rejected. Revoke access instead.",
        )
    if worker.station_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This worker did not choose a station.",
        )

    station = (
        db.query(tables.Station)
        .filter(tables.Station.id == worker.station_id)
        .first()
    )
    if station is None or station.manager_id != manager.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This worker is not assigned to one of your stations.",
        )

    try:
        db.delete(worker)
        db.commit()
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database delete failed: {error}",
        )

    return {"status": "rejected", "user_id": worker_id}


@router.post("/station-requests", status_code=status.HTTP_201_CREATED)
def create_station_request(
    payload: validations.StationRequestCreate,
    db: Session = Depends(get_db),
):
    """Ask the administrator to open a new station managed by this manager."""
    manager = _require_manager(payload.manager_id, db)
    name = payload.name.strip()
    moto_brand = payload.moto_brand.strip()

    duplicate_station = (
        db.query(tables.Station)
        .filter(func.lower(tables.Station.name) == name.lower())
        .first()
    )
    if duplicate_station is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A station with this name already exists.",
        )

    duplicate_request = (
        db.query(tables.StationRequest)
        .filter(
            tables.StationRequest.manager_id == manager.id,
            tables.StationRequest.status == tables.StationRequestStatus.PENDING,
            func.lower(tables.StationRequest.name) == name.lower(),
        )
        .first()
    )
    if duplicate_request is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a pending request for this station.",
        )

    station_request = tables.StationRequest(
        manager_id=manager.id,
        name=name,
        moto_brand=moto_brand,
        initial_batteries=payload.initial_batteries,
        landmark=payload.landmark.strip() if payload.landmark and payload.landmark.strip() else None,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )

    try:
        db.add(station_request)
        db.commit()
        db.refresh(station_request)
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write failed: {error}",
        )

    return _request_payload(station_request)


@router.patch("/reports/{report_id}")
def resolve_report(
    report_id: str,
    payload: validations.ManagerReportResolution,
    db: Session = Depends(get_db),
):
    """Resolve or reopen a driver report for one of the manager's stations."""
    manager = _require_manager(payload.manager_id, db)

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

    station = (
        db.query(tables.Station)
        .filter(tables.Station.id == report.station_id)
        .first()
    )
    if station is None or station.manager_id != manager.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This report belongs to a station you do not manage.",
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
