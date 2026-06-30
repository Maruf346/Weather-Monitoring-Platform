from django.db import models
from django.utils import timezone


class WeatherReading(models.Model):
    timestamp      = models.DateTimeField(db_index=True)
    location       = models.CharField(max_length=100, default='Dhaka, Bangladesh')
    latitude       = models.FloatField()
    longitude      = models.FloatField()

    # Core measurements
    temperature    = models.FloatField(help_text='°C')
    humidity       = models.FloatField(help_text='%')
    pressure       = models.FloatField(help_text='hPa')
    rain           = models.FloatField(default=0.0, help_text='mm')
    wind_speed     = models.FloatField(default=0.0, help_text='km/h')
    wind_direction = models.FloatField(default=0.0, help_text='degrees')
    weather_code   = models.IntegerField(default=0, help_text='WMO weather code')

    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes  = [models.Index(fields=['-timestamp'])]

    def __str__(self):
        return f'{self.location} @ {self.timestamp:%Y-%m-%d %H:%M} — {self.temperature}°C'

    @property
    def weather_description(self):
        WMO_CODES = {
            0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
            45: 'Foggy', 48: 'Icy fog',
            51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
            61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
            71: 'Light snow', 73: 'Snow', 75: 'Heavy snow',
            80: 'Light showers', 81: 'Showers', 82: 'Heavy showers',
            95: 'Thunderstorm', 96: 'Thunderstorm with hail',
        }
        return WMO_CODES.get(self.weather_code, 'Unknown')

    @property
    def wind_direction_label(self):
        dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        idx = round(self.wind_direction / 45) % 8
        return dirs[idx]


class ForecastResult(models.Model):
    VARIABLE_CHOICES = [
        ('temperature', 'Temperature'),
        ('humidity',    'Humidity'),
        ('pressure',    'Pressure'),
        ('rain',        'Rain'),
    ]

    created_at      = models.DateTimeField(auto_now_add=True, db_index=True)
    forecast_time   = models.DateTimeField(help_text='Time being predicted')
    variable        = models.CharField(max_length=20, choices=VARIABLE_CHOICES)
    predicted_value = models.FloatField()
    lower_bound     = models.FloatField(null=True, blank=True)
    upper_bound     = models.FloatField(null=True, blank=True)
    minutes_ahead   = models.IntegerField(help_text='30 or 60')
    model_used      = models.CharField(max_length=50, default='ARIMA')

    class Meta:
        ordering = ['-created_at', 'minutes_ahead']

    def __str__(self):
        return (
            f'{self.variable} forecast @ {self.forecast_time:%H:%M} '
            f'({self.minutes_ahead}min ahead) = {self.predicted_value:.2f}'
        )


class AlertLog(models.Model):
    SEVERITY_CHOICES = [
        ('info',     'Info'),
        ('warning',  'Warning'),
        ('high',     'High'),
        ('critical', 'Critical'),
    ]

    TYPE_CHOICES = [
        ('temperature_anomaly', 'Temperature Anomaly'),
        ('humidity_anomaly',    'Humidity Anomaly'),
        ('pressure_anomaly',    'Pressure Anomaly'),
        ('rain_anomaly',        'Rain Anomaly'),
        ('wind_anomaly',        'Wind Anomaly'),
        ('general_anomaly',     'General Anomaly'),
    ]

    triggered_at    = models.DateTimeField(default=timezone.now, db_index=True)
    severity        = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='warning')
    alert_type      = models.CharField(max_length=30, choices=TYPE_CHOICES, default='general_anomaly')
    title           = models.CharField(max_length=200)
    description     = models.TextField()
    anomaly_score   = models.FloatField(default=0.0, help_text='Isolation Forest score')
    weather_reading = models.ForeignKey(
        WeatherReading, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='alerts'
    )
    is_active       = models.BooleanField(default=True)

    class Meta:
        ordering = ['-triggered_at']

    def __str__(self):
        return f'[{self.get_severity_display()}] {self.title} @ {self.triggered_at:%Y-%m-%d %H:%M}'

    @property
    def severity_color(self):
        colors = {
            'info':     'blue',
            'warning':  'yellow',
            'high':     'orange',
            'critical': 'red',
        }
        return colors.get(self.severity, 'gray')
