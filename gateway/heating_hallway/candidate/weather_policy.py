"""Pure weather-source policy for the Hallway heating learner (no HA services).

Weather forecasts and instantaneous outdoor temperature are different inputs.
Never infer a provider when multiple active providers exist, and never feed a
stale/malformed hourly sequence into the 60-minute thermal prediction.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from math import isfinite

MAX_FORECAST_CACHE = timedelta(minutes=90)
MAX_OUTDOOR_AGE = timedelta(minutes=90)

def active_weather_ids(weather_states):
    return sorted({s.entity_id for s in weather_states if
        getattr(s,"entity_id","").startswith("weather.") and
        s.state not in ("unknown","unavailable")})

def select_weather(configured, weather_states):
    available=active_weather_ids(weather_states)
    if configured:
        return configured if configured in available else None
    return available[0] if len(available)==1 else None

def outdoor_temperature(state, now, max_age=MAX_OUTDOOR_AGE):
    if state is None or state.state in ("unavailable","unknown"):return None
    observed=getattr(state,"last_reported",None) or getattr(state,"last_updated",None)
    if not isinstance(observed,datetime):return None
    if observed.tzinfo is None or now.tzinfo is None:return None
    if not timedelta(0)<=now-observed<=max_age:return None
    try:
        value=float(state.state)
    except (TypeError,ValueError,OverflowError):
        return None
    return value if isfinite(value) and -30<=value<=50 else None

def weather_current_temperature(state, now):
    if state is None or state.state in ("unavailable","unknown"):return None
    observed=getattr(state,"last_reported",None) or getattr(state,"last_updated",None)
    if not isinstance(observed,datetime) or observed.tzinfo is None or now.tzinfo is None:
        return None
    if not timedelta(0)<=now-observed<=MAX_OUTDOOR_AGE:return None
    try:
        value=float(state.attributes.get("temperature"))
    except (AttributeError,TypeError,ValueError,OverflowError):
        return None
    return value if isfinite(value) and -30<=value<=50 else None

def parse_hourly_forecast(rows,now):
    if now.tzinfo is None or not isinstance(rows,list):return []
    parsed=[]
    for item in rows:
        if not isinstance(item,dict):continue
        try:
            raw=item.get("datetime")
            if not isinstance(raw,str):continue
            ts=datetime.fromisoformat(raw.replace("Z","+00:00"))
            temp=float(item["temperature"])
            if ts.tzinfo is None or not isfinite(temp) or not -30<=temp<=50:continue
            parsed.append((ts.astimezone(timezone.utc),temp))
        except (TypeError,ValueError,KeyError,OverflowError):continue
    parsed.sort(key=lambda x:x[0])
    points=[]
    for ts,temp in parsed:
        if not points or ts>points[-1][0]:
            points.append((ts,temp))
    # Predictions need both a near-term anchor and a 60-minute horizon.
    if len(points)<2 or points[0][0] > now+timedelta(minutes=65):
        return []
    if points[-1][0] < now+timedelta(minutes=60):
        return []
    if points[0][0] < now-timedelta(hours=2):
        # A provider may return prior hour(s), but never an old cached forecast.
        points=[p for p in points if p[0]>=now-timedelta(hours=2)]
    return points[:24] if len(points)>=2 else []

def cached_forecast_valid(rows, fetched_at, now):
    return (isinstance(fetched_at,datetime) and fetched_at.tzinfo is not None
        and now.tzinfo is not None
        and timedelta(0)<=now-fetched_at<=MAX_FORECAST_CACHE
        and bool(rows) and rows[0][0]<=now+timedelta(minutes=65)
        and rows[-1][0]>=now+timedelta(minutes=60))
