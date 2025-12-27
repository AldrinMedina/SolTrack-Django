from django.http import StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from dashboard.models import Contract
import time
import json
from django.http import JsonResponse
from dashboard.models import Alert
from datetime import timedelta
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from dashboard.models import Alert, ShipmentLog
from django.utils import timezone
def ensure_aware(dt):
    """Ensures a datetime object is timezone-aware."""
    if dt is None:
        return None
    # Use timezone.make_aware if it's naive, otherwise return dt
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
def _save_iot_summary_log(contract, device, msg, log_type="IoT Data"):
    """Helper to save the IoT summary logs (Points 2 & 3)."""
    from .contract_functions import create_shipment_log
    create_shipment_log(
        contract=contract,
        device=device,
        message=msg,
        log_type=log_type,
    )
def get_summarized_log_data(contract, device, temp_threshold=0.5, min_stable_seconds=60): 
    from ..models import IoTData
    device_id = device.device_id
    readings = IoTData.objects.filter(device_id=device_id).order_by("created_at")
    
    # We remove 'log_summary' creation as we save directly to DB

    if not readings.exists():
        # Do not save a log entry, just exit
        return

    first = next(
        (r for r in readings if r.temperature is not None and r.created_at is not None),
        None
    )
    if not first:
        return

    current_temp = first.temperature
    start_time = ensure_aware(first.created_at)
    prev_time = start_time
    was_offline = False

    for i in range(1, len(readings)):
        r = readings[i]
        if r.temperature is None or r.created_at is None:
            continue

        new_time = ensure_aware(r.created_at)
        gap = (new_time - prev_time).total_seconds()

        # --- OFFLINE EVENT (Point 3) ---
        if gap > 120:
            duration = timedelta(seconds=gap)
            msg = f"⚠ Device offline detected. Gap of {duration} between readings."
            _save_iot_summary_log(contract, device, msg, log_type="Alert") # ACTION: SAVE LOG
            was_offline = True

        # --- TEMP CHANGE EVENT (Point 2) ---
        # Also check for re-connection after offline event
        if was_offline or abs(r.temperature - current_temp) >= temp_threshold: # <--- Implementation point 3
            
            if was_offline:
                # Log the RECONNECTION event
                msg = (
                    f"📡 Device reconnected — resumed at {r.temperature:.2f}°C "
                    f"after offline period."
                )
                _save_iot_summary_log(contract, device, msg, log_type="Alert") # ACTION: SAVE LOG
                was_offline = False
            
            # Log the TEMPERATURE CHANGE event
            elif abs(r.temperature - current_temp) >= temp_threshold:
                duration = new_time - start_time
                msg = (
                    f"Temp changed from {current_temp:.2f}°C → {r.temperature:.2f}°C. "
                    f"Previous stable period: {duration}."
                )
                _save_iot_summary_log(contract, device, msg) # ACTION: SAVE LOG (Defaults to 'IoT Data')

            current_temp = r.temperature
            start_time = new_time

        prev_time = new_time

    # --- FINAL STATE LOG (Point 4) ---
    # Log the final stable period up to the last processed reading
    last_time = ensure_aware(readings.last().created_at)
    duration = last_time - start_time
    
    if duration.total_seconds() >= min_stable_seconds:
        msg = (
            f"Temp stable at {current_temp:.2f}°C for {duration} "
            f"(up to {last_time.strftime('%H:%M:%S')})."
        )
        _save_iot_summary_log(contract, device, msg) # ACTION: SAVE LOG (Defaults to 'IoT Data')

    return
def create_alert(contract=None, device=None, alert_type='Notice', message='', severity='Warning',
                 category='System', metadata=None):
    if metadata is None:
        metadata = {}
    return Alert.objects.create(
        contract=contract,
        device=device,
        alert_type=alert_type,
        alert_message=message,
        severity=severity,
        status='Active',
        is_read=False,
        category=category,
        metadata=metadata,
        triggered_at=timezone.now()
    )

@login_required
def clear_all_alerts(request):
    if request.method == 'POST':
        Alert.objects.filter(status='Active').update(status='Cleared', is_read=True)
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'POST required'}, status=400)

@login_required
def mark_alert_read(request, alert_id):
    if request.method == 'POST':
        a = get_object_or_404(Alert, pk=alert_id)
        a.is_read = True
        a.save(update_fields=['is_read'])
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'POST required'}, status=400)
    
@login_required
def poll_contract_updates(request):
    contracts = Contract.objects.filter(seller_id=request.user.user_id)

    events = []

    for c in contracts:
        if c.status == "Refunded":
            events.append({"id": c.contract_id, "event": "refunded"})
            c.status = "Refunded"
            c.save(update_fields=["status"])

        elif c.status == "Completed":
            events.append({"id": c.contract_id, "event": "completed"})
            c.status = "Completed"
            c.save(update_fields=["status"])

    return JsonResponse({"events": events})

