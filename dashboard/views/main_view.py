# dashboard/views/main_view.py
import os
import json
import random
import math
import time
import urllib.request
import threading
from datetime import datetime, timedelta
import json

from web3 import Web3
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg, Min, Max, Q, F
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from ..models import (
    Contract,
    Product,
    IoTDevice,
    IoTData,
    IoTDataHistory,
    Product,
    ShipmentLog,
    ContractAddresses,
    Alert,
)
from dashboard.models import CustomUser

from .config import web3, CHAIN_ID, GAS_PRICE_GWEI, DEPLOYER_ADDRESS
from .notify_functions import create_alert
from .notify_functions import create_alert
# Avoid importing contract_watchers at module import time to reduce startup
# memory/CPU. We will import the needed functions lazily inside the activation
# code path.
from .contract_functions import (
    attach_iot_device_to_contract,
    detach_iot_device_from_contract,
    deploy_contract_on_chain,
    seller_activate_on_chain,
    execute_onchain_action,
    gas_dict,
    create_shipment_log, 
)

from .notify_functions import get_summarized_log_data
User = get_user_model()

def toggle_other_reason(request):
    reason_code = request.GET.get("reason_code")

    if reason_code == "OTHER":
        html = render_to_string("dashboard/partials/other_reason_field.html")
        return HttpResponse(html)

    return HttpResponse("")
    
@login_required
def contract_details_modal(request, contract_id):
    contract = get_object_or_404(Contract, pk=contract_id)
    
    return render(request, "dashboard/partials/contract_details_modal.html", {
        "contract": contract
    })
    
@login_required
def reject_contract_modal(request, contract_id):
    contract = get_object_or_404(Contract, contract_id=contract_id)

    if contract.status != "Pending" or request.user.role != "Seller":
        return render(request, "dashboard/modals/forbidden.html")

    return render(
        request,
        "dashboard/modals/reject_contract_modal.html",
        {"contract": contract}
    )
    
@login_required
def badge_counts_view(request):
    user = request.user
    user_contracts = Contract.objects.filter(Q(buyer=user) | Q(seller=user))
    active_contracts = user_contracts.filter(status__in=['Pending', 'Active']).count()
    ongoing_contracts = user_contracts.filter(status='Active').count()
    completed_contracts = user_contracts.filter(status__in=['Completed', 'Refunded']).count()

    alert_count = Alert.objects.filter(
        contract__in=user_contracts, 
        status='Active' 
    ).count()

    context = {
        'active_count': active_contracts,
        'ongoing_count': ongoing_contracts,
        'completed_count': completed_contracts,
        'alerts_count': alert_count,
    }
    
    return render(request, "dashboard/partials/badge_counts.html", context)

def contract_temp_out_of_range_for(contract_db, window_seconds=180):
    device = contract_db.IoT_Assigned
    if not device:
        return False

    cutoff = timezone.now() - timezone.timedelta(seconds=window_seconds)
    readings = IoTData.objects.filter(
        device=device,
        recorded_at__gte=cutoff
    )

    if not readings.exists():
        return False

    for r in readings:
        if r.temperature is None:
            continue
        if r.temperature < contract_db.min_temp or r.temperature > contract_db.max_temp:
            return True
    return False

@login_required
def active_view(request):
    contracts = Contract.objects.filter(
        status__in=["Pending", "Active", "Refunded", "Rejected"]
    ).order_by('-contract_id')
    devices = IoTDevice.objects.all()

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/active_list.html", {
            "contracts": contracts,
            "devices": devices
        })

    return render(request, "dashboard/active.html", {
        "contracts": contracts,
        "devices": devices
    })
    
def create_contract_modal(request):
    sellers = CustomUser.objects.filter(role="Seller")
    buyer_addr = request.session.get("m_address")

    return render(request, "dashboard/modals/create_contract_modal.html", {
        "sellers": sellers,
        "buyer_address": buyer_addr,
    })

