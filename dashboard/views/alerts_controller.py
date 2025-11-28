from dashboard.models import Alert

from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required


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