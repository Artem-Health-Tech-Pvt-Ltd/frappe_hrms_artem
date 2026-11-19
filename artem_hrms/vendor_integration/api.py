import json
import requests
from requests.auth import HTTPBasicAuth

REQUEST_TIMEOUT_SECONDS = 30


def send_vendor_request(vendor_config, payload, is_update=False):
    """Dynamically executes HTTP request to vendor API based on vendor configuration.

    Args:
        vendor_config (Document): Loaded 'Biometric Vendor Configuration' DocType instance.
        payload (dict or list): Prepared request body.
        is_update (bool): Flag indicating if this is an update request.

    Returns:
        tuple: (status_code, body) where body is parsed JSON or raw text response.
    """
    url = vendor_config.api_base_url
    method = (vendor_config.http_method or "POST").upper()

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # 1. Parse and apply Custom Headers (if configured)
    if vendor_config.custom_headers:
        try:
            custom_headers = json.loads(vendor_config.custom_headers)
            if isinstance(custom_headers, dict):
                headers.update(custom_headers)
        except (ValueError, TypeError):
            pass

    # 2. Build Authentication Strategy
    auth = None
    auth_type = vendor_config.auth_type

    if auth_type == "Bearer Token":
        token = vendor_config.get_password("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    elif auth_type == "Basic Auth":
        username = vendor_config.username
        password = vendor_config.get_password("password")
        if username and password:
            auth = HTTPBasicAuth(username, password)

    elif auth_type == "API Key / Secret":
        api_key = vendor_config.api_key
        api_secret = vendor_config.get_password("api_secret")
        if api_key:
            headers["X-API-Key"] = api_key
        if api_secret:
            headers["X-API-Secret"] = api_secret

    # 3. Dispatch Request
    try:
        response = requests.request(
            method=method,
            url=url,
            json=payload,
            auth=auth,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}

        return response.status_code, body

    except Exception as e:
        # Propagate exception to be handled by the worker in employee_sync.py
        raise e