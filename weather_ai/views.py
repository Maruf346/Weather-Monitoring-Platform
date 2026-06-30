import json
from django.shortcuts import render
from weather_ai.models import WeatherReading, AlertLog, ForecastResult
from services.weather_service import get_latest_reading, get_recent_readings


WMO_ICONS = {
    0:  ('☀️',  'Clear Sky'),
    1:  ('🌤️', 'Mainly Clear'),
    2:  ('⛅',  'Partly Cloudy'),
    3:  ('☁️',  'Overcast'),
    45: ('🌫️', 'Foggy'),
    48: ('🌫️', 'Icy Fog'),
    51: ('🌦️', 'Light Drizzle'),
    53: ('🌧️', 'Drizzle'),
    55: ('🌧️', 'Heavy Drizzle'),
    61: ('🌧️', 'Light Rain'),
    63: ('🌧️', 'Rain'),
    65: ('⛈️', 'Heavy Rain'),
    71: ('🌨️', 'Light Snow'),
    73: ('❄️',  'Snow'),
    75: ('❄️',  'Heavy Snow'),
    80: ('🌦️', 'Showers'),
    81: ('🌦️', 'Heavy Showers'),
    82: ('⛈️', 'Violent Showers'),
    95: ('⛈️', 'Thunderstorm'),
    96: ('⛈️', 'Thunderstorm + Hail'),
}


def _wmo(code):
    return WMO_ICONS.get(code, ('🌡️', 'Unknown'))


def _chart_data(readings):
    """Build JSON-serialisable chart arrays from a queryset/list."""
    labels   = [r.timestamp.strftime('%H:%M') for r in readings]
    temps    = [round(r.temperature, 1)  for r in readings]
    humids   = [round(r.humidity, 1)     for r in readings]
    pressure = [round(r.pressure, 1)     for r in readings]
    rain     = [round(r.rain, 2)         for r in readings]
    return (
        json.dumps(labels),
        json.dumps(temps),
        json.dumps(humids),
        json.dumps(pressure),
        json.dumps(rain),
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────

def dashboard(request):
    latest   = get_latest_reading()
    readings = list(get_recent_readings(hours=24))

    # Downsample to ≤48 points so the chart stays readable
    step    = max(1, len(readings) // 48)
    sampled = readings[::step]

    temps = [r.temperature for r in readings]
    temp_min = round(min(temps), 1) if temps else 0
    temp_max = round(max(temps), 1) if temps else 0
    temp_avg = round(sum(temps) / len(temps), 1) if temps else 0

    trend = 'stable'
    if latest and len(temps) >= 6:
        if sum(temps[-3:]) / 3 > sum(temps[:3]) / 3 + 1:
            trend = 'rising'
        elif sum(temps[-3:]) / 3 < sum(temps[:3]) / 3 - 1:
            trend = 'falling'

    chart_labels, chart_temp, chart_humidity, chart_pressure, chart_rain = _chart_data(sampled)
    icon, desc = _wmo(latest.weather_code if latest else 0)

    context = {
        'page':           'dashboard',
        'latest':         latest,
        'weather_icon':   icon,
        'weather_desc':   desc,
        'temp_min':       temp_min,
        'temp_max':       temp_max,
        'temp_avg':       temp_avg,
        'trend':          trend,
        'recent_readings': list(reversed(readings[-10:])),
        'total_readings': WeatherReading.objects.count(),
        'chart_labels':   chart_labels,
        'chart_temp':     chart_temp,
        'chart_humidity': chart_humidity,
        'chart_pressure': chart_pressure,
        'chart_rain':     chart_rain,
    }
    return render(request, 'weather_ai/dashboard.html', context)


# ── Forecast ──────────────────────────────────────────────────────────────────

def forecast(request):
    from services.forecast_service import (
        generate_forecasts, get_latest_forecast_set,
        needs_refresh, build_chart_data,
    )

    # Auto-regenerate when stale (>60 min old) or missing
    refreshed = False
    if needs_refresh(max_age_minutes=60):
        generate_forecasts(steps=2)
        refreshed = True

    forecasts = get_latest_forecast_set()
    readings  = list(get_recent_readings(hours=24))

    chart = {}
    if readings:
        chart = build_chart_data(readings, forecasts)

    latest_fc = ForecastResult.objects.order_by('-created_at').first()

    context = {
        'page':       'forecast',
        'forecasts':  forecasts,
        'latest':     get_latest_reading(),
        'refreshed':  refreshed,
        'latest_fc':  latest_fc,
        **chart,
    }
    return render(request, 'weather_ai/forecast.html', context)


def alerts(request):
    all_alerts = AlertLog.objects.order_by('-triggered_at')[:50]
    return render(request, 'weather_ai/alerts.html', {
        'page':       'alerts',
        'all_alerts': all_alerts,
    })


def history(request):
    readings = WeatherReading.objects.order_by('-timestamp')[:100]
    return render(request, 'weather_ai/history.html', {
        'page':     'history',
        'readings': readings,
    })
