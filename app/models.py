"""SQLAlchemy ORM models. Column names follow the wire contract used by the
Flutter client (note the odd casing of missinG_REASON / overtimE_MINUTES /
employeE_ID / overtimE_DATE / checK_IN / checK_OUT / supervisoR_ID)."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)

from .database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), unique=True, index=True)
    name = Column(String(200))
    designation = Column(String(200), default="")
    cell_no = Column(String(50), nullable=True)
    email = Column(String(200), unique=True, index=True)
    address = Column(String(500), nullable=True)
    nid = Column(String(50), nullable=True)
    type_id = Column(Integer, default=2)  # 1 = admin, 2 = employee
    supervisor_id = Column(Integer, default=0)
    status_id = Column(Integer, default=1)  # 1 = active
    joining_date = Column(DateTime)
    permanent_date = Column(DateTime, nullable=True)

    # --- security (server side only, never exposed) ---
    password_hash = Column(String(500), default="")
    # Registered reference photo (base64 JPEG) used for face verification.
    reference_face = Column(Text, nullable=True)

    # --- payroll (used to build the payslip) ---
    basic_salary = Column(Float, default=0.0)


class EmployeeContactInfo(Base):
    __tablename__ = "employee_contact_info"

    id = Column(Integer, primary_key=True)  # == employees.id
    permanent_address = Column(String(500), nullable=True)
    personal_email = Column(String(200), nullable=True)
    second_cell_no = Column(String(50), nullable=True)
    father_name = Column(String(200), nullable=True)
    father_cell_no = Column(String(50), nullable=True)
    mother_name = Column(String(200), nullable=True)
    mother_cell_no = Column(String(50), nullable=True)
    secondary_contact_name = Column(String(200), nullable=True)
    secondary_contact_cell = Column(String(50), nullable=True)


class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, index=True)
    employee_name = Column(String(200), default="")
    date_time = Column(String(20), index=True)  # yyyy-MM-dd (the working day)
    check_in = Column(String(25), nullable=True)  # yyyy-MM-ddTHH:mm:ss
    check_out = Column(String(25), nullable=True)  # yyyy-MM-ddTHH:mm:ss
    overtimE_MINUTES = Column(Integer, default=0)
    late_duration = Column(Integer, default=0)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    check_out_latitude = Column(Float, nullable=True)
    check_out_longitude = Column(Float, nullable=True)
    check_in_address = Column(String(500), nullable=True)
    check_out_address = Column(String(500), nullable=True)
    # Stored base64 is decoded to a file; the column keeps the file path.
    check_in_face = Column(String(500), nullable=True)
    check_out_face = Column(String(500), nullable=True)
    missinG_REASON = Column(String(1000), nullable=True)
    status = Column(String(50), default="Present")
    # Approval fields are used on the attendance-edit request list.
    approval_status_id = Column(Integer, default=0)
    approval_status = Column(String(50), nullable=True)


class AttendanceEditRequest(Base):
    __tablename__ = "attendance_edit_requests"

    id = Column(Integer, primary_key=True, index=True)
    attendance_id = Column(Integer, index=True)  # original attendance row id
    employee_id = Column(Integer, index=True)
    employee_name = Column(String(200), default="")
    date_time = Column(String(20), index=True)
    # Full proposed attendance JSON payload (as sent by the client).
    payload = Column(Text)
    approval_status_id = Column(Integer, default=1)  # 1 Pending
    approval_status = Column(String(50), default="Pending")
    rejection_reason = Column(String(1000), nullable=True)
    approved_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Overtime(Base):
    __tablename__ = "overtime"

    id = Column(Integer, primary_key=True, index=True)
    employeE_ID = Column(Integer, index=True)
    overtimE_DATE = Column(String(25), nullable=True)
    checK_IN = Column(String(25), nullable=True)
    checK_OUT = Column(String(25), nullable=True)
    overtimE_MINUTES = Column(Integer, default=0)
    status = Column(String(50), default="Pending")
    reason = Column(String(1000), default="")
    supervisoR_ID = Column(Integer, nullable=True)
    name = Column(String(200), nullable=True)
    designation = Column(String(200), nullable=True)


class LeaveType(Base):
    __tablename__ = "leave_types"

    id = Column(Integer, primary_key=True)
    leave_name = Column(String(200))
    leave_short_name = Column(String(50))
    leave_count = Column(Integer, default=0)


class UserLeave(Base):
    __tablename__ = "user_leaves"

    id = Column(Integer, primary_key=True, index=True)
    leave_id = Column(Integer, index=True)
    employee_id = Column(Integer, index=True)
    apply_date = Column(String(25))
    start_date = Column(String(25))
    end_date = Column(String(25))
    reason = Column(String(1000), default="")
    total_days = Column(Integer, default=0)
    is_approved = Column(Integer, default=0)
