# Security and Authentication

## Passwords

`app/core/security.py` uses `argon2.PasswordHasher` through `hash_password()` and `verify_password()`. Passwords are never returned by public response schemas.

Registration validation requires a password length of at least 8 characters, an uppercase character, a lowercase character, a digit, and a special character. `UserRegistrationRequest` applies the same policy before calling `AuthService.register`.

## JWT access tokens

`create_access_token()` creates an HS256 access token with:

- `sub`: user UUID
- `role`: user role
- `type`: `access`
- `iat`
- `exp`
- `jti`

`get_current_user()` validates the signature and configured algorithm, requires `type=access`, parses the subject as a UUID, and loads an active `User` from the database.

## Refresh tokens

`create_refresh_token()` creates a refresh token with a token family (`tf`) and unique JTI. `AuthService.login()` persists the token in `refresh_tokens`.

`AuthService.refresh_tokens()`:

1. Verifies the JWT signature and refresh type.
2. Requires a stored token record.
3. Uses a row lock during rotation.
4. Rejects revoked or expired records.
5. Revokes the old record and records `replaced_by`.
6. Persists the replacement token in the same transaction.

`AuthService.logout()` marks the stored token revoked and attempts to add a Redis revocation key.

## MFA

`AuthService.setup_mfa()` generates a TOTP secret and provisioning URI. `AuthService.verify_mfa()` enables MFA after validating the password and TOTP code. Login checks MFA state through `AuthService.login()`.

The MFA setup response contains the secret by design so the client can provision it. Transport security and client-side handling are deployment responsibilities.

## RBAC and object authorization

Roles are declared by `UserRole`: `PATIENT`, `DOCTOR`, `ADMIN`, and `SUPPORT`.

`require_role()` supplies role dependencies. Services additionally enforce ownership and participation:

- Only patients create bookings and payments.
- Only admins create/update doctor profiles.
- Doctors may manage their own availability.
- Booking reads are limited to the patient, assigned doctor, or admin.
- Consultation reads are limited to participants or admin.
- Prescriptions are created by the assigned doctor or admin and read by the patient, assigned doctor, or admin.
- Payments are read by the owning patient or admin.

## Rate limiting

`app/core/security.py` implements Redis counters for login, registration, refresh, and MFA. Redis failures are fail-open by design; database authorization and uniqueness constraints remain independent controls.

## Sensitive data handling

`app/core/logging.py` removes configured sensitive keys including authorization data, tokens, passwords, MFA secrets, clinical notes, email, phone, amounts, provider payment IDs, and event payloads before JSON rendering.

Production OpenTelemetry does not use the development console span exporter. HTTP logs contain method, route, status, duration, and correlation ID rather than request bodies or credentials.

## Production configuration rules

When `APP_ENV` is `production` or `prod`, `Settings` rejects:

- SQLite database URLs.
- The default database password.
- Wildcard CORS.
- Non-HTTPS CORS origins.
- Short or placeholder JWT secrets.
- JWT algorithms other than the configured supported HS256 mode.

Secrets must be supplied through environment variables or a secret manager and must not be committed to `.env.example` or source control.
