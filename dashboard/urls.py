from django.urls import path
from . import views

urlpatterns = [
    # ============================================================
    # DASHBOARD PAGES (HTMX containers)
    # These render the FULL page unless HX-Request header is present,
    # in which case the partial is returned.
    # ============================================================
    path("active/", views.active_view, name="active"),
    path("active/", views.active_view, name="active_view"),

    path("ongoing/", views.ongoing_view, name="ongoing"),
    path("ongoing/", views.ongoing_view, name="ongoing_view"),

    path("completed/", views.completed_view, name="completed"),
    path("completed/", views.completed_view, name="completed_view"),
    path("", views.overview_view, name="overview"),
    # ============================================================
    # MODALS (HTMX loads modal HTML directly into #mainModal)
    # ============================================================
    path("modal/create/", views.create_contract_modal, name="create_contract_modal"),
    path("modal/activate/<int:contract_id>/",
         views.activate_contract_modal,
         name="activate_contract_modal"),
    path("modal/action/<int:contract_id>/",
         views.contract_action_modal,
         name="contract_action_modal"),

    # ============================================================
    # CONTRACT ACTIONS (submitted BY HTMX from modals)
    # ============================================================
    path("contract/create/", views.create_contract_view, name="create_contract_view"),
    path("contract/activate/<int:contract_id>/", views.activate_contract_view, name="activate_contract"),
    path('contract/details/<int:contract_id>/', views.contract_details_modal, name='contract_details_modal'),
    path("contract/<int:contract_id>/action/",
         views.process_contract_action,
         name="process_contract_action"),
    path("contract/<int:contract_id>/alerts/", views.contract_alerts, name="contract_alerts"),
    path("contracts/<int:contract_id>/reject/", views.reject_contract, name="reject_contract"),
    path("contracts/<int:contract_id>/refund/manual/", views.manual_refund_contract, name="manual_refund_contract"),
    path(
        "contracts/<int:contract_id>/reject/modal/",
        views.reject_contract_modal,
        name="reject_contract_modal"
    ),
    # ============================================================
    # HTMX PARTIAL REFRESH ENDPOINTS (IoT + Activity Logs)
    # ============================================================
    path("ajax/contract/<int:contract_id>/latest-iot/",
         views.ajax_latest_iot,
         name="ajax_latest_iot"),

    path("ajax/contract/<int:contract_id>/logs/",
         views.shipment_logs,
         name="shipment_logs"),
    path('ajax/badge_counts/', views.badge_counts_view, name='badge_counts'),
    # ============================================================
    # REPORT DOWNLOAD
    # ============================================================
    path("completed/<int:contract_id>/download/",
         views.download_contract_report,
         name="download_contract_report"),
    path('download/logs/<int:contract_id>/', views.download_shipment_logs, name='download_logs'),
    # ============================================================
    # OTHER DASHBOARD ROUTES (if used in your UI)
    # ============================================================
    path("alerts/", views.alerts_view, name="alerts_view"),
    path("analytics/", views.analytics_view, name="analytics_view"),

    # Product management
    path("products/", views.product_manager_view, name="product_manager"),
    path("products/add/", views.product_create_view, name="product_add"),
    path("products/edit/<int:pk>/", views.product_edit_view, name="product_edit"),
    path("products/delete/<int:pk>/", views.product_delete_view, name="product_delete"),

    # Required by your forms (AJAX product list)
    path("get-products/<int:seller_id>/",
         views.get_products_by_seller,
         name="get_products_by_seller"),
]
