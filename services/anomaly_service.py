"""
Isolation Forest anomaly detection service.

Trains on all stored WeatherReading data (temperature, humidity, pressure,
rain, wind_speed) and flags readings that deviate from the learned pattern.
Saves results as AlertLog entries.
"""

import logging
import numpy as np

from django.utils import timezone

from weather_ai.models import WeatherReading, AlertLog

logger = logging.getLogger(__name__)

FEATURES = ['temperature', 'humidity', 'pressure', 'rain', 'wind_speed']

# contamination: expected fraction of anomalies in training data (~10% for demo)
CONTAMINATION = 0.10


# ── Training ──────────────────────────────────────────────────────────────────

def _build_matrix(readings):
    """Convert a list/qs of WeatherReadings into a numpy feature matrix."""
    return np.array([[getattr(r, f) for f in FEATURES] for r in readings],
                    dtype=float)


def train_isolation_forest(readings=None):
    """
    Fit an IsolationForest and StandardScaler on stored readings.
    Returns (model, scaler, hist_stats) or (None, None, None) if not enough data.
    """
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    if readings is None:
        readings = list(WeatherReading.objects.order_by('timestamp'))

    if len(readings) < 20:
        logger.warning('Not enough readings to train IsolationForest (%d).', len(readings))
        return None, None, None

    X = _build_matrix(readings)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_scaled)

    # Historical stats per feature (for alert descriptions)
    hist_stats = {
        feat: {'mean': float(np.mean(X[:, i])), 'std': float(np.std(X[:, i]))}
        for i, feat in enumerate(FEATURES)
    }

    logger.info('IsolationForest trained on %d readings.', len(readings))
    return model, scaler, hist_stats


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_readings(model, scaler, readings):
    """
    Return a list of (WeatherReading, anomaly_flag, score) tuples.
    anomaly_flag: -1 = anomaly, 1 = normal
    score: more negative → more anomalous
    """
    if not readings:
        return []

    X = _build_matrix(readings)
    X_scaled = scaler.transform(X)

    flags  = model.predict(X_scaled)           # -1 or 1
    scores = model.decision_function(X_scaled)  # raw anomaly score

    return list(zip(readings, flags.tolist(), scores.tolist()))


# ── Alert creation ────────────────────────────────────────────────────────────

def _dominant_feature(reading, hist_stats):
    """Find which feature deviates most from its historical mean (z-score)."""
    best_feat, best_z = 'temperature', 0.0
    for feat in FEATURES:
        std = hist_stats[feat]['std']
        if std == 0:
            continue
        z = abs(getattr(reading, feat) - hist_stats[feat]['mean']) / std
        if z > best_z:
            best_z, best_feat = z, feat
    return best_feat, best_z


def _severity(score: float) -> str:
    """Map IsolationForest score (negative = bad) to a severity label."""
    if score > -0.05:
        return 'info'
    elif score > -0.10:
        return 'warning'
    elif score > -0.15:
        return 'high'
    return 'critical'


def _alert_type(feature: str) -> str:
    return {
        'temperature': 'temperature_anomaly',
        'humidity':    'humidity_anomaly',
        'pressure':    'pressure_anomaly',
        'rain':        'rain_anomaly',
        'wind_speed':  'wind_anomaly',
    }.get(feature, 'general_anomaly')


def _build_alert(reading, score, hist_stats):
    """
    Create and save an AlertLog for an anomalous WeatherReading.
    Skips if an alert already exists for this reading.
    """
    # Skip duplicates
    if AlertLog.objects.filter(weather_reading=reading).exists():
        return None

    feat, z = _dominant_feature(reading, hist_stats)
    sev  = _severity(score)
    atype = _alert_type(feat)

    mean = hist_stats[feat]['mean']
    std  = hist_stats[feat]['std']
    val  = getattr(reading, feat)
    direction = 'above' if val > mean else 'below'

    labels = {
        'temperature': (f'{val:.1f}°C',    'Temperature', '°C'),
        'humidity':    (f'{val:.0f}%',      'Humidity',    '%'),
        'pressure':    (f'{val:.0f} hPa',   'Pressure',    'hPa'),
        'rain':        (f'{val:.1f} mm',    'Rainfall',    'mm'),
        'wind_speed':  (f'{val:.1f} km/h',  'Wind Speed',  'km/h'),
    }
    val_str, feat_label, unit = labels.get(feat, (str(val), feat, ''))

    title = f'Anomalous {feat_label}: {val_str}'
    description = (
        f'Detected at {reading.timestamp:%Y-%m-%d %H:%M UTC}. '
        f'{feat_label} of {val_str} is {z:.1f}σ {direction} '
        f'the historical average ({mean:.1f} ± {std:.1f} {unit}). '
        f'Isolation Forest score: {score:.4f}.'
    )

    return AlertLog.objects.create(
        triggered_at    = reading.timestamp,
        severity        = sev,
        alert_type      = atype,
        title           = title,
        description     = description,
        anomaly_score   = round(score, 4),
        weather_reading = reading,
        is_active       = True,
    )


# ── Full pipeline ─────────────────────────────────────────────────────────────

def run_detection(scan_hours: int = 48) -> dict:
    """
    Full pipeline: train → score recent readings → create alerts.
    Returns {'scanned': N, 'anomalies': M, 'alerts_created': K}.
    """
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(hours=scan_hours)

    all_readings    = list(WeatherReading.objects.order_by('timestamp'))
    recent_readings = [r for r in all_readings if r.timestamp >= cutoff]

    if not all_readings:
        return {'scanned': 0, 'anomalies': 0, 'alerts_created': 0}

    model, scaler, hist_stats = train_isolation_forest(all_readings)
    if model is None:
        return {'scanned': 0, 'anomalies': 0, 'alerts_created': 0}

    scored   = score_readings(model, scaler, recent_readings)
    anomalies = [(r, s) for r, flag, s in scored if flag == -1]

    created = 0
    for reading, score in anomalies:
        alert = _build_alert(reading, score, hist_stats)
        if alert:
            created += 1

    logger.info(
        'Anomaly scan complete: %d scanned, %d anomalies, %d new alerts.',
        len(recent_readings), len(anomalies), created,
    )
    return {
        'scanned':        len(recent_readings),
        'anomalies':      len(anomalies),
        'alerts_created': created,
    }


def get_alert_summary() -> dict:
    """Quick stats for the alert panel."""
    qs = AlertLog.objects.all()
    return {
        'total':    qs.count(),
        'active':   qs.filter(is_active=True).count(),
        'critical': qs.filter(severity='critical').count(),
        'high':     qs.filter(severity='high').count(),
        'warning':  qs.filter(severity='warning').count(),
        'info':     qs.filter(severity='info').count(),
    }
