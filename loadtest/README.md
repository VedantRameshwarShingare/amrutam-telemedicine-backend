# Local Load Test

This lightweight runner uses the existing `httpx` dependency and exercises health, login, doctor discovery, availability, and booking without changing application code.

Set credentials for an existing patient. Optionally set `LOADTEST_DOCTOR_ID` and a comma-separated `LOADTEST_SLOT_IDS` to control the discovery and booking targets.

PowerShell example:

```powershell
$env:LOADTEST_EMAIL = "patient@example.com"
$env:LOADTEST_PASSWORD = "use-a-local-test-password"
$env:LOADTEST_DOCTOR_ID = "doctor-uuid"
$env:LOADTEST_SLOT_IDS = "slot-uuid-1,slot-uuid-2"
\.venv\Scripts\python.exe .\loadtest\load_test.py --base-url http://127.0.0.1:8000 --concurrency 2 --duration 30
```

Booking `409` responses are reported as expected contention, not errors. All other unexpected statuses and transport failures are counted as errors. The process exits non-zero if no requests complete or any unexpected errors occur.