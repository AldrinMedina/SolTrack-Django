from dashboard.models import Alert

from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

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