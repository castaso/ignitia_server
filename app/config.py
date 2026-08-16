"""Application configuration, overridable via environment variables or a .env file."""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


class Settings:
    HOST = _env("HOST", "0.0.0.0")
    PORT = int(_env("PORT", "86"))

    JWT_SECRET = _env("JWT_SECRET", "change-me-to-a-long-random-string")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_HOURS = int(_env("JWT_EXPIRE_HOURS", "720"))

    OFFICE_LATITUDE = float(_env("OFFICE_LATITUDE", "23.810331"))
    OFFICE_LONGITUDE = float(_env("OFFICE_LONGITUDE", "90.412521"))
    OFFICE_RADIUS_METERS = float(_env("OFFICE_RADIUS_METERS", "300"))

    OFFICE_START_TIME = _env("OFFICE_START_TIME", "09:00")
    OFFICE_END_TIME = _env("OFFICE_END_TIME", "18:00")

    FACE_SIMILARITY_THRESHOLD = float(_env("FACE_SIMILARITY_THRESHOLD", "0.72"))
    UPLOAD_DIR = _env("UPLOAD_DIR", "uploads/faces")

    # Face embedding matcher (SFace via OpenCV FaceRecognizerSF). When both
    # model files exist, face verification uses embeddings instead of the
    # perceptual-hash baseline. Cosine threshold as recommended for SFace.
    FACE_DETECTOR_MODEL = _env(
        "FACE_DETECTOR_MODEL", "app/data/face_detection_yunet.onnx"
    )
    FACE_EMBEDDING_MODEL = _env(
        "FACE_EMBEDDING_MODEL", "app/data/face_recognition_sface.onnx"
    )
    FACE_EMBEDDING_THRESHOLD = float(_env("FACE_EMBEDDING_THRESHOLD", "0.363"))

    DATABASE_URL = _env("DATABASE_URL", "sqlite:///./ignitia.db")

    # Approval status ids (convention used by the Flutter client).
    APPROVAL_PENDING = 1
    APPROVAL_APPROVED = 2
    APPROVAL_REJECTED = 3

    # Client-side message the app displays when blocked outside the office.
    MESSAGE_OUTSIDE_RANGE = (
        "You are not within the allowed office range. Proxy attendance is blocked."
    )
    MESSAGE_FACE_FAILED = (
        "Face verification failed. The captured face does not match the "
        "registered employee photo. Proxy attendance is blocked."
    )


settings = Settings()
