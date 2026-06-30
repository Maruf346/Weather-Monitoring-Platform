"""
Management command: run ARIMA forecast on stored weather data.

Usage:
    python manage.py run_forecast
    python manage.py run_forecast --steps 3
"""

from django.core.management.base import BaseCommand
from services.forecast_service import generate_forecasts, get_latest_forecast_set


class Command(BaseCommand):
    help = 'Train ARIMA models and generate weather forecasts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--steps',
            type=int,
            default=2,
            help='Number of 1-hour steps to forecast (default: 2).',
        )

    def handle(self, *args, **options):
        steps = options['steps']
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Running ARIMA forecast ({steps} step(s) ahead)...'
        ))
        self.stdout.write('  This may take a few seconds while models converge.')

        created = generate_forecasts(steps=steps)

        if created == 0:
            self.stdout.write(self.style.ERROR('  No forecasts generated — insufficient data?'))
            return

        self.stdout.write(self.style.SUCCESS(f'  Generated {created} forecast records.\n'))

        forecasts = get_latest_forecast_set()
        for variable, horizons in forecasts.items():
            for minutes, fr in horizons.items():
                if fr:
                    self.stdout.write(
                        f'  {variable:>12}  +{minutes}min : '
                        f'{fr.predicted_value:.2f}  '
                        f'[{fr.lower_bound:.2f} to {fr.upper_bound:.2f}]  '
                        f'({fr.model_used})'
                    )

        self.stdout.write(self.style.SUCCESS('\nDone. Visit /forecast/ to view predictions.'))
