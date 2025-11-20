from django.http import StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from dashboard.models import Contract
import time
import json
from django.http import JsonResponse
@login_required
def poll_contract_updates(request):
    contracts = Contract.objects.filter(seller_id=request.user.user_id)

    events = []

    for c in contracts:
        if c.status == "Refunded":
            events.append({"id": c.contract_id, "event": "refunded"})
            c.status = "RefundedNotified"
            c.save(update_fields=["status"])

        elif c.status == "Completed":
            events.append({"id": c.contract_id, "event": "completed"})
            c.status = "CompletedNotified"
            c.save(update_fields=["status"])

    return JsonResponse({"events": events})

