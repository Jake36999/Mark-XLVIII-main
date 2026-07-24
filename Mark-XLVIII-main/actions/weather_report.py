from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WMO_CONDITIONS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _condition(value: Any) -> str:
    try:
        return WMO_CONDITIONS.get(int(value), f"weather code {int(value)}")
    except (TypeError, ValueError):
        return "conditions unavailable"


def _target_date(when: str) -> str:
    lowered = when.strip().lower()
    if lowered in {"", "today", "now", "current"}:
        return date.today().isoformat()
    if lowered == "tomorrow":
        return (date.today() + timedelta(days=1)).isoformat()
    try:
        return date.fromisoformat(lowered).isoformat()
    except ValueError:
        return date.today().isoformat()


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
    *,
    get: Callable[..., Any] = requests.get,
) -> str:
    params = parameters or {}
    city = params.get("city")
    when = str(params.get("time") or "today")
    if not city or not isinstance(city, str) or not city.strip():
        msg = "The city is missing for the weather report."
        _log(msg, player)
        return msg

    city = city.strip()
    try:
        location_response = get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=12,
        )
        location_response.raise_for_status()
        locations = location_response.json().get("results") or []
        if not locations:
            raise ValueError(f"No matching location was found for {city}.")
        location = locations[0]
        forecast_response = get(
            FORECAST_URL,
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 7,
            },
            timeout=15,
        )
        forecast_response.raise_for_status()
        forecast = forecast_response.json()
        daily = forecast.get("daily") or {}
        target = _target_date(when)
        dates = list(daily.get("time") or [])
        index = dates.index(target) if target in dates else 0

        label = ", ".join(
            part for part in [str(location.get("name") or city), str(location.get("admin1") or ""), str(location.get("country") or "")] if part
        )
        lines = [
            f"Weather for {label} on {dates[index] if dates else target}:",
            f"- Conditions: {_condition((daily.get('weather_code') or [None])[index])}",
            f"- Temperature: {(daily.get('temperature_2m_min') or ['?'])[index]} to {(daily.get('temperature_2m_max') or ['?'])[index]} C",
            f"- Maximum precipitation probability: {(daily.get('precipitation_probability_max') or ['?'])[index]}%",
        ]
        current = forecast.get("current") or {}
        if target == date.today().isoformat() and current:
            lines.extend(
                [
                    f"- Current: {current.get('temperature_2m', '?')} C, feels like {current.get('apparent_temperature', '?')} C",
                    f"- Wind: {current.get('wind_speed_10m', '?')} km/h; precipitation: {current.get('precipitation', '?')} mm",
                ]
            )
        lines.append("- Source: Open-Meteo")
        msg = "\n".join(lines)
    except Exception as exc:
        msg = f"Weather lookup failed for {city}: {exc}"

    _log(msg, player)
    if session_memory:
        try:
            session_memory.set_last_search(query=f"weather in {city} {when}", response=msg)
        except Exception:
            pass
    return msg


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
