# System-level fallback constants for the vendor sync engine.
# All vendor-specific credentials, URLs, and branch mappings now live in the
# Biometric Vendor Configuration DocType (configured via the Desk UI and
# stored encrypted via Password fields / get_password()).

REQUEST_TIMEOUT_SECONDS = 30

MAX_429_RETRIES = 3
RETRY_DELAY_SECONDS = 60

# Sync status values written back to Employee custom fields.
PENDING = "Pending"
SYNCED = "Synced"
FAILED = "Failed"
NOT_SYNCED = "Not Synced"

# Auth types supported by Biometric Vendor Configuration.
AUTH_NONE = "No Auth"
AUTH_BEARER = "Bearer Token"
AUTH_BASIC = "Basic Auth"
AUTH_API_KEY = "API Key / Secret"