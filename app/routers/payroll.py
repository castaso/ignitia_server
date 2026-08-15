"""Payroll endpoint.

Wire contract (Flutter client):
  GET /api/Payroll/GetPayslip?employee_id=&salary_year=&salary_month=
      -> {isSuccess, message, data: SalaryModel|null}

The payslip is derived from the employee record and that month's attendance
(see lib/models/payroll/salary_model.dart for the exact JSON keys).
"""

import calendar
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_employee
from ..models import Attendance, Employee, UserLeave
from ..schemas import fail, ok

router = APIRouter()


def _is_weekend(day: date) -> bool:
    return day.weekday() in (5, 6)


@router.get("/Payroll/GetPayslip")
def get_payslip(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    employee_id: int = Query(0),
    salary_year: int = Query(2026),
    salary_month: int = Query(1),
):
    employee = db.get(Employee, employee_id or auth.id)
    if employee is None:
        return fail("Employee not found")

    days_of_month = calendar.monthrange(salary_year, salary_month)[1]
    month_key = f"{salary_year:04d}-{salary_month:02d}"

    start = f"{month_key}-01"
    end = f"{month_key}-{days_of_month:02d}"

    present_days = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.date_time >= start,
            Attendance.date_time <= end,
            Attendance.check_in.isnot(None),
        )
        .count()
    )
    leave_days = (
        db.query(UserLeave)
        .filter(
            UserLeave.employee_id == employee.id,
            UserLeave.is_approved == 1,
            UserLeave.start_date >= start,
            UserLeave.end_date <= end,
        )
        .count()
    )
    holidays = sum(
        1
        for d in range(1, days_of_month + 1)
        if _is_weekend(date(salary_year, salary_month, d))
    )
    absent_days = max(0, days_of_month - holidays - present_days - leave_days)

    total_ot_minutes = sum(
        r.overtimE_MINUTES or 0
        for r in db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.date_time >= start,
            Attendance.date_time <= end,
        )
        .all()
    )
    ot_hours = f"{total_ot_minutes // 60}.{total_ot_minutes % 60:02d}"

    basic = float(employee.basic_salary or 0.0)
    medical = round(basic * 0.10, 2)
    conveyance = round(basic * 0.05, 2)
    gross = round(basic + medical + conveyance, 2)

    hourly_rate = basic / 240 if days_of_month else 0.0
    ot_amount = round((total_ot_minutes / 60) * hourly_rate, 2)
    overtime = round(total_ot_minutes / 60, 2)

    absent_deduction = round(
        absent_days * (basic / days_of_month) if days_of_month else 0.0, 2
    )
    ait = round(gross * 0.10, 2)
    net_pay = round(
        gross + ot_amount - absent_deduction - ait, 2
    )

    data = {
        "employee_id": employee.employee_id,
        "name": employee.name,
        "designation": employee.designation,
        "email": employee.email,
        "joining_date": (
            employee.joining_date.strftime("%Y-%m-%d") if employee.joining_date else ""
        ),
        "bank_name": "",
        "bank_account_no": "",
        "payment_mode": "Bank",
        "days_of_month": days_of_month,
        "holidays": holidays,
        "present_days": present_days,
        "leave_days": leave_days,
        "absent_days": absent_days,
        "basic_salary": basic,
        "medical_allowance": medical,
        "convenyence_allowance": conveyance,
        "gross_salary": gross,
        "ot_hours": ot_hours,
        "other_allowance": 0.0,
        "bonus": 0.0,
        "other_allowance_description": "",
        "overtime": overtime,
        "ot_amount": ot_amount,
        "absent_deduction": absent_deduction,
        "other_deduction_description": "",
        "other_deduction": 0.0,
        "ait": ait,
        "net_pay": net_pay,
        "is_disbursed": 0,
    }
    return ok(data=data)
