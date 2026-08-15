"""Security helpers: password hashing, JWT, geo-fence and face verification.

The geo-fence and face checks run on the SERVER (this module is the source
of truth). The client only proves that a live single face was present and
that the device reported coordinates inside range; the server re-validates
both against the configured office and the employee's registered photo.

Face verification uses a perceptual hash (dHash) + colour-histogram
similarity. It is a lightweight, dependency-light baseline (only Pillow) and
is NOT a state-of-the-art face matcher - swap
``FACE_VERIFICATION_METHOD`` for a real embedding model (e.g. FaceNet/ArcFace)
in production.
"""

import base64
import binascii
import hashlib
import hmac
import io
import os
import secrets
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt

import jwt
from PIL import Image, ImageOps

from .config import settings

# ---------------------------------------------------------------------------
# Password hashing (stdlib PBKDF2 - no native deps)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
        ).hex()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def create_token(employee_id: int) -> str:
    payload = {
        "sub": str(employee_id),
        "exp": datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str):
    """Return the employee id (int) or None."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return int(payload["sub"])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Geo-fence (haversine distance in metres)
# ---------------------------------------------------------------------------


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates in metres."""
    earth_radius = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return earth_radius * 2 * asin(sqrt(a))


def is_within_office(latitude: float | None, longitude: float | None) -> bool:
    """Return True only when the supplied coordinates are inside the configured
    geo-fence. Any missing/None coordinate fails closed."""
    if latitude is None or longitude is None:
        return False
    try:
        distance = haversine_meters(
            float(latitude),
            float(longitude),
            settings.OFFICE_LATITUDE,
            settings.OFFICE_LONGITUDE,
        )
    except (TypeError, ValueError):
        return False
    return distance <= settings.OFFICE_RADIUS_METERS


# ---------------------------------------------------------------------------
# Face verification
# ---------------------------------------------------------------------------


def _decode_image(base64_str: str | None) -> Image.Image | None:
    """Decode a base64 JPEG/PNG string into a PIL image (RGB)."""
    if not base64_str:
        return None
    try:
        # The client may send a data-URL prefix; strip it if present.
        if base64_str.startswith("data:"):
            base64_str = base64_str.split(",", 1)[1]
        raw = base64.b64decode(base64_str, validate=True)
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img).convert("RGB")
        return img
    except (binascii.Error, ValueError, OSError, Image.DecompressionBombError):
        return None


def _dhash(img: Image.Image, hash_size: int = 8) -> str:
    """Difference hash: compare horizontally adjacent pixels."""
    gray = ImageOps.grayscale(img.resize((hash_size + 1, hash_size)))
    px = gray.load()
    bits = []
    for y in range(hash_size):
        for x in range(hash_size):
            bits.append(1 if px[x, y] > px[x + 1, y] else 0)
    return "".join(str(b) for b in bits)


def _histogram_similarity(img_a: Image.Image, img_b: Image.Image) -> float:
    size = (32, 32)
    hist_a = img_a.resize(size).convert("L").histogram()
    hist_b = img_b.resize(size).convert("L").histogram()
    total = 0
    diff = 0
    for va, vb in zip(hist_a, hist_b):
        total += va + vb
        diff += abs(va - vb)
    if total == 0:
        return 1.0
    return 1.0 - (diff / (2 * total))


def _hamming(a: str, b: str) -> float:
    if len(a) != len(b):
        return 0.0
    diff = sum(1 for x, y in zip(a, b) if x != y)
    return 1.0 - (diff / len(a))


def face_similarity(base64_a: str | None, base64_b: str | None) -> float | None:
    """Return similarity in [0,1] or None when either image is undecodable."""
    img_a = _decode_image(base64_a)
    img_b = _decode_image(base64_b)
    if img_a is None or img_b is None:
        return None
    dhash_a = _dhash(img_a)
    dhash_b = _dhash(img_b)
    # 50% perceptual hash + 50% grayscale histogram similarity.
    score = 0.5 * _hamming(dhash_a, dhash_b) + 0.5 * _histogram_similarity(img_a, img_b)
    return max(0.0, min(1.0, score))


def verify_face(reference_base64: str | None, capture_base64: str | None) -> tuple[bool, str]:
    """Server-side face verification. Returns (ok, error_message).

    Fails closed: if there is no reference photo or the capture cannot be
    decoded, verification is rejected.
    """
    if not reference_base64:
        return (
            False,
            "No reference face is registered for this employee. "
            "Face verification cannot be performed.",
        )
    score = face_similarity(reference_base64, capture_base64)
    if score is None:
        return False, "The submitted face image is invalid or could not be decoded."
    if score < settings.FACE_SIMILARITY_THRESHOLD:
        return False, settings.MESSAGE_FACE_FAILED
    return True, ""


# ---------------------------------------------------------------------------
# Face snapshot storage
# ---------------------------------------------------------------------------


def store_face_snapshot(base64_str: str | None, filename: str) -> str | None:
    """Decode and persist a captured face to disk. Returns the stored path."""
    if not base64_str:
        return None
    img = _decode_image(base64_str)
    if img is None:
        return None
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, filename)
    img.save(path, "JPEG", quality=85)
    return path