@login_required
def create_contract_view(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    seller_id = request.POST.get("seller")
    seller = CustomUser.objects.get(user_id=seller_id)

    contract = Contract.objects.create(
        buyer=request.user,
        seller=seller,
        buyer_address=request.POST.get("buyer_address"),
        seller_address=request.POST.get("seller_address"),
        product_name=request.POST.get("product_name"),
        quantity=request.POST.get("quantity"),
        price=request.POST.get("Price"),
        min_temp=request.POST.get("min_temp"),
        max_temp=request.POST.get("max_temp"),
        temperature_time=request.POST.get("temperature_time"),
        status="Pending",
        final_price = request.POST.get("final_price")
    )
    create_shipment_log(
        contract,
        f"Contract created. Product: {contract.product_name} (Qty: {contract.quantity}). Total Escrow: {contract.final_price} ETH."
    )
    create_alert(
     contract=contract,  
     device=contract.IoT_Assigned,
     alert_type="Contract Created",
     message=f"New contract created: {contract.product_name}",
     severity="Info",
     category="System"
    )
    
    contracts = Contract.objects.filter(status="Pending")
    devices = IoTDevice.objects.all()

    resp = render(request, "dashboard/partials/active_list.html", {
        "contracts": contracts,
        "devices": devices
    })
    resp["HX-Toast"] = "Contract created"
    resp["HX-Trigger"] = "closeModal" 
    resp["HX-Toast-Level"] = "success"
    
    return resp

@login_required
def activate_contract_modal(request, contract_id):
    contract = get_object_or_404(Contract, pk=contract_id)
    devices = IoTDevice.objects.all()

    return render(request, "dashboard/modals/activate_contract_modal.html", {
        "contract": contract,
        "devices": devices
    })

@login_required
def contract_action_modal(request, contract_id):
    contract = get_object_or_404(Contract, pk=contract_id)
    action = request.GET.get("action")
    if action == "refund":
        return render(request, "dashboard/modals/refund_contract_modal.html", {
            "contract": contract,
            "action": action
        })
    return render(request, "dashboard/modals/contract_action_modal.html", {
        "contract": contract,
        "action": action
    })

@login_required
def ongoing_view(request):
    contracts = Contract.objects.filter(status="Active")

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/ongoing_list.html", {
            "contracts": contracts
        })

    return render(request, "dashboard/ongoing.html", {
        "contracts": contracts
    })
    
def format_ts(ts):
    ts = ensure_aware(ts)
    return ts.strftime("%Y-%m-%d %H:%M:%S")

def ensure_aware(dt):
    if dt is None:
        return None
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
    
def save_log(contract, device, log_time, message):
    exists = ShipmentLog.objects.filter(
        contract=contract,
        device=device,
        log_time=log_time,
        message=message
    ).exists()

    if not exists:
        ShipmentLog.objects.create(
         contract=contract,
         device=device,
         log_time=ensure_aware(log_time),
         message=message
        )

def completed_view(request):
    contracts = Contract.objects.filter(
        Q(status="Completed") | Q(status="Refunded")
    ).order_by('-contract_id') 

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/completed_list.html", {
            "contracts": contracts
        })

    return render(request, "dashboard/completed.html", {
        "contracts": contracts
    })

