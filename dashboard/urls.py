from django.urls import path
from . import views

urlpatterns = [
    path("", views.overview_view, name="overview"),
    path('active/', views.active_view, name='active'),
    path('ongoing/', views.ongoing_view, name='ongoing'),
    path('completed/', views.completed_view, name='completed'),
    path('alerts/', views.alerts_view, name='alerts'),
    path('analytics/', views.analytics_view, name='analytics'),
]
