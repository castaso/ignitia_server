"""Attendance endpoints - the core of the "prevent proxy attendance" feature.

Server-side enforcement (this router is authoritative):
  * Geo-fence   - every check-in / check-out is validated against the
                  configured office centre + radius (haversine distance).
  * Face        - every check-in / check-out capture is matched against the
                  employee's registered reference photo. A failure blocks the
                  attendance with the exact message string the client shows:
                  "You are not within the allowed office range. Proxy
                  attendance is blocked." / "Face verification failed...".

Wire contract (Flutter client): see lib/repo/api_service.dart and the
AttendanceModel JSON keys in lib/models/attendance/attendance_model.g.dart.
"""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..dates import date_key, datetime_key, parse_date
from ..deps import get_current_employee
from ..models import Attendance, AttendanceEditRequest, Employee, UserLeave
from ..schemas import (
    AttendanceIn,
    attendance_json,
    fail,
    ok,
)
from ..security import is_within_office, store_face_snapshot, verify_face

router = APIRouter()

STATUS_PRESENT = "Present"
STATUS_LATE = "Late"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _office_start() -> datetime:
    h, m = settings.OFFICE_START_TIME.split(":")
    return datetime.now().replace(hour=int(h), minute=int(m), second=0, microsecond=0)


def _office_end() -> datetime:
    h, m = settings.OFFICE_END_TIME.split(":")
    return datetime.now().replace(hour=int(h), minute=int(m), second=0, microsecond=0)


def _late_duration(check_in: datetime) -> int:
    start = _office_start()
    diff = int((check_in - start).total_seconds() // 60)
    return diff if diff > 0 else 0


def _overtime_minutes(check_out: datetime) -> int:
    end = _office_end()
    diff = int((check_out - end).total_seconds() // 60)
    return diff if diff > 0 else 0


def _is_weekend(day: datetime) -> bool:
    return day.weekday() in (5, 6)  # Saturday / Sunday


def _resolve_employee_id(auth_employee: Employee, body_id: int | None) -> int:
    return body_id if body_id else auth_employee.id


# ---------------------------------------------------------------------------
# check-in / check-out
# ---------------------------------------------------------------------------


@router.post("/Attendance/v2/checkin")
def check_in(
    payload: AttendanceIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
):
    employee_id = _resolve_employee_id(auth, payload.employee_id)
    employee = db.get(Employee, employee_id)
    if employee is None:
        return fail("Employee not found")

    # 1. Server-side geo-fence validation.
    if not is_within_office(payload.latitude, payload.longitude):
        return fail(settings.MESSAGE_OUTSIDE_RANGE)

    # 2. Server-side face verification.
    ok_face, error = verify_face(employee.reference_face, payload.check_in_face)
    if not ok_face:
        return fail(error)

    day = date_key(payload.date_time) or datetime.now().strftime("%Y-%m-%d")
    existing = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.date_time == day)
        .first()
    )
    if existing is not None and existing.check_in:
        return fail("You have already checked in for this day")

    now = datetime.now()
    check_in_str = datetime_key(now)
    face_path = store_face_snapshot(
        payload.check_in_face,
        f"emp{employee_id}_{day}_in.jpg",
    )

    if existing is None:
        record = Attendance(
            employee_id=employee_id,
            employee_name=employee.name,
            date_time=day,
            check_in=check_in_str,
            late_duration=_late_duration(now),
            latitude=payload.latitude,
            longitude=payload.longitude,
            check_in_address=payload.check_in_address,
            check_in_face=face_path,
            missinG_REASON=payload.missinG_REASON,
            status=STATUS_LATE if _late_duration(now) > 0 else STATUS_PRESENT,
        )
        db.add(record)
    else:
        existing.check_in = check_in_str
        existing.late_duration = _late_duration(now)
        existing.latitude = payload.latitude
        existing.longitude = payload.longitude
        existing.check_in_address = payload.check_in_address
        existing.check_in_face = face_path
        existing.missinG_REASON = payload.missinG_REASON
        existing.status = STATUS_LATE if _late_duration(now) > 0 else STATUS_PRESENT
    db.commit()
    return ok(message="Check-in successful")


