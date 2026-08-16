"""Security helpers: password hashing, JWT, geo-fence and face verification.

The geo-fence and face checks run on the SERVER (this module is the source
of truth). The client only proves that a live single face was present and
that the device reported coordinates inside range; the server re-validates
both against the configured office and the employee's registered photo.

Face verification: when the bundled SFace (OpenCV FaceRecognizerSF) and YuNet
(OpenCV FaceDetectorYN) models are present and a face is detected in both
images, the capture is matched against the reference photo by embedding
cosine similarity (threshold 0.363 by default). Otherwise it falls back to a
perceptual hash (dHash) + colour-histogram comparison on the detected / centre
face region. Featureless (blank / solid-colour) submissions are rejected.
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
from PIL import Image, ImageOps, ImageStat

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
# Password reset tokens (email-based)
# ---------------------------------------------------------------------------


def generate_reset_token() -> str:
    """Cryptographically random reset token shown only in the reset email."""
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """Store only a digest of the reset token in the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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


try:
    import cv2
except Exception:
    cv2 = None


def _yunet_detector():
    """Lazily build the YuNet face detector (returns None when unavailable)."""
    if cv2 is None:
        return None
    try:
        if not os.path.exists(settings.FACE_DETECTOR_MODEL):
            return None
        return cv2.FaceDetectorYN_create(
            settings.FACE_DETECTOR_MODEL, "", (320, 320)
        )
    except Exception:
        return None


def _sface_recognizer():
    """Lazily build the SFace embedding recognizer (None when unavailable)."""
    if cv2 is None:
        return None
    try:
        if not os.path.exists(settings.FACE_EMBEDDING_MODEL):
            return None
        return cv2.FaceRecognizerSF_create(
            settings.FACE_EMBEDDING_MODEL, ""
        )
    except Exception:
        return None


def _detect_bbox(img: Image.Image):
    """Return (x, y, w, h) ints of the largest detected face, or None when the
    detector is unavailable or no face is found."""
    detector = _yunet_detector()
    if detector is None:
        return None
    try:
        import numpy as np

        bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        height, width = bgr.shape[:2]
        detector.setInputSize((width, height))
        _ok, faces = detector.detect(bgr)
        if faces is None or len(faces) == 0:
            return None
        largest = max(faces, key=lambda f: float(f[2]) * float(f[3]))
        return (int(largest[0]), int(largest[1]), int(largest[2]), int(largest[3]))
    except Exception:
        return None


def _sface_match(img_a: Image.Image, img_b: Image.Image) -> float | None:
    """Cosine similarity via YuNet detection + SFace embeddings, or None when
    the models are unavailable or a face is not detected in either image."""
    detector = _yunet_detector()
    recognizer = _sface_recognizer()
    if detector is None or recognizer is None:
        return None
    try:
        import numpy as np

        def embed(img: Image.Image):
            bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
            height, width = bgr.shape[:2]
            detector.setInputSize((width, height))
            _ok, faces = detector.detect(bgr)
            if faces is None or len(faces) == 0:
                return None
            largest = max(faces, key=lambda f: float(f[2]) * float(f[3]))
            aligned = recognizer.alignCrop(bgr, largest)
            return recognizer.feature(aligned)

        feat_a = embed(img_a)
        feat_b = embed(img_b)
        if feat_a is None or feat_b is None:
            return None
        return float(recognizer.match(feat_a, feat_b, cv2.FACE_RECOGNIZER_SF_FR_COSINE))
    except Exception:
        return None


def _face_region(img: Image.Image) -> Image.Image:
    """Crop to the detected face (with a margin). If no face is detected, fall
    back to the centre 60% of the image - selfie captures are face-centred."""
    detected = _detect_bbox(img)
    width, height = img.size
    if detected is not None:
        x, y, w, h = detected
        margin = 0.2
        left = max(0, int(x - w * margin))
        top = max(0, int(y - h * margin))
        right = min(width, int(x + w * (1 + 2 * margin)))
        bottom = min(height, int(y + h * (1 + 2 * margin)))
        if right - left > 8 and bottom - top > 8:
            return img.crop((left, top, right, bottom))
    cx, cy = width // 2, height // 2
    box_w = max(8, int(width * 0.3))
    box_h = max(8, int(height * 0.3))
    return img.crop(
        (cx - box_w, cy - box_h, cx + box_w, cy + box_h)
    )


