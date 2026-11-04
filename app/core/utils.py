from uuid import UUID

from fastapi import HTTPException, status


def parse_uuid(value: str, label: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label} identifier.",
        ) from None
