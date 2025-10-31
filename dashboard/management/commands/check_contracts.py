from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from dashboard.models import Contract, IoTData
from dashboard.views.contract_functions import run_auto_checks_for_all_contracts, Contract
import math
import time

def log_status(stage, message, level="INFO"):
	ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	prefix = {
		"INFO":  f"\033[94m[INFO {ts}]",
		"WARN":  f"\033[93m[WARN {ts}]",
		"ERROR": f"\033[91m[ERR  {ts}]",
		"OK":    f"\033[92m[DONE {ts}]",
	}.get(level, f"[{level}]")

	sys.stdout.write(f"{prefix} {stage}: {message}\033[0m\n")
	sys.stdout.flush()

def haversine(lat1, lon1, lat2, lon2):
	R = 6371000  # Earth radius in meters
	phi1, phi2 = math.radians(lat1), math.radians(lat2)
	dphi = math.radians(lat2 - lat1)
	dlambda = math.radians(lon2 - lon1)
	a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
	return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def parse_coords(coord_str):
	if not coord_str:
		return None, None
	try:
		lat_str, lon_str = coord_str.split(',')
		return float(lat_str.strip()), float(lon_str.strip())
	except ValueError:
		return None, None
class Command(BaseCommand):
	help = "Automatically checks contracts for auto refund or completion (IoT-based)."

	def add_arguments(self, parser):
	 parser.add_argument("--contract", type=int, help="Check only this specific contract ID")
	 parser.add_argument("--temp-window", type=int, default=180, help="Temperature breach duration (seconds)")
	 parser.add_argument("--loc-window", type=int, default=180, help="Location arrival duration (seconds)")
	 parser.add_argument("--loc-radius-m", type=float, default=30.0, help="Radius (in meters) for completion")
	 parser.add_argument("--loop", action="store_true", help="Continuously check every 30s (for live testing)")
	 
	def handle(self, *args, **opts):
	 contract_id = opts.get("contract")
	 temp_window = opts["temp_window"]
	 loc_window = opts["loc_window"]
	 loc_radius_km = opts["loc_radius_m"] / 1000.0  # convert m → km
	 loop = opts.get("loop")

	while True:
		start_time = timezone.now().strftime("%H:%M:%S")
		log_status("System", f"Contract check time: {start_time}", "INFO")
		if contract_id:
			try:
				c = Contract.objects.get(pk=contract_id)
			except Contract.DoesNotExist:
				log_status("ContractLookup", f"Contract {contract_id} not found.", "ERROR")
				if not loop:
					break
			time.sleep(30)
			continue

			from dashboard.views.contract_functions import (
				contract_temp_out_of_range_for,
				contract_within_end_coords_for,
				execute_onchain_action,
			)

			log_status("ContractCheck", f"Checking contract {contract_id} | Status={getattr(c, 'status', 'N/A')} | IoT={getattr(c, 'IoT_Assigned_id', 'None')}", "INFO")

			log_status("Temperature", "Evaluating temperature window...", "INFO")
			if contract_temp_out_of_range_for(c, window_seconds=temp_window):
				log_status("Temperature", f"⚠️ Temp breach detected for contract {contract_id}. Initiating refund.", "WARN")
				execute_onchain_action(c, "refund")
				if not loop:
					break
				time.sleep(30)
				continue

			log_status("Location", "Evaluating location window...", "INFO")
			if contract_within_end_coords_for(c, radius_km=loc_radius_km, window_seconds=loc_window):
				log_status("Location", f"✅ Contract {contract_id} within destination for required window. Completing contract.", "OK")
				execute_onchain_action(c, "complete")
				if not loop:
					break
				time.sleep(30)
				continue

			log_status("Contract", f"No auto action required for contract {contract_id}.", "INFO")

		else:
			summary = run_auto_checks_for_all_contracts(
				check_temp_seconds=temp_window,
				check_location_seconds=loc_window,
				location_radius_km=loc_radius_km
			)

			self.stdout.write(self.style.SUCCESS("Auto check finished."))
			self.stdout.write(f"Refunded: {summary['refunds']}")
			self.stdout.write(f"Completed: {summary['completions']}")
			self.stdout.write(f"Skipped: {summary['skipped']}")
		if not loop:
			break
		time.sleep(30)


		 

