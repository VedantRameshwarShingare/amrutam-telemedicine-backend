# API Reference

The application is created by `app.main.app`. Domain routers are mounted by `app/api/router.py` under `/api/v1`.

Authentication uses `Authorization: Bearer <access-token>` for protected endpoints. Successful mutation responses use the status codes listed below. Validation errors are produced by FastAPI/Pydantic; application errors use the JSON shape `{"error":{"code":"...","message":"..."}}` where handled by the application exception handlers.

## System

| Method | Path | Auth | Handler |
| --- | --- | --- | --- |
| `GET` | `/health` | No | `app.main.healthcheck` |
| `GET` | `/metrics` | No | `app.main.metrics` |
| `GET` | `/api/v1/health` | No | `app.api.router.api_health` |

## Authentication

| Method | Path | Auth/role | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Public | `UserRegistrationRequest` | `UserPublicResponse`, `201` |
| `POST` | `/api/v1/auth/login` | Public | `LoginRequest` | `TokenPairResponse`, `200` |
| `POST` | `/api/v1/auth/refresh` | Public | `RefreshTokenRequest` | `TokenPairResponse`, `200` |
| `POST` | `/api/v1/auth/logout` | Public | `LogoutRequest` | `{"status":"success"}`, `200` |
| `POST` | `/api/v1/auth/mfa/setup` | Public credentials | `MFATokenSetupRequest` | `MFASetupResponse`, `200` |
| `POST` | `/api/v1/auth/mfa/verify` | Public credentials | `MFAVerifyRequest` | object containing `verified`/`status`, `200` |
| `GET` | `/api/v1/auth/me` | Active user | None | `UserPublicResponse`, `200` |
| `GET` | `/api/v1/auth/admin-example` | `ADMIN` | None | message object, `200` |

`UserRegistrationRequest` fields: `email: EmailStr`, `phone: str` length 8-32, `password: str` length 8-128, and optional `role: UserRole | None`. Public registration rejects `ADMIN` in `AuthService.register`.

`LoginRequest` fields: `email: EmailStr`, `password: str`.

`TokenPairResponse` fields: `access_token`, `refresh_token`, and `token_type` (default `bearer`).

## Doctors and availability

| Method | Path | Auth/role | Request | Response |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/doctors` | Active user | Query filters/pagination | `DoctorListResponse`, `200` |
| `GET` | `/api/v1/doctors/{doctor_id}` | Active user | None | `DoctorResponse`, `200` |
| `GET` | `/api/v1/doctors/{doctor_id}/availability` | Active user | Optional `start`, `end` | list of `AvailabilitySlotResponse`, `200` |
| `POST` | `/api/v1/doctors` | `ADMIN` | `DoctorCreateRequest` | `DoctorResponse`, `201` |
| `PATCH` | `/api/v1/doctors/{doctor_id}` | `ADMIN` | `DoctorUpdateRequest` | `DoctorResponse`, `200` |
| `POST` | `/api/v1/doctors/me/availability` | `DOCTOR` | `AvailabilitySlotCreateRequest` | `AvailabilitySlotResponse`, `201` |
| `PATCH` | `/api/v1/doctors/me/availability/{slot_id}` | `DOCTOR` owner | `AvailabilitySlotUpdateRequest` | `AvailabilitySlotResponse`, `200` |
| `DELETE` | `/api/v1/doctors/me/availability/{slot_id}` | `DOCTOR` owner | None | `204` |

`DoctorCreateRequest`: `user_id`, `license_number`, `specialization`, `experience_years` 0-80, `consultation_fee` non-negative decimal with two decimal places, optional `status` defaulting to `ACTIVE`.

`AvailabilitySlotCreateRequest`: timezone-aware `start_time` and `end_time`; start must precede end and the interval must not overlap another non-cancelled slot for the doctor.

## Bookings

| Method | Path | Auth/role | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/bookings` | `PATIENT` | `BookingCreateRequest` | `BookingResponse`, `201` |
| `GET` | `/api/v1/bookings` | Active user | `page`, `page_size` | `BookingListResponse`, `200` |
| `GET` | `/api/v1/bookings/{booking_id}` | Patient, assigned doctor, or admin | None | `BookingResponse`, `200` |
| `POST` | `/api/v1/bookings/{booking_id}/cancel` | Patient, assigned doctor, or admin | `BookingCancelRequest` | `BookingResponse`, `200` |

`BookingCreateRequest`: `slot_id: UUID`, `idempotency_key: str` length 8-128.

`BookingCancelRequest`: optional `reason` with maximum length 500.

## Consultations and prescriptions

| Method | Path | Auth/role | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/consultations` | Patient or assigned doctor participant | `ConsultationCreateRequest` | `ConsultationResponse`, `201` |
| `GET` | `/api/v1/consultations/{consultation_id}` | Patient, assigned doctor, or admin | None | `ConsultationResponse`, `200` |
| `PATCH` | `/api/v1/consultations/{consultation_id}/status` | Assigned doctor or admin | `ConsultationStatusRequest` | `ConsultationResponse`, `200` |
| `POST` | `/api/v1/prescriptions/consultations/{consultation_id}` | Assigned doctor or admin | `PrescriptionCreateRequest` | `PrescriptionResponse`, `201` |
| `GET` | `/api/v1/prescriptions/{prescription_id}` | Patient, assigned doctor, or admin | None | `PrescriptionResponse`, `200` |

Consultation statuses are `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`, and `CANCELLED`. The implemented transitions are `SCHEDULED -> IN_PROGRESS/CANCELLED` and `IN_PROGRESS -> COMPLETED/CANCELLED`.

Prescription medication items contain `name`, `dosage`, `frequency`, `duration`, and optional `instructions`.

## Payments and analytics

| Method | Path | Auth/role | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/payments` | `PATIENT` owning the confirmed booking | `PaymentCreateRequest` | `PaymentResponse`, `201` |
| `GET` | `/api/v1/payments/{payment_id}` | Patient owner or admin | None | `PaymentResponse`, `200` |
| `GET` | `/api/v1/analytics/summary` | `ADMIN` | None | summary object, `200` |

`PaymentCreateRequest`: `booking_id: UUID`, `idempotency_key` length 8-128, and three-letter `currency` defaulting to `INR`.

Payment statuses are `PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, and `REFUNDED`. The mock provider returns success by default and returns a decline for idempotency keys beginning with `fail-`.
