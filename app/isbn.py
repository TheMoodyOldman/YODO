"""ISBN parsing for the book scanner: validate check digits, convert ISBN-10 to ISBN-13, and pick ISBNs
out of barcode payloads or text read from a copyright page.

Taiwan-published books mostly start 978-957, 978-986 or 978-626.
"""

import re

# A run of digits (and X) joined only by spaces, tabs or dashes: "978-986-7778-17-8", "978 986 …".
# Text is read run by run so a number is never cut in the middle: the first ten digits of an ISBN-13
# often form a valid ISBN-10 by chance (978-986-7778-17-8 -> 9789867778), which would open the wrong book.
_RUN = re.compile(r"[0-9Xx](?:[ \t\-‐-―]*[0-9Xx])*")


def _isbn13_ok(digits: str) -> bool:
    if len(digits) != 13 or not digits.isdigit() or digits[:3] not in ("978", "979"):
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    return total % 10 == 0


def _isbn10_ok(digits: str) -> bool:
    if len(digits) != 10 or not digits[:9].isdigit() or not (digits[9].isdigit() or digits[9] == "X"):
        return False
    total = sum((10 - i) * (10 if d == "X" else int(d)) for i, d in enumerate(digits))
    return total % 11 == 0


def _to_13(isbn10: str) -> str:
    core = "978" + isbn10[:9]
    check = (10 - sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core)) % 10) % 10
    return core + str(check)


def normalize(value: str | None) -> str | None:
    """Return a valid ISBN-13 for an ISBN-10 or ISBN-13 in any common spelling, else None."""
    if not value:
        return None
    digits = re.sub(r"[\s\-]", "", value).upper().removeprefix("ISBN").lstrip(":：")
    if _isbn13_ok(digits):
        return digits
    if _isbn10_ok(digits):
        return _to_13(digits)
    return None


def _from_run(digits: str) -> list[str]:
    """ISBNs in one run of digits. 13+ digits: valid ISBN-13 windows (a barcode's 5-digit price add-on can
    be glued on). Exactly 10: an ISBN-10, unless it starts 978/979 (then it is an ISBN-13 that lost digits).
    Anything else is not trusted: guessing from part of a number finds the wrong book."""
    if len(digits) == 10:
        return [_to_13(digits)] if _isbn10_ok(digits) and digits[:3] not in ("978", "979") else []
    found, i = [], 0
    while i + 13 <= len(digits):
        if _isbn13_ok(digits[i:i + 13]):
            found.append(digits[i:i + 13])
            i += 13
        else:
            i += 1
    return found


def find_all(text: str | None) -> list[str]:
    """Every valid ISBN in free text (barcode payload, copyright page, OCR), as ISBN-13, in order, no repeats."""
    found: list[str] = []
    for match in _RUN.finditer(text or ""):
        digits = re.sub(r"[^0-9X]", "", match.group(0).upper())
        for isbn in _from_run(digits):
            if isbn not in found:
                found.append(isbn)
    return found


def pretty(isbn13: str) -> str:
    """978-XXXXXXXXX-X: a readable form that does not pretend to know the publisher split."""
    return f"{isbn13[:3]}-{isbn13[3:12]}-{isbn13[12]}"
