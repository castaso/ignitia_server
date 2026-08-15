"""Overtime endpoints.

Wire contract (Flutter client):
  GET  /api/Overtime?id=&startDate=&endDate=
  POST /api/Overtime?employeeName=          body OvertimeModel
  PUT  /api/Overtime?employeeName=          body OvertimeModel
  DELETE /api/Overtime?id=&employeeName=
  PUT  /api/Overtime/ApproveOvertime?supervisorId=  body OvertimeModel
  PUT  /api/Overtime/RejectOvertime?supervisorId=   body OvertimeModel
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..dates import date_key
from ..deps import get_current_employee
from ..models import Employee, Overtime
from ..schemas import (
    OvertimeIn,
    fail,
    ok,
    overtime_json,
)

router = APIRouter()


def _populate(row: Overtime, payload: OvertimeIn, employee_name: str = "") -> None:
    row.employeE_ID = payload.employeE_ID
    row.overtimE_DATE = payload.overtimE_DATE
    row.checK_IN = payload.checK_IN
    row.checK_OUT = payload.checK_OUT
    row.overtimE_MINUTES = payload.overtimE_MINUTES
    row.status = payload.status or "Pending"
    row.reason = payload.reason or ""
    row.supervisoR_ID = payload.supervisoR_ID
    row.name = payload.name or employee_name
    row.designation = payload.designation


@router.get("/Overtime")
def get_overtime_list(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
    startDate: str = Query(""),
    endDate: str = Query(""),
):
    employee_id = id or auth.id
    query = db.query(Overtime).filter(Overtime.employeE_ID == employee_id)
    if startDate:
        start = date_key(startDate)
        if start:
            query = query.filter(Overtime.overtimE_DATE >= start)
    if endDate:
        end = date_key(endDate)
        if end:
            query = query.filter(Overtime.overtimE_DATE <= end)
    rows = query.order_by(Overtime.id.desc()).all()
    return ok(data=[overtime_json(r) for r in rows])


@router.post("/Overtime")
def add_overtime(
    payload: OvertimeIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    employeeName: str = Query(""),
):
    row = Overtime()
    _populate(row, payload, employee_name=employeeName)
    if row.employeE_ID is None:
        row.employeE_ID = auth.id
    db.add(row)
    db.commit()
    return ok(message="Overtime request submitted")


@router.put("/Overtime")
def update_overtime(
    payload: OvertimeIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    employeeName: str = Query(""),
):
    row = db.get(Overtime, payload.id)
    if row is None:
        return fail("Overtime request not found")
    _populate(row, payload, employee_name=employeeName)
    db.commit()
    return ok(message="Overtime request updated")


@router.delete("/Overtime")
def delete_overtime(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
    employeeName: str = Query(""),
):
    row = db.get(Overtime, id)
    if row is None:
        return fail("Overtime request not found")
    db.delete(row)
    db.commit()
    return ok(message="Overtime request deleted")


@router.put("/Overtime/ApproveOvertime")
def approve_overtime(
    payload: OvertimeIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    supervisorId: int = Query(0),
):
    row = db.get(Overtime, payload.id)
    if row is None:
        return fail("Overtime request not found")
    row.status = "Approved"
    row.supervisoR_ID = supervisorId or auth.id
    db.commit()
    return ok(message="Overtime request approved")


@router.put("/Overtime/RejectOvertime")
def reject_overtime(
    payload: OvertimeIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    supervisorId: int = Query(0),
):
    row = db.get(Overtime, payload.id)
    if row is None:
        return fail("Overtime request not found")
    row.status = "Rejected"
    row.supervisoR_ID = supervisorId or auth.id
    db.commit()
    return ok(message="Overtime request rejected")
