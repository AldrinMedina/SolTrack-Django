from dashboard.models import Alert
from django.utils import timezone

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
