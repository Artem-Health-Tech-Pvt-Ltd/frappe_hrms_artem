import requests
from requests.auth import HTTPBasicAuth

from .constants import (
    VENDOR_BASE_URL,
    VENDOR_USERNAME,
    VENDOR_PASSWORD,
    REQUEST_TIMEOUT_SECONDS,
)

ADD_PATH = "/api/v1/hims/users/add"
UPDATE_PATH = "/api/v1/hims/users/update"


def add_employees(employees):
    return _post(f"{VENDOR_BASE_URL.rstrip('/')}{ADD_PATH}", employees)


def update_employees(employees):
    return _post(f"{VENDOR_BASE_URL.rstrip('/')}{UPDATE_PATH}", employees)


def _post(url, employees):
    response = requests.post(
        url,
        json=employees,
        auth=HTTPBasicAuth(VENDOR_USERNAME, VENDOR_PASSWORD),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return response.status_code, body