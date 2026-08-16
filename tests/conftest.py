"""Shared fixtures. Environment variables must be set BEFORE importing the app
so the isolated temp database is used."""

import base64
import io
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="ignitia_test_")

os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "faces")
os.environ["JWT_SECRET"] = "test-secret-0123456789-0123456789-0123456789"
os.environ["OFFICE_LATITUDE"] = "23.810331"
os.environ["OFFICE_LONGITUDE"] = "90.412521"
os.environ["OFFICE_RADIUS_METERS"] = "300"
os.environ["OFFICE_START_TIME"] = "09:00"
os.environ["OFFICE_END_TIME"] = "18:00"
os.environ["FACE_SIMILARITY_THRESHOLD"] = "0.72"

import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Employee, LeaveType
from app.security import hash_password


def make_face(color=(235, 200, 170), eyes=True):
    """Generate a deterministic synthetic 'face' as a base64 JPEG. Identical
    calls produce identical images so face verification passes for the same
    face and fails for clearly different ones."""
    img = Image.new("RGB", (120, 120), color)
    if eyes:
        draw = ImageDraw.Draw(img)
        draw.ellipse([35, 30, 85, 80], fill=(200, 150, 120))
        draw.ellipse([48, 50, 58, 62], fill=(40, 30, 25))
        draw.ellipse([62, 50, 72, 62], fill=(40, 30, 25))
        draw.rectangle([50, 70, 70, 76], fill=(160, 100, 80))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture(scope="session", autouse=True)
def _db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if db.query(Employee).count() == 0:
        demo = Employee(
            employee_id="EMP001",
            name="Demo Employee",
            designation="Software Engineer",
            email="demo@ignitia.local",
            type_id=2,
            status_id=1,
            basic_salary=30000.0,
        )
        demo.password_hash = hash_password("demo1234")
        demo.reference_face = make_face()
        db.add(demo)
        admin = Employee(
            employee_id="ADM001",
            name="Admin",
            designation="HR Manager",
            email="admin@ignitia.local",
            type_id=1,
            status_id=1,
        )
        admin.password_hash = hash_password("admin1234")
        admin.reference_face = make_face()
        db.add(admin)
        for name, short, count in (
            ("Casual Leave", "CL", 10),
            ("Sick Leave", "SL", 14),
            ("Earned Leave", "EL", 12),
        ):
            db.add(LeaveType(leave_name=name, leave_short_name=short, leave_count=count))
        db.commit()
    db.close()
    yield
    engine.dispose()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/api/Login", json={"email": "demo@ignitia.local", "password": "demo1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["isSuccess"] is True
    assert body["data"]["employee_id"] == "EMP001"
    return body["message"]


@pytest.fixture(scope="session")
def admin_token(client):
    r = client.post("/api/Login", json={"email": "admin@ignitia.local", "password": "admin1234"})
    assert r.status_code == 200
    return r.json()["message"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}
