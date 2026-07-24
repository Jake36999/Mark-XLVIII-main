from __future__ import annotations

from datetime import date

from actions.weather_report import weather_action


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_weather_action_returns_structured_forecast():
    today = date.today().isoformat()
    responses = iter(
        [
            FakeResponse(
                {
                    "results": [
                        {
                            "name": "London",
                            "admin1": "England",
                            "country": "United Kingdom",
                            "latitude": 51.5,
                            "longitude": -0.12,
                        }
                    ]
                }
            ),
            FakeResponse(
                {
                    "current": {
                        "temperature_2m": 19.0,
                        "apparent_temperature": 18.5,
                        "precipitation": 0.0,
                        "wind_speed_10m": 12.0,
                    },
                    "daily": {
                        "time": [today],
                        "weather_code": [2],
                        "temperature_2m_min": [12.0],
                        "temperature_2m_max": [21.0],
                        "precipitation_probability_max": [20],
                    },
                }
            ),
        ]
    )

    result = weather_action({"city": "London", "time": "today"}, get=lambda *_args, **_kwargs: next(responses))

    assert "London, England, United Kingdom" in result
    assert "partly cloudy" in result
    assert "12.0 to 21.0 C" in result
    assert "Source: Open-Meteo" in result


def test_weather_action_requires_city_without_network_call():
    result = weather_action({}, get=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network called")))

    assert "city is missing" in result.lower()
