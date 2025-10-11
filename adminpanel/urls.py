from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),

    path('contracts/', views.admin_contracts, name='admin_contracts'),
    path("delete_contract/<int:contract_id>/", views.delete_contract, name="delete_contract"),


    path('users/', views.admin_users, name='admin_users'),
    path("approve_user/<int:user_id>/", views.approve_user, name="approve_user"),
    path("deactivate_user/<int:user_id>/", views.deactivate_user, name="deactivate_user"),

    
    path('devices/', views.admin_devices, name='admin_devices'),
    path("toggle_device/<int:device_id>/", views.toggle_device_status, name="toggle_device_status"),
    path("delete_device/<int:device_id>/", views.delete_device, name="delete_device"),


    path('reports/', views.admin_reports, name='admin_reports'),
    path('settings/', views.admin_settings, name='admin_settings'),
]
