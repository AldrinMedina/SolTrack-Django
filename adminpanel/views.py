# adminpanel/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Count, Avg
from django.http import JsonResponse

from dashboard.models import Contract, IoTDevice, IoTDataHistory, Alert
from accounts.models import CustomUser

def is_admin(user):
    return user.is_staff or getattr(user, "role", "") == "admin"

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    # --- Basic analytics ---
    total_contracts = Contract.objects.count()
    active_contracts = Contract.objects.filter(status__in=["Active", "Ongoing", "In Transit"]).count()
    completed_contracts = Contract.objects.filter(status__in=["Completed", "Delivered"]).count()

    # IoT overview
    total_devices = IoTDevice.objects.count()
    active_devices = IoTDevice.objects.filter(status="Active").count()
    alert_count = Alert.objects.filter(status="Active").count()

    avg_temp = IoTDataHistory.objects.aggregate(Avg("avg_temp"))["avg_temp__avg"] or 0

    context = {
        "total_contracts": total_contracts,
        "active_contracts": int(active_contracts),
        "completed_contracts": int(completed_contracts),
        "total_devices": int(total_devices),
        "active_devices": active_devices,
        "alert_count": alert_count,
        "avg_temp": round(avg_temp, 2),
    }
    return render(request, 'adminpanel/admin_dashboard.html', context)

@login_required
@user_passes_test(is_admin)
def admin_contracts(request):
    contracts = Contract.objects.select_related("buyer", "seller").all().order_by("-start_date")

    context = {
        "contracts": contracts
    }
    return render(request, 'adminpanel/contracts.html', context)

def delete_contract(request, contract_id):
    if request.method == "POST":
        try:
            Contract.objects.get(id=contract_id).delete()
            return JsonResponse({"success": True})
        except Contract.DoesNotExist:
            return JsonResponse({"success": False, "error": "Contract not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})

@login_required
@user_passes_test(is_admin)
def admin_users(request):
    buyers = CustomUser.objects.filter(role="Buyer").order_by("-created_at")
    sellers = CustomUser.objects.filter(role="Seller").order_by("-created_at")
    managers = CustomUser.objects.filter(role="ProductManager").order_by("-created_at") if hasattr(CustomUser.Role, "PRODUCTMANAGER") else []

    context = {
        "buyers": buyers,
        "sellers": sellers,
        "managers": managers,
    }
    return render(request, "adminpanel/users.html", context)

@login_required
@user_passes_test(is_admin)
def approve_user(request, user_id):
    if request.method == "POST":
        try:
            user = CustomUser.objects.get(user_id=user_id)
            user.is_approved = True
            user.save()
            return JsonResponse({"success": True})
        except CustomUser.DoesNotExist:
            return JsonResponse({"success": False, "error": "User not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})

@login_required
@user_passes_test(is_admin)
def deactivate_user(request, user_id):
    if request.method == "POST":
        try:
            user = CustomUser.objects.get(user_id=user_id)
            user.is_active = False
            user.save()
            return JsonResponse({"success": True})
        except CustomUser.DoesNotExist:
            return JsonResponse({"success": False, "error": "User not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})


@login_required
@user_passes_test(is_admin)
def admin_devices(request):
    devices = IoTDevice.objects.all().order_by("-created_at")
    contracts = Contract.objects.all().order_by("-start_date")

    if request.method == "POST":
        # Handle device registration
        device_name = request.POST.get("device_name")
        adafruit_feed = request.POST.get("adafruit_feed")
        contract_id = request.POST.get("contract_id")

        if device_name and adafruit_feed:
            try:
                contract = Contract.objects.get(contract_id=contract_id) if contract_id else None
                IoTDevice.objects.create(
                    device_name=device_name,
                    adafruit_feed=adafruit_feed,
                    contract=contract,
                    status="Active"
                )
                messages.success(request, "Device registered successfully.")
                return redirect("admin_devices")
            except Contract.DoesNotExist:
                messages.error(request, "Invalid contract selected.")
        else:
            messages.error(request, "Please fill in all required fields.")

    context = {
        "devices": devices,
        "contracts": contracts,
    }
    return render(request, "adminpanel/iot_devices.html", context)

@login_required
@user_passes_test(is_admin)
def toggle_device_status(request, device_id):
    if request.method == "POST":
        try:
            device = IoTDevice.objects.get(id=device_id)
            device.status = "Inactive" if device.status == "Active" else "Active"
            device.save()
            return JsonResponse({"success": True, "new_status": device.status})
        except IoTDevice.DoesNotExist:
            return JsonResponse({"success": False, "error": "Device not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})


@login_required
@user_passes_test(is_admin)
def delete_device(request, device_id):
    if request.method == "POST":
        try:
            device = IoTDevice.objects.get(id=device_id)
            device.delete()
            return JsonResponse({"success": True})
        except IoTDevice.DoesNotExist:
            return JsonResponse({"success": False, "error": "Device not found"})
    return JsonResponse({"success": False, "error": "Invalid request"})

@login_required
@user_passes_test(is_admin)
def admin_reports(request):
    return render(request, 'adminpanel/reports.html')

@login_required
@user_passes_test(is_admin)
def admin_settings(request):
    return render(request, 'adminpanel/system_settings.html')