@login_required
def activate_contract_view(request, contract_id):
    if request.method != "POST":
        return HttpResponse(status=405)

    contract = get_object_or_404(Contract, pk=contract_id)

    if contract.status != "Pending":
        return JsonResponse({"error": "Contract is not in a Pending state"}, status=400)

    device_id = request.POST.get("iot_device_select")
    if not device_id:
        return JsonResponse({"error": "No IoT device selected"}, status=400)

    device = get_object_or_404(IoTDevice, pk=device_id)
    if device.status != "Available":
        return JsonResponse({"error": "Selected IoT device is not available"}, status=400)
    
    seller_pk =  request.POST.get("seller_private_key")
    def log_info(msg): print(f"[ACTIVATION/INFO] {msg}")
    def log_err(msg): print(f"[ACTIVATION/ERROR] {msg}")
    def _activation_thread(contract_id, device_id):
        log_info(f"[Contract {contract_id}] Activation thread started.")

        try:
            contract = Contract.objects.get(pk=contract_id)
            device = IoTDevice.objects.get(pk=device_id)

            try:
                attach_iot_device_to_contract(device, contract)
                create_shipment_log(contract, f"IoT Device {device.device_name} attached to contract.", device=device)
                
                log_info(f"IoT device {device.device_name} assigned")
            except Exception as e:
                log_err(f"Failed to assign IoT device: {e}")
                return

            if not contract.contract_address or not contract.contract_abi:
                try:
                    addr, abi_json, _ = deploy_contract_on_chain(contract)
                    contract.contract_address = addr
                    contract.contract_abi = abi_json
                    create_shipment_log(contract, f"Smart Contract deployed. Address: {addr}", log_type="TX")
                    contract.save(update_fields=["contract_address", "contract_abi"])
                    log_info(f"Deployed on-chain at {addr}")
                except Exception as e:
                    log_err(f"Deployment failed: {e}")
                    detach_iot_device_from_contract(contract)
                    return
            buyer_private_key = contract.buyer.private_key
            buyer_address = Web3.to_checksum_address(contract.buyer_address)
            price_wei = int(contract.final_price * (10**18))
            if not buyer_private_key:
                 log_err(f"Buyer private key missing for contract {contract_id}.")
                 detach_iot_device_from_contract(contract)
                 return
            try:
                nonce = web3.eth.get_transaction_count(buyer_address)
                tx = {
                    "nonce": nonce,
                    "to": Web3.to_checksum_address(DEPLOYER_ADDRESS), # Funds go to Deployer/Escrow wallet
                    "value": price_wei,
                    "gas": 21000,
                    "gasPrice": web3.to_wei(GAS_PRICE_GWEI, "gwei"),
                    "chainId": CHAIN_ID
                }

                signed = web3.eth.account.sign_transaction(tx, buyer_private_key)
                tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
                initial_payment_receipt = receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

                if initial_payment_receipt.status == 0:
                    log_err(f"Buyer payment failed on-chain: {tx_hash.hex()}")
                    detach_iot_device_from_contract(contract)
                    return

                addr_rec, _ = ContractAddresses.objects.get_or_create(contract=contract)
                addr_rec.init_payment_add = initial_payment_receipt.transactionHash.hex() 
                addr_rec.init_payment_gas = gas_dict(initial_payment_receipt)
                addr_rec.save(update_fields=["init_payment_add", "init_payment_gas"])
                create_shipment_log(
                    contract, 
                    f"Initial payment of {contract.final_price} ETH sent by Buyer to Deployer/Escrow.",
                    log_type="Financial"
                )
                log_info(f"Buyer funds transferred to Deployer/Escrow wallet. TX: {tx_hash.hex()}")

            except Exception as e:
                log_err(f"Buyer initial payment error: {e}")
                detach_iot_device_from_contract(contract)
                return

            success, err = seller_activate_on_chain(
                contract,
                seller_pk
            )
            if success:
                create_shipment_log(contract, f"Contract state activated on-chain by Seller.")
            if not success:
                log_err(f"On-chain activation failed: {err}")
                detach_iot_device_from_contract(contract)
                return

            contract.status = "Active"
            contract.start_date = timezone.now()
            contract.save(update_fields=["status", "start_date"])
            # Lazy import to avoid heavy watcher imports until needed
            from .contract_watchers import start_watcher, start_iot_fetcher
            start_watcher(contract_id)
            start_iot_fetcher(contract_id)

            create_alert(
                contract=contract,
                device=contract.IoT_Assigned,
                alert_type="Contract Activated",
                message="Contract successfully activated and monitoring started.",
                severity="Info",
                category="System"
            )

            log_info(f"[Contract {contract_id}] Activation complete")

        except Exception as e:
            log_err(f"[Contract {contract_id}] Activation thread error: {e}")
            
    threading.Thread(
        target=_activation_thread,
        args=(contract.contract_id, device.device_id),
        daemon=True
    ).start()

    resp = render(
        request,
        "dashboard/partials/contract_card.html",
        {"contract": contract, "devices": IoTDevice.objects.all()}
    )
    
    resp["HX-Toast"] = "Activation started"
    resp["HX-Trigger"] = "closeModal"
    return resp

