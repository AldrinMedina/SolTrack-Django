from django.apps import AppConfig

class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        import os

        from dashboard.models import Contract
        from dashboard.views.contract_watchers import start_watcher
        if os.environ.get("RUN_MAIN") != "true":
         return
        try:
            ongoing = Contract.objects.filter(status="Ongoing")
            for c in ongoing:
                start_watcher(c.contract_id)
                print(f"[BOOT] Restarted watcher for contract {c.contract_id}")
        except Exception as e:
            print(f"[BOOT] Skipped watcher restore: {e}")

