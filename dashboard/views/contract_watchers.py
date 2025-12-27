import threading
from threading import Event
import time
import traceback
import os
from Adafruit_IO import Client 
from Adafruit_IO import RequestError, AdafruitIOError
from django.utils import timezone
from django.db import transaction
from ..models import Contract, IoTData, ShipmentLog, IoTDataHistory
from .notify_functions import create_alert, get_summarized_log_data
from .contract_functions import execute_onchain_action, create_shipment_log, resolve_contract
ADAFRUIT_IO_USERNAME = os.getenv("ADAFRUIT_IO_USERNAME")
ADAFRUIT_IO_KEY = os.getenv("ADAFRUIT_IO_KEY")
aio = Client(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)
CHECK_INTERVAL_SECONDS = 12
LOG_GEN_INTERVAL_CYCLES = 5  
TEMP_LOG_THRESHOLD = 1.0          
MIN_STABLE_PERIOD_SECONDS = 60
MAX_STALE_DATA_SECONDS = 300
SHIPMENT_LOG_INTERVAL_SECONDS = 60
_active_watchers = {}
_active_iot_fetchers = {}
_fetcher_stop_events = {}
_lock = threading.Lock()
stop_event = Event()
def log_info(msg): print(f"[WATCHER/INFO] {msg}")
def log_warn(msg): print(f"[WATCHER/WARN] {msg}")
def log_err(msg): print(f"[WATCHER/ERROR] {msg}")
def log_iot(msg): print(f"[IOT/INFO] {msg}")
def log_iot_warn(msg): print(f"[IOT/WARN] {msg}")

def ensure_aware(dt):
    if dt is None:
        return None
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt

def fetch_adafruit_iot_data():

    try:
        temp_feed = aio.receive('text-feed')
        temperature = float(temp_feed.value) if temp_feed and temp_feed.value is not None else None

        return temperature

    except Exception as e:
        print(f"[IOT FETCH] Error fetching from Adafruit: {e}")
        return None

def _iot_fetcher_loop(contract_id):
    last_heartbeat_time = None 
    last_logged_temp = None
    current_stable_temp = None
    stable_temp_start_time = None

    while not _stop_event.is_set():
        try:
            contract_db = Contract.objects.select_related('IoT_Assigned').get(pk=contract_id)
            
            if contract_db.status in ["Completed", "Refunded", "Rejected"]:
                break

            device = contract_db.IoT_Assigned
            if not device:
                if _stop_event.wait(timeout=CHECK_INTERVAL_SECONDS):
                    break
                continue

            temp = fetch_adafruit_iot_data()
            if temp is None:
                if _stop_event.wait(timeout=CHECK_INTERVAL_SECONDS):
                    break
                continue

            now = timezone.now()

            IoTData.objects.create(
                device=device,
                contract=contract_db,
                temperature=temp,
                created_at=now,
                recorded_at=now
            )

            if last_heartbeat_time is None or (now - last_heartbeat_time).total_seconds() >= SHIPMENT_LOG_INTERVAL_SECONDS:
                msg = f"Periodic Temp Check: {temp}°C"
                create_shipment_log(contract_db, msg, log_type="IoT Data")
                last_heartbeat_time = now

            if current_stable_temp is None:
                current_stable_temp = temp
                stable_temp_start_time = now

            temp_diff = abs(temp - current_stable_temp)

            if temp_diff > TEMP_LOG_THRESHOLD:
                duration = (now - stable_temp_start_time).total_seconds()
                if duration >= MIN_STABLE_PERIOD_SECONDS:
                    msg = f"Stable period ended. Held {current_stable_temp}°C for {int(duration/60)}m."
                    create_shipment_log(contract_db, msg, log_type="IoT Data")
                
                current_stable_temp = temp
                stable_temp_start_time = now
            
            else:
                duration = (now - stable_temp_start_time).total_seconds()
                if duration >= MIN_STABLE_PERIOD_SECONDS and last_logged_temp != current_stable_temp:
                    msg = f"Temp stabilized at {current_stable_temp}°C (Held for {int(duration/60)}m)."
                    create_shipment_log(contract_db, msg, log_type="IoT Data")
                    last_logged_temp = current_stable_temp

        except Contract.DoesNotExist:
            break
        except Exception:
            if _stop_event.wait(timeout=CHECK_INTERVAL_SECONDS):
                break

        if _stop_event.wait(timeout=CHECK_INTERVAL_SECONDS):
            break

    with _lock:
        if contract_id in _active_iot_fetchers:
            _active_iot_fetchers.pop(contract_id, None)
        
