"""Live HA-independent forecast quality and fallback tests."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import unittest
from candidate.weather_policy import (
    select_weather,parse_hourly_forecast,outdoor_temperature,
    weather_current_temperature,cached_forecast_valid)

NOW=datetime(2026,10,31,17,0,tzinfo=timezone.utc)
def w(e,state="cloudy"):return SimpleNamespace(entity_id=e,state=state)
def s(value,age=5,attributes=None):
    return SimpleNamespace(state=str(value),last_reported=NOW-timedelta(minutes=age),
        attributes=attributes or {})

class WeatherTests(unittest.TestCase):
    def test_multiple_providers_require_explicit_selection(self):
        weather=[w("weather.forecast_home"),w("weather.ha_general")]
        self.assertIsNone(select_weather(None,weather))
        self.assertEqual(select_weather("weather.ha_general",weather),"weather.ha_general")
    def test_bad_provider_never_silently_falls_back(self):
        self.assertIsNone(select_weather("weather.missing",[w("weather.ha_general")]))
    def test_exactly_one_provider_without_config(self):
        self.assertEqual(select_weather("",[w("weather.ha_general")]),"weather.ha_general")
    def test_unavailable_provider_rejected(self):
        self.assertIsNone(select_weather("weather.ha_general",[w("weather.ha_general","unavailable")]))
    def test_fresh_outdoor(self):
        self.assertEqual(outdoor_temperature(s(7.5),NOW),7.5)
        self.assertIsNone(outdoor_temperature(s(7.5,age=100),NOW))
        self.assertIsNone(outdoor_temperature(s(99),NOW))
    def test_weather_current_outdoor_fallback(self):
        self.assertEqual(weather_current_temperature(s("cloudy",attributes={"temperature":9}),NOW),9)
        self.assertIsNone(weather_current_temperature(s("cloudy",age=120,attributes={"temperature":9}),NOW))
    def test_hourly_sequence(self):
        rows=[{"datetime":(NOW+timedelta(hours=i)).isoformat(),"temperature":i+7}
              for i in range(4)]
        parsed=parse_hourly_forecast(list(reversed(rows)),NOW)
        self.assertEqual(len(parsed),4)
        self.assertEqual(parsed[0][1],7)
        self.assertTrue(cached_forecast_valid(parsed,NOW,NOW+timedelta(minutes=10)))
        self.assertFalse(cached_forecast_valid(parsed,NOW,NOW+timedelta(minutes=91)))
    def test_missing_near_future(self):
        rows=[{"datetime":(NOW+timedelta(hours=i)).isoformat(),"temperature":8}
              for i in range(3,5)]
        self.assertEqual(parse_hourly_forecast(rows,NOW),[])
    def test_missing_horizon(self):
        rows=[{"datetime":NOW.isoformat(),"temperature":8},
             {"datetime":(NOW+timedelta(minutes=30)).isoformat(),"temperature":7}]
        self.assertEqual(parse_hourly_forecast(rows,NOW),[])
    def test_bad_temperature_and_timezone_rejected(self):
        rows=[{"datetime":NOW.isoformat(),"temperature":"NaN"},
              {"datetime":(NOW+timedelta(hours=1)).isoformat(),"temperature":9},
              {"datetime":(NOW+timedelta(hours=2)).isoformat(),"temperature":10},
              {"datetime":"2026-10-31T17:00:00","temperature":8}]
        parsed=parse_hourly_forecast(rows,NOW)
        self.assertEqual(len(parsed),2)
        self.assertEqual(parsed[0][1],9)
    def test_old_cache_never_kept(self):
        rows=[(NOW,8),(NOW+timedelta(hours=1),9)]
        self.assertFalse(cached_forecast_valid(rows,NOW-timedelta(hours=3),NOW))

if __name__=="__main__":unittest.main()
