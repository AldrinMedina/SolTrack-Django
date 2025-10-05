from django.shortcuts import render

# Create your views here.
def overview_view(request):
    return render(request, "dashboard/overview.html")

def active_view(request):
    return render(request, 'dashboard/active.html')

def ongoing_view(request):
    return render(request, 'dashboard/ongoing.html')

def completed_view(request):
    return render(request, 'dashboard/completed.html')

def alerts_view(request):
    return render(request, 'dashboard/alerts.html')

def analytics_view(request):
    return render(request, 'dashboard/analytics.html')