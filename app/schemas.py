"""Pydantic request schemas and response-builder helpers matching the wire
contract of the Flutter client.

Response envelope used everywhere (unless noted):

    {"isSuccess": bool, "message": str, "data": <object|list|null>}
"""

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict

# --- requests -----------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str

    model_config = ConfigDict(extra="ignore")


class ChangePasswordRequest(BaseModel):
    email: str
    oldPassword: str
    newPassword: str

    model_config = ConfigDict(extra="ignore")


class AttendanceIn(BaseModel):
    """Body of check-in / check-out / edit-attendance requests.

    The client serialises the full AttendanceModel (toJson), so unknown
    fields are tolerated.
    """

    id: int = 0
    employee_id: Optional[int] = None
    employee_name: Optional[str] = None
    date_time: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    late_duration: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    overtimE_MINUTES: int = 0
    check_out_latitude: Optional[float] = None
    check_out_longitude: Optional[float] = None
    check_in_address: Optional[str] = None
    check_out_address: Optional[str] = None
    check_in_face: Optional[str] = None
    check_out_face: Optional[str] = None
    # Base64 JPEG frames captured live during the blink challenge. When absent
    # and LIVENESS_REQUIRED is true the request is rejected.
    liveness_frames: Optional[List[str]] = None
    status: Optional[str] = None
    missinG_REASON: Optional[str] = None
    approval_status_id: Optional[int] = None
    approval_status: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class OvertimeIn(BaseModel):
    id: int = 0
    employeE_ID: Optional[int] = None
    overtimE_DATE: Optional[str] = None
    checK_IN: Optional[str] = None
    checK_OUT: Optional[str] = None
    overtimE_MINUTES: int = 0
    status: Optional[str] = None
    reason: Optional[str] = None
    supervisoR_ID: Optional[int] = None
    name: Optional[str] = None
    designation: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class UserLeaveIn(BaseModel):
    id: int = 0
    leave_id: Optional[int] = None
    employee_id: Optional[int] = None
    apply_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    reason: Optional[str] = None
    total_days: Optional[int] = None
    is_approved: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class ContactInfoIn(BaseModel):
    id: Optional[int] = None
    permanent_address: Optional[str] = None
    personal_email: Optional[str] = None
    second_cell_no: Optional[str] = None
    father_name: Optional[str] = None
    father_cell_no: Optional[str] = None
    mother_name: Optional[str] = None
    mother_cell_no: Optional[str] = None
    secondary_contact_name: Optional[str] = None
    secondary_contact_cell: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class ProfileIn(BaseModel):
    """Body of PUT /api/Employees -> {employeeInfo: {...}, contactInfo: {...}}"""

    employeeInfo: Optional[dict] = None
    contactInfo: Optional[ContactInfoIn] = None

    model_config = ConfigDict(extra="ignore")


# --- responses ----------------------------------------------------------


def ok(data: Any = None, message: str = "Success") -> dict:
    return {"isSuccess": True, "message": message, "data": data}


def fail(message: str, data: Any = None) -> dict:
    return {"isSuccess": False, "message": message, "data": data}


def employee_json(emp) -> dict:
    return {
        "id": emp.id,
        "name": emp.name,
        "designation": emp.designation or "",
        "cell_no": emp.cell_no,
        "email": emp.email,
        "address": emp.address,
        "nid": emp.nid,
        "type_id": emp.type_id,
        "employee_id": emp.employee_id,
        "supervisor_id": emp.supervisor_id,
        "status_id": emp.status_id,
        "joining_date": emp.joining_date.isoformat() if emp.joining_date else None,
        "permanent_date": emp.permanent_date.isoformat() if emp.permanent_date else None,
    }


def contact_json(contact) -> dict:
    return {
        "id": contact.id,
        "permanent_address": contact.permanent_address,
        "personal_email": contact.personal_email,
        "second_cell_no": contact.second_cell_no,
        "father_name": contact.father_name,
        "father_cell_no": contact.father_cell_no,
        "mother_name": contact.mother_name,
        "mother_cell_no": contact.mother_cell_no,
        "secondary_contact_name": contact.secondary_contact_name,
        "secondary_contact_cell": contact.secondary_contact_cell,
    }


def attendance_json(row, *, include_faces: bool = False) -> dict:
    """Serialize an Attendance (or attendance-edit request) row to the exact
    JSON shape AttendanceModel.fromJson expects.

    The client parses ``date_time`` with a full datetime pattern, so a plain
    ``yyyy-MM-dd`` value is normalised to ``yyyy-MM-ddTHH:mm:ss`` (midnight).
    """
    approval_status_id = getattr(row, "approval_status_id", 0) or 0
    approval_status = getattr(row, "approval_status", None)
    date_time = row.date_time
    if date_time and len(date_time) == 10:
        date_time = f"{date_time}T00:00:00"
    result = {
        "id": row.id or 0,
        "employee_id": row.employee_id,
        "employee_name": row.employee_name,
        "date_time": date_time,
        "check_in": row.check_in,
        "check_out": row.check_out,
        "late_duration": row.late_duration,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "overtimE_MINUTES": row.overtimE_MINUTES or 0,
        "check_out_latitude": row.check_out_latitude,
        "check_out_longitude": row.check_out_longitude,
        "check_in_address": row.check_in_address,
        "check_out_address": row.check_out_address,
        "status": row.status or "",
        "missinG_REASON": row.missinG_REASON,
        "approval_status_id": approval_status_id,
        "approval_status": approval_status,
    }
    # Face images are large base64 strings; only expose file paths when asked.
    result["check_in_face"] = row.check_in_face if include_faces else ""
    result["check_out_face"] = row.check_out_face if include_faces else ""
    return result


def leave_type_json(leave_type) -> dict:
    return {
        "id": leave_type.id,
        "leave_name": leave_type.leave_name,
        "leave_short_name": leave_type.leave_short_name,
        "leave_count": leave_type.leave_count,
    }


def user_leave_json(leave) -> dict:
    return {
        "id": leave.id,
        "leave_id": leave.leave_id,
        "employee_id": leave.employee_id,
        "apply_date": leave.apply_date,
        "start_date": leave.start_date,
        "end_date": leave.end_date,
        "reason": leave.reason,
        "total_days": leave.total_days,
        "is_approved": leave.is_approved,
    }


def overtime_json(row) -> dict:
    return {
        "id": row.id,
        "employeE_ID": row.employeE_ID,
        "overtimE_DATE": row.overtimE_DATE,
        "checK_IN": row.checK_IN,
        "checK_OUT": row.checK_OUT,
        "overtimE_MINUTES": row.overtimE_MINUTES or 0,
        "status": row.status or "",
        "reason": row.reason or "",
        "supervisoR_ID": row.supervisoR_ID,
        "name": row.name,
        "designation": row.designation,
    }
