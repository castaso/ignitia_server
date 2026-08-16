"""Wire-contract tests. These mirror the exact endpoints and JSON keys the
Flutter client in /workspace/lib/repo/api_service.dart expects."""

from tests.conftest import auth, make_face

from app.config import settings


def test_login_returns_jwt_in_message_field(token):
    assert token.startswith("eyJ")


def test_login_bad_credentials_returns_401(client):
    r = client.post("/api/Login", json={"email": "demo@ignitia.local", "password": "nope"})
    assert r.status_code == 401


def test_protected_endpoint_requires_bearer_token(client):
    assert client.get("/api/Employees/profile", params={"id": 1}).status_code == 401


def test_employee_list_and_profile(client, token):
    r = client.get("/api/Employees", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["isSuccess"] is True
    assert body["data"][0]["employee_id"] == "EMP001"

    r = client.get("/api/Employees/profile", params={"id": 1}, headers=auth(token))
    assert r.json()["data"]["name"] == "Demo Employee"


def test_contact_info(client, token):
    r = client.get("/api/Employees/GetContactInfo", params={"id": 1}, headers=auth(token))
    assert r.json()["data"]["id"] == 1


def checkin_body(**overrides):
    body = {
        "id": 0,
        "employee_id": 1,
        "employee_name": "Demo Employee",
        "date_time": "2026-08-15",
        "latitude": 23.810331,
        "longitude": 90.412521,
        "check_in_address": "Office",
        "check_in_face": make_face(),
        "status": "Present",
        "late_duration": 0,
        "overtimE_MINUTES": 0,
    }
    body.update(overrides)
    return body


def test_checkin_within_range_succeeds(client, token):
    r = client.post("/api/Attendance/v2/checkin", json=checkin_body(), headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["isSuccess"] is True
    assert body["message"] == "Check-in successful"


def test_duplicate_checkin_rejected(client, token):
    r = client.post("/api/Attendance/v2/checkin", json=checkin_body(), headers=auth(token))
    assert r.json()["isSuccess"] is False
    assert "already checked in" in r.json()["message"]


def test_checkin_outside_geofence_blocked(client, token):
    body = checkin_body(date_time="2026-08-17", latitude=24.0, longitude=91.0)
    r = client.post("/api/Attendance/v2/checkin", json=body, headers=auth(token))
    body = r.json()
    assert body["isSuccess"] is False
    assert body["message"] == settings.MESSAGE_OUTSIDE_RANGE


def test_checkin_missing_coordinates_blocked(client, token):
    body = checkin_body(date_time="2026-08-18", latitude=None, longitude=None)
    r = client.post("/api/Attendance/v2/checkin", json=body, headers=auth(token))
    assert r.json()["isSuccess"] is False


def test_checkin_wrong_face_blocked(client, token):
    body = checkin_body(date_time="2026-08-19", check_in_face=make_face((10, 10, 40)))
    r = client.post("/api/Attendance/v2/checkin", json=body, headers=auth(token))
    assert r.json()["isSuccess"] is False
    assert r.json()["message"] == settings.MESSAGE_FACE_FAILED


def test_checkin_blank_face_rejected(client, token):
    body = checkin_body(date_time="2026-08-20", check_in_face=make_face((255, 255, 255), eyes=False))
    r = client.post("/api/Attendance/v2/checkin", json=body, headers=auth(token))
    assert r.json()["isSuccess"] is False
    assert "invalid" in r.json()["message"].lower()


def checkout_body(**overrides):
    body = {
        "id": 0,
        "employee_id": 1,
        "date_time": "2026-08-15",
        "check_out_latitude": 23.810331,
        "check_out_longitude": 90.412521,
        "check_out_address": "Office",
        "check_out_face": make_face(),
        "overtimE_MINUTES": 0,
    }
    body.update(overrides)
    return body


def test_checkout_flow(client, token):
    r = client.post("/api/Attendance/v2/checkout", json=checkout_body(), headers=auth(token))
    body = r.json()
    assert body["isSuccess"] is True
    assert body["message"] == "Check-out successful"


def test_search_attendance_returns_contract_keys(client, token):
    params = {"id": 1, "startDate": "01-Aug-2026", "endDate": "31-Aug-2026"}
    r = client.get("/api/Attendance/searchAttendanceByDate", params=params, headers=auth(token))
    body = r.json()
    assert body["isSuccess"] is True
    row = body["data"][0]
    # exact keys AttendanceModel.fromJson reads
    for key in (
        "id", "employee_id", "employee_name", "date_time", "check_in", "check_out",
        "overtimE_MINUTES", "late_duration", "latitude", "longitude",
        "check_out_latitude", "check_out_longitude", "check_in_address",
        "check_out_address", "check_in_face", "check_out_face", "missinG_REASON",
        "status", "approval_status_id", "approval_status",
    ):
        assert key in row, f"missing key {key}"
    assert row["date_time"].endswith("T00:00:00")


def test_attendance_summary(client, token):
    params = {"id": 1, "startDate": "01-Aug-2026", "endDate": "31-Aug-2026"}
    r = client.get("/api/Attendance/userAttendanceSummary", params=params, headers=auth(token))
    body = r.json()
    data = body["data"]
    for key in ("total_days", "present_days", "late_days", "leave_days",
                "weekend_holiday", "overtime_duration"):
        assert key in data
    assert data["present_days"] >= 1
    assert data["total_days"] == 31


def test_edit_request_submit_list_approve(client, token, admin_token):
    r = client.put(
        "/api/Attendance/requestEditAttendance",
        params={"id": 1, "name": "Demo Employee"},
        json=checkin_body(),
        headers=auth(token),
    )
    assert r.json()["isSuccess"] is True

    params = {"id": 1, "startDate": "01-Aug-2026", "endDate": "31-Aug-2026"}
    r = client.get("/api/Attendance/getAttendanceRequest", params=params, headers=auth(token))
    rows = r.json()["data"]
    assert len(rows) == 1
    assert rows[0]["approval_status"] == "Pending"
    request_id = rows[0]["id"]

    r = client.post(
        "/api/Attendance/approveAttendance",
        params={"requestId": request_id, "approvedBy": 2, "approvalStatusId": 2,
                "rejectionReason": ""},
        headers=auth(admin_token),
    )
    assert r.json()["isSuccess"] is True


def test_leave_endpoints(client, token):
    r = client.get("/api/Leave/getLeaveList", headers=auth(token))
    body = r.json()
    assert body["isSuccess"] is True
    assert any(lt["leave_short_name"] == "CL" for lt in body["data"])

    r = client.get("/api/Leave/getEmployeeLeaveSummary", params={"employeeId": 1},
                   headers=auth(token))
    row = r.json()["data"][0]
    assert "employeE_ID" in row and "employeE_NAME" in row
    assert "leavE_SHORT_NAME" in row and "balance" in row


def test_overtime_add_and_list(client, token):
    ot = {
        "id": 0, "employeE_ID": 1, "overtimE_DATE": "2026-08-15T18:30:00",
        "checK_IN": "2026-08-15T09:00:00", "checK_OUT": "2026-08-15T18:30:00",
        "overtimE_MINUTES": 30, "status": "Pending", "reason": "project",
    }
    r = client.post("/api/Overtime", params={"employeeName": "Demo Employee"},
                    json=ot, headers=auth(token))
    assert r.json()["isSuccess"] is True

    r = client.get("/api/Overtime", params={"id": 1}, headers=auth(token))
    body = r.json()
    assert body["isSuccess"] is True
    assert len(body["data"]) == 1
    row = body["data"][0]
    assert "employeE_ID" in row and "overtimE_MINUTES" in row


def test_payslip_generation(client, token):
    r = client.get("/api/Payroll/GetPayslip", params={"employee_id": 1, "salary_year": 2026,
                                                     "salary_month": 8}, headers=auth(token))
    body = r.json()
    assert body["isSuccess"] is True
    data = body["data"]
    for key in ("basic_salary", "gross_salary", "net_pay", "present_days",
                "absent_days", "is_disbursed"):
        assert key in data
    assert data["employee_id"] == "EMP001"


def test_reference_face_registration(client, token):
    r = client.put("/api/Employees/referenceFace", json={"face_base64": make_face()},
                   headers=auth(token))
    assert r.json()["isSuccess"] is True


def test_forget_and_reset_password(client, monkeypatch):
    captured = {}

    def fake_send(to, subject, body):
        captured["body"] = body
        return True

    monkeypatch.setattr("app.routers.login.send_email", fake_send)

    r = client.post("/api/Login/ForgetPassword", params={"email": "demo@ignitia.local"})
    assert r.json()["isSuccess"] is True

    token = None
    for line in captured["body"].splitlines():
        if "token=" in line:
            token = line.split("token=")[1].strip()
    assert token

    r = client.post("/api/Login/ResetPassword",
                    json={"email": "demo@ignitia.local", "token": token,
                          "newPassword": "newpass123"})
    assert r.json()["isSuccess"] is True

    # old password rejected, new password accepted
    assert client.post("/api/Login", json={"email": "demo@ignitia.local",
                                           "password": "demo1234"}).status_code == 401
    assert client.post("/api/Login", json={"email": "demo@ignitia.local",
                                           "password": "newpass123"}).json()["isSuccess"] is True

    # a used token must not work again
    r = client.post("/api/Login/ResetPassword",
                    json={"email": "demo@ignitia.local", "token": token,
                          "newPassword": "another123"})
    assert r.json()["isSuccess"] is False

    # restore the demo password so session-scoped fixtures keep working
    captured.clear()
    client.post("/api/Login/ForgetPassword", params={"email": "demo@ignitia.local"})
    for line in captured["body"].splitlines():
        if "token=" in line:
            restore_token = line.split("token=")[1].strip()
    r = client.post("/api/Login/ResetPassword",
                    json={"email": "demo@ignitia.local", "token": restore_token,
                          "newPassword": "demo1234"})
    assert r.json()["isSuccess"] is True


def test_forget_password_does_not_enumerate(client, monkeypatch):
    captured = {}

    def fake_send(to, subject, body):
        captured["sent"] = True

    monkeypatch.setattr("app.routers.login.send_email", fake_send)
    r = client.post("/api/Login/ForgetPassword", params={"email": "ghost@ignitia.local"})
    assert r.json()["isSuccess"] is True  # same response for unknown email
    assert "sent" not in captured  # no email actually sent
