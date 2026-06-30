from django.contrib import admin
from .models import WeatherReading, ForecastResult, AlertLog


@admin.register(WeatherReading)
class WeatherReadingAdmin(admin.ModelAdmin):
    list_display  = ('timestamp', 'location', 'temperature', 'humidity', 'pressure', 'rain', 'wind_speed', 'weather_description')
    list_filter   = ('location',)
    search_fields = ('location',)
    readonly_fields = ('created_at', 'weather_description', 'wind_direction_label')
    date_hierarchy = 'timestamp'
    ordering      = ('-timestamp',)

    fieldsets = (
        ('Location & Time', {
            'fields': ('timestamp', 'location', 'latitude', 'longitude')
        }),
        ('Measurements', {
            'fields': ('temperature', 'humidity', 'pressure', 'rain', 'wind_speed', 'wind_direction', 'weather_code')
        }),
        ('Derived', {
            'fields': ('weather_description', 'wind_direction_label', 'created_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(ForecastResult)
class ForecastResultAdmin(admin.ModelAdmin):
    list_display  = ('forecast_time', 'variable', 'predicted_value', 'lower_bound', 'upper_bound', 'minutes_ahead', 'model_used', 'created_at')
    list_filter   = ('variable', 'minutes_ahead', 'model_used')
    readonly_fields = ('created_at',)
    ordering      = ('-created_at',)


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display  = ('triggered_at', 'severity', 'alert_type', 'title', 'anomaly_score', 'is_active')
    list_filter   = ('severity', 'alert_type', 'is_active')
    search_fields = ('title', 'description')
    readonly_fields = ('triggered_at',)
    ordering      = ('-triggered_at',)
    actions       = ['mark_resolved']

    @admin.action(description='Mark selected alerts as resolved')
    def mark_resolved(self, request, queryset):
        queryset.update(is_active=False)
