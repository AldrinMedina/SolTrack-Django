import threading
import time
from dashboard.models import Contract
from django.db import connection
def release_iot_device(contract):
    if contract.IoT_Assigned:
        device = contract.IoT_Assigned
        device.contract = None
        device.status = "Available"
        device.save(update_fields=["contract", "status"])
        print(f"[WATCH {contract.contract_id}] IoT '{device.device_name}' released")
        
def keep_db_alive():
    try:
        connection.close_if_unusable_or_obsolete()
    except:
        pass
WATCHERS = {}   # contract_id → thread


def start_watcher(contract_id):
    if contract_id in WATCHERS:
        print(f"[WATCH {contract_id}] already running")
        return

    def watcher():
        print(f"[WATCH {contract_id}] Started")

        # lazy import to avoid circular
        from dashboard.views.contract_functions import (
            contract_temp_out_of_range_for,
            contract_within_end_coords_for,
            execute_onchain_action
        )

        last_log = 0

        while True:
            keep_db_alive() 
            try:
                c = Contract.objects.get(pk=contract_id)
            except Contract.DoesNotExist:
                print(f"[WATCH {contract_id}] STOP — Contract deleted")
                break

            if c.status != "Ongoing":
                print(f"[WATCH {contract_id}] STOP — Status = {c.status}")
                break

            # 🔥 load dynamic configuration from DB
            temp_window = c.temperature_time
            loc_window = c.location_time
            radius_km = c.radius / 1000.0

            # heartbeat every 2 minutes only
            if time.time() - last_log > 120:
                print(f"[WATCH {contract_id}] checking… (temp:{temp_window}s / loc:{loc_window}s / r:{c.radius}m)")
                last_log = time.time()

            # refund check
            if contract_temp_out_of_range_for(c, window_seconds=temp_window):
                print(f"[WATCH {contract_id}] REFUND — temperature violation")                
                if execute_onchain_action(c, "refund"):
                    c.status = "Refunded"
                    c.save(update_fields=["status"])
                    release_iot_device(c)
                break

            # completion check
            if contract_within_end_coords_for(c, radius_km=radius_km, window_seconds=loc_window):
                print(f"[WATCH {contract_id}] COMPLETE — location verified")
                if execute_onchain_action(c, "complete"):
                    c.status = "Completed"
                    c.save(update_fields=["status"])
                    release_iot_device(c)
                break

            time.sleep(30)

        print(f"[WATCH {contract_id}] STOP")
        WATCHERS.pop(contract_id, None)

    t = threading.Thread(target=watcher, daemon=True)
    WATCHERS[contract_id] = t
    t.start()
