"""
Management command: run Isolation Forest anomaly detection.

Usage:
    python manage.py run_anomaly              # scan last 48h
    python manage.py run_anomaly --hours 72   # scan last 72h
    python manage.py run_anomaly --reset      # delete all alerts first, then scan
"""

from django.core.management.base import BaseCommand
from weather_ai.models import AlertLog
from services.anomaly_service import run_detection, get_alert_summary


class Command(BaseCommand):
    help = 'Run Isolation Forest anomaly detection on recent weather readings.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours', type=int, default=48,
            help='How many hours of recent data to scan (default: 48).',
        )
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete all existing alerts before scanning.',
        )

    def handle(self, *args, **options):
        if options['reset']:
            deleted, _ = AlertLog.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'  Cleared {deleted} existing alert(s).'))

        hours = options['hours']
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Running Isolation Forest anomaly detection (last {hours}h)...'
        ))

        result = run_detection(scan_hours=hours)

        self.stdout.write(self.style.SUCCESS(
            f'  Scanned:        {result["scanned"]} readings\n'
            f'  Anomalies found:{result["anomalies"]}\n'
            f'  New alerts:     {result["alerts_created"]}'
        ))

        summary = get_alert_summary()
        self.stdout.write(
            f'\n  Alert database summary:\n'
            f'    Total:    {summary["total"]}\n'
            f'    Active:   {summary["active"]}\n'
            f'    Critical: {summary["critical"]}\n'
            f'    High:     {summary["high"]}\n'
            f'    Warning:  {summary["warning"]}\n'
            f'    Info:     {summary["info"]}'
        )

        self.stdout.write(self.style.SUCCESS('\nDone. Visit /alerts/ to view results.'))
