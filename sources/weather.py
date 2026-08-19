"""Open-Meteo — today's conditions, sunrise and sunset.

No API key, no signup, no token to re-paste every month: the only weather
source that survives running unattended.

Two weather codes come back and they often disagree. The DAILY code is the
most significant thing that happens anywhere in the 24 hours, so a shower
at dawn labels a clear afternoon "heavy showers". The CURRENT code is what
it is actually doing. This uses current for the condition and the icon and
carries the day's rain chance alongside it — the honest way to say "clear
now, but take a coat".
"""

from __future__ import annotations

from datetime import datetime

import requests

ENDPOINT = "https://api.open-meteo.com/v1/forecast"
DAILY = ("weather_code,temperature_2m_max,temperature_2m_min,"
         "sunrise,sunset,precipitation_probability_max")

# WMO 4677, collapsed to the distinctions worth reading on a page you only
# glance at: the words, and which of the seven icons to draw.
CONDITIONS = {
    0: ("Clear", "sun"),
    1: ("Mostly clear", "sun"),
    2: ("Partly cloudy", "partly"),
    3: ("Overcast", "cloud"),
    45: ("Fog", "fog"),
    48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "rain"),
    53: ("Drizzle", "rain"),
    55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"),
    57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"),
    63: ("Rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"),
    67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"),
    73: ("Snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Showers", "rain"),
    81: ("Showers", "rain"),
    82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"),
    86: ("Snow showers", "snow"),
    95: ("Thunderstorms", "storm"),
    96: ("Thunderstorms", "storm"),
    99: ("Thunderstorms", "storm"),
}


def _clock(stamp: str) -> str:
    """'2026-08-17T19:54' → '7:54'."""
    try:
        return datetime.fromisoformat(stamp).strftime("%-I:%M")
    except (TypeError, ValueError):
        return ""


def fetch(source: dict, settings: dict) -> list[dict]:
    lat, lon = source["latitude"], source["longitude"]
    reply = requests.get(
        ENDPOINT,
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code",
            "daily": DAILY,
            "temperature_unit": source.get("units", "fahrenheit"),
            "timezone": settings.get("timezone", "America/New_York"),
            "forecast_days": 1,
        },
        timeout=settings.get("timeout", 20),
    )
    reply.raise_for_status()
    data = reply.json()

    day = data["daily"]
    now = data.get("current") or {}
    label, icon = CONDITIONS.get(now.get("weather_code"), ("—", "cloud"))

    return [{
        "title": label,
        "icon": icon,
        # A fixed URL, so this item's id never moves. Seed it from the
        # title instead and every shift in the weather leaves another dead
        # entry in seen.json — forty-two of them a day.
        "url": source.get("link") or
               f"https://forecast.weather.gov/MapClick.php?lat={lat}&lon={lon}",
        "source": source.get("place", ""),
        "temp": round(now.get("temperature_2m") or day["temperature_2m_max"][0]),
        "high": round(day["temperature_2m_max"][0]),
        "low": round(day["temperature_2m_min"][0]),
        "rain": day["precipitation_probability_max"][0],
        "sunrise": _clock(day["sunrise"][0]),
        "sunset": _clock(day["sunset"][0]),
    }]
