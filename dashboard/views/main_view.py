from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone 
from django.core.cache import cache
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, Http404, JsonResponse

import json 
from datetime import datetime
from web3 import Web3

from dashboard.models import Contract, IoTDevice, IoTDataHistory, Alert, IoTData, Product
from accounts.models import CustomUser
from dashboard.forms import ProductForm

import os
from dotenv import load_dotenv # NEW
from eth_account import Account # NEW
from accounts.models import CustomUser
from web3.exceptions import ContractLogicError
load_dotenv() 
from Adafruit_IO import Client 
from Adafruit_IO import RequestError

import math

SEPOLIA_URL = os.getenv("SEPOLIA_RPC_URL")
DEPLOYER_PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")


# Solidity Code (SimpleTransfer Contract)


web3 = Web3(Web3.HTTPProvider(SEPOLIA_URL))

# Get the deployer account address from the private key
 # The address used for transactions
TEMP_FEED = 'text-feed'
TEMP_THRESHOLD = 20.0 	# Example threshold value (°C) - Kept from alpha.py for consistency
THRESHOLD_DURATION = 300 	# 5 minutes in seconds (5 * 60)

ADAFRUIT_IO_USERNAME = os.getenv("ADAFRUIT_IO_USERNAME")
ADAFRUIT_IO_KEY = os.getenv("ADAFRUIT_IO_KEY")

aio = Client(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)





DELIVERY_THRESHOLD_KM = 0.010 # Distance threshold to mark destination reached
DELIVERY_COOLDOWN_SECONDS = 180 # 3 minutes (3 * 60)

def haversine(lat1, lon1, lat2, lon2):
    """Calculates the distance between two points on Earth in kilometers."""
    R = 6371.0 # Radius of Earth in kilometers
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def _check_delivery_status(contract_db):
    """Checks GPS progress and updates contract status if delivered."""
    if contract_db.status not in ['Ongoing', 'In Transit']:
        return 0.0, contract_db.status
    
    # 1. Parse Coords (Check for missing data)
    try:
        s_lat, s_lon = map(float, contract_db.start_coord.split(','))
        e_lat, e_lon = map(float, contract_db.end_coord.split(','))
    except (AttributeError, ValueError):
        return 0.0, "Coords Missing"
        
    # 2. Get Latest GPS Data
    try:
        # Assuming the contract is linked to one device (Device ID 1 is a common placeholder)
        latest_data = IoTData.objects.filter(device_id=1).latest('recorded_at')
        current_lat = latest_data.gps_lat
        current_lon = latest_data.gps_long
        
        if current_lat is None or current_lon is None:
             return 0.0, "Tracking N/A"
        
    except IoTData.DoesNotExist:
        return 0.0, "No GPS Data"
        
    # 3. Calculate Progress
    total_route_distance_km = haversine(s_lat, s_lon, e_lat, e_lon)
    remaining_distance_km = haversine(current_lat, current_lon, e_lat, e_lon)
    distance_covered_km = haversine(s_lat, s_lon, current_lat, current_lon)

    if total_route_distance_km <= 0.01:
        progress_percent = 100.0
    else:
        progress_ratio = min(distance_covered_km / total_route_distance_km, 1.0)
        progress_percent = progress_ratio * 100
    
    # 4. Check for Delivery Completion (100% and 3 minutes elapsed)
    if remaining_distance_km < DELIVERY_THRESHOLD_KM:
        # Check if 3 minutes have passed since the contract was activated
        if (timezone.now() - contract_db.start_date).total_seconds() >= DELIVERY_COOLDOWN_SECONDS:
            
            # Update status to Delivered
            if contract_db.status != 'Completed':
                contract_db.status = 'Completed'
                contract_db.end_date = timezone.now()
                contract_db.save()
                print(f"Contract {contract_db.contract_id}: Completed!") # Required console print
            
            return 100.0, "Completed"

    # Return progress percentage and status string
    return progress_percent, f"{progress_percent:.0f}%"

