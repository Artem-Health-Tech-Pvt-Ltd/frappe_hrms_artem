import requests
from requests.auth import HTTPBasicAuth

from .constants import (
    FACEBIO_BASE_URL,
    FACEBIO_PASSWORD,
    FACEBIO_USERNAME,
    REQUEST_TIMEOUT_SECONDS,
)

def add_employees(employees: list[dict]) -> tuple[int, dict]:
    return _post("/api/v1/hims/users/add", employees)

def update_employees(employees: list[dict]) -> tuple[int, dict]:
    return _post("/api/v1/hims/users/update", employees)

def _post(path: str, employees: list[dict]) -> tuple[int, dict]:
    url = f"{FACEBIO_BASE_URL.rstrip('/')}{path}"
    response = requests.post(
        url,
        json=employees,
        auth=HTTPBasicAuth(FACEBIO_USERNAME, FACEBIO_PASSWORD),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return response.status_code, body