@router.post("/Attendance/v2/checkout")
def check_out(
    payload: AttendanceIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
):
    employee_id = _resolve_employee_id(auth, payload.employee_id)
    employee = db.get(Employee, employee_id)
    if employee is None:
        return fail("Employee not found")

    # 1. Server-side geo-fence validation.
    if not is_within_office(payload.check_out_latitude, payload.check_out_longitude):
        return fail(settings.MESSAGE_OUTSIDE_RANGE)

    # 2. Server-side face verification.
    ok_face, error = verify_face(employee.reference_face, payload.check_out_face)
    if not ok_face:
        return fail(error)

    day = date_key(payload.date_time) or datetime.now().strftime("%Y-%m-%d")
    record = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date_time == day,
        )
        .first()
    )
    if record is None or not record.check_in:
        return fail("No active check-in found for this day")
    if record.check_out:
        return fail("You have already checked out for this day")

    now = datetime.now()
    check_out_str = datetime_key(now)
    face_path = store_face_snapshot(
        payload.check_out_face,
        f"emp{employee_id}_{day}_out.jpg",
    )

    record.check_out = check_out_str
    record.check_out_face = face_path
    record.check_out_latitude = payload.check_out_latitude
    record.check_out_longitude = payload.check_out_longitude
    record.check_out_address = payload.check_out_address
    record.overtimE_MINUTES = _overtime_minutes(now)
    record.status = STATUS_LATE if (record.late_duration or 0) > 0 else STATUS_PRESENT
    db.commit()
    return ok(message="Check-out successful")


# ---------------------------------------------------------------------------
# search / summary
# ---------------------------------------------------------------------------


@router.get("/Attendance/searchAttendanceByDate")
def search_attendance_by_date(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
    startDate: str = Query(""),
    endDate: str = Query(""),
):
    employee_id = id or auth.id
    start = date_key(startDate)
    end = date_key(endDate) or datetime.now().strftime("%Y-%m-%d")
    query = db.query(Attendance).filter(Attendance.employee_id == employee_id)
    if start:
        query = query.filter(Attendance.date_time >= start)
    if end:
        query = query.filter(Attendance.date_time <= end)
    records = query.order_by(Attendance.date_time.desc()).all()
    return ok(data=[attendance_json(r) for r in records])


@router.get("/Attendance/userAttendanceSummary")
def user_attendance_summary(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
    startDate: str = Query(""),
    endDate: str = Query(""),
):
    employee_id = id or auth.id
    start_dt = parse_date(startDate)
    end_dt = parse_date(endDate) or datetime.now()

    total_days = 0
    weekend_holiday = 0
    if start_dt is not None:
        total_days = (end_dt - start_dt).days + 1
        cursor = start_dt
        while cursor <= end_dt:
            if _is_weekend(cursor):
                weekend_holiday += 1
            cursor += timedelta(days=1)

    start = start_dt.strftime("%Y-%m-%d") if start_dt else None
    end = end_dt.strftime("%Y-%m-%d")
    query = db.query(Attendance).filter(Attendance.employee_id == employee_id)
    if start:
        query = query.filter(Attendance.date_time >= start)
    query = query.filter(Attendance.date_time <= end)
    records = query.all()

    present_days = 0
    late_days = 0
    overtime_duration = 0
    for r in records:
        if r.check_in:
            present_days += 1
            if (r.late_duration or 0) > 0:
                late_days += 1
        overtime_duration += r.overtimE_MINUTES or 0

    leave_days = (
        db.query(UserLeave)
        .filter(
            UserLeave.employee_id == employee_id,
            UserLeave.is_approved == 1,
        )
        .count()
    )

    data = {
        "total_days": total_days,
        "present_days": present_days,
        "late_days": late_days,
        "leave_days": leave_days,
        "weekend_holiday": weekend_holiday,
        "overtime_duration": overtime_duration,
    }
    return ok(data=data)


# ---------------------------------------------------------------------------
# attendance edit requests
# ---------------------------------------------------------------------------


@router.put("/Attendance/requestEditAttendance")
def request_edit_attendance(
    payload: AttendanceIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
    name: str = Query(""),
):
    employee_id = id or auth.id
    employee = db.get(Employee, employee_id)
    if employee is None:
        return fail("Employee not found")

    day = date_key(payload.date_time) or datetime.now().strftime("%Y-%m-%d")
    original = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.date_time == day)
        .first()
    )
    original_id = original.id if original else 0

    request = AttendanceEditRequest(
        attendance_id=original_id,
        employee_id=employee_id,
        employee_name=employee.name,
        date_time=day,
        payload=json.dumps(payload.model_dump(exclude_none=True)),
        approval_status_id=settings.APPROVAL_PENDING,
        approval_status="Pending",
    )
    db.add(request)
    db.commit()
    return ok(message="Attendance edit request submitted for approval")


