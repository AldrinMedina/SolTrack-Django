from django.apps import AppConfig
import threading, time
import os
from django.utils import timezone

_thread_started = False
class DashboardConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'dashboard'
	def ready(self):
		global _thread_started
		if _thread_started:
			return
		_thread_started = True
		if os.environ.get("RUN_MAIN") != "true":
			return
		def background_auto_check():
			print(f"[AUTO] Running in PID {os.getpid()}")
			#apps not loaded yet error fix
			from dashboard.views.contract_functions import run_auto_checks_for_all_contracts

			while True:
				try:
					print(f"[{timezone.now()}] auto-check contract on")
					summary = run_auto_checks_for_all_contracts(
						check_temp_seconds=180,
						check_location_seconds=180,
						location_radius_km=0.03
					)
					print("auto-check deets", summary)
				except Exception as e:
					print("auto-check failed", e)
				time.sleep(30)  #shunt 30 secs
		threading.Thread(target=background_auto_check, daemon=True).start()