def face_similarity(base64_a: str | None, base64_b: str | None) -> float | None:
    """Return similarity in [0,1] or None when either image is undecodable.

    Faces are cropped (YuNet face detection, centre-crop fallback) before
    comparison so the background does not dominate the score.
    """
    img_a = _decode_image(base64_a)
    img_b = _decode_image(base64_b)
    if img_a is None or img_b is None:
        return None
    face_a = _face_region(img_a)
    face_b = _face_region(img_b)
    dhash_a = _dhash(face_a)
    dhash_b = _dhash(face_b)
    # 50% perceptual hash + 50% grayscale histogram similarity.
    score = 0.5 * _hamming(dhash_a, dhash_b) + 0.5 * _histogram_similarity(face_a, face_b)
    return max(0.0, min(1.0, score))


def _is_featureless(img: Image.Image, variance_threshold: float = 10.0) -> bool:
    """True when the (face) region is essentially a flat colour. Featureless
    submissions (blank / solid-colour frames) would otherwise share a nearly
    identical perceptual hash and could pass verification."""
    try:
        stddev = ImageStat.Stat(img.convert("L")).stddev[0]
        return bool(stddev < variance_threshold)
    except Exception:
        return False


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
    img_a = _decode_image(reference_base64)
    img_b = _decode_image(capture_base64)
    if img_a is None or img_b is None:
        return False, "The submitted face image is invalid or could not be decoded."
    if _is_featureless(_face_region(img_a)) or _is_featureless(_face_region(img_b)):
        return False, "The submitted face image is invalid (blank or featureless)."

    # Primary: SFace embedding cosine similarity (when the models are bundled
    # and a face is detected in both images).
    sface_score = _sface_match(img_a, img_b)
    if sface_score is not None:
        if sface_score < settings.FACE_EMBEDDING_THRESHOLD:
            return False, settings.MESSAGE_FACE_FAILED
        return True, ""

    # Fallback: perceptual hash + histogram on the face region.
    score = face_similarity(reference_base64, capture_base64)
    if score is None:
        return False, "The submitted face image is invalid or could not be decoded."
    if score < settings.FACE_SIMILARITY_THRESHOLD:
        return False, settings.MESSAGE_FACE_FAILED
    return True, ""


# ---------------------------------------------------------------------------
# Liveness (blink challenge) frame validation
# ---------------------------------------------------------------------------


def _pixel_mae(img_a: Image.Image, img_b: Image.Image) -> float:
    """Mean absolute pixel difference (0..1) between two down-scaled
    grayscale images. Two identical frames produce 0.0; a blink or head
    motion produces a measurable delta in the eye region."""
    a = img_a.convert("L").resize((64, 64))
    b = img_b.convert("L").resize((64, 64))
    pa = a.getdata()
    pb = b.getdata()
    total = sum(abs(x - y) for x, y in zip(pa, pb))
    return total / (64 * 64 * 255.0)


def validate_liveness_frames(
    frames: list[str] | None, *, required: bool = False
) -> tuple[bool, str]:
    """Validate the liveness frame sequence captured during the blink
    challenge. Returns (ok, error_message).

    Guarantees enforced:
      - a minimum number of frames must be supplied;
      - every frame must decode and contain a non-flat (featureless) image;
      - consecutive frames must show real motion: at least one adjacent pair
        must differ enough that a single replayed still photo is rejected.

    The blink itself is detected client-side (ML Kit eye classification) and
    the frames submitted here prove the capture was a live sequence rather
    than one static image replayed N times.
    """
    if not frames:
        if required:
            return (
                False,
                "Liveness verification is required. "
                "Live face frames were not provided.",
            )
        return True, ""

    if len(frames) < settings.MIN_LIVENESS_FRAMES:
        return (
            False,
            f"Liveness verification requires at least "
            f"{settings.MIN_LIVENESS_FRAMES} live frames.",
        )

    decoded: list[Image.Image] = []
    for frame in frames:
        img = _decode_image(frame)
        if img is None:
            return False, "A liveness frame could not be decoded."
        if _is_featureless(_face_region(img)):
            return False, "A liveness frame is blank or featureless."
        decoded.append(img)

    pair_deltas = [_pixel_mae(a, b) for a, b in zip(decoded, decoded[1:])]
    max_delta = max(pair_deltas) if pair_deltas else 0.0
    if max_delta < settings.LIVENESS_MIN_DIVERSITY:
        return (
            False,
            "Liveness frames show no motion (static or replayed image).",
        )
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