@login_required(login_url='login')
def shipment_logs(request, contract_id):
    try:
        contract = Contract.objects.get(pk=contract_id)
        summarized_logs = ShipmentLog.objects.filter(contract=contract).order_by("log_time")

        return render(request, "dashboard/partials/shipment_logs.html", {
            "logs": summarized_logs
        })

    except Contract.DoesNotExist:
        return render(request, "dashboard/partials/shipment_logs.html", {
            "logs": [{"log_time": "N/A", "log_message": "Contract not found."}]
        })
    except Exception as e:
        print("Error loading logs:", e)
        return render(request, "dashboard/partials/shipment_logs.html", {
            "logs": [{
                "log_time": "N/A",
                "log_message": f"Error loading logs: {e}. Check background worker status."
            }]
        })
        from django.db.models import F 

@login_required(login_url='login')
def shipment_log_view(request, contract_id):    
    contract = get_object_or_404(Contract, pk=contract_id)
    logs = ShipmentLog.objects.filter(contract=contract) 

    return render(request, "dashboard/partials/shipment_logs.html", { 
        "contract": contract,
        "logs": logs
    })        

#justincase dont del
@login_required(login_url='login')
def shipment_log_views(request, contract_id):   
    try:
        contract = Contract.objects.select_related("IoT_Assigned").get(pk=contract_id)

        if not contract.IoT_Assigned:
            return JsonResponse({"error": "No IoT device assigned"}, status=404)

        device = contract.IoT_Assigned
        summarized_logs = get_summarized_log_data(contract, device)

        return JsonResponse({
            "contract_id": contract_id,
            "product_name": contract.product_name, 
            "quantity": contract.quantity,
            "device_name": device.device_name,
            "device_id": device.device_id,
            "log": summarized_logs
        })
            
    except Contract.DoesNotExist:
        return JsonResponse({"error": f"Contract {contract_id} not found."}, status=404)
        
    except Exception as e:
        print(f"[LOG VIEW] Error fetching logs for contract {contract_id}: {e}")
        return JsonResponse({"error": str(e)}, status=500)
        
def shipment_details_view(request, contract_id):
	try:
		contract = Contract.objects.select_related('buyer', 'seller').get(contract_id=contract_id)
	except Contract.DoesNotExist:
		raise Http404("Shipment not found")

	device = contract.IoT_Assigned
	latest_iot = None

	if device:
		latest_iot = IoTData.objects.filter(device_id=device.device_id).order_by('-recorded_at').first()

	data = {
		"contract_id": contract.contract_id,
		"product_name": contract.product_name,
		"quantity": contract.quantity,
		"price": float(contract.price) if contract.price else None,
		"status": contract.status,
		"contract_address": contract.contract_address,
		"deployment_date": contract.start_date.strftime("%Y-%m-%d %H:%M:%S") if contract.start_date else "N/A",
		"buyer_name": getattr(contract.buyer, 'full_name', getattr(contract.buyer, 'username', "N/A")),
		"buyer_email": getattr(contract.buyer, 'email', "N/A"),
		"buyer_wallet": getattr(contract.buyer, 'm_address', 'N/A'),
		"seller_name": getattr(contract.seller, 'full_name', getattr(contract.seller, 'username', "N/A")),
		"seller_email": getattr(contract.seller, 'email', "N/A"),
		"seller_wallet": getattr(contract.seller, 'm_address', 'N/A'),
		"latest_temp": latest_iot.temperature if latest_iot else "N/A",
		"battery_voltage": latest_iot.battery_voltage if latest_iot else "N/A",
		"recorded_at": latest_iot.recorded_at.strftime("%Y-%m-%d %H:%M:%S") if latest_iot else "N/A",
		"device_name": getattr(device, "device_name", "No Device Linked"),
	}

	return JsonResponse(data)
		
