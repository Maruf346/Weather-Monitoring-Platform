from weather_ai.models import AlertLog


def global_weather_context(request):
    return {
        'alert_count': AlertLog.objects.filter(is_active=True).count(),
    }
