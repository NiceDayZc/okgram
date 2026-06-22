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

Identity-consistency note (the #1 cause of session bounces / "login_required"):
    Instagram does NOT identify a session by ``sessionid`` alone. It correlates
    ``sessionid`` + the device fingerprint + ``X-MID`` + ``IG-U-RUR`` (region
    routing) + ``X-IG-WWW-Claim`` + the source IP/geo + the app id. The locale,
    country and timezone below MUST be internally consistent (e.g. a TH IP with
    an ``en_US`` locale and a Bangkok timezone is fine, but ``country=US`` with a
    Bangkok timezone is a contradiction that gets flagged). Keep them aligned to
    the account's real region -- see DEFAULT_COUNTRY / TIMEZONE_OFFSET.
"""

# ---------------------------------------------------------------------------
# Endpoint / domains
# ---------------------------------------------------------------------------
API_DOMAIN = "i.instagram.com"
API_VERSION = "v1"
BASE_API_URL = f"https://{API_DOMAIN}/api/{API_VERSION}/"

# Instagram Lite domain (from dex: iglite-z.instagram.com) -- same backend
LITE_API_DOMAIN = "iglite-z.instagram.com"

# Web domain (used with public_request / web_profile_info / graphql, and as the
# private base when running in web mode -- the web client calls www.../api/v1).
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

# X-IG-App-ID -- two different ids exist and a session is bound to ONE of them:
#   APP_ID     = the Instagram *Android app* id (mobile private API)
#   WEB_APP_ID = the Instagram *web app* id (www.instagram.com, browser sessions)
# A sessionid minted by the web app is bound to WEB_APP_ID; replaying it against
# the mobile API with APP_ID is a (detectable) origin mismatch -- pick the mode
# that matches where the session came from (see okgram.config MODE_* + client).
APP_ID = "567067343352427"
WEB_APP_ID = "936619743392459"

# X-ASBD-ID -- a stable constant the web/app client sends on most requests.
ASBD_ID = "129477"

# Bloks version id (server-driven UI). This is a live value the server expects to
# match the running client; okgram.live_config refreshes it from launcher/sync at
# runtime, so this is only the cold-start default. (The previous hard-coded value
# here was a repeating placeholder pattern -- itself a fingerprint flag -- so it is
# now a realistic non-patterned default that the live sync overwrites.)
BLOKS_VERSION_ID = "16e9197b9ce6dd5bb2dd4f25f5cd5f8b09e94e0b8e7a4f7c8c0a4cf2c0c5c5b2"

# X-IG-Capabilities (base64 bitfield of the features the client supports)
CAPABILITIES = "3brTv10="

# Other header capabilities/constants
CONNECTION_TYPE = "WIFI"
# X-FB-Connection-Type mirrors the radio type the app reports.
FB_CONNECTION_TYPE = "WIFI"
PIGEON_SESSION_PREFIX = "UFS-"

# ---------------------------------------------------------------------------
# Operating mode
# ---------------------------------------------------------------------------
# "mobile" -> talk to the i.instagram.com private API as the Android app
#             (OkHttp TLS, mobile UA, APP_ID, Bearer auth).
# "web"    -> talk to www.instagram.com as the browser web client
#             (Chrome TLS, browser UA, WEB_APP_ID, cookie+csrf auth, no Bearer).
#             This is the *origin-consistent* mode for a sessionid exported from
#             a browser, so it bounces far less than forcing a web session to
#             impersonate a phone.
MODE_MOBILE = "mobile"
MODE_WEB = "web"

# ---------------------------------------------------------------------------
# Locale / language / timezone (match the real account to reduce flag risk)
# ---------------------------------------------------------------------------
# NOTE: locale (UI language) and region (country/timezone) are independent. Many
# Thai users run an English UI on a Thai SIM/region -- that is consistent. What
# must NOT happen is country/timezone disagreeing with the source IP.
LOCALE = "en_US"
LANGUAGE = "en-US"
ACCEPT_LANGUAGE = "en-US"

# Default region = Thailand (matches a Thai residential IP). Override per client.
DEFAULT_COUNTRY = "TH"
DEFAULT_COUNTRY_CODE = 66
TIMEZONE_OFFSET = 25200  # +07:00 (Asia/Bangkok) in seconds
# Whether the account is routed through an EU data center (GDPR). Thailand -> no.
EU_DC_ENABLED = "false"

# Known-consistent region presets: (locale, language, country, country_code, tz)
REGION_PRESETS = {
    "TH": ("en_US", "en-US", "TH", 66, 25200),
    "TH_NATIVE": ("th_TH", "th-TH", "TH", 66, 25200),
    "US": ("en_US", "en-US", "US", 1, -25200),   # America/Los_Angeles
    "US_EAST": ("en_US", "en-US", "US", 1, -14400),
    "GB": ("en_GB", "en-GB", "GB", 44, 3600),
    "SG": ("en_US", "en-US", "SG", 65, 28800),
}

# ---------------------------------------------------------------------------
# Signature key (legacy HMAC) -- newer IG uses signed_body=SIGNATURE.<json>
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

# Browser User-Agent used in web mode (must match the curl_cffi 'chrome'
# impersonation TLS so the UA and the JA3/JA4 fingerprint agree).
WEB_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 "
    "Instagram 314.0.0.20.114"
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

# ---------------------------------------------------------------------------
# GEO auto-sync (works for EVERY country -- aligns the reported region to the
# real egress IP so the fingerprint never contradicts the network).
# ---------------------------------------------------------------------------
# Providers are tried in order; each returns enough to derive ISO country +
# calling code + timezone offset (seconds) + (optional) primary language. They
# are queried THROUGH the client's own transport/proxy so the detected geo is
# the geo IG actually sees. All failures fall back to DEFAULT_COUNTRY silently.
GEO_PROVIDERS = (
    # name, url, json-key map handled in geo.py
    "https://ipapi.co/json/",
    "http://ip-api.com/json/?fields=status,country,countryCode,timezone,offset,currency,query",
    "https://ipwho.is/",
    "https://ipinfo.io/json",
    "https://www.cloudflare.com/cdn-cgi/trace",   # last resort: country only
)
GEO_CACHE_TTL = 6 * 3600          # re-detect at most every 6h
GEO_LOOKUP_TIMEOUT = 8            # seconds per provider

# EU / EEA ISO-2 codes -> IG routes these through EU data centers (X-IG-EU-DC-ENABLED).
EU_DC_COUNTRIES = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "IS", "LI", "NO", "GB", "CH",
})

# ISO-2 -> international calling code (used for the login `country_codes` field and
# X-IG header consistency). Comprehensive enough to cover every country a provider
# may return; geo.py prefers the provider-supplied calling code and uses this as a
# fallback. (Values are ITU E.164 country codes.)
COUNTRY_CALLING_CODES = {
    "AF": 93, "AL": 355, "DZ": 213, "AD": 376, "AO": 244, "AR": 54, "AM": 374,
    "AU": 61, "AT": 43, "AZ": 994, "BH": 973, "BD": 880, "BY": 375, "BE": 32,
    "BZ": 501, "BJ": 229, "BT": 975, "BO": 591, "BA": 387, "BW": 267, "BR": 55,
    "BN": 673, "BG": 359, "BF": 226, "BI": 257, "KH": 855, "CM": 237, "CA": 1,
    "CV": 238, "CF": 236, "TD": 235, "CL": 56, "CN": 86, "CO": 57, "KM": 269,
    "CG": 242, "CD": 243, "CR": 506, "CI": 225, "HR": 385, "CU": 53, "CY": 357,
    "CZ": 420, "DK": 45, "DJ": 253, "DO": 1, "EC": 593, "EG": 20, "SV": 503,
    "GQ": 240, "ER": 291, "EE": 372, "ET": 251, "FJ": 679, "FI": 358, "FR": 33,
    "GA": 241, "GM": 220, "GE": 995, "DE": 49, "GH": 233, "GR": 30, "GT": 502,
    "GN": 224, "GW": 245, "GY": 592, "HT": 509, "HN": 504, "HK": 852, "HU": 36,
    "IS": 354, "IN": 91, "ID": 62, "IR": 98, "IQ": 964, "IE": 353, "IL": 972,
    "IT": 39, "JM": 1, "JP": 81, "JO": 962, "KZ": 7, "KE": 254, "KI": 686,
    "KW": 965, "KG": 996, "LA": 856, "LV": 371, "LB": 961, "LS": 266, "LR": 231,
    "LY": 218, "LI": 423, "LT": 370, "LU": 352, "MO": 853, "MG": 261, "MW": 265,
    "MY": 60, "MV": 960, "ML": 223, "MT": 356, "MH": 692, "MR": 222, "MU": 230,
    "MX": 52, "FM": 691, "MD": 373, "MC": 377, "MN": 976, "ME": 382, "MA": 212,
    "MZ": 258, "MM": 95, "NA": 264, "NR": 674, "NP": 977, "NL": 31, "NZ": 64,
    "NI": 505, "NE": 227, "NG": 234, "KP": 850, "MK": 389, "NO": 47, "OM": 968,
    "PK": 92, "PW": 680, "PS": 970, "PA": 507, "PG": 675, "PY": 595, "PE": 51,
    "PH": 63, "PL": 48, "PT": 351, "PR": 1, "QA": 974, "RO": 40, "RU": 7,
    "RW": 250, "WS": 685, "SM": 378, "ST": 239, "SA": 966, "SN": 221, "RS": 381,
    "SC": 248, "SL": 232, "SG": 65, "SK": 421, "SI": 386, "SB": 677, "SO": 252,
    "ZA": 27, "KR": 82, "SS": 211, "ES": 34, "LK": 94, "SD": 249, "SR": 597,
    "SZ": 268, "SE": 46, "CH": 41, "SY": 963, "TW": 886, "TJ": 992, "TZ": 255,
    "TH": 66, "TL": 670, "TG": 228, "TO": 676, "TT": 1, "TN": 216, "TR": 90,
    "TM": 993, "TV": 688, "UG": 256, "UA": 380, "AE": 971, "GB": 44, "US": 1,
    "UY": 598, "UZ": 998, "VU": 678, "VA": 39, "VE": 58, "VN": 84, "YE": 967,
    "ZM": 260, "ZW": 263, "XK": 383,
}

# ISO-2 -> a representative timezone offset (seconds) used ONLY as a fallback when
# a provider returns the country but no usable offset. Providers normally supply
# the precise offset, so this stays coarse (capital-city tz).
COUNTRY_DEFAULT_TZ_OFFSET = {
    "TH": 25200, "VN": 25200, "ID": 25200, "KH": 25200, "LA": 25200,
    "SG": 28800, "MY": 28800, "PH": 28800, "CN": 28800, "HK": 28800, "TW": 28800,
    "JP": 32400, "KR": 32400, "IN": 19800, "BD": 21600, "PK": 18000, "AE": 14400,
    "SA": 10800, "TR": 10800, "RU": 10800, "GB": 0, "IE": 0, "PT": 0,
    "FR": 3600, "DE": 3600, "ES": 3600, "IT": 3600, "NL": 3600, "SE": 3600,
    "PL": 3600, "CH": 3600, "GR": 7200, "RO": 7200, "ZA": 7200, "EG": 7200,
    "BR": -10800, "AR": -10800, "US": -18000, "CA": -18000, "MX": -21600,
    "CO": -18000, "PE": -18000, "CL": -10800, "AU": 36000, "NZ": 43200,
}

# ---------------------------------------------------------------------------
# Live config sync (pull values that legitimately change from IG itself, instead
# of hard-coding). okgram.live_config drives this on cold start / on demand.
# ---------------------------------------------------------------------------
# Endpoints (relative to the private API) whose responses/headers carry values we
# adopt at runtime: server bloks version, password public key, www-claim, mid,
# rur routing, qe/launcher experiment + config flags.
LIVE_SYNC_ENDPOINTS = (
    "launcher/sync/",
    "qe/sync/",
)
# Response headers IG sets that the client must capture and (for the IG-U-* ones)
# echo back on every subsequent request to keep session continuity.
LIVE_RESPONSE_HEADERS = (
    "ig-set-authorization",
    "x-ig-set-www-claim",
    "ig-set-x-mid",
    "ig-set-ig-u-ds-user-id",
    "ig-set-ig-u-rur",
    "ig-set-ig-u-shbid",
    "ig-set-ig-u-shbts",
    "ig-set-ig-u-ig-direct-region-hint",
    "ig-set-password-encryption-key-id",
    "ig-set-password-encryption-pub-key",
)