def _get_live_iot_data():
  
    if aio is None:
        print("AIO Client not initialized. Returning mock data.")
        # Fallback/Mock data if AIO setup failed
        return -100.0, "N/A", "bg-secondary" 

    try:
        # Fetch the latest value from the temperature feed
        temp_str = aio.receive(TEMP_FEED).value
        temperature = float(temp_str)
        temperature_str = f"{temperature:.1f}°C"

        if temperature > TEMP_THRESHOLD:
            status_class = "status-warning" # A custom class, maybe 'bg-warning' in Bootstrap
        else:
            status_class = "status-normal"
            
        return temperature, temperature_str, status_class
        
    except RequestError as e:
        print(f"Error fetching Temperature feed from Adafruit IO: {e}")
    except ValueError:
        print("Invalid temperature value received from feed.")
    except Exception as e:
        print(f"An unexpected error occurred during IoT data fetch: {e}")
    
    # Return default/error values
    return -100.0, "N/A", "bg-secondary"


def _get_current_temp(threshold_float):
    """Mocks a live temperature reading based on the threshold."""
    current_temp_mock = IoTData.objects.latest('recorded_at').temperature
    return f"{current_temp_mock:.1f}°C", current_temp_mock


def dashboard_data(request):
    """Return optimized dashboard metrics as JSON."""

    user = request.user
    user_role = request.session.get("user_role", "").lower()
    user_id = request.session.get("user_id")

    # --- CACHE LAYER (30 seconds to reduce load) ---
    cache_key = f"dashboard_stats_{user_role}_{user_id}"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    # --- Base Query ---
    base_filter = {}
    if user_role == "buyer":
        base_filter["buyer_id"] = user_id
    elif user_role == "seller":
        base_filter["seller_id"] = user_id

    # Preload buyer/seller to prevent extra queries
    contracts = (
        Contract.objects.filter(**base_filter)
        .select_related("buyer", "seller")
        .defer("contract_abi")  # avoid loading large JSON field
    )

    # --- Contract Stats (1 aggregate query instead of 4 counts) ---
    stats = contracts.aggregate(
        total=Count("contract_id"),
        active=Count("contract_id", filter=Q(status__in=["Active", "Ongoing", "In Transit"])),
        ongoing=Count("contract_id", filter=Q(status__in=["In Transit", "Ongoing"])),
        completed=Count("contract_id", filter=Q(status__in=["Completed", "Delivered"]))
    )
    total_contracts = stats.get("total", 0)
    active_contracts = stats.get("active", 0)
    ongoing_contracts = stats.get("ongoing", 0)
    completed_contracts = stats.get("completed", 0)

    # --- IoT and Alerts Stats ---
    avg_temp = (
        IoTDataHistory.objects.filter(contract__in=contracts)
        .aggregate(avg=Avg("avg_temp"))
        .get("avg") or 0
    )

    total_records = IoTDataHistory.objects.filter(contract__in=contracts).count()
    normal_records = IoTDataHistory.objects.filter(contract__in=contracts, result="Normal").count()
    success_rate = round((normal_records / total_records) * 100, 1) if total_records else 0

    active_alerts = Alert.objects.filter(
        device__contract__in=contracts, status="Active"
    ).count()

    system_status = "All sensors online" if active_alerts == 0 else "Issues detected"
    status_color = "bg-success" if active_alerts == 0 else "bg-danger"

    # --- Temperature History (latest 10 readings) ---
    temp_history_qs = (
        IoTDataHistory.objects.filter(contract__in=contracts)
        .order_by("-recorded_at")[:10]
    )
    temp_history = list(temp_history_qs.values_list("recorded_at", "avg_temp"))
    chart_labels = [t[0].strftime("%H:%M") for t in reversed(temp_history)]
    chart_values = [t[1] for t in reversed(temp_history)]

    # --- Prepare response ---
    result = {
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
    }

    cache.set(cache_key, result, 30)  # cache for 30 seconds
    return JsonResponse(result)



