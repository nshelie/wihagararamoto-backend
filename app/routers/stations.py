from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import parse_uuid
from app.models import tables
from app.schemas import validations

router = APIRouter(
    prefix="/api/v1/stations",
    tags=["Driver Stations Query Engine"],
)


def _as_station(station: tables.Station) -> dict:
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


@router.get("", response_model=List[validations.StationResponse])
def list_stations(db: Session = Depends(get_db)):
    """Return every station, used by the worker panel to pick a station."""
    stations = db.query(tables.Station).order_by(tables.Station.name.asc()).all()
    return [_as_station(station) for station in stations]


@router.get("/filter", response_model=List[validations.StationResponse])
def get_filtered_stations(moto_brand: str, db: Session = Depends(get_db)):
    """Return all stations matching the driver's motorcycle brand."""
    matching_stations = (
        db.query(tables.Station)
        .filter(tables.Station.moto_brand.ilike(moto_brand))
        .all()
    )

    return [_as_station(station) for station in matching_stations]


@router.get("/{station_id}", response_model=validations.StationResponse)
def get_station(station_id: str, db: Session = Depends(get_db)):
    """Return one station, used by the worker panel for its assigned station."""
    station = (
        db.query(tables.Station)
        .filter(tables.Station.id == parse_uuid(station_id, "station"))
        .first()
    )
    if station is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Station not found.",
        )

    return _as_station(station)


@router.post("/report", status_code=status.HTTP_201_CREATED)
def report_station_issue(
    payload: validations.DriverReportCreate,
    db: Session = Depends(get_db),
):
    """Store a driver-submitted station issue report."""
    driver = (
        db.query(tables.User)
        .filter(tables.User.id == parse_uuid(payload.driver_id, "driver"))
        .first()
    )
    if driver is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver account not found.",
        )
    if driver.role != tables.UserRole.DRIVER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only drivers can submit station reports.",
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

    report = tables.DriverReport(
        station_id=station.id,
        driver_id=driver.id,
        issue_description=payload.issue_description.strip(),
    )

    try:
        db.add(report)
        db.commit()
        db.refresh(report)
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write failed: {error}",
        )

    return {
        "status": "success",
        "report_id": str(report.id),
        "message": f"Report submitted for {station.name}.",
    }
