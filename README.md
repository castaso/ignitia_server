# ignitia_server

Backend for the **i_employment** Flutter app (client repo: `castaso/ignitia`),
with the headline feature **"prevent proxy attendance"** implemented
**server-side**:

- **Geo-fence** - every check-in / check-out is re-validated against the
  configured office centre + radius using haversine distance.
- **Face verification** - every submitted face capture is matched against the
  employee's registered reference photo before the attendance is accepted.

The client only proves that a *live single face* was present and that the
device reported coordinates inside range; this server is the **source of
truth** and rejects any attendance that fails either check.

The API is **wire-compatible** with the Flutter client: same endpoints, Bearer
auth, response envelope `{ "isSuccess": bool, "message": str, "data": ... }`,
and the exact JSON keys the client parses (including the quirky
`missinG_REASON` / `overtimE_MINUTES` / `employeE_ID` / `overtimE_DATE` /
`checK_IN` / `checK_OUT`).

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# optional: configure office location / thresholds
cp .env.example .env

# create tables + demo user + reference face
.venv/bin/python seed.py

# run on 0.0.0.0:86 (the port the Flutter client points at)
.venv/bin/python run.py
```

Interactive API docs: `http://localhost:86/docs`

## Demo credentials

| Role | Email | Password |
|------|-------|----------|
| Employee | `demo@ignitia.local` | `demo1234` |
| Admin | `admin@ignitia.local` | `admin1234` |

The demo user already has a synthetic reference face registered, so the
face-verification path can be exercised immediately. To register a real
photo, send the base64 JPEG to `PUT /api/Employees/referenceFace` (a real
registration UI is expected to be added to the app).

## Configuration (.env)

| Key | Default | Purpose |
|-----|---------|---------|
| `JWT_SECRET` | `change-me-...` | Signing secret - **change in production** |
| `JWT_EXPIRE_HOURS` | `720` | Token lifetime |
| `OFFICE_LATITUDE` / `OFFICE_LONGITUDE` | Dhaka placeholder `23.810331, 90.412521` | Office centre |
| `OFFICE_RADIUS_METERS` | `300` | Allowed distance from centre |
| `OFFICE_START_TIME` / `OFFICE_END_TIME` | `09:00` / `18:00` | For `late_duration` / `overtimE_MINUTES` |
| `FACE_SIMILARITY_THRESHOLD` | `0.72` | 0..1; lower = stricter |
| `UPLOAD_DIR` | `uploads/faces` | Where submitted faces are stored |
| `DATABASE_URL` | `sqlite:///./ignitia.db` | DB connection |

> The Flutter client carries a *placeholder* geo-fence
> (`lib/config/office_location_config.dart`: 23.810331, 90.412521, 300 m).
> Adjust the server values to the real office; the server values win.

## API surface (all under `/api`)

Matching `lib/repo/api_service.dart`:

- **Auth**: `POST /Login`, `POST /Login/ChangePassword`, `POST /Login/ForgetPassword?email=`,
  plus server-side `POST /Login/ResetPassword` (reset-link flow, see below)
- **Attendance**: `POST /Attendance/v2/checkin`, `POST /Attendance/v2/checkout`,
  `GET /Attendance/searchAttendanceByDate`, `GET /Attendance/userAttendanceSummary`,
  `PUT /Attendance/requestEditAttendance`, `GET /Attendance/getAttendanceRequest`,
  `DELETE /Attendance/deleteAttendanceRequest`, `POST /Attendance/approveAttendance`
- **Employees**: `GET /Employees`, `GET /Employees/profile`, `GET /Employees/GetContactInfo`,
  `PUT /Employees`, plus server-only `PUT /Employees/referenceFace`
- **Leave**: `GET /Leave/getEmployeeLeaveSummary`, `GET /Leave/getLeaveList`,
  `GET /Leave`, `POST /Leave`, `PUT /Leave`, `PUT /Leave/approveEmployeeLeave`, `DELETE /Leave`
- **Overtime**: `GET /Overtime`, `POST /Overtime`, `PUT /Overtime`,
  `PUT /Overtime/ApproveOvertime`, `PUT /Overtime/RejectOvertime`, `DELETE /Overtime`
