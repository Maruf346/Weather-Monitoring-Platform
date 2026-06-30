"""
Fetches weather data from the Open-Meteo free API (no key required).
Saves results as WeatherReading records.
"""

import logging
from datetime import datetime, timezone as dt_timezone

import requests
from django.conf import settings
from django.utils import timezone

from weather_ai.models import WeatherReading

logger = logging.getLogger(__name__)

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

CURRENT_VARS = (
    "temperature_2m,"
    "relative_humidity_2m,"
    "rain,"
    "surface_pressure,"
    "wind_speed_10m,"
    "wind_direction_10m,"
    "weather_code"
)

HOURLY_VARS = (
    "temperature_2m,"
    "relative_humidity_2m,"
    "rain,"
    "surface_pressure,"
    "wind_speed_10m,"
    "wind_direction_10m,"
    "weather_code"
)


def _get_coords():
    return {
        "latitude":  getattr(settings, "WEATHER_LATITUDE",  23.8103),
        "longitude": getattr(settings, "WEATHER_LONGITUDE", 90.4125),
    }


def _get_location_name():
    return getattr(settings, "WEATHER_LOCATION_NAME", "Dhaka, Bangladesh")


# ── Current weather ───────────────────────────────────────────────────────────

def fetch_current_weather():
    """
    Fetch the latest weather snapshot from Open-Meteo and save it.
    Returns the saved WeatherReading instance, or None on failure.
    """
    coords = _get_coords()
    params = {
        **coords,
        "current": CURRENT_VARS,
        "timezone": "auto",
    }

    try:
        resp = requests.get(OPEN_METEO_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error("Open-Meteo current fetch failed: %s", exc)
        return None

    current = data.get("current", {})
    if not current:
        logger.error("Open-Meteo response missing 'current' key: %s", data)
        return None

    raw_time = current.get("time", "")
    try:
        ts = datetime.fromisoformat(raw_time).replace(tzinfo=dt_timezone.utc)
    except (ValueError, TypeError):
        ts = timezone.now()

    reading, created = WeatherReading.objects.get_or_create(
        timestamp=ts,
        location=_get_location_name(),
        defaults={
            "latitude":       coords["latitude"],
            "longitude":      coords["longitude"],
            "temperature":    current.get("temperature_2m", 0.0),
            "humidity":       current.get("relative_humidity_2m", 0.0),
            "pressure":       current.get("surface_pressure", 0.0),
            "rain":           current.get("rain", 0.0),
            "wind_speed":     current.get("wind_speed_10m", 0.0),
            "wind_direction": current.get("wind_direction_10m", 0.0),
            "weather_code":   current.get("weather_code", 0),
        },
    )

    if created:
        logger.info("Saved new reading: %s", reading)
    else:
        logger.debug("Reading already exists: %s", reading)

    return reading


# ── Historical / bulk fetch ───────────────────────────────────────────────────

def fetch_historical_weather(past_days: int = 7):
    """
    Fetch hourly weather for the past N days and bulk-save new records.
    Skips timestamps already in the database.
    Returns the number of new records saved.
    """
    coords = _get_coords()
    params = {
        **coords,
        "hourly":    HOURLY_VARS,
        "past_days": past_days,
        "timezone":  "auto",
    }

    try:
        resp = requests.get(OPEN_METEO_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error("Open-Meteo historical fetch failed: %s", exc)
        return 0

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])
    if not times:
        logger.warning("No hourly data returned from Open-Meteo.")
        return 0

    location = _get_location_name()
    lat      = coords["latitude"]
    lon      = coords["longitude"]

    existing_ts = set(
        WeatherReading.objects.filter(location=location)
        .values_list("timestamp", flat=True)
    )

    to_create = []
    for i, raw_time in enumerate(times):
        try:
            ts = datetime.fromisoformat(raw_time).replace(tzinfo=dt_timezone.utc)
        except (ValueError, TypeError):
            continue

        if ts in existing_ts:
            continue

        to_create.append(WeatherReading(
            timestamp      = ts,
            location       = location,
            latitude       = lat,
            longitude      = lon,
            temperature    = _safe(hourly, "temperature_2m",       i),
            humidity       = _safe(hourly, "relative_humidity_2m", i),
            pressure       = _safe(hourly, "surface_pressure",     i),
            rain           = _safe(hourly, "rain",                 i),
            wind_speed     = _safe(hourly, "wind_speed_10m",       i),
            wind_direction = _safe(hourly, "wind_direction_10m",   i),
            weather_code   = int(_safe(hourly, "weather_code",     i)),
        ))

    if to_create:
        WeatherReading.objects.bulk_create(to_create, ignore_conflicts=True)
        logger.info("Saved %d historical readings.", len(to_create))

    return len(to_create)


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_recent_readings(hours: int = 24):
    """Return readings for the past N hours, oldest-first."""
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(hours=hours)
    return (
        WeatherReading.objects
        .filter(timestamp__gte=cutoff)
        .order_by("timestamp")
    )


def get_latest_reading():
    """Return the single most recent WeatherReading, or None."""
    return WeatherReading.objects.order_by("-timestamp").first()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _safe(hourly: dict, key: str, index: int, default: float = 0.0) -> float:
    try:
        val = hourly[key][index]
        return float(val) if val is not None else default
    except (KeyError, IndexError, TypeError, ValueError):
        return default