@require_GET
def get_products_by_seller(request, seller_id):
	try:
		seller = CustomUser.objects.get(pk=seller_id)
		products = Product.objects.filter(seller=seller, quantity_available__gt=0)

		product_list = list(products.values(
			'product_id',
			'product_name',
			'price_eth',
			'max_temp',
			'min_temp',
			'temp_time_range',
			'description',
			'quantity_available',
		))

		return JsonResponse({'products': product_list, "seller_address": getattr(seller, 'm_address', None)})

	except CustomUser.DoesNotExist:
		return JsonResponse({'error': 'Seller not found.'}, status=404)
	except Exception as e:
		print("DEBUG: EXCEPTION in get_products_by_seller:", e)
		return JsonResponse({'error': 'Could not retrieve products.'}, status=500)

@login_required(login_url='login')
def overview_view(request):
	user = request.user 
	user_role = request.session.get("user_role", "").lower()

	if user_role.lower() == "buyer":
		contracts = Contract.objects.filter(buyer=user)
	elif user_role.lower() == "seller":
		contracts = Contract.objects.filter(seller=user)
	else:
		contracts = Contract.objects.all()
		
	total_contracts = contracts.count()
	active_contracts = contracts.filter(status__in=["Active", "Ongoing"]).count()
	completed_contracts = contracts.filter(status__in=["Completed"]).count()
	iot_data = IoTDataHistory.objects.filter(contract__in=contracts)
	avg_temp = iot_data.aggregate(avg=Avg("avg_temp"))["avg"] or 0
	total_records = iot_data.count()
	normal_records = iot_data.filter(result="Normal").count()
	success_rate = round((normal_records / total_records) * 100, 1) if total_records > 0 else 0
	alerts = []
	active_alerts = []
	active_alert_count = 0
	active_sensors = (
		IoTDevice.objects
		.filter(contract__in=contracts.filter(status__in=["Active","Ongoing"]))
		.select_related("contract")
	)

	temp_history = (
		iot_data.order_by("-recorded_at")[:10]  # get latest 10 readings
		.values_list("recorded_at", "avg_temp")
	)
	chart_labels = [t[0].strftime("%H:%M") for t in reversed(temp_history)]
	chart_values = [t[1] for t in reversed(temp_history)]

	context = {
		"user_role": user_role,
		"total_contracts": total_contracts,
		"active_contracts": active_contracts,
		"completed_contracts": completed_contracts,
		"avg_temp": round(avg_temp, 2),
		"success_rate": success_rate,
		"active_sensors": active_sensors,
		"active_alerts": active_alerts,
		"active_alert_count": active_alert_count,
		"chart_labels_json": json.dumps(chart_labels),
		"chart_values_json": json.dumps(chart_values)
	}

	return render(request, "dashboard/overview.html", context)
	
def analytics_view(request):
	return render(request, 'dashboard/analytics.html')
	
@login_required(login_url='login')
def product_manager_view(request):
	if request.user.role.lower() != "seller":
		messages.error(request, "Access denied. Only sellers can manage products.")
		return redirect("overview")

	products = Product.objects.filter(seller=request.user).order_by("-created_at")
	return render(request, "dashboard/products/product_manager.html", {"products": products})
	
@login_required(login_url='login')
def product_create_view(request):
	if request.user.role.lower() != "seller":
		messages.error(request, "Access denied.")
		return redirect("overview")

	if request.method == "POST":
		form = ProductForm(request.POST)
		if form.is_valid():
			product = form.save(commit=False)
			product.seller = request.user
			product.save()
			messages.success(request, "Product added successfully.")
			return redirect("product_manager")
	else:
		form = ProductForm()
	return render(request, "dashboard/products/product_form.html", {"form": form, "title": "Add Product"})


@login_required(login_url='login')
def product_edit_view(request, pk):
	product = get_object_or_404(Product, pk=pk, seller=request.user)
	if request.method == "POST":
		form = ProductForm(request.POST, instance=product)
		if form.is_valid():
			form.save()
			messages.success(request, "Product updated successfully.")
			return redirect("product_manager")
	else:
		form = ProductForm(instance=product)
	return render(request, "dashboard/products/product_form.html", {"form": form, "title": "Edit Product"})

@login_required(login_url='login')
def product_delete_view(request, pk):
	product = get_object_or_404(Product, pk=pk, seller=request.user)
	product.delete()
	messages.success(request, "Product deleted successfully.")
	return redirect("product_manager")	
	
