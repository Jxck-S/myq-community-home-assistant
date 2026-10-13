"""Constants for the myQ Community integration."""

from datetime import timedelta

DOMAIN = "myq_community"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_CODE = "code"
CONF_TOKEN = "token"

SCAN_INTERVAL = timedelta(minutes=5)
# History events fetched per community per update (one page)
HISTORY_LIMIT = 10