- **Payroll**: `GET /Payroll/GetPayslip`

### Auth contract details (important)

- A successful `POST /Login` returns the raw **JWT in the `message` field**
  (the client does `FieldValue.token = responseModel.message`).
- All protected endpoints expect `Authorization: Bearer <jwt>` (the client
  prepends `Bearer ` itself).
- Failed logins return **HTTP 401** - the client maps this to "Unauthorized"
  and does not attempt to parse `data` (a 200-with-null-data response would
  crash its `data!` access).
- Business failures (geo-fence / face / duplicate check-in) return **HTTP 200**
  with `isSuccess: false` and a human-readable `message`, which the app shows.

### Password reset flow

`POST /Login/ForgetPassword?email=` always returns success (anti-account-
enumeration). When the email exists it issues a one-time, expiring reset token
(only its hash is stored) and emails a reset link. Without SMTP config the link
is written to the server log instead. The link target is
`POST /Login/ResetPassword` with body `{email, token, newPassword}`. Configure
`SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` in `.env` to send
real mail.

## Face verification - how it works

1. The employee registers a reference photo (`PUT /api/Employees/referenceFace`).
2. On check-in/out the app sends its captured face as base64 JPEG
   (`check_in_face` / `check_out_face`).
3. The server detects the face (OpenCV YuNet) and compares embeddings with
   **SFace** (cosine similarity, threshold `FACE_EMBEDDING_THRESHOLD`). When
   the SFace models are unavailable or no face is detected (e.g. the synthetic
   demo face), it falls back to a perceptual-hash + histogram comparison of
   the face region (`FACE_SIMILARITY_THRESHOLD`).
4. Blank / featureless submissions are rejected outright.
5. Accepted captures are decoded and saved to `uploads/faces/`.

## Liveness (blink challenge) - how it works

Real-time liveness prevents a static or replayed photo from passing the face
check:

1. The app runs a blink challenge on the live camera stream (ML Kit eye-state
   classification): eyes-open -> eyes-closed -> eyes-open. When a blink is
   detected it submits a short sequence of the captured frames as base64 JPEG
   in `liveness_frames` along with the check-in/out request.
2. Before capturing, the app fetches a fresh single-use challenge
   (`GET /api/Attendance/livenessChallenge`) and submits it as `challenge_id`
   with the frames. The server consumes it on first use, so a pre-recorded
   frame sequence cannot be replayed against a later check-in
   (`LIVENESS_CHALLENGE_TTL_SECONDS` bounds each challenge's lifetime).
3. The server (`validate_liveness_frames` in `app/security.py`) requires a
   minimum number of frames (`MIN_LIVENESS_FRAMES`), rejects frames that do
   not decode or are blank/featureless, and rejects sequences with no motion
   (a single still photo replayed N times produces identical consecutive
   frames, which fails `LIVENESS_MIN_DIVERSITY`).
4. With `LIVENESS_REQUIRED=true` the check-in/out is rejected outright when no
   `liveness_frames` are supplied.

The blink is detected on-device; the server validates the frame sequence was
live, tied to a fresh challenge, and not a static replay. The motion + fresh-
challenge checks also apply on web, where the app captures a short live burst
in place of ML Kit blink classification.

## Roadmap / known gaps

- No Alembic migrations yet (tables are created with `create_all`).
- Password reset links are only emailed when SMTP is configured; otherwise the
  link is logged (dev mode).
- Face verification falls back to a perceptual-hash baseline only when the
  SFace embedding models are unavailable or no face is detected; the bundled
  SFace + YuNet models provide real embedding-based matching.
- The client's hard-coded base URL `http://27.147.159.195:86/api/` must point
  at this server (e.g. via a local override / reverse proxy in the preview
  environment).

## Tests

```bash
pytest tests/ -v
```

The suite spins the app up against an isolated temp database and exercises
the exact wire contract used by the Flutter client (login/JWT, 401 handling,
geo-fence and face blocks, check-in/out, search, summary, edit-request
approval, leave, overtime, payslip).