def _watcher_loop(contract_id):
    consecutive_breach_count = 0
    breach_start_time = None
    breach_type = None
    log_cycle_counter = 0
    is_offline = False 
    
    while not _stop_event.is_set():
        try:
            with transaction.atomic():
                contract_db = Contract.objects.select_for_update().get(pk=contract_id)
                if contract_db.status != 'Active':
                    break

                device = contract_db.IoT_Assigned
                if not device:
                    if _stop_event.wait(timeout=CHECK_INTERVAL_SECONDS): break
                    continue

                now = timezone.now()
                latest = IoTData.objects.filter(device=device).order_by("-recorded_at").first()
                
                time_diff = (now - latest.recorded_at).total_seconds() if latest and latest.temperature is not None else None

                if time_diff is None or time_diff > MAX_STALE_DATA_SECONDS:
                    if not is_offline:
                        is_offline = True
                        gap_msg = f"Gap of {str(now - latest.recorded_at)} between readings." if latest else "No data available."
                        msg = f"Device offline detected. {gap_msg}"
                        create_shipment_log(contract_db, msg, device=device, log_type="Alert")
                        create_alert(
                            contract=contract_db, 
                            device=device, 
                            alert_type="Device Offline", 
                            message=msg, 
                            severity="Critical", 
                            category="Connectivity"
                        )                    
            
                    consecutive_breach_count = 0
                    breach_start_time = None
                    if _stop_event.wait(timeout=CHECK_INTERVAL_SECONDS): break
                    continue 
                
                if is_offline:
                    is_offline = False
                    msg = f"Device reconnected — resumed at {latest.temperature:.2f}°C after offline period."
                    create_shipment_log(contract_db, msg, device=device, log_type="System")
                    create_alert(
                        contract=contract_db, 
                        device=device, 
                        alert_type="Device Reconnected", 
                        message=msg, 
                        severity="Info", 
                        category="Connectivity"
                    )

                temp = latest.temperature
                min_t = contract_db.min_temp
                max_t = contract_db.max_temp

                if temp < min_t or temp > max_t:
                    consecutive_breach_count += 1
                    if breach_start_time is None:
                        breach_start_time = now
                        breach_type = "Low" if temp < min_t else "High"
                        msg = f"Temperature breach started: {temp:.2f}°C (Outside {min_t}°C - {max_t}°C)."
                        create_shipment_log(contract_db, msg, device=device, log_type="Alert")
                        create_alert(
                            contract=contract_db,
                            device=device,
                            alert_type="Breach Started",
                            message=msg,
                            severity="Warning",
                            category="Temperature"
                        )
                    
                    if breach_start_time:
                        elapsed = (now - breach_start_time).total_seconds()
                        if elapsed >= 60 and (int(elapsed) % 60 == 0):
                            create_shipment_log(
                                contract_db, 
                                f"Breach ongoing for {elapsed:.0f}s, temp={temp}°C",
                                log_type="Critical"
                            )
                            create_alert(
                                contract=contract_db,
                                device=device,
                                alert_type="Breach Ongoing",
                                message=f"Breach ongoing for {elapsed:.0f}s, temp={temp}°C",
                                severity="Warning",
                                category="Temperature"
                            )
                 
                    if breach_start_time and (now - breach_start_time).total_seconds() > contract_db.temperature_time:
                        reason = f"Temperature breach exceeded allowable time window"
                        try:
                            resolve_contract(
                                contract_id=contract_db.contract_id,
                                action="refund",
                                reason=reason,
                                source="System",
                                execute_chain=True   
                            )
                        except Exception:
                            if _stop_event.wait(timeout=CHECK_INTERVAL_SECONDS): break
                            continue
                        return 
                        
                else:                 
                    if breach_start_time is not None:                      
                        elapsed = (now - breach_start_time).total_seconds()
                        msg = f"Breach ended after {elapsed:.0f} seconds. Current temp: {temp:.2f}°C."
                        create_shipment_log(contract_db, msg, device=device, log_type="System")
                        create_alert(
                            contract=contract_db,
                            device=device,
                            alert_type="Breach Ended",
                            message=msg,
                            severity="Info",
                            category="Temperature"
                        )
                    
                    consecutive_breach_count = 0
                    breach_start_time = None
                    breach_type = None

                log_cycle_counter += 1
                if log_cycle_counter >= LOG_GEN_INTERVAL_CYCLES:
                    log_cycle_counter = 0
                    log_data = get_summarized_log_data(contract_db, device)
                    if log_data and log_data['temp_diff'] > TEMP_LOG_THRESHOLD:
                         create_shipment_log(
                            contract_db,
                            f"Periodic summary: Avg:{log_data['avg']:.2f}°C, Min:{log_data['min']:.2f}°C, Max:{log_data['max']:.2f}°C",
                            device=device,
                            log_type="Report"
                        )
                    IoTDataHistory.objects.filter(contract=contract_db).delete()

        except Contract.DoesNotExist:
            break
        except Exception:
            pass

        if _stop_event.wait(timeout=CHECK_INTERVAL_SECONDS): break

    with _lock:
        _active_watchers.pop(contract_id, None)

def start_watcher(contract_id):
    with _lock:
        if contract_id in _active_watchers:
            return
        thread = threading.Thread(target=_watcher_loop, args=(contract_id,), daemon=True)
        _active_watchers[contract_id] = thread
        thread.start()

def start_iot_fetcher(contract_id):
    with _lock:
        if contract_id in _active_iot_fetchers:
            return

        stop_event = threading.Event()
        _fetcher_stop_events[contract_id] = stop_event

        def _run():
            try:
                _iot_fetcher_loop(contract_id, stop_event)
            except Exception as e:
                log_err(f"IoT fetcher crashed for {contract_id}: {e}")
                # Auto-restart logic
                if not stop_event.is_set():
                    start_iot_fetcher(contract_id)

        thread = threading.Thread(target=_run, daemon=True)
        _active_iot_fetchers[contract_id] = thread
        thread.start()

def stop_iot_fetcher(contract_id):
    with _lock:
        event = _fetcher_stop_events.pop(contract_id, None)
        if event:
            event.set()