@router.get("/Attendance/getAttendanceRequest")
def get_attendance_request(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
    startDate: str = Query(""),
    endDate: str = Query(""),
):
    employee_id = id or auth.id
    start = date_key(startDate)
    end = date_key(endDate) or datetime.now().strftime("%Y-%m-%d")
    query = db.query(AttendanceEditRequest).filter(
        AttendanceEditRequest.employee_id == employee_id
    )
    if start:
        query = query.filter(AttendanceEditRequest.date_time >= start)
    if end:
        query = query.filter(AttendanceEditRequest.date_time <= end)
    requests = query.order_by(AttendanceEditRequest.created_at.desc()).all()

    rows = []
    for req in requests:
        row = _merge_request_payload(req, db)
        rows.append(attendance_json(row))
    return ok(data=rows)


def _merge_request_payload(req: AttendanceEditRequest, db: Session):
    """Build an Attendance-shaped object from an edit request: original row
    overlaid with the proposed payload and the request's approval fields."""
    original = db.get(Attendance, req.attendance_id) if req.attendance_id else None
    payload = {}
    try:
        payload = json.loads(req.payload or "{}")
    except json.JSONDecodeError:
        payload = {}

    if original is not None:
        result = Attendance(
            id=req.id,
            employee_id=original.employee_id,
            employee_name=original.employee_name,
            date_time=original.date_time,
            check_in=original.check_in,
            check_out=original.check_out,
            overtimE_MINUTES=original.overtimE_MINUTES,
            late_duration=original.late_duration,
            latitude=original.latitude,
            longitude=original.longitude,
            check_out_latitude=original.check_out_latitude,
            check_out_longitude=original.check_out_longitude,
            check_in_address=original.check_in_address,
            check_out_address=original.check_out_address,
            check_in_face=original.check_in_face,
            check_out_face=original.check_out_face,
            missinG_REASON=original.missinG_REASON,
            status=original.status,
        )
    else:
        result = Attendance(id=req.id, employee_id=req.employee_id,
                            employee_name=req.employee_name, date_time=req.date_time,
                            status="")

    for key, value in payload.items():
        if hasattr(result, key) and value is not None:
            try:
                setattr(result, key, value)
            except Exception:
                pass

    result.id = req.id
    result.approval_status_id = req.approval_status_id
    result.approval_status = req.approval_status
    return result


@router.delete("/Attendance/deleteAttendanceRequest")
def delete_attendance_request(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    requestId: int = Query(0),
):
    request = db.get(AttendanceEditRequest, requestId)
    if request is None:
        return fail("Request not found")
    db.delete(request)
    db.commit()
    return ok(message="Attendance edit request deleted")


@router.post("/Attendance/approveAttendance")
def approve_attendance(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    requestId: int = Query(0),
    approvedBy: int = Query(0),
    approvalStatusId: int = Query(0),
    rejectionReason: str = Query(""),
):
    request = db.get(AttendanceEditRequest, requestId)
    if request is None:
        return fail("Request not found")

    if approvalStatusId == settings.APPROVAL_APPROVED:
        request.approval_status_id = settings.APPROVAL_APPROVED
        request.approval_status = "Approved"
        request.approved_by = approvedBy or auth.id
        if request.attendance_id:
            original = db.get(Attendance, request.attendance_id)
            if original is not None:
                _apply_payload(original, request.payload)
        db.commit()
        return ok(message="Attendance edit request approved")
    elif approvalStatusId == settings.APPROVAL_REJECTED:
        request.approval_status_id = settings.APPROVAL_REJECTED
        request.approval_status = "Rejected"
        request.rejection_reason = rejectionReason
        db.commit()
        return ok(message="Attendance edit request rejected")
    return fail("Invalid approval status")


def _apply_payload(attendance: Attendance, payload_json: str) -> None:
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        return
    allowed = {
        "check_in", "check_out", "overtimE_MINUTES", "late_duration",
        "latitude", "longitude", "check_out_latitude", "check_out_longitude",
        "check_in_address", "check_out_address", "missinG_REASON", "status",
    }
    for key, value in payload.items():
        if key in allowed and value is not None and hasattr(attendance, key):
            try:
                setattr(attendance, key, value)
            except Exception:
                pass
