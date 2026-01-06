from django.urls import path

# Import only the specific view functions that are actually used for URLs.
# This avoids importing heavy helper modules (PDF generation, blockchain,
# Adafruit IO client, etc.) on every dashboard request.
from .views.main_view import (
    overview_view,
    active_view,
    ongoing_view,
    completed_view,
    analytics_view,
    alerts_view,
    product_manager_view,
    product_create_view,
    product_edit_view,
    product_delete_view,
    get_products_by_seller,
    create_contract_view,
    activate_contract_view,
    process_contract_action,
    shipment_details_view,
    shipment_log_view,
    ajax_latest_iot,
    shipment_logs,
    create_contract_modal,
    activate_contract_modal,
    contract_action_modal,
    contract_alerts,
    badge_counts_view,
    contract_details_modal,
    reject_contract_modal,
)
from .views.download_report import download_contract_report
from .views.download_logs import download_shipment_logs
from .views.contract_functions import reject_contract, manual_refund_contract

urlpatterns = [
    # ============================================================
    # DASHBOARD PAGES (HTMX containers)
    # These render the FULL page unless HX-Request header is present,
    # in which case the partial is returned.
    # ============================================================
    path("active/", active_view, name="active"),
    path("active/", active_view, name="active_view"),

    path("ongoing/", ongoing_view, name="ongoing"),
    path("ongoing/", ongoing_view, name="ongoing_view"),

    path("completed/", completed_view, name="completed"),
    path("completed/", completed_view, name="completed_view"),
    path("", overview_view, name="overview"),
    # ============================================================
    # MODALS (HTMX loads modal HTML directly into #mainModal)
    # ============================================================
    path("modal/create/", create_contract_modal, name="create_contract_modal"),
    path("modal/activate/<int:contract_id>/",
         activate_contract_modal,
         name="activate_contract_modal"),
    path("modal/action/<int:contract_id>/",
         contract_action_modal,
         name="contract_action_modal"),

    # ============================================================
    # CONTRACT ACTIONS (submitted BY HTMX from modals)
    # ============================================================
    path("contract/create/", create_contract_view, name="create_contract_view"),
    path("contract/activate/<int:contract_id>/", activate_contract_view, name="activate_contract"),
    path('contract/details/<int:contract_id>/', contract_details_modal, name='contract_details_modal'),
    path("contract/<int:contract_id>/action/",
         process_contract_action,
         name="process_contract_action"),
    path("contract/<int:contract_id>/alerts/", contract_alerts, name="contract_alerts"),
    path("contracts/<int:contract_id>/reject/", reject_contract, name="reject_contract"),
    path("contracts/<int:contract_id>/refund/manual/", manual_refund_contract, name="manual_refund_contract"),
    path(
        "contracts/<int:contract_id>/reject/modal/",
        reject_contract_modal,
        name="reject_contract_modal"
    ),
    # ============================================================
    # HTMX PARTIAL REFRESH ENDPOINTS (IoT + Activity Logs)
    # ============================================================
    path("ajax/contract/<int:contract_id>/latest-iot/",
         ajax_latest_iot,
         name="ajax_latest_iot"),

    path("ajax/contract/<int:contract_id>/logs/", shipment_logs, name="shipment_logs"),
    path('ajax/badge_counts/', badge_counts_view, name='badge_counts'),
    # ============================================================
    # REPORT DOWNLOAD
    # ============================================================
    path("completed/<int:contract_id>/download/",
         download_contract_report,
         name="download_contract_report"),
    path('download/logs/<int:contract_id>/', download_shipment_logs, name='download_logs'),
    # ============================================================
    # OTHER DASHBOARD ROUTES (if used in your UI)
    # ============================================================
    path("alerts/", alerts_view, name="alerts_view"),
    path("analytics/", analytics_view, name="analytics_view"),

    # Product management
    path("products/", product_manager_view, name="product_manager"),
    path("products/add/", product_create_view, name="product_add"),
    path("products/edit/<int:pk>/", product_edit_view, name="product_edit"),
    path("products/delete/<int:pk>/", product_delete_view, name="product_delete"),

    # Required by your forms (AJAX product list)
    path("get-products/<int:seller_id>/",
         get_products_by_seller,
         name="get_products_by_seller"),
]
