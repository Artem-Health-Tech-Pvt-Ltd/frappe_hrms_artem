# Mock Vendor Server

A standalone Flask app that mimics a real biometric vendor API for testing the
vendor sync engine end-to-end.

## What it supports

All 4 auth types configured in `Biometric Vendor Configuration`:
- **No Auth** — accepts any request
- **Bearer Token** — requires `Authorization: Bearer <secret>`
- **Basic Auth** — requires `Authorization: Basic <base64(user:pass)>`
- **API Key / Secret** — requires `X-API-Key` + `X-API-Secret` headers

Plus:
- **Custom headers** — captures and echoes back
- **Status code simulator** — set `?_status=422` (or any code) to test error paths
- **Slow response** — `?_delay=3` to test client-side timeouts
- **Request log + dump endpoint** — every request is saved and viewable

## Run

```bash
cd /home/artem/apps/frappe-bench/apps/artem_hrms/artem_hrms/vendor_integration/mock_vendor
pip install flask  # if not installed
python3 server.py
# Server listening on http://127.0.0.1:5050
```

## Configure Biometric Vendor Configuration records

Create one vendor record per auth type you want to test, all pointing here:

| Vendor Name | API Base URL | Auth Type | Credentials |
|---|---|---|---|
| `Mock - No Auth` | `http://127.0.0.1:5050/users/add` | No Auth | — |
| `Mock - Bearer` | `http://127.0.0.1:5050/users/add` | Bearer Token | token = `test-bearer-secret` |
| `Mock - Basic` | `http://127.0.0.1:5050/users/add` | Basic Auth | user = `kem`, password = `kem-secret` |
| `Mock - API Key` | `http://127.0.0.1:5050/users/add` | API Key/Secret | api_key = `my-key`, api_secret = `my-secret` |

## Test endpoints

| Path | Purpose |
|---|---|
| `POST/GET /users/add` | Main sync endpoint (configurable via URL) |
| `GET /dump` | JSON dump of all requests received |
| `POST /dump/clear` | Reset the log |
| `GET /` | Web UI to view captured requests |

## Response shaping

By default returns:
```json
{
  "data": [{"employee_id": "VEND-1", "uuid": "uuid-from-attendance-device-id"}]
}
```

Query params to trigger edge cases:
- `?_status=422&_msg=Bad%20branch` — returns HTTP 422 with custom message
- `?_status=401` — returns HTTP 401
- `?_status=429` — returns HTTP 429
- `?_delay=N` — sleeps N seconds before responding

Example: `http://127.0.0.1:5050/users/add?_status=422&_msg=Invalid%20department`
