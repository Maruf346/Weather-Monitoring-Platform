"""
Management command: fetch weather data from Open-Meteo.

Usage:
  python manage.py fetch_weather            # fetch current snapshot
  python manage.py fetch_weather --history  # also pull past 7 days of hourly data
  python manage.py fetch_weather --history --days 14
"""

import sys
from django.core.management.base import BaseCommand

from services.weather_service import fetch_current_weather, fetch_historical_weather


class Command(BaseCommand):
    help = "Fetch weather data from Open-Meteo and save to database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--history",
            action="store_true",
            help="Also fetch historical hourly data.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of past days to fetch when --history is set (default: 7).",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Fetching current weather..."))
        reading = fetch_current_weather()

        if reading:
            self.stdout.write(self.style.SUCCESS(
                f"  Current: {reading.temperature}°C, "
                f"Humidity {reading.humidity}%, "
                f"Pressure {reading.pressure} hPa, "
                f"Rain {reading.rain} mm"
            ))
        else:
            self.stdout.write(self.style.ERROR("  Failed to fetch current weather."))

        if options["history"]:
            days = options["days"]
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"Fetching historical data for past {days} days..."
            ))
            saved = fetch_historical_weather(past_days=days)
            self.stdout.write(self.style.SUCCESS(
                f"  Saved {saved} new historical records."
            ))

        self.stdout.write(self.style.SUCCESS("Done."))
