"""Set or reset a password for an existing account.

Useful for accounts created before login existed, or to recover a forgotten password.

Run from wihagararamoto_backend:
    .\\venv\\Scripts\\python.exe -m app.set_password 0786857654 newpass123
"""

import sys

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.tables import User


def set_password(phone: str, new_password: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone_number == phone).first()
        if user is None:
            print(f"No account found with phone number {phone}.")
            return

        user.password_hash = hash_password(new_password)
        db.commit()
        print(
            f"Password updated for {user.full_name} "
            f"({user.phone_number}, {user.role.value})."
        )
    except Exception as error:
        db.rollback()
        print(f"Database error: {error}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m app.set_password <phone_number> <new_password>")
        raise SystemExit(2)

    phone, new_password = sys.argv[1], sys.argv[2]
    if len(new_password) < 6:
        print("Password must be at least 6 characters.")
        raise SystemExit(2)
    set_password(phone, new_password)
