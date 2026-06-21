"""
All constants for the Instagram Private API client

These values are derived from/reference Instagram Lite 516.0.0.8.103 (APKPure)
combined with an Instagram Android profile that works reliably against the
i.instagram.com/api/v1 backend.

Important NOTE on "what actually works":
    - The request structure / signing / headers / endpoints are what make the
      client function.
    - APP_VERSION / VERSION_CODE must be "updatable" because Instagram
      periodically rejects versions that are too old -> change them in this
      single file.
"""

# ---------------------------------------------------------------------------
# Endpoint / domains
# ---------------------------------------------------------------------------
API_DOMAIN = "i.instagram.com"
API_VERSION = "v1"
BASE_API_URL = f"https://{API_DOMAIN}/api/{API_VERSION}/"

# Instagram Lite domain (from dex: iglite-z.instagram.com) — same backend
LITE_API_DOMAIN = "iglite-z.instagram.com"

# Web domain (used with public_request / web_profile_info / graphql)
WEB_DOMAIN = "www.instagram.com"
GRAPHQL_URL = f"https://{WEB_DOMAIN}/graphql/query/"
WEB_API_URL = f"https://{WEB_DOMAIN}/api/v1/"

# ---------------------------------------------------------------------------
# App profile (change this when IG starts rejecting the version)
# ---------------------------------------------------------------------------
# Value from the reverse-engineered Instagram Lite APK
IG_LITE_VERSION = "516.0.0.8.103"

# Instagram Android profile used as the default (stable with the private API)
# The APP_VERSION/VERSION_CODE pair must always match
APP_VERSION = "314.0.0.20.114"
VERSION_CODE = "542473058"

# X-IG-App-ID (pulled from the APK's classes.dex) = standard Instagram app id
APP_ID = "567067343352427"

# Bloks version id (server-driven UI) — adjustable, using a commonly known value
BLOKS_VERSION_ID = "0e35c0f0c0c0e4f3b6c2e0b7e7c7b0d0c0e4f3b6c2e0b7e7c7b0d0c0e4f3b6c2"

# X-IG-Capabilities (base64 bitfield of the features the client supports)
CAPABILITIES = "3brTv10="

# Other header capabilities/constants
CONNECTION_TYPE = "WIFI"
PIGEON_SESSION_PREFIX = "UFS-"

# ---------------------------------------------------------------------------
# Locale / language / timezone (match the real account to reduce flag risk)
# ---------------------------------------------------------------------------
LOCALE = "en_US"
LANGUAGE = "en-US"
TIMEZONE_OFFSET = 25200  # +07:00 (Bangkok) in seconds
ACCEPT_LANGUAGE = "en-US"

# ---------------------------------------------------------------------------
# Signature key (legacy HMAC) — newer IG uses signed_body=SIGNATURE.<json>
# without HMAC anymore, but kept around for a few old endpoints
# ---------------------------------------------------------------------------
SIGNATURE_KEY_VERSION = "4"
# Newer IG does not verify HMAC -> use the fixed prefix "SIGNATURE"
UNSIGNED_PREFIX = "SIGNATURE"

# ---------------------------------------------------------------------------
# Request defaults
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 30          # seconds
MAX_RETRIES = 3               # number of retries on a transient error
RETRY_BACKOFF = 2.0          # backoff multiplier (seconds)
# Random delay between requests (seconds) to mimic human behavior and reduce rate-limit risk
REQUEST_DELAY_RANGE = (1.0, 3.0)

# Instagram Android User-Agent template
USER_AGENT_TEMPLATE = (
    "Instagram {app_version} Android "
    "({android_version}/{android_release}; "
    "{dpi}; {resolution}; {manufacturer}; {model}; {device}; {cpu}; "
    "{locale}; {version_code})"
)

# Sticker tray / extra capabilities required by some endpoints
SUPPORTED_CAPABILITIES = [
    {"name": "SUPPORTED_SDK_VERSIONS", "value": (
        "119.0,120.0,121.0,122.0,123.0,124.0,125.0,126.0,127.0,128.0,"
        "129.0,130.0,131.0,132.0,133.0,134.0,135.0,136.0,137.0,138.0"
    )},
    {"name": "FACE_TRACKER_VERSION", "value": "14"},
    {"name": "COMPRESSION", "value": "ETC2_COMPRESSION"},
    {"name": "world_tracker", "value": "world_tracker_enabled"},
    {"name": "gyroscope", "value": "gyroscope_enabled"},
]
