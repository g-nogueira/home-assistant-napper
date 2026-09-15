"""Constants for the Napper integration."""

from datetime import timedelta

DOMAIN = "napper"

API_BASE_URL = "https://api.napper.app"
API_CLIENT_VERSION = "6.71.0"
API_LANGUAGE = "en"
API_LOCALE = "en-US"
API_SOURCE = "APP"
API_TIMEOUT_SECONDS = 15
TOKEN_REFRESH_MARGIN = timedelta(days=7)
DEFAULT_POLL_INTERVAL_SECONDS = 60
MIN_POLL_INTERVAL_SECONDS = 30
MAX_POLL_INTERVAL_SECONDS = 3600

CONF_ACCOUNT_ID = "account_id"
CONF_DEVICE_ID = "device_id"
CONF_ID_TOKEN = "id_token"
CONF_ID_TOKEN_EXPIRES_AT = "id_token_expires_at"
CONF_OTP = "otp"
CONF_POLL_INTERVAL_SECONDS = "poll_interval_seconds"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_REFRESH_TOKEN_EXPIRES_AT = "refresh_token_expires_at"

PLATFORMS = ["binary_sensor", "sensor"]
