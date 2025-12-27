# dashboard/views/__init__.py

# Import ONLY the actual Django view functions.
# Do NOT expose internal helpers or blockchain utilities here.
from .download_report import (
 download_contract_report,
)
from .download_logs import (
 download_shipment_logs,
)
from .main_view import (
    overview_view,
    dashboard_data,
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
from .contract_functions import (
	reject_contract,
	manual_refund_contract,
)
# Optional: Expose watcher starter if used explicitly (normally internal)
from .contract_watchers import start_watcher, start_iot_fetcher
from .notify_functions import (
	create_alert
)
