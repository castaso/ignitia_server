"""FastAPI dependencies."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import Employee
from .security import decode_token


def get_current_employee(
    request: Request, db: Session = Depends(get_db)
) -> Employee:
    """Resolve the Bearer token to an active Employee or raise 401."""
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = header.split(" ", 1)[1].strip()
    employee_id = decode_token(token)
    if employee_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    employee = db.get(Employee, employee_id)
    if employee is None or employee.status_id != 1:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return employee
