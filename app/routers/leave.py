"""Leave endpoints.

Wire contract (Flutter client):
  GET  /api/Leave/getEmployeeLeaveSummary?employeeId=
  GET  /api/Leave/getLeaveList
  GET  /api/Leave?employeeId=
  POST /api/Leave?employeeName=         body UserLeaveModel
  PUT  /api/Leave?employeeName=         body UserLeaveModel
  PUT  /api/Leave/approveEmployeeLeave?supervisorId=  body UserLeaveModel
  DELETE /api/Leave?id=&employeeName=
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_employee
from ..models import Employee, LeaveType, UserLeave
from ..schemas import (
    UserLeaveIn,
    fail,
    leave_type_json,
    ok,
    user_leave_json,
)

router = APIRouter()


@router.get("/Leave/getEmployeeLeaveSummary")
def get_employee_leave_summary(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    employeeId: int = Query(0),
):
    employee_id = employeeId or auth.id
    employee = db.get(Employee, employee_id)
    if employee is None:
        return fail("Employee not found")
    leave_types = db.query(LeaveType).order_by(LeaveType.id).all()
    rows = []
    for lt in leave_types:
        taken = (
            db.query(UserLeave)
            .filter(
                UserLeave.employee_id == employee_id,
                UserLeave.leave_id == lt.id,
                UserLeave.is_approved == 1,
            )
            .count()
        )
        entitlement = lt.leave_count
        rows.append(
            {
                "employeE_ID": employee_id,
                "employeE_NAME": employee.name,
                "leavE_SHORT_NAME": lt.leave_short_name,
                "entitlement": entitlement,
                "taken": taken,
                "balance": max(0, entitlement - taken),
            }
        )
    return ok(data=rows)


@router.get("/Leave/getLeaveList")
def get_leave_list(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
):
    leave_types = db.query(LeaveType).order_by(LeaveType.id).all()
    return ok(data=[leave_type_json(lt) for lt in leave_types])


@router.get("/Leave")
def get_user_leave(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    employeeId: int = Query(0),
):
    employee_id = employeeId or auth.id
    leaves = (
        db.query(UserLeave)
        .filter(UserLeave.employee_id == employee_id)
        .order_by(UserLeave.id.desc())
        .all()
    )
    return ok(data=[user_leave_json(l) for l in leaves])


@router.post("/Leave")
def add_employee_leave(
    payload: UserLeaveIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    employeeName: str = Query(""),
):
    leave = UserLeave(
        leave_id=payload.leave_id or 0,
        employee_id=payload.employee_id or auth.id,
        apply_date=payload.apply_date,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason or "",
        total_days=payload.total_days or 0,
        is_approved=payload.is_approved or 0,
    )
    db.add(leave)
    db.commit()
    return ok(message="Leave request submitted")


@router.put("/Leave")
def update_employee_leave(
    payload: UserLeaveIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    employeeName: str = Query(""),
):
    leave = db.get(UserLeave, payload.id)
    if leave is None:
        return fail("Leave request not found")
    if payload.leave_id is not None:
        leave.leave_id = payload.leave_id
    if payload.start_date is not None:
        leave.start_date = payload.start_date
    if payload.end_date is not None:
        leave.end_date = payload.end_date
    if payload.reason is not None:
        leave.reason = payload.reason
    if payload.total_days is not None:
        leave.total_days = payload.total_days
    db.commit()
    return ok(message="Leave request updated")


@router.put("/Leave/approveEmployeeLeave")
def approve_employee_leave(
    payload: UserLeaveIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    supervisorId: int = Query(0),
):
    leave = db.get(UserLeave, payload.id)
    if leave is None:
        return fail("Leave request not found")
    leave.is_approved = 1
    db.commit()
    return ok(message="Leave request approved")


@router.delete("/Leave")
def delete_employee_leave(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
    employeeName: str = Query(""),
):
    leave = db.get(UserLeave, id)
    if leave is None:
        return fail("Leave request not found")
    db.delete(leave)
    db.commit()
    return ok(message="Leave request deleted")
