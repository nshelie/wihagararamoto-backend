import uuid

from app.core.database import SessionLocal
from app.models.tables import Station, QueueStatus

def seed_test_stations():
    print("Initializing WihagararaMoto station seeding script...")
    db = SessionLocal()
    
    try:
        mock_stations = [
            Station(
                id=uuid.uuid4(),
                name="Kimironko Moto Swap Alpha",
                moto_brand="Spiro",
                available_batteries=15,
                current_queue=QueueStatus.QUIET,
                landmark="Hafi ya Kimironko Market, iruhande rwa sitasiyo ya peteroli",
                latitude=-1.9367,
                longitude=30.1266,
            ),
            Station(
                id=uuid.uuid4(),
                name="Nyabugogo Central Hub",
                moto_brand="Spiro",
                available_batteries=4,
                current_queue=QueueStatus.VERY_BUSY,
                landmark="Hafi ya gari ya moshi Nyabugogo, ku muhanda munini",
                latitude=-1.9396,
                longitude=30.0475,
            ),
            Station(
                id=uuid.uuid4(),
                name="Remera Power Box Prime",
                moto_brand="Ampersand",
                available_batteries=28,
                current_queue=QueueStatus.MODERATE,
                landmark="Hafi ya kizunga cya Remera, imbere ya Stade Amahoro",
                latitude=-1.9565,
                longitude=30.1113,
            ),
            Station(
                id=uuid.uuid4(),
                name="Kicukiro Sonatubes Station",
                moto_brand="Spiro",
                available_batteries=9,
                current_queue=QueueStatus.MODERATE,
                landmark="Kuri Sonatubes, hafi y'isoko rya Kicukiro",
                latitude=-1.9713,
                longitude=30.0976,
            ),
            Station(
                id=uuid.uuid4(),
                name="Gahanga E-Moto Exchange",
                moto_brand="Gururide",
                available_batteries=11,
                current_queue=QueueStatus.QUIET,
                landmark="Ku muhanda wa Gahanga, mbere ya stade",
                latitude=-1.9968,
                longitude=30.0916,
            )
        ]

        # Insert only stations that are missing so re-running the script is safe
        existing = {station.name: station for station in db.query(Station).all()}
        new_stations = [station for station in mock_stations if station.name not in existing]

        # Backfill location data for demo stations created before coordinates existed
        for mock in mock_stations:
            current = existing.get(mock.name)
            if current is None:
                continue
            if current.landmark is None and mock.landmark is not None:
                current.landmark = mock.landmark
            if current.latitude is None and mock.latitude is not None:
                current.latitude = mock.latitude
            if current.longitude is None and mock.longitude is not None:
                current.longitude = mock.longitude

        if not new_stations:
            db.commit()
            print("All mock stations already exist. Location data refreshed.")
            return

        db.add_all(new_stations)
        db.commit()
        print(f"Success: {len(new_stations)} mock station(s) committed to the database.")
        
    except Exception as error:
        db.rollback()
        print(f"Database error: {error}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_test_stations()
