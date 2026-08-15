"""Authentication endpoints.

Wire contract (Flutter client):
  POST /api/Login                  body {email, password}
  POST /api/Login/ChangePassword   body {email, oldPassword, newPassword}
  POST /api/Login/ForgetPassword   query ?email=

The client reads the JWT from the login response `message` field
(FieldValue.token = responseModel.message) and re-sends it as
`Authorization: Bearer <token>`, so a successful login returns the raw JWT
inside `message`. Failed logins return HTTP 401 (the client maps this to an
"Unauthorized" message).
"""

import logging
import secrets

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Employee
from ..schemas import (
    ChangePasswordRequest,
    LoginRequest,
    employee_json,
    fail,
    ok,
)
from ..security import create_token, hash_password, verify_password

logger = logging.getLogger("ignitia")

router = APIRouter()


@router.post("/Login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    employee = db.query(Employee).filter(Employee.email == email).first()
    # Failed logins return 401 so the client (which reads the token from
    # `message` and dereferences `data!`) does not attempt to parse the body.
    if employee is None or not verify_password(payload.password, employee.password_hash):
        return JSONResponse(status_code=401, content=fail("Invalid email or password"))
    if employee.status_id != 1:
        return JSONResponse(status_code=401, content=fail("Your account is inactive"))
    token = create_token(employee.id)
    return ok(data=employee_json(employee), message=token)


@router.post("/Login/ChangePassword")
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    employee = db.query(Employee).filter(Employee.email == email).first()
    if employee is None:
        return fail("Account not found")
    if not verify_password(payload.oldPassword, employee.password_hash):
        return fail("Current password is incorrect")
    employee.password_hash = hash_password(payload.newPassword)
    db.commit()
    return ok(message="Password changed successfully")


@router.post("/Login/ForgetPassword")
def forget_password(db: Session = Depends(get_db), email: str = Query("")):
    employee = db.query(Employee).filter(Employee.email == email.strip().lower()).first()
    if employee is None:
        return fail("Account not found")
    # Demo behaviour: issue a temporary password. A production deployment
    # should email a secure reset link instead.
    temp_password = secrets.token_urlsafe(8)
    employee.password_hash = hash_password(temp_password)
    db.commit()
    logger.info("Temporary password for %s: %s", email, temp_password)
    return ok(message="A temporary password has been sent to your email")
