"""Employee endpoints.

Wire contract (Flutter client):
  GET /api/Employees              -> {isSuccess, message, data: [EmployeeModel]}
  GET /api/Employees/profile?id=  -> {isSuccess, message, data: EmployeeModel}
  GET /api/Employees/GetContactInfo?id= -> {.., data: EmployeeContactInfoModel}
  PUT /api/Employees              body {employeeInfo, contactInfo}

Extra server-only endpoint (no client equivalent):
  PUT /api/Employees/referenceFace  body {face_base64}   register the reference
       photo used for server-side face verification. `face_base64` is the same
       base64-JPEG format the app submits as check_in_face / check_out_face.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_employee
from ..models import Employee, EmployeeContactInfo
from ..schemas import (
    ContactInfoIn,
    ProfileIn,
    contact_json,
    employee_json,
    fail,
    ok,
)
from ..security import _decode_image

router = APIRouter()

_EMPLOYEE_FIELDS = {
    "name", "designation", "cell_no", "email", "address", "nid",
    "employee_id", "supervisor_id", "status_id",
}


class ReferenceFaceIn(BaseModel):
    face_base64: str

    model_config = ConfigDict(extra="ignore")


@router.get("/Employees")
def get_employee_list(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
):
    employees = db.query(Employee).order_by(Employee.id).all()
    return ok(data=[employee_json(e) for e in employees])


@router.get("/Employees/profile")
def get_profile(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
):
    employee = db.get(Employee, id or auth.id)
    if employee is None:
        return fail("Employee not found")
    return ok(data=employee_json(employee))


@router.get("/Employees/GetContactInfo")
def get_contact_info(
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
    id: int = Query(0),
):
    employee_id = id or auth.id
    contact = db.get(EmployeeContactInfo, employee_id)
    if contact is None:
        contact = EmployeeContactInfo(id=employee_id)
        db.add(contact)
        db.commit()
    return ok(data=contact_json(contact))


@router.put("/Employees")
def update_employee(
    payload: ProfileIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
):
    employee = db.get(Employee, auth.id)
    if employee is None:
        return fail("Employee not found")

    info = payload.employeeInfo or {}
    for key, value in info.items():
        if key in _EMPLOYEE_FIELDS and value is not None:
            if key == "email":
                email = str(value).strip().lower()
                other = (
                    db.query(Employee)
                    .filter(Employee.email == email, Employee.id != auth.id)
                    .first()
                )
                if other is not None:
                    return fail("Email is already in use by another account")
                setattr(employee, key, email)
            else:
                setattr(employee, key, value)

    if payload.contactInfo is not None:
        contact = db.get(EmployeeContactInfo, auth.id)
        if contact is None:
            contact = EmployeeContactInfo(id=auth.id)
            db.add(contact)
        for key, value in payload.contactInfo.model_dump(exclude_none=True).items():
            if key != "id" and hasattr(contact, key):
                setattr(contact, key, value)

    db.commit()
    return ok(message="Profile updated successfully")


@router.put("/Employees/referenceFace")
def register_reference_face(
    payload: ReferenceFaceIn,
    db: Session = Depends(get_db),
    auth: Employee = Depends(get_current_employee),
):
    if _decode_image(payload.face_base64) is None:
        return fail("Invalid face image")
    auth.reference_face = payload.face_base64
    db.commit()
    return ok(message="Reference face registered successfully")
