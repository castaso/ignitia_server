"""Seed the database with a demo employee + leave types + a synthetic
reference face image so the API is usable immediately.

Run with:  python seed.py

It is idempotent: existing demo data is left untouched.
"""

import io
from datetime import datetime

from PIL import Image, ImageDraw

from app.database import Base, SessionLocal, engine
from app.models import Employee, LeaveType
from app.security import hash_password


def make_demo_face(seed: str) -> str:
    """Generate a small, synthetic face-like JPEG and return it as base64.

    This is only a stand-in so the demo can exercise the face-verification
    path. In production, upload a real photo of the employee (see
    PUT /api/Employees/referenceFace).
    """
    import base64

    img = Image.new("RGB", (120, 120), (235, 200, 170))
    draw = ImageDraw.Draw(img)
    draw.ellipse([35, 30, 85, 80], fill=(200, 150, 120))  # head
    draw.ellipse([48, 50, 58, 62], fill=(40, 30, 25))  # left eye
    draw.ellipse([62, 50, 72, 62], fill=(40, 30, 25))  # right eye
    draw.rectangle([50, 70, 70, 76], fill=(160, 100, 80))  # mouth
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(Employee).first() is None:
        demo = Employee(
            employee_id="EMP001",
            name="Demo Employee",
            designation="Software Engineer",
            cell_no="01700000000",
            email="demo@ignitia.local",
            address="Office Area",
            nid="1234567890",
            type_id=2,
            supervisor_id=1,
            status_id=1,
            joining_date=datetime(2024, 1, 1),
            basic_salary=30000.0,
        )
        demo.password_hash = hash_password("demo1234")
        demo.reference_face = make_demo_face("demo-reference")
        db.add(demo)

        admin = Employee(
            employee_id="ADM001",
            name="Admin",
            designation="HR Manager",
            email="admin@ignitia.local",
            type_id=1,
            status_id=1,
            joining_date=datetime(2024, 1, 1),
            basic_salary=0.0,
        )
        admin.password_hash = hash_password("admin1234")
        admin.reference_face = make_demo_face("admin-reference")
        db.add(admin)

    if db.query(LeaveType).count() == 0:
        for name, short, count in (
            ("Casual Leave", "CL", 10),
            ("Sick Leave", "SL", 14),
            ("Earned Leave", "EL", 12),
        ):
            db.add(LeaveType(leave_name=name, leave_short_name=short, leave_count=count))

    db.commit()
    db.close()
    print("Seeded. Logins -> demo@ignitia.local / demo1234, admin@ignitia.local / admin1234")


if __name__ == "__main__":
    main()
