"""Authentication endpoints.

Wire contract (Flutter client):
  POST /api/Login                  body {email, password}
  POST /api/Login/ChangePassword   body {email, oldPassword, newPassword}
  POST /api/Login/ForgetPassword   query ?email=

Server extension (no client equivalent yet):
  POST /api/Login/ResetPassword    body {email, token, newPassword}

The client reads the JWT from the login response `message` field
(FieldValue.token = responseModel.message) and re-sends it as
`Authorization: Bearer <token>`, so a successful login returns the raw JWT
inside `message`. Failed logins return HTTP 401 (the client maps this to an
"Unauthorized" message).
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..email import send_email
from ..models import Employee, PasswordResetToken
from ..schemas import (
    ChangePasswordRequest,
    LoginRequest,
    employee_json,
    fail,
    ok,
)
from ..security import (
    create_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)

logger = logging.getLogger("ignitia")

router = APIRouter()


class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    newPassword: str

    model_config = ConfigDict(extra="ignore")


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
    if len(payload.newPassword) < 6:
        return fail("New password must be at least 6 characters")
    employee.password_hash = hash_password(payload.newPassword)
    db.commit()
    return ok(message="Password changed successfully")


@router.post("/Login/ForgetPassword")
def forget_password(db: Session = Depends(get_db), email: str = Query("")):
    # Always return success to avoid account enumeration. A reset link is only
    # issued when the email actually exists.
    email = email.strip().lower()
    employee = db.query(Employee).filter(Employee.email == email).first()
    if employee is None:
        logger.info("Reset requested for unknown email: %s", email)
        return ok(message="If that email is registered, a reset link has been sent")

    token = generate_reset_token()
    db.add(
        PasswordResetToken(
            email=email,
            token_hash=hash_reset_token(token),
            expires_at=datetime.utcnow()
            + timedelta(minutes=settings.RESET_TOKEN_TTL_MINUTES),
            used=0,
        )
    )
    db.commit()
    reset_url = f"/api/Login/ResetPassword?email={email}&token={token}"
    send_email(
        email,
        "Reset your ignitia password",
        f"Use this one-time link to reset your password (valid for "
        f"{settings.RESET_TOKEN_TTL_MINUTES} minutes):\n\n{reset_url}\n\n"
        f"If you did not request this, ignore this email.",
    )
    return ok(message="If that email is registered, a reset link has been sent")


@router.post("/Login/ResetPassword")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if len(payload.newPassword) < 6:
        return fail("New password must be at least 6 characters")
    employee = db.query(Employee).filter(Employee.email == email).first()
    if employee is None:
        return fail("Invalid or expired reset link")

    token_hash = hash_reset_token(payload.token.strip())
    record = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.email == email,
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == 0,
        )
        .order_by(PasswordResetToken.created_at.desc())
        .first()
    )
    if record is None or record.expires_at < datetime.utcnow():
        return fail("Invalid or expired reset link")

    record.used = 1
    employee.password_hash = hash_password(payload.newPassword)
    db.commit()
    return ok(message="Password reset successfully. Please sign in with your new password")
