"""Create the first administrator account so the approval panel can be used.

Run from wihagararamoto_backend:
    .\\venv\\Scripts\\python.exe -m app.seed_admin

Override the defaults with ADMIN_PHONE / ADMIN_PASSWORD environment variables.
"""

import os

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.tables import User, UserRole

DEFAULT_ADMIN_PHONE = "0788000000"
DEFAULT_ADMIN_PASSWORD = "admin123"


def seed_admin() -> None:
    phone = os.getenv("ADMIN_PHONE", DEFAULT_ADMIN_PHONE)
    password = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.phone_number == phone).first()
        if existing is not None:
            print(f"An account with phone {phone} already exists (role: {existing.role.value}).")
            if not existing.password_hash:
                existing.password_hash = hash_password(password)
                existing.is_activated = True
                db.commit()
                print("Added a password so this account can log in.")
            return

        admin = User(
            full_name="System Administrator",
            phone_number=phone,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_activated=True,
        )
        db.add(admin)
        db.commit()
        print(f"Admin account created. Phone: {phone}  Password: {password}")
        print("Change this password before using the app outside your computer.")
    except Exception as error:
        db.rollback()
        print(f"Database error: {error}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
