"""Constants for the VW Group EU Data Act integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "cupra_eu_data_act"


def raw_unique_id(vin: str, key: str) -> str:
    """Unique_id for a raw data-point sensor.

    Dataset ``key`` UUIDs are shared across vehicles, so they must be namespaced
    by VIN to avoid collisions between config entries (one entry's entity would
    otherwise be dropped by the registry).
    """
    return f"{vin}_{key}"

# --- Portal / OIDC endpoints ---------------------------------------------
BASE_URL = "https://eu-data-act.drivesomethinggreater.com"
IDENTITY_BASE = "https://identity.vwgroup.io"
CALLBACK_LOGIN_PATH = "/services/callbacklogin"

OIDC_AUTHORIZE_URL = IDENTITY_BASE + "/oidc/v1/authorize"
OIDC_SCOPE = "openid cars profile"
OIDC_REDIRECT_URI = BASE_URL + "/login"
DEFAULT_COUNTRY = "de"
DEFAULT_LANGUAGE = "de"

# proxy_api paths (relative to BASE_URL)
VEHICLES_PATH = "/proxy_api/consent/me/vehicles"
RELATION_PATH = "/proxy_api/vum/v2/users/me/relations/{vin}"
METADATA_PATH = "/proxy_api/euda-apim/datarequest/vehicles/{vin}/metadata/partial"
LIST_PATH = "/proxy_api/euda-apim/datadelivery/vehicles/{vin}/{identifier}/list"
DOWNLOAD_PATH = "/proxy_api/euda-apim/datadelivery/vehicles/{vin}/{identifier}/download"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)

# --- Config entry keys ----------------------------------------------------
CONF_BRAND = "brand"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_VIN = "vin"
CONF_IDENTIFIER = "identifier"
CONF_NICKNAME = "nickname"

# --- Scheduling -----------------------------------------------------------
DATASET_INTERVAL = timedelta(minutes=15)
POST_DATASET_BUFFER = timedelta(seconds=45)
RETRY_INTERVAL = timedelta(minutes=1)
MIN_INTERVAL = timedelta(seconds=30)
# Portal/IdP outages and rate limits: retry and keep previous data, never reauth.
TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
# Backoff after repeated transient HTTP (listing or download); cap at 30 minutes.
SERVER_ERROR_BACKOFF_INTERVALS = (
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=30),
)

NO_CONTENT_SUFFIX = "_no_content_found.zip"

# --- Local dataset cache (P4 / upstream #31) ----------------------------
CACHE_DIR_NAME = "cupra_eu_data_act_cache"
MAX_CACHED_DATASETS = 10
MAX_CACHE_BYTES_PER_VIN = 50_000_000

# --- Subscription / snapshot health (A3, B11) ----------------------------
SUBSCRIPTION_VALIDITY = timedelta(days=365)
SUBSCRIPTION_WARNING_BEFORE = timedelta(days=30)
SNAPSHOT_STALE_THRESHOLD = timedelta(hours=12)
