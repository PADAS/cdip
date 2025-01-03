import logging
from enum import Enum

import requests
import time
import rest_framework.request
from django_celery_beat.models import CrontabSchedule
from pytz import timezone

from cdip_admin import settings

logger = logging.getLogger(__name__)

oauth_token_url = f"{settings.KEYCLOAK_SERVER}/auth/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"


def get_admin_access_token():
    logger.debug("Getting Keycloak Admin Access Token")
    payload = {
        "grant_type": "client_credentials",
        "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
        "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
    }
    response = requests.post(oauth_token_url, data=payload)

    if response.status_code != 200:
        logger.warning(f"[{response.status_code}], {response.text}")
        return

    return response.json()



def add_base_url(request, url):
    if url and not url.startswith("http"):
        if not url.startswith("/"):
            url = "/" + url

        if isinstance(request, rest_framework.request.Request):
            request = request._request

        url = request.build_absolute_uri(url)
    return url


def generate_short_id_milliseconds():
    """
    Returns a short id as an alphanumeric string.
    The typical length will be 7-8 characters
    The id will be unique if the function is called in different milliseconds.
    """
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    # Epoch since year 2000 in milliseconds
    current_time_ms = int((time.time_ns() - time.mktime((2000, 1, 1, 0, 0, 0, 0, 0, 0)) * 1e9) // 1_000_000)
    # Convert to base to get a short id
    base = len(alphabet)
    short_id = ""
    while current_time_ms:
        current_time_ms, index = divmod(current_time_ms, base)
        short_id += alphabet[index]
    return short_id


class AutoNameEnum(Enum):
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name


def timezone_from_offset(utc_offset):
    """
    Create a pytz.timezone object from an integer UTC offset in hours.

    Args:
        utc_offset (int): The UTC offset in hours (e.g., -3, 5, etc.).

    Returns:
        pytz.timezone: A timezone object with the specified offset.
    """
    # Note: The sign is reversed for Etc/GMT timezones
    tz_name = f"Etc/GMT{-utc_offset:+d}"
    return timezone(tz_name)


def parse_crontab_schedule_from_dict(value):
    tz_offset = value.get("tz_offset", 0)
    timezone = timezone_from_offset(tz_offset)
    crontab_schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=value.get("minute", "*"),
        hour=value.get("hour", "*"),
        day_of_week=value.get("day_of_week", "*"),
        day_of_month=value.get("day_of_month", "*"),
        month_of_year=value.get("month_of_year", "*"),
        timezone=timezone
    )
    return crontab_schedule
