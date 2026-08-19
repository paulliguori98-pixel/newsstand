"""National Weather Service — today's conditions, with sun times computed locally.

Open-Meteo answered instantly from a laptop and timed out on every single
build from GitHub's runners, which is what a shared datacenter IP being
throttled looks like. api.weather.gov exists for exactly this kind of
unattended public use and doesn't rate-limit by origin.

It doesn't report sunrise and sunset, so those are computed here with
NOAA's solar position algorithm. That's deliberate: no second API to fail,
nothing to rate-limit, and it works offline forever. Accurate to about a
minute against published tables, and correct across daylight saving
because the UTC offset comes from the zoneinfo database rather than a
hardcoded constant.

Set `forecast_url` and `hourly_url` in config.yaml to skip the gridpoint
lookup — one less request per build, one less thing to fail. Without them
this falls back to resolving them from the coordinates.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

POINTS = "https://api.weather.gov/points/{lat},{lon}"

# NWS writes conditions as free text — "Patchy Fog then Partly Sunny" — so
# match on vocabulary, and order matters. "Partly Cloudy" has to be tested
# before "cloudy" or it never reaches the right icon.
ICONS = [
    ("thunder", "storm"), ("tstorm", "storm"),
    ("snow", "snow"), ("sleet", "snow"), ("flurr", "snow"),
    ("wintry", "snow"), ("ice", "snow"), ("freezing", "snow"),
    ("rain", "rain"), ("shower", "rain"), ("drizzle", "rain"),
    ("fog", "fog"), ("haze", "fog"), ("smoke", "fog"),
    ("partly cloudy", "partly"), ("partly sunny", "partly"),
    ("mostly cloudy", "cloud"), ("overcast", "cloud"), ("cloud", "cloud"),
    ("mostly sunny", "sun"), ("sunny", "sun"), ("clear", "sun"), ("fair", "sun"),
]


def _icon_for(text: str) -> str:
    low = (text or "").lower()
    for needle, icon in ICONS:
        if needle in low:
            return icon
    return "cloud"


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
    now = _get(hourly_url, settings)["properties"]["periods"][0]

    # periods[0] is whichever half of the day we're in. In daylight it's
    # today's high and tonight's low; after dark it's tonight's low and
    # tomorrow's high, which is the number you'd actually want in the
    # evening anyway.
    first, second = periods[0], (periods[1] if len(periods) > 1 else periods[0])
    if first.get("isDaytime"):
        high, low = first["temperature"], second["temperature"]
    else:
        low, high = first["temperature"], second["temperature"]

    rain = (first.get("probabilityOfPrecipitation") or {}).get("value")
    condition = now.get("shortForecast") or first.get("shortForecast") or "—"
    sunrise, sunset = _sun_times(datetime.now(tz).date(), lat, lon, tz)

    return [{
        "title": condition,
        "icon": _icon_for(condition),
        # A fixed URL, so this item's id never moves. Seed it from the
        # title instead and every shift in the weather leaves another dead
        # entry in seen.json — forty-two of them a day.
        "url": source.get("link") or f"https://forecast.weather.gov/MapClick.php?lat={lat}&lon={lon}",
        "source": source.get("place", ""),
        "temp": now["temperature"],
        "high": high,
        "low": low,
        "rain": rain,
        "sunrise": sunrise,
        "sunset": sunset,
    }]
