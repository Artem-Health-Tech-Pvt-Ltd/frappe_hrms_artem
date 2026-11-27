import json
import requests
from requests.auth import HTTPBasicAuth

REQUEST_TIMEOUT_SECONDS = 30


def send_vendor_request(vendor_config, payload, is_update=False):
    """Dynamically executes HTTP request to vendor API based on vendor configuration.
    Supports separate authentication sections for Employee Creation API and Employee Update API.

    Args:
        vendor_config (Document): Loaded 'Biometric Vendor Configuration' DocType instance.
        payload (dict or list): Prepared request body.
        is_update (bool): Flag indicating if this is an update request.

    Returns:
        tuple: (status_code, body) where body is parsed JSON or raw text response.
    """
    if is_update and getattr(vendor_config, "api_update_url", None):
        url = vendor_config.api_update_url
    else:
        url = vendor_config.api_base_url

    if is_update and getattr(vendor_config, "update_http_method", None):
        method = vendor_config.update_http_method.upper()
    else:
        method = (vendor_config.http_method or "POST").upper()

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Determine whether to use separate Update Authentication or Creation Authentication
    use_update_auth = is_update and (
        bool(getattr(vendor_config, "update_auth_type", None))
        or bool(getattr(vendor_config, "update_custom_headers", None))
    )

    if use_update_auth:
        custom_headers_str = getattr(vendor_config, "update_custom_headers", None)
        auth_type = getattr(vendor_config, "update_auth_type", None)
        token = vendor_config.get_password("update_token") if hasattr(vendor_config, "get_password") else None
        if not token and hasattr(vendor_config, "get_password"):
            token = vendor_config.get_password("token")
        username = getattr(vendor_config, "update_username", None) or getattr(vendor_config, "username", None)
        password = vendor_config.get_password("update_password") if hasattr(vendor_config, "get_password") else None
        if not password and hasattr(vendor_config, "get_password"):
            password = vendor_config.get_password("password")
        api_key = getattr(vendor_config, "update_api_key", None) or getattr(vendor_config, "api_key", None)
        api_secret = vendor_config.get_password("update_api_secret") if hasattr(vendor_config, "get_password") else None
        if not api_secret and hasattr(vendor_config, "get_password"):
            api_secret = vendor_config.get_password("api_secret")
    else:
        custom_headers_str = getattr(vendor_config, "custom_headers", None)
        auth_type = getattr(vendor_config, "auth_type", None)
        token = vendor_config.get_password("token") if hasattr(vendor_config, "get_password") else None
        username = getattr(vendor_config, "username", None)
        password = vendor_config.get_password("password") if hasattr(vendor_config, "get_password") else None
        api_key = getattr(vendor_config, "api_key", None)
        api_secret = vendor_config.get_password("api_secret") if hasattr(vendor_config, "get_password") else None

    # 1. Parse and apply Custom Headers (if configured)
    if custom_headers_str:
        try:
            custom_headers = json.loads(custom_headers_str)
            if isinstance(custom_headers, dict):
                headers.update(custom_headers)
        except (ValueError, TypeError):
            pass

    # 2. Build Authentication Strategy (4 configurable auth methods: No Auth, Bearer Token, Basic Auth, API Key / Secret)
    auth = None

    if auth_type == "Bearer Token":
        if token:
            headers["Authorization"] = f"Bearer {token}"

    elif auth_type == "Basic Auth":
        if username and password:
            auth = HTTPBasicAuth(username, password)

    elif auth_type == "API Key / Secret":
        if api_key:
            headers["X-API-Key"] = api_key
        if api_secret:
            headers["X-API-Secret"] = api_secret

    elif auth_type == "No Auth":
        auth = None

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