from django.urls import path
from . import views


urlpatterns = [
    path("overview/", views.overview_view, name="overview"),
    path('overview/data/', views.dashboard_data, name='dashboard_data'),
    path('active/', views.active_view, name='active'),
    path('contract/create/', views.create_contract_view, name='create_contract'),
    path('contract/<int:contract_id>/action/', views.process_contract_action, name='process_contract_action'),
    
    path('ongoing/', views.ongoing_view, name='ongoing'),
    path('ongoing/data/', views.ongoing_data_json, name='ongoing_data_json'),
    path('ongoing/<int:contract_id>/details/', views.shipment_details_view, name='shipment_details'),
    
    path('completed/', views.completed_view, name='completed'),
    path('completed/<int:contract_id>/', views.download_contract_report, name='download_contract_report'),
    path('alerts/', views.alerts_view, name='alerts'),
    path('analytics/', views.analytics_view, name='analytics'),


    path("products/", views.product_manager_view, name="product_manager"),
    path("products/add/", views.product_create_view, name="product_add"),
    path("products/edit/<int:pk>/", views.product_edit_view, name="product_edit"),
    path("products/delete/<int:pk>/", views.product_delete_view, name="product_delete"),
    path('get-products/<int:seller_id>/', views.get_products_by_seller, name='get_products_by_seller'),
    path('contract/<int:contract_id>/activate/', views.contract_functions.activate_contract, name='activate_contract'),
    path('api/contract/<int:contract_id>/temperature/', views.contract_functions.get_contract_temperature, name='contract_temp_api'),
    path('process_contract_action/<int:contract_id>/', views.contract_functions.process_contract_action, name='process_contract_action'),    
    path('ongoing/<int:contract_id>/details/', views.shipment_details_view, name='shipment_details'),
    path('api/products-by-seller/<int:seller_pk>/', views.get_products_by_seller, name='get_products_by_seller'),   
    ]
