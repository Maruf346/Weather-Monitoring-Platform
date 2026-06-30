"""
One-shot demo setup command. Runs in order:
  1. Fetch 7 days of historical weather from Open-Meteo
  2. Fetch latest current reading
  3. Run ARIMA forecast (2 steps)
  4. Run Isolation Forest anomaly detection (full history)

Usage:
    python manage.py setup_demo
    python manage.py setup_demo --days 14   # more history
    python manage.py setup_demo --reset     # wipe alerts first
"""

from django.core.management.base import BaseCommand
from weather_ai.models import AlertLog, ForecastResult


class Command(BaseCommand):
    help = 'Bootstrap the demo: fetch weather, run forecast, detect anomalies.'

    def add_arguments(self, parser):
        parser.add_argument('--days',  type=int, default=7,   help='Days of history to fetch (default: 7)')
        parser.add_argument('--reset', action='store_true',   help='Clear forecasts and alerts before running')

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('=== Weather AI Demo Setup ===\n'))

        if options['reset']:
            fc, _ = ForecastResult.objects.all().delete()
            al, _ = AlertLog.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'  Cleared {fc} forecast(s) and {al} alert(s).\n'))

        # ── Step 1: Historical data ───────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('Step 1/4  Fetching historical weather data...'))
        from services.weather_service import fetch_historical_weather
        saved = fetch_historical_weather(past_days=options['days'])
        self.stdout.write(self.style.SUCCESS(f'  Saved {saved} historical records.\n'))

        # ── Step 2: Current reading ───────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('Step 2/4  Fetching current weather...'))
        from services.weather_service import fetch_current_weather
        reading = fetch_current_weather()
        if reading:
            self.stdout.write(self.style.SUCCESS(
                f'  Current: {reading.temperature}C  '
                f'Humidity {reading.humidity}%  '
                f'Pressure {reading.pressure} hPa\n'
            ))
        else:
            self.stdout.write(self.style.ERROR('  Failed to fetch current weather.\n'))

        # ── Step 3: ARIMA forecast ────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('Step 3/4  Running ARIMA forecast...'))
        from services.forecast_service import generate_forecasts, get_latest_forecast_set
        created = generate_forecasts(steps=2)
        self.stdout.write(self.style.SUCCESS(f'  Generated {created} forecast record(s).'))
        forecasts = get_latest_forecast_set()
        for variable, horizons in forecasts.items():
            for minutes, fr in horizons.items():
                if fr:
                    self.stdout.write(
                        f'    {variable:>12}  +{minutes}min : {fr.predicted_value:.2f}'
                        f'  [{fr.lower_bound:.2f} to {fr.upper_bound:.2f}]'
                        f'  ({fr.model_used})'
                    )
        self.stdout.write('')

        # ── Step 4: Anomaly detection ─────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('Step 4/4  Running anomaly detection...'))
        from services.anomaly_service import run_detection, get_alert_summary
        result = run_detection(scan_hours=options['days'] * 24)
        summary = get_alert_summary()
        self.stdout.write(self.style.SUCCESS(
            f'  Scanned {result["scanned"]} readings, '
            f'found {result["anomalies"]} anomalies, '
            f'created {result["alerts_created"]} new alert(s).'
        ))
        self.stdout.write(
            f'  Summary: {summary["critical"]} critical / '
            f'{summary["high"]} high / '
            f'{summary["warning"]} warning / '
            f'{summary["info"]} info\n'
        )

        # ── Done ──────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            '=== Setup complete! ===\n'
            'Start the server:  python manage.py runserver\n'
            'Open dashboard:    http://127.0.0.1:8000/'
        ))