@login_required(login_url='login')	
def alerts_view(request):
    # Reverting to show ALL alerts (Active and Inactive) for all users, ordered by newest first.
    alerts = Alert.objects.all().order_by('-triggered_at')

    user_role = request.session.get("user_role", "").lower()

    return render(request, "dashboard/alerts.html", {
        "alerts": alerts,
        "user_role": user_role
    })


def dashboard_data(request):
	user = request.user
	user_role = request.session.get("user_role", "").lower()
	user_id = request.session.get("user_id")
	if user_role.lower() == "buyer":
		contracts = Contract.objects.filter(buyer_id=user_id)
	elif user_role.lower() == "seller":
		contracts = Contract.objects.filter(seller_id=user_id)
	else:
		contracts = Contract.objects.all()

	total_contracts = contracts.count()
	active_contracts = contracts.filter(status__in=["Active", "Ongoing"]).count()
	ongoing_contracts = contracts.filter(status__in=["Ongoing"]).count()
	completed_contracts = contracts.filter(status__in=["Completed"]).count()

	devices = IoTDevice.objects.filter(contract__in=contracts)
	iot_data = IoTData.objects.filter(device__in=devices)

	avg_temp = iot_data.aggregate(avg=Avg("temperature"))["avg"] or 0
	total_records = iot_data.count()

	normal_records = iot_data.filter(temperature__range=(2, 8)).count()
	success_rate = round((normal_records / total_records) * 100, 1) if total_records > 0 else 0

	active_alerts = 0
	system_status = "All sensors online" if active_alerts == 0 else "Issues detected"
	status_color = "bg-success" if active_alerts == 0 else "bg-danger"

	temp_history = (
		iot_data.order_by("-recorded_at")[:10]
		.values_list("recorded_at", "temperature")
	)
	chart_labels = [t[0].strftime("%H:%M") for t in reversed(temp_history)]
	chart_values = [t[1] for t in reversed(temp_history)]

	return JsonResponse({
		"total_contracts": total_contracts,
		"active_contracts": active_contracts,
		"ongoing_contracts": ongoing_contracts,
		"completed_contracts": completed_contracts,
		"avg_temp": round(avg_temp, 2),
		"success_rate": success_rate,
		"active_alerts": active_alerts,
		"chart_labels": chart_labels,
		"chart_values": chart_values,
		"system_status": system_status,
		"status_color": status_color,
	})

@login_required
def process_contract_action(request, contract_id):
	contract = get_object_or_404(Contract, pk=contract_id)
	if request.method != "POST":
		return HttpResponse(status=405)
	action = request.POST.get("action")
	
	if action == "complete":
		success = execute_onchain_action(contract, "complete")
		if not success:
			return JsonResponse({"error": "Failed to complete contract on-chain. Check contract state."}, status=500)
		toast_msg = "Shipment completed"

	elif action == "refund":
		success = execute_onchain_action(contract, "refund")
		if not success:
			return JsonResponse({"error": "On-chain refund failed"}, status=500)
		toast_msg = "Refund successful"

	else:
		return HttpResponse("Invalid action", status=400)
	resp = JsonResponse({"ok": True})
	resp["HX-Trigger"] = json.dumps({
		"closeModal": {},      
		"reloadOngoingList": {} 
	})	
	resp["HX-Toast"] = toast_msg
	return resp

@login_required(login_url='login')
def contract_alerts(request, contract_id):
    alerts = Alert.objects.filter(contract_id=contract_id).order_by("-triggered_at")
    contract = Contract.objects.get(pk=contract_id)

    return render(request, "dashboard/alerts.html", {
        "alerts": alerts,
        "contract": contract
    })

@login_required
def ajax_latest_iot(request, contract_id):
    contract = get_object_or_404(Contract, pk=contract_id)
    device = contract.IoT_Assigned
    temp = None
    timestamp = None

    if device:
        latest = IoTData.objects.filter(device=device).order_by("-created_at").first()
        if latest:
            temp = latest.temperature
            timestamp = latest.created_at

    return render(request, "dashboard/partials/iot_box.html", {
        "contract": contract,
        "device": device,
        "temp": temp,
        "timestamp": timestamp
    })

