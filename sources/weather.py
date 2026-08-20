"""National Weather Service — the day's weather, written as a sentence.

Open-Meteo answered instantly from a laptop and timed out on every single
build from GitHub's runners, which is what a shared datacenter IP being
throttled looks like. api.weather.gov exists for exactly this kind of
unattended public use.

Sunrise and sunset are computed here with NOAA's solar position algorithm
rather than fetched. No second API to fail, nothing to rate-limit, accurate
to about a minute, and correct across daylight saving because the offset
comes from the zoneinfo database.

The rain clause comes from the hourly forecast: find the hours at or above
a floor, say when they are and how likely. Below the floor there's no
clause at all — "0% chance of rain" is noise, not information.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

POINTS = "https://api.weather.gov/points/{lat},{lon}"
DAILY = ("weather_code,temperature_2m_max,temperature_2m_min,"
         "sunrise,sunset,precipitation_probability_max")

# Below this, say nothing. A 12% chance is not worth a sentence.
RAIN_FLOOR = 20
# Read top-down; the first threshold the peak clears wins.
RAIN_LADDER = (
    (80, "Rain is near certain"),
    (60, "Rain is likely"),
    (45, "An even chance of rain"),
    (30, "A one-in-three chance of rain"),
    (20, "A one-in-five chance of rain"),
)


def _clock(stamp: str) -> str:
    """'2026-08-20T19:54' → '7:54'."""
    try:
        return datetime.fromisoformat(stamp).strftime("%-I:%M")
    except (TypeError, ValueError):
        return ""


def _hour(stamp: str) -> str:
    """'2026-08-20T16:00-04:00' → '4pm'."""
    try:
        when = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return ""
    return f"{when.strftime('%-I')}{'am' if when.hour < 12 else 'pm'}"


def _sun_times(day: date, lat: float, lon: float, tz: ZoneInfo) -> tuple[str, str]:
    """Sunrise and sunset as 'H:MM', by NOAA's algorithm.

    Taking the offset from a real datetime rather than a constant is what
    keeps this right on the two days a year the clocks move.
    """
    offset = datetime(day.year, day.month, day.day, 12, tzinfo=tz).utcoffset()
    tz_hours = offset.total_seconds() / 3600 if offset else 0.0

    jd = day.toordinal() + 1721424.5  # Julian day at 00:00 UT
    t = (jd + 0.5 - tz_hours / 24 - 2451545) / 36525

    mean_long = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    mean_anom = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    eccent = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)

    centre = (math.sin(math.radians(mean_anom)) * (1.914602 - t * (0.004817 + 0.000014 * t))
              + math.sin(math.radians(2 * mean_anom)) * (0.019993 - 0.000101 * t)
              + math.sin(math.radians(3 * mean_anom)) * 0.000289)

    app_long = mean_long + centre - 0.00569 - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * t))
    mean_obliq = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    obliq = mean_obliq + 0.00256 * math.cos(math.radians(125.04 - 1934.136 * t))

    decl = math.degrees(math.asin(math.sin(math.radians(obliq)) * math.sin(math.radians(app_long))))
    vary = math.tan(math.radians(obliq / 2)) ** 2

    eq_time = 4 * math.degrees(
        vary * math.sin(math.radians(2 * mean_long))
        - 2 * eccent * math.sin(math.radians(mean_anom))
        + 4 * eccent * vary * math.sin(math.radians(mean_anom)) * math.cos(math.radians(2 * mean_long))
        - 0.5 * vary * vary * math.sin(math.radians(4 * mean_long))
        - 1.25 * eccent * eccent * math.sin(math.radians(2 * mean_anom))
    )

    # 90.833° rather than 90° accounts for refraction and the sun's disc.
    ratio = (math.cos(math.radians(90.833)) / (math.cos(math.radians(lat)) * math.cos(math.radians(decl)))
             - math.tan(math.radians(lat)) * math.tan(math.radians(decl)))
    if not -1 <= ratio <= 1:
        return "", ""  # polar day or night; never happens at this latitude

    hour_angle = math.degrees(math.acos(ratio))
    noon = 720 - 4 * lon - eq_time + tz_hours * 60
    return _hm(noon - hour_angle * 4), _hm(noon + hour_angle * 4)


def _hm(minutes: float) -> str:
    total = round(minutes) % 1440
    hour, minute = divmod(total, 60)
    return f"{(hour + 11) % 12 + 1}:{minute:02d}"


def _rain(hours: list[dict]) -> str:
    """The rain clause, or empty when there's nothing worth saying.

    First and last hour above the floor, so a gap in the middle is folded
    into one window. That's the honest simplification: "between 4 and 7"
    is what you'd tell someone anyway.
    """
    wet = [(h, ((h.get("probabilityOfPrecipitation") or {}).get("value") or 0))
           for h in hours]
    peak = max((p for _, p in wet), default=0)
    if peak < RAIN_FLOOR:
        return ""

    run = [h for h, p in wet if p >= RAIN_FLOOR]
    word = next(w for threshold, w in RAIN_LADDER if peak >= threshold)
    start, end = _hour(run[0]["startTime"]), _hour(run[-1]["startTime"])
    if start == end:
        return f"{word} around {start}."
    return f"{word} between {start} and {end}."


def _get(url: str, settings: dict) -> dict:
    reply = requests.get(
        url,
        headers={
            # NWS asks callers to identify themselves and will refuse a
            # bare python-requests agent.
            "User-Agent": settings.get("user_agent", "newsstand"),
            "Accept": "application/geo+json",
        },
        timeout=settings.get("timeout", 20),
    )
    reply.raise_for_status()
    return reply.json()


def fetch(source: dict, settings: dict) -> list[dict]:
    lat, lon = source["latitude"], source["longitude"]
    tz = ZoneInfo(settings.get("timezone", "America/New_York"))

    forecast_url = source.get("forecast_url")
    hourly_url = source.get("hourly_url")
    if not forecast_url or not hourly_url:
        point = _get(POINTS.format(lat=lat, lon=lon), settings)["properties"]
        forecast_url = forecast_url or point["forecast"]
        hourly_url = hourly_url or point["forecastHourly"]

    periods = _get(forecast_url, settings)["properties"]["periods"]
    hours = _get(hourly_url, settings)["properties"]["periods"][:18]
    now = hours[0] if hours else {}

    # periods[0] is whichever half of the day we're in. In daylight it's
    # today's high and tonight's low; after dark it's tonight's low and
    # tomorrow's high, which is the number you'd want in the evening anyway.
    first, second = periods[0], (periods[1] if len(periods) > 1 else periods[0])
    if first.get("isDaytime"):
        high, low = first["temperature"], second["temperature"]
    else:
        low, high = first["temperature"], second["temperature"]

    sunrise, sunset = _sun_times(datetime.now(tz).date(), lat, lon, tz)
    condition = now.get("shortForecast") or first.get("shortForecast") or "—"

    phrase = _rain(hours) or f"{condition} all day."
    detail = (f"It reaches {high}° today and falls to {low}° overnight. "
              f"The sun is up from {sunrise} until {sunset}.")

    return [{
        "title": condition,
        "phrase": phrase,
        "detail": detail,
        # A fixed URL, so this item's id never moves. Seed it from the
        # title instead and every shift in the weather leaves another dead
        # entry in seen.json — forty-two of them a day.
        "url": source.get("link") or
               f"https://forecast.weather.gov/MapClick.php?lat={lat}&lon={lon}",
        "source": source.get("place", ""),
        "temp": now.get("temperature", high),
        "high": high,
        "low": low,
        "sunrise": sunrise,
        "sunset": sunset,
    }]
