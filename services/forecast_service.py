"""
ARIMA-based weather forecasting service.
Trains on the last 7 days of hourly WeatherReading data and produces
1-hour and 2-hour ahead predictions with confidence intervals.
"""

import json
import warnings
import logging
from datetime import timedelta

import pandas as pd
from django.utils import timezone

from weather_ai.models import WeatherReading, ForecastResult

logger = logging.getLogger(__name__)

VARIABLES    = ['temperature', 'humidity', 'pressure']
ARIMA_ORDERS = [(2, 1, 2), (1, 1, 1), (1, 1, 0), (0, 1, 1), (0, 1, 0)]


# ── Data helpers ──────────────────────────────────────────────────────────────

def _get_series(variable: str, n: int = 168):
    rows = list(
        WeatherReading.objects
        .order_by('-timestamp')
        .values('timestamp', variable)[:n]
    )
    if not rows:
        return None
    rows.reverse()
    values = [float(r[variable]) for r in rows]
    return pd.Series(values, name=variable)


# ── ARIMA fitting ─────────────────────────────────────────────────────────────

def _fit_arima(series):
    from statsmodels.tsa.arima.model import ARIMA
    for order in ARIMA_ORDERS:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                result = ARIMA(
                    series, order=order,
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                ).fit(method_kwargs={'warn_convergence': False})
            return result, order
        except Exception as exc:
            logger.debug("ARIMA%s failed for '%s': %s", order, series.name, exc)
    return None, None


# ── Forecast generation ───────────────────────────────────────────────────────

def generate_forecasts(steps: int = 2) -> int:
    """Train ARIMA per variable and save ForecastResult rows. Returns count."""
    now     = timezone.now()
    created = 0

    for variable in VARIABLES:
        series = _get_series(variable)
        if series is None or len(series) < 12:
            logger.warning("Not enough data to forecast '%s'.", variable)
            continue

        fitted, order = _fit_arima(series)
        if fitted is None:
            logger.error("All ARIMA orders failed for '%s'.", variable)
            continue

        model_name = f'ARIMA{order}'
        logger.info("Forecasting '%s' with %s", variable, model_name)

        try:
            fc       = fitted.get_forecast(steps=steps)
            predicted = fc.predicted_mean
            conf_int  = fc.conf_int()
        except Exception as exc:
            logger.error("get_forecast failed for '%s': %s", variable, exc)
            continue

        for i in range(steps):
            ForecastResult.objects.create(
                forecast_time   = now + timedelta(hours=(i + 1)),
                variable        = variable,
                predicted_value = round(float(predicted.iloc[i]), 2),
                lower_bound     = round(float(conf_int.iloc[i, 0]), 2),
                upper_bound     = round(float(conf_int.iloc[i, 1]), 2),
                minutes_ahead   = 60 * (i + 1),
                model_used      = model_name,
            )
            created += 1

    return created


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_latest_forecast_set() -> dict:
    """
    Returns {variable: {60: ForecastResult|None, 120: ForecastResult|None}}.
    """
    result = {}
    for variable in VARIABLES:
        result[variable] = {}
        for minutes in [60, 120]:
            result[variable][minutes] = (
                ForecastResult.objects
                .filter(variable=variable, minutes_ahead=minutes)
                .order_by('-created_at')
                .first()
            )
    return result


def needs_refresh(max_age_minutes: int = 60) -> bool:
    latest = ForecastResult.objects.order_by('-created_at').first()
    if not latest:
        return True
    return (timezone.now() - latest.created_at) > timedelta(minutes=max_age_minutes)


def build_chart_data(readings: list, forecasts: dict) -> dict:
    """
    Combine historical readings with ARIMA forecast into Chart.js-ready JSON.
    The forecast line visually connects at the last actual data point.
    """
    n = len(readings)

    hist_labels = [r.timestamp.strftime('%H:%M') for r in readings]
    hist_temps  = [round(r.temperature, 1) for r in readings]
    hist_humid  = [round(r.humidity, 1)    for r in readings]

    f60  = forecasts.get('temperature', {}).get(60)
    f120 = forecasts.get('temperature', {}).get(120)

    anchor = round(readings[-1].temperature, 1) if readings else None

    fc_values = [f60.predicted_value  if f60  else None,
                 f120.predicted_value if f120 else None]
    fc_upper  = [f60.upper_bound      if f60  else None,
                 f120.upper_bound     if f120 else None]
    fc_lower  = [f60.lower_bound      if f60  else None,
                 f120.lower_bound     if f120 else None]

    # x-axis: all historical labels + 2 future markers
    all_labels = hist_labels + ['+1h', '+2h']

    # Actual: historical values, then null for future slots
    actual_padded = hist_temps + [None, None]

    # Forecast: null for first (n-1) slots, then anchor → predictions
    pred_padded  = [None] * (n - 1) + [anchor] + fc_values
    upper_padded = [None] * (n - 1) + [anchor] + fc_upper
    lower_padded = [None] * (n - 1) + [anchor] + fc_lower

    return {
        'all_labels':  json.dumps(all_labels),
        'actual_data': json.dumps(actual_padded),
        'pred_data':   json.dumps(pred_padded),
        'upper_data':  json.dumps(upper_padded),
        'lower_data':  json.dumps(lower_padded),
        'hist_humid':  json.dumps(hist_humid),
    }