@login_required(login_url='login')
def overview_view(request):
    user = request.user  # The currently logged-in user

    # 🧠 Determine the user role (Buyer/Seller/Admin)
    user_role = request.session.get("user_role", "").lower()


    # 🧩 Filter contracts based on user role
    if user_role.lower() == "buyer":
        contracts = Contract.objects.filter(buyer=user)
    elif user_role.lower() == "seller":
        contracts = Contract.objects.filter(seller=user)
    else:  # Admin sees all
        contracts = Contract.objects.all()

    # 📊 Count stats
    total_contracts = contracts.count()
    active_contracts = contracts.filter(status__in=["Active", "Ongoing", "In Transit"]).count()
    completed_contracts = contracts.filter(status__in=["Completed", "Delivered"]).count()

    # --- IOT DATA METRICS ---
    iot_data = IoTDataHistory.objects.filter(contract__in=contracts)
    avg_temp = iot_data.aggregate(avg=Avg("avg_temp"))["avg"] or 0

    total_records = iot_data.count()
    normal_records = iot_data.filter(result="Normal").count()
    success_rate = round((normal_records / total_records) * 100, 1) if total_records > 0 else 0

    # --- ALERTS ---
    alerts = Alert.objects.filter(device__contract__in=contracts)
    active_alerts = alerts.filter(status="Active")
    active_alert_count = active_alerts.count()

    # Active sensors (linked to active contracts)
    active_sensors = (
        IoTDevice.objects
        .filter(contract__in=contracts.filter(status__in=["Active","Ongoing", "In Transit"]))
        .select_related("contract")
    )

    # Recent temperature readings for chart
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

