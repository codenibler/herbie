from __future__ import annotations

import logging
import os

import requests
from dotenv import load_dotenv


load_dotenv(override=True)

GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_WEATHER_LOCATION = "Amsterdam"

WEATHER_CODE_DESCRIPTIONS = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy with rime",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "light freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "heavy showers",
    85: "light snow showers",
    86: "snow showers",
    95: "a thunderstorm",
    96: "a thunderstorm with hail",
    99: "a strong thunderstorm with hail",
}


def _get_weather_location() -> str:
    location = os.getenv("WEATHER_LOCATION", DEFAULT_WEATHER_LOCATION).strip()
    return location or DEFAULT_WEATHER_LOCATION


def _resolve_location(location_name: str) -> dict[str, object]:
    response = requests.get(
        GEOCODING_API_URL,
        params={
            "name": location_name,
            "count": 1,
            "language": "en",
            "format": "json",
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") or []

    if not results:
        raise ValueError(f"I could not find weather data for {location_name}.")

    return results[0]


def _fetch_weather(latitude: float, longitude: float) -> dict[str, object]:
    response = requests.get(
        WEATHER_API_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_gusts_10m",
                    "precipitation",
                    "cloud_cover",
                    "is_day",
                ]
            ),
            "daily": ",".join(
                [
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "precipitation_sum",
                ]
            ),
            "forecast_days": 1,
            "timezone": "auto",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _describe_weather_code(weather_code: int) -> str:
    return WEATHER_CODE_DESCRIPTIONS.get(weather_code, "doing some mysterious weather nonsense")


def _build_clothing_recommendation(
    apparent_temperature_c: float,
    precipitation_mm: float,
    precipitation_probability: int,
    wind_speed_kmh: float,
) -> str:
    clothing: list[str] = []

    if apparent_temperature_c < 0:
        clothing.extend(["a warm coat", "a scarf", "gloves"])
    elif apparent_temperature_c < 8:
        clothing.extend(["a coat", "a sweater"])
    elif apparent_temperature_c < 15:
        clothing.extend(["a light jacket", "layers"])
    elif apparent_temperature_c < 22:
        clothing.extend(["a light layer", "long trousers"])
    elif apparent_temperature_c < 28:
        clothing.extend(["a T-shirt", "light clothes"])
    else:
        clothing.extend(["very light clothes", "something breathable"])

    extras: list[str] = []
    if precipitation_mm > 0 or precipitation_probability >= 50:
        extras.append("bring an umbrella")
        if apparent_temperature_c < 15:
            extras.append("wear something water-resistant")
    if wind_speed_kmh >= 25:
        extras.append("add a windproof layer")

    recommendation = ", ".join(clothing[:2])
    if extras:
        recommendation = f"{recommendation}, and {', and '.join(extras)}"

    return recommendation


def get_weather_analysis() -> str:
    location_name = _get_weather_location()
    logging.info("Fetching weather analysis for %s", location_name)

    try:
        location = _resolve_location(location_name)
        weather = _fetch_weather(location["latitude"], location["longitude"])
    except requests.RequestException as error:
        logging.error("Weather request failed for %s: %s", location_name, error)
        return "I couldn't reach the weather service just now. The sky remains coy."
    except ValueError as error:
        logging.error("Weather lookup failed for %s: %s", location_name, error)
        return str(error)

    current = weather["current"]
    daily = weather["daily"]

    display_name = location.get("name", location_name)
    country = location.get("country")
    if country:
        display_name = f"{display_name}, {country}"

    temperature_c = round(float(current["temperature_2m"]))
    apparent_temperature_c = round(float(current["apparent_temperature"]))
    wind_speed_kmh = round(float(current["wind_speed_10m"]))
    precipitation_mm = float(current["precipitation"])
    cloud_cover = round(float(current["cloud_cover"]))
    weather_description = _describe_weather_code(int(current["weather_code"]))

    day_max_c = round(float(daily["temperature_2m_max"][0]))
    day_min_c = round(float(daily["temperature_2m_min"][0]))
    precipitation_probability = int(round(float(daily["precipitation_probability_max"][0])))

    clothing_recommendation = _build_clothing_recommendation(
        apparent_temperature_c=apparent_temperature_c,
        precipitation_mm=precipitation_mm,
        precipitation_probability=precipitation_probability,
        wind_speed_kmh=wind_speed_kmh,
    )

    return (
        f"In {display_name}, it's {temperature_c} degrees and {weather_description}. "
        f"It feels like {apparent_temperature_c}, with wind around {wind_speed_kmh} kilometers per hour "
        f"and about {cloud_cover} percent cloud cover. Expect roughly {day_min_c} to {day_max_c} today. "
        f"Wear {clothing_recommendation}."
    )
