from django.urls import path
from . import views

app_name = 'weather_ai'

urlpatterns = [
    path('',          views.dashboard, name='dashboard'),
    path('forecast/', views.forecast,  name='forecast'),
    path('alerts/',   views.alerts,    name='alerts'),
    path('history/',  views.history,   name='history'),
]