def get_products_by_seller(request, seller_id):
    """
    Fetches products associated with a specific seller ID and returns JSON.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid method.'}, status=405)
        
    try:
        # Query products where the foreign key 'seller' matches the seller_id (pk)
        products = Product.objects.filter(seller__pk=seller_id, quantity_available__gt=0)
        
        # Serialize the products into a list of dictionaries for JSON response
        product_list = list(products.values(
            'product_id', 
            'product_name', 
            'price_eth', 
            'max_temp', 
            'quantity_available'
        ))
        
        return JsonResponse({'products': product_list})
        
    except Exception as e:
        # It's helpful to log the error to the console for debugging
        print(f"Error fetching products for seller {seller_id}: {e}")
        return JsonResponse({'error': 'Could not retrieve products.'}, status=500)
        
@login_required(login_url='login')
def active_view(request):
    sellers = CustomUser.objects.filter(role__iexact='seller')
    user_role = request.user.role.lower() 
    print ( request.session.get('m_address'))
    deployer_user = None
    try:
        # Fetch the Deployer who is the user with ID 10
        deployer_user = CustomUser.objects.get(pk=10) 
    except CustomUser.DoesNotExist:
        # Fallback if user 10 is deleted, providing essential address information
        deployer_user = type('Deployer', (object,), {
            'organization': 'System Deployer (User Not Found)',
            'm_address': '0x00...DeployerAddress...00' # Placeholder or use an environment variable if available
        })
    except Exception as e:
         print(f"Error fetching Deployer (ID 10): {e}")    
    if request.user.role.lower() == "seller":
      print("seller")
    if request.user.role.lower() == "buyer":
      print("buyer")
    
    # --- Live Data Fetch from Supabase via Django ORM ---
    try:
        contracts_queryset = Contract.objects.filter(status__in=['Active', 'Ongoing', 'In Transit', 'Pending']).all() 
        # Added 'Pending' contracts to queryset to show contracts waiting for activation
    except Exception as e:
        print(f"Database query error: {e}")
        contracts_queryset = []

    active_contracts = []
    
    for contract_instance in contracts_queryset:
        
        # 1. Get the temperature threshold (now a FloatField from the DB)
        temp_threshold_float = contract_instance.max_temp
        
        # 2. Get/Mock the current temperature
        current_temp_str, current_temp_float = _get_current_temp(temp_threshold_float) # Assuming _get_current_temp exists
        
        # 3. Determine status
        status = contract_instance.status
        status_class = 'primary' # Default color
        
        if status == 'Pending':
            # Pending status should not trigger temperature check
            status_class = 'warning'
        elif status in ['Ongoing', 'In Transit', 'Active']:
            status_class = 'info'
            # Only check temperature deviation for actively tracked contracts
            if current_temp_float > temp_threshold_float:
                status = 'Temp Alert' # Changed from 'Alert' to 'Temp Alert' for clarity
                status_class = 'danger' # Use danger for temp alert
        else:
             # Fallback for any other 'active' state not explicitly handled
             status_class = 'secondary'
        
        # 4. Assemble final data object
        buyer_name = contract_instance.buyer.full_name if contract_instance.buyer and contract_instance.buyer.full_name else contract_instance.buyer_address
        seller_name = contract_instance.seller.full_name if contract_instance.seller and contract_instance.seller.full_name else contract_instance.seller_address
        active_contracts.append({
            'contract': contract_instance,
            
            # Use the derived names (which fall back to addresses)
            'buyer_name': buyer_name,
            'seller_name': seller_name,
   
            'current_temp': current_temp_str, 
            'status': status,
            'status_class': status_class,
        })
    
    # --- NEW LOGIC: Fetch products if user is a Buyer ---
    products = []
    if user_role.lower() == "buyer":
        try:
            # Assuming the Product model is imported correctly (from dashboard.models import Product)
            products = Product.objects.all()
        except Exception as e:
            print(f"Error fetching products: {e}")

    sellers = []
    if user_role.lower() == "buyer":
        try:
            # Fetch all users whose role is 'Seller'
            sellers = CustomUser.objects.filter(role__iexact='seller') 
        except Exception as e:
            print(f"Error fetching sellers: {e}")

    context = {
        'contracts': active_contracts,
        'role': user_role,
        'current_user': request.user,
        'sellers': sellers,
        'deployer_user': deployer_user,
    }
    return render(request, 'dashboard/active.html', context)


    
    

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
            messages.success(request, "✅ Product added successfully.")
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
            messages.success(request, "✅ Product updated successfully.")
            return redirect("product_manager")
    else:
        form = ProductForm(instance=product)
    return render(request, "dashboard/products/product_form.html", {"form": form, "title": "Edit Product"})


@login_required(login_url='login')
def product_delete_view(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    product.delete()
    messages.success(request, "🗑️ Product deleted successfully.")
    return redirect("product_manager")

    
@login_required(login_url='login')
def ongoing_view(request):
    user = request.user
    user_role = request.session.get("user_role", "").capitalize()
    
    contracts = Contract.objects.filter(status__in=['Ongoing', 'Alert']).order_by('-start_date')
    
    if user_role == "Buyer":
        contracts = contracts.filter(buyer_address=user.m_address)
    elif user_role == "Seller":
        contracts = contracts.filter(seller_address=user.m_address)

    ongoing_data = []
    for contract in contracts:
        
        # 💡 FIX: Query the IoTDevice linked to the Contract
        try:
            device = IoTDevice.objects.get(contract=contract)
        except IoTDevice.DoesNotExist:
            current_temp = 'N/A (No Device)'
        else:
            # 💡 CORRECT QUERY: Filter IoTData using the Device object
            latest_data = IoTData.objects.filter(device=device).order_by('-recorded_at').first()
            current_temp = latest_data.temperature if latest_data else 'N/A'

        ongoing_data.append({
            'contract_id': contract.contract_id,
            'product_name': contract.product_name,
            # ... other contract fields
            'status': contract.status,
            'max_temp': contract.max_temp,
            'current_temp': current_temp, # Now correctly populated
        })

    context = {
        "ongoing_data": ongoing_data,
        "role": user_role
    }

    return render(request, 'dashboard/ongoing.html', context)
@login_required(login_url='login')
def ongoing_data_json(request):
    user = request.user
    user_role = user.role.lower()

    # 1. Filter contracts based on role (already correct)
    if user_role == "buyer":
        contracts = Contract.objects.filter(buyer=user, status__in=["Ongoing", "In Transit"])
    elif user_role == "seller":
        contracts = Contract.objects.filter(seller=user, status__in=["Ongoing", "In Transit"])
    else:  # admin
        contracts = Contract.objects.filter(status__in=["Ongoing", "In Transit"])

    # --- NEW: Fetch Live Adafruit IO Data ONCE ---
    live_temp_float, live_temp_str, _ = _get_live_iot_data()
    
    # 2. Determine temperature display (use "N/A" if the fetch failed)
    temperature_display = live_temp_str if live_temp_float != -100.0 else "N/A"
        

    # 3. Build the JSON response data
    ongoing_data_list = []
    
    for contract in contracts:
        ongoing_data_list.append({
            "contract_id": contract.contract_id,
            "product_name": contract.product_name,
            # CRITICAL FIX: Use the live temperature string from Adafruit IO
            "temperature": temperature_display, 
            "status": contract.status,
            "min_temp": contract.min_temp,
            "max_temp": contract.max_temp,
            "buyer_name": contract.buyer.full_name if hasattr(contract.buyer, 'full_name') else "—",
            "seller_name": contract.seller.full_name if hasattr(contract.seller, 'full_name') else "—",
        })

    return JsonResponse({"ongoing_data": ongoing_data_list})

@login_required(login_url='login')
def shipment_details_view(request, contract_id):
    """
    Returns JSON details about a specific shipment (contract) for the modal.
    """
    try:
        contract = Contract.objects.select_related('buyer', 'seller').get(contract_id=contract_id)
    except Contract.DoesNotExist:
        raise Http404("Shipment not found")

    # 🧠 Get latest IoT data linked to this contract
    device = IoTDevice.objects.filter(contract_id=contract_id).first()
    latest_iot = IoTData.objects.filter(device_id=device.device_id).order_by('-recorded_at').first()

    # ✅ Structure data for JSON response
    data = {
        "contract_id": contract.contract_id,
        "product_name": contract.product_name,
        "quantity": contract.quantity,
        "price": float(contract.price) if contract.price else None,
        "status": contract.status,
        "contract_address": contract.contract_address,
        "deployment_date": contract.start_date.strftime("%Y-%m-%d %H:%M:%S") if contract.start_date else "N/A",

        # 🧾 Parties
        "buyer_name": contract.buyer.full_name if hasattr(contract.buyer, 'full_name') else contract.buyer.username,
        "buyer_email": contract.buyer.email,
        "buyer_wallet": getattr(contract.buyer, 'm_address', 'N/A'),
        "seller_name": contract.seller.full_name if hasattr(contract.seller, 'full_name') else contract.seller.username,
        "seller_email": contract.seller.email,
        "seller_wallet": getattr(contract.seller, 'm_address', 'N/A'),

        # 🌡 IoT Data Summary
        "latest_temp": latest_iot.temperature if latest_iot else "N/A",
        # "min_temp": latest_iot.min_temp if latest_iot else "N/A",
        # "max_temp": latest_iot.max_temp if latest_iot else "N/A",
        "battery_voltage": latest_iot.battery_voltage if latest_iot else "N/A",
        "recorded_at": latest_iot.recorded_at.strftime("%Y-%m-%d %H:%M:%S") if latest_iot else "N/A",
    }

    return JsonResponse(data)

@login_required(login_url='login')
@require_POST
def complete_shipment(request, contract_id):
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            # Should not happen with the provided JS, but for robustness
            return JsonResponse({'status': 'error', 'message': 'Invalid Content-Type'}, status=400)

        # 1. Fetch Contract from DB
        contract_db = Contract.objects.get(contract_id=contract_id)
        
        # Security Check: Only the buyer should finalize the contract
        user_role = request.user.role.lower()
        if user_role != 'buyer':
             return JsonResponse({'status': 'error', 'message': 'Permission denied. Only the Buyer can complete the contract.'}, status=403)
        
        # Get necessary info
        contract_address = contract_db.contract_address
        contract_abi = contract_db.contract_abi

        # 2. Web3 setup
        if not web3.is_connected():
            raise ConnectionError("Web3 provider not connected.")
        
        # Load the contract instance
        contract_instance = web3.eth.contract(address=contract_address, abi=contract_abi)
        
        # Load the account used to sign the transaction (The Buyer's account)
        buyer_wallet = request.user.eth_address
        buyer_private_key = request.user.eth_private_key
        buyer_account = Account.from_key(buyer_private_key)

        # 3. Build and sign the transaction to call the 'releasePayment' function
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 1. Calling releasePayment on contract {contract_address} from buyer {buyer_wallet}...")
        
        

        gas_estimate = contract_instance.functions.releasePayment().estimate_gas({'from': buyer_wallet})
        
        transaction = contract_instance.functions.releasePayment().build_transaction({
            'from': buyer_wallet,
            'nonce': web3.eth.get_transaction_count(buyer_wallet),
            'gas': gas_estimate + 10000, # Add buffer
            'gasPrice': web3.eth.gas_price
        })

        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=buyer_private_key)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 4. Sending signed transaction...")
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 5. Tx submitted. Hash: {tx_hash.hex()}")
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] -> Waiting for transaction receipt...")
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt.status == 1:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 6. SUCCESS: Payment released. Block: {receipt.blockNumber}")
        else:
            raise ContractLogicError(f"Transaction failed on-chain. Status: {receipt.status}")

        # 4. Update Django DB Status to 'Completed' (Assuming the current status is 'ongoing')
        contract_db.status = 'Completed'
        contract_db.end_date = timezone.now()
        contract_db.save()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 7. DATABASE UPDATE: Contract ID {contract_id} status updated to Completed.")

        return JsonResponse({'status': 'success', 'message': 'Payment released and contract completed.'})
    except Contract.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': f'Contract ID {contract_id} not found in database.'}, status=404)
    except ConnectionError:
        return JsonResponse({'status': 'error', 'message': 'Critical error: Web3 provider connection failed.'}, status=503)
    except ContractLogicError as e:
        # This captures a failure in the smart contract itself (e.g., require() statement failed)
        error_message = str(e).split("reason: '")[-1].split("'")[0] if "reason" in str(e) else "Smart contract transaction failed."
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Contract Logic Failed. Details: {error_message}")
        return JsonResponse({'status': 'error', 'message': f'Contract failed on the blockchain: {error_message}'}, status=400)
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] UNEXPECTED ERROR: {e}")
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500) 
    

@login_required(login_url='login')
def completed_view(request):
    user = request.user
    user_role = request.session.get("user_role", "").lower()
    user_id = request.session.get("user_id")

    try:
        # Filter contracts by role
        if user_role == "buyer":
            contracts_queryset = Contract.objects.filter(buyer_id=user_id, status__in=['Completed', 'Refunded'])
        elif user_role == "seller":
            contracts_queryset = Contract.objects.filter(seller_id=user_id, status__in=['Completed', 'Refunded'])
        else:  # Admin sees all
            contracts_queryset = Contract.objects.filter(status__in=['Completed', 'Refunded'])
    except Exception as e:
        print(f"Database query error: {e}")
        contracts_queryset = []

    completed_contracts = []
    
    for contract_instance in contracts_queryset:
        if contract_instance.status == 'Refunded':
            status = 'Refunded'
            status_class = 'danger'
        else:
            status = 'Complete'
            status_class = 'primary'
        temp_threshold_float = contract_instance.max_temp or 0
        # final_temp_str = f"{temp_threshold_float - 0.5:.1f}°C" 
        final_temp_str = f"{IoTData.objects.latest('recorded_at').temperature:.1f}°C"
        completed_contracts.append({
            'contract': contract_instance,
            'buyer_name': contract_instance.buyer.full_name if contract_instance.buyer else "N/A",
            'seller_name': contract_instance.seller.full_name if contract_instance.seller else "N/A",
            'current_temp': final_temp_str,
            'status': status,
            'status_class': status_class,
        })
    
    context = {
        'contracts': completed_contracts
    }
    
    return render(request, 'dashboard/completed.html', context)


@login_required(login_url='login')
def alerts_view(request):
    user = request.user
    user_role = request.session.get("user_role", "").lower()
    user_id = request.session.get("user_id")
    # Filter contracts based on user role
    if user_role == "buyer":
        contracts = Contract.objects.filter(buyer_id=user_id)
    elif user_role == "seller":
        contracts = Contract.objects.filter(seller_id=user_id)
    else:  # Admin sees all
        contracts = Contract.objects.all()

    # Get devices linked to those contracts
    devices = IoTDevice.objects.filter(contract__in=contracts)

    # Get alerts only from those devices
    alerts = Alert.objects.filter(device__in=devices).select_related('device').order_by('-triggered_at')

    context = {
        "alerts": alerts,
        "user_role": user_role
    }

    return render(request, "dashboard/alerts.html", context)

def analytics_view(request):
    return render(request, 'dashboard/analytics.html')

def download_license(request, user_id):
    try:
        user = CustomUser.objects.get(pk=user_id)
        if not user.business_license:
            raise Http404("No license uploaded")
        response = HttpResponse(user.business_license, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="license_{user_id}.pdf"'
        return response
    except CustomUser.DoesNotExist:
        raise Http404("User not found")
