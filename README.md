# Clinic Appointment API

A REST API for a clinic appointment (booking) system: doctors publish free time slots, patients book them, and both sides can view/cancel their own appointments.

Built with Python 3.11, Django 5.2, Django REST Framework, PostgreSQL 16 — no other framework, as required by the brief.

## Quickstart

```bash
git clone <this-repo-url>
cd clinic-appointments
docker compose up --build
```

That's it — no `.env` file needs to be created first. `docker-compose.yml` has a sane development default for every variable (`${VAR:-default}` syntax); if you *do* want to override something, copy `.env.example` to `.env` and Compose will pick it up automatically for variable substitution.

Once it's up:

- API base: `http://localhost:8000/api/`
- Swagger UI: `http://localhost:8000/api/docs/`
- Django admin: `http://localhost:8000/admin/`

Populate some demo data to explore the API by hand (see [Demo data](#demo-data) below).

## Running the tests

```bash
docker compose exec api python manage.py test apps --noinput -v 2
```

(or, without Docker, `python manage.py test apps --noinput -v 2` inside a virtualenv with `requirements.txt` installed and `POSTGRES_HOST=localhost` etc. pointing at a real Postgres — SQLite is not supported, several constraints below are PostgreSQL-specific).

39 tests, organized by which business rule they prove:

| File | Rule(s) |
|---|---|
| `apps/appointments/tests/test_rule1_concurrency.py` | **Rule 1** — 10 real concurrent threads book the same slot; asserts exactly one `201`, the rest `400`, zero `500`. Plus a second test proving the DB constraint alone (bypassing the view) still rejects a double booking. |
| `apps/appointments/tests/test_rule2_rule3_booking_validation.py` | Rules 2, 3 — no booking the past; no overlapping bookings for one patient, including a DB-constraint-only test. |
| `apps/appointments/tests/test_rule4_cancellation_window.py` | Rule 4 (and 5) — cancel only >2h before start; cancelling frees the slot for rebooking. |
| `apps/appointments/tests/test_rule6_permissions.py` | Rule 6 — patients/doctors only ever see their own data; role gating on every endpoint; anonymous access is rejected. |
| `apps/slots/tests/test_rule7_no_overlapping_slots.py` | Rule 7 — a doctor can't create overlapping slots for themselves; different doctors can overlap freely; DB-constraint-only test. |
| `apps/appointments/tests/test_rule8_utc_handling.py` | Rule 8 — non-UTC ISO 8601 input is converted and stored as UTC; responses use UTC. |
| `apps/appointments/tests/test_admin_n_plus_one.py` | Bonus — proves the admin appointments list's query count does not grow with result count. |
| `apps/users/tests/test_auth.py`, `apps/doctors/tests/test_doctors_listing.py` | Registration/login/refresh; doctor filtering, pagination, free-slots endpoint. |

## Demo data

```bash
docker compose exec api python manage.py seed_demo_data
```

Creates 3 doctors (`dr_cardio`, `dr_neuro`, `dr_derma`), 3 patients (`patient_demo1..3`) and an admin (`admin_demo`), all with password `DemoPass123!`, plus a day of 30-minute slots for each doctor. Safe to re-run.

## Endpoints

| Method & path | Who | What |
|---|---|---|
| `POST /api/auth/register/` | anyone | patient self-registration |
| `POST /api/auth/login/` | anyone | JWT access + refresh (rate-limited) |
| `POST /api/auth/refresh/` | anyone | refresh an access token |
| `GET /api/doctors/` | authenticated | list doctors, filter by `specialization`/`branch`, paginated |
| `GET /api/doctors/{id}/slots/?date=YYYY-MM-DD` | authenticated | that doctor's free slots on a UTC date |
| `POST /api/appointments/` | patient | book a slot (`{"slot": <id>}`) |
| `GET /api/appointments/` | patient | the caller's own appointments |
| `POST /api/appointments/{id}/cancel/` | patient | cancel own appointment (>2h rule) |
| `POST /api/slots/` | doctor | create a batch of slots in one request |
| `GET /api/slots/mine/` | doctor | own schedule, with who booked each slot |
| `GET /api/admin/appointments/` | admin | all appointments; filter by `doctor`, `branch`, `date_from`/`date_to`, `status` |
| `GET /api/docs/` | — | Swagger UI (bonus) |

## Design decisions and why

**Role model.** `User.role` (`patient`/`doctor`/`admin`) is an explicit field, kept separate from Django's `is_staff`/`is_superuser` (which stay reserved for Django-admin access only). Every business permission check reads `request.user.role`, never `is_staff`. This keeps "who can call this endpoint" trivially auditable in one place (`apps/common/permissions.py`) instead of scattered assumptions about Django's built-in flags.

**Registration is patient-only.** `POST /api/auth/register/` always creates a patient, even if the request body includes a `role` field (it's ignored — see `PatientRegisterSerializer`). Doctor and admin accounts are provisioned out of band (Django admin, or `seed_demo_data` for local exploration). Opening self-registration to all roles would let anyone declare themselves a doctor, which is a much bigger hole than the brief is asking us to close.

**The race condition (rule 1) — the core of the assignment.** Two layers, deliberately redundant:

1. **Application layer:** `POST /api/appointments/` wraps the whole check-then-create sequence in `transaction.atomic()` and takes a row lock on the target `Slot` with `select_for_update()`. Two concurrent requests for the *same* slot are serialized by Postgres itself — the second one only proceeds once the first has committed (or rolled back), at which point it correctly sees the slot as already booked and returns a clean `400`.
2. **Database layer:** `Appointment` has `UniqueConstraint(fields=["slot"], condition=Q(status="booked"))` — a partial unique index that makes it *impossible*, at the schema level, for two `booked` rows to reference the same slot, no matter what application code does (or fails to do) in the future. The view catches the resulting `IntegrityError` and turns it into a `400` with a specific message, as defense in depth.

`test_rule1_concurrency.py` proves this isn't just a theoretical argument: it fires 10 real concurrent HTTP requests (via `threading`) at the same slot and asserts exactly one `201` and nine clean `400`s.

**Rule 3 (no overlapping bookings for one patient) and rule 7 (no overlapping slots for one doctor)** use the same defense-in-depth pattern, but the database half is a PostgreSQL `ExclusionConstraint` (GIST index, `btree_gist` extension) on a time range rather than a simple unique index — because the thing being prevented is a *range overlap*, not an exact duplicate. This is what stops the case a naive "check for an overlap, then insert" application check cannot fully close on its own: two different (non-identical) time ranges being inserted at the same instant by two racing requests.

**Why `Appointment.start_time`/`end_time` are denormalized from `Slot`.** PostgreSQL's `ExclusionConstraint` can only reference columns of the table it's declared on — it can't reach through a `slot__start_time` join. Copying the times onto `Appointment` at booking time (they never change afterwards — cancelling doesn't move them, rebooking creates a new row) makes the rule-3 constraint expressible directly on `Appointment`, and is a fair trade for a hard integrity guarantee.

**"Free" is derived, not stored.** `Slot` has no `is_booked` boolean. A slot is free iff it has no related `Appointment` with `status="booked"` (see `Slot.is_free`/`active_appointment`). A redundant flag could theoretically drift out of sync with reality (e.g. after a bug in a future migration or a bulk update); deriving it from the actual booking state removes that failure mode entirely, at the cost of one extra (indexed, cheap) lookup.

**Permissions are two-layered on purpose (rule 6).** `get_queryset()` filters every list/detail endpoint to the caller's own data, *and* object-level permission classes (`IsOwnerPatient`, `IsOwnerDoctor`) re-check ownership on the object DRF actually resolves. Either one alone is a single point of failure if a future view forgets to apply it; together, an ownership bug requires forgetting both.

**Bulk slot creation.** The brief asks for creating a day's slots in one request. `POST /api/slots/` takes an overall `[start_time, end_time)` window (full ISO 8601 datetimes, not just times-of-day, so timezone handling stays consistent with rule 8) plus `slot_duration_minutes`, and slices it into equal back-to-back slots, created atomically — if any of them would overlap a slot the doctor already owns, the entire batch is rolled back rather than partially created, so a doctor never ends up with a confusing half-created day.

**JWT / password hashing.** Both come from `djangorestframework-simplejwt` and Django's own `set_password`/`check_password` (PBKDF2) — none of it hand-rolled, per the brief's explicit requirement.

**Pagination & filtering.** DRF's `PageNumberPagination` (page size configurable via `DRF_PAGE_SIZE`) and `django-filter` for `specialization`/`branch`/`doctor`/`branch`/`date_from`/`date_to`.

**N+1 avoidance (bonus).** `GET /api/admin/appointments/` and `GET /api/slots/mine/` use `select_related`/`prefetch_related` so listing N rows doesn't cost N extra queries. This is verified, not just claimed: `test_admin_n_plus_one.py` measures the actual query count (via `CaptureQueriesContext`) at 3 vs. 12 appointments and asserts it doesn't grow. One related gotcha worth calling out: `Slot.active_appointment` deliberately iterates `self.appointments.all()` in Python instead of calling `.filter(status="booked").first()`, because `.filter()` always issues a fresh query and would silently defeat `prefetch_related("appointments")` upstream, reintroducing the exact N+1 this test guards against.

**Why plain `CharField`s for `specialization`/`branch` instead of separate lookup tables.** The brief doesn't ask for managing a catalog of specialties or branches, and a smaller, correct model beats a speculative one — this is exactly the kind of judgment call the brief invites us to make and document rather than guess at.

## What I'd do differently with more time

- **Refresh token revocation on logout.** `SIMPLE_JWT` rotates refresh tokens but doesn't blacklist them (`BLACKLIST_AFTER_ROTATION = False`, and `rest_framework_simplejwt.token_blacklist` isn't installed) — there's no `/api/auth/logout/`. Fine for the scope here, but a real deployment would want token blacklisting on logout/password change.
- **Doctor/patient profile fields are minimal.** No phone number, avatar, working-hours template, etc. — out of scope for what's being graded, but the first thing a real product would need.
- **Slot editing/deletion isn't implemented** (only create + list). The brief doesn't ask for it, but a real doctor would want to edit or cancel a slot they haven't published bookings against yet.
- **No idempotency key on booking.** A retried `POST /api/appointments/` after a dropped connection (rather than a genuine race) would currently just get a clean 400 ("already booked") if the first request actually succeeded server-side — acceptable, but an `Idempotency-Key` header would be more precise about *why* it failed.
- **Rate limiting is login-only.** A production API would likely throttle booking/cancellation too, to blunt scripted abuse, not just brute-force login attempts.
- **No `/api/auth/me/` endpoint.** Small convenience omission — the JWT payload does carry `role`, so a client can decode it client-side, but a dedicated endpoint would be friendlier.
- **Structured logging / request IDs** aren't set up — would matter a lot for debugging a real production incident, not for what's being evaluated here.

None of the above affect the 8 business rules or the deliverable checklist in the brief; they're the honest list of "next things," not missing requirements.

## Environment variables

See `.env.example` for the full list with defaults. Nothing needs to be created for `docker compose up` to work — see [Quickstart](#quickstart).

## Repository layout

```
apps/
  users/         custom User model (role field), registration, JWT login/refresh
  doctors/       Doctor profile, doctor listing + free-slots endpoint
  slots/         Slot model, bulk slot creation, doctor's own schedule
  appointments/  Appointment model, booking/cancellation, admin listing, seed command
  common/        shared permission classes, test fixtures
config/          Django project settings/urls
docker/          container entrypoint (waits for Postgres, runs migrations)
docs/            architecture/ER/concurrency diagrams and DB model notes from planning
```
