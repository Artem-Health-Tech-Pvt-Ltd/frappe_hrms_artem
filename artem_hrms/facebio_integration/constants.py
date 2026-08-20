FACEBIO_BASE_URL = "https://kem.my-attendance.in"
FACEBIO_USERNAME = "KemHospitalhims"
FACEBIO_PASSWORD = "PX]h9Yr3=2f@!23Wxks8"
REQUEST_TIMEOUT_SECONDS = 30

# Map of Frappe Employee.branch → branch value sent to FaceBio.
# Employee is only synced if their Frappe branch is a key here (case-insensitive trim).
# Add entries here when FaceBio approves more branches.
BRANCH_MAP = {
    "Seth G S Medical College and King Edward Memorial Hospital": "KEM Hospital",
}
