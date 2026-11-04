import re

# Rwandan mobile numbers are stored in local form: 0 + 9 digits starting with 7.
_LOCAL_MOBILE = re.compile(r"^07\d{8}$")


def normalize_phone(raw: str) -> str:
    """Normalize +250..., 250..., 9-digit and spaced forms to 07XXXXXXXX.

    Raises ValueError for anything that is not a Rwandan mobile number, so the
    same stored format can be used for uniqueness, login and display.
    """
    digits = re.sub(r"[\s\-()]", "", (raw or "").strip())

    if digits.startswith("+250"):
        digits = "0" + digits[4:]
    elif digits.startswith("250") and len(digits) == 12:
        digits = "0" + digits[3:]
    elif re.fullmatch(r"7\d{8}", digits):
        digits = "0" + digits

    if not _LOCAL_MOBILE.fullmatch(digits):
        raise ValueError("Enter a valid Rwandan mobile number, for example 0788123456.")

    return digits
