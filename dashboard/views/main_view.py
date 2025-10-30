import os
import json 
import random 
import math
from datetime import datetime
import time
import urllib.request
import threading

from Adafruit_IO import Client 
from Adafruit_IO import RequestError, AdafruitIOError
from dotenv import load_dotenv 
from eth_account import Account 
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.platypus import KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from solcx import compile_source, install_solc, set_solc_version
from web3 import Web3
from web3.exceptions import ContractLogicError

from django.core.cache import cache
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone 
from django.http import HttpResponseRedirect, HttpResponse, Http404, JsonResponse, StreamingHttpResponse
from django.urls import reverse
from django.db import models
from django.db.models import Avg, Min, Max, Q
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from accounts.models import CustomUser
from dashboard.models import Contract, IoTDevice, IoTDataHistory, Alert, IoTData, Product
from dashboard.forms import ProductForm
from .contract_functions import activate_contract 

load_dotenv()

install_solc('0.5.16')
set_solc_version('0.5.16')

SEPOLIA_URL = os.getenv("SEPOLIA_RPC_URL")
DEPLOYER_PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")
web3 = Web3(Web3.HTTPProvider(SEPOLIA_URL))

ADAFRUIT_IO_USERNAME = os.getenv("ADAFRUIT_IO_USERNAME")
ADAFRUIT_IO_KEY = os.getenv("ADAFRUIT_IO_KEY")
aio = Client(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)
SUPABASE_URL = os.getenv("SUPA_REST")
SUPABASE_KEY = os.getenv("SUPA_SERVICE_KEY")

TEMP_FEED = 'text-feed'
TEMP_THRESHOLD = 20.0       
THRESHOLD_DURATION = 300    
DELIVERY_THRESHOLD_KM = 0.010 
DELIVERY_COOLDOWN_SECONDS = 180

SUPABASE_IOTDATA_URL = f"{SUPABASE_URL}/rest/v1/iot_data"
SUPABASE_HEADERS = {
	"apikey": SUPABASE_KEY,
	"Authorization": f"Bearer {SUPABASE_KEY}",
	"Content-Type": "application/json",
	"Prefer": "return=minimal"
}


def push_iot_to_supabase(temperature=None, battery_voltage=None, gps_lat=None, gps_long=None, device_id=1):
	payload = {
		"device_id": device_id,
		"temperature": temperature,
		"battery_voltage": battery_voltage,
		"gps_lat": gps_lat,
		"gps_long": gps_long,
		"recorded_at": datetime.utcnow().isoformat(),
	}

	try:
		data = json.dumps(payload).encode("utf-8")
		req = urllib.request.Request(SUPABASE_IOTDATA_URL, data=data, headers=SUPABASE_HEADERS, method="POST")
		with urllib.request.urlopen(req) as resp:
			if resp.status in (200, 201, 204):
				print(f"Iot shunt {payload}")
			else:
				print(f"Supabase error {resp.status}: {resp.read().decode()}")
	except Exception as e:
		print("Failed to push IoT data to Supabase:", e)
		
def async_push_iot_to_supabase(**kwargs):
	def _runner():
		print(f"async shunt, iot: {kwargs}")
		try:
			push_iot_to_supabase(**kwargs)
		except Exception as e:
			print("async failed ", e)
	t = threading.Thread(target=_runner, daemon=True)
	t.start()
		
		
def get_products_by_seller(request, seller_id):
	if request.method != 'GET':
		return JsonResponse({'error': 'Invalid method.'}, status=405)
		
	try:
		products = Product.objects.filter(seller__pk=seller_id, quantity_available__gt=0)
		
		product_list = list(products.values(
			'product_id', 
			'product_name', 
			'price_eth', 
			'max_temp', 
			'quantity_available'
		))
		
		return JsonResponse({'products': product_list})
		
	except Exception as e:
		print(f"Error fetching products for seller {seller_id}: {e}")
		return JsonResponse({'error': 'Could not retrieve products.'}, status=500)
		
def haversine(lat1, lon1, lat2, lon2):
	R = 6371.0 
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
def get_latest_temperature(contract):

	if not hasattr(contract, 'IoT_Assigned') or not contract.IoT_Assigned:
		return 'N/A'
	
	device_id = contract.IoT_Assigned.device_id
	
	try:
		latest_data = IoTData.objects.filter(
			device_id=device_id
		).order_by('-recorded_at').only('temperature').first()
		
		if latest_data and latest_data.temperature is not None:
			return f"{latest_data.temperature:.1f}"
		
		return 'No Data'
		
	except Exception as e:
		print(f"Error fetching temperature for device {device_id}: {e}")
		return 'Error'
		
def stream_contract_temperature(request, contract_id):
	def event_stream():
		last_sent = {
			"temperature": None,
			"battery_voltage": None,
			"gps_lat": None,
			"gps_long": None,
		}

		while True:
			try:
				contract = Contract.objects.filter(pk=contract_id).select_related('IoT_Assigned').first()
				if not contract or not contract.IoT_Assigned:
					yield f"data: {json.dumps({'temperature': None})}\n\n"
					time.sleep(1.5)
					continue

				device = contract.IoT_Assigned

				live_temp = fetch_adafruit_temp_for_live_display()

				latest_iot = IoTData.objects.filter(device=device).order_by('-recorded_at').first()
				battery = latest_iot.battery_voltage if latest_iot else None
				#gps_lat = latest_iot.gps_lat if latest_iot else None
				#gps_long = latest_iot.gps_long if latest_iot else None
				gps_lat = aio.receive('gps-feed').lat
				gps_long = aio.receive('gps-feed').lon

				temperature = live_temp if live_temp is not None else (
					latest_iot.temperature if latest_iot else None
				)

				current_data = {
					"temperature": temperature,
					"battery_voltage": battery,
					"gps_lat": gps_lat,
					"gps_long": gps_long,
				}

				if any(current_data[k] != last_sent.get(k) for k in current_data) and temperature is not None:
					try:
						async_push_iot_to_supabase(
							temperature=temperature,
							battery_voltage=battery,
							gps_lat=gps_lat,
							gps_long=gps_long,
							device_id=1,
						)
						last_sent = current_data.copy()
						print(f"Update for {contract_id} with live temp {temperature:.2f}°C")
					except Exception as e:
						print(f"Shunt failed for contract {contract_id}: {e}")

				yield f"data: {json.dumps({'temperature': temperature})}\n\n"
				time.sleep(1.5)

			except GeneratorExit:
				break
			except Exception as e:
				print(f"SSE error for contract {contract_id}: {e}")
				yield f"data: {json.dumps({'temperature': None})}\n\n"
				time.sleep(5)

	response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
	response["Cache-Control"] = "no-cache"
	return response

				
def _get_live_iot_data():
  
	if aio is None:
		print("AIO Client not initialized. Returning mock data.")
		return -100.0, "N/A", "bg-secondary" 

	try:
		temp_str = aio.receive(TEMP_FEED).value
		temperature = float(temp_str)
		temperature_str = f"{temperature:.1f}°C"

		if temperature > TEMP_THRESHOLD:
			status_class = "status-warning"
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
	current_temp_mock = IoTData.objects.latest('recorded_at').temperature
	return f"{current_temp_mock:.1f}°C", current_temp_mock


def dashboard_data(request):
	user = request.user
	user_role = request.session.get("user_role", "").lower()
	user_id = request.session.get("user_id")
	# Filter contracts based on user role
	if user_role.lower() == "buyer":
		contracts = Contract.objects.filter(buyer_id=user_id)
	elif user_role.lower() == "seller":
		contracts = Contract.objects.filter(seller_id=user_id)
	else:
		contracts = Contract.objects.all()

	# Contract stats
	total_contracts = contracts.count()
	active_contracts = contracts.filter(status__in=["Active", "Ongoing", "In Transit"]).count()
	ongoing_contracts = contracts.filter(status__in=["In Transit", "Ongoing"]).count()
	completed_contracts = contracts.filter(status__in=["Completed", "Delivered"]).count()

	# 🌡️ IoT Data (real-time readings)
	devices = IoTDevice.objects.filter(contract__in=contracts)
	iot_data = IoTData.objects.filter(device__in=devices)

	avg_temp = iot_data.aggregate(avg=Avg("temperature"))["avg"] or 0
	total_records = iot_data.count()

	# Optional: define “Normal” temperature range (e.g., 2°C to 8°C)
	normal_records = iot_data.filter(temperature__range=(2, 8)).count()
	success_rate = round((normal_records / total_records) * 100, 1) if total_records > 0 else 0

	# 🚨 Alerts
	active_alerts = Alert.objects.filter(device__in=devices, status="Active").count()
	system_status = "All sensors online" if active_alerts == 0 else "Issues detected"
	status_color = "bg-success" if active_alerts == 0 else "bg-danger"


	# 📈 Chart data (latest 10 readings)
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


		
@login_required(login_url='login')
def active_view(request):
	try:
		# Most common filter: 'role' field exists and value is 'seller' (case-insensitive)
		sellers = CustomUser.objects.filter(
			role__iexact='seller'
		).exclude(
			pk=request.user.pk
		)
		
		# ADDED PRINT STATEMENT FOR DEBUGGING
		print(f"DEBUG: Sellers found with role__iexact='seller': {sellers.count()}")
		
	except Exception as e:
		# This catches an error if the 'role' field is named something else.
		print(f"CRITICAL ERROR: Failed to query CustomUser roles. Check CustomUser model. Error: {e}")
		sellers = CustomUser.objects.none() # Fallback to an empty queryset
		
	# --- END OF REPLACEMENT BLOCK ---

	user_role = getattr(request.user, 'role', '').lower()
	print(request.session.get("user_PK"))
	print(request.session.get("m_address"))

	if user_role == "buyer":
	 contracts_base_query = Contract.objects.filter(buyer_address=request.user.m_address)
	 print('buyer')
	elif user_role == "seller":
	 contracts_base_query = Contract.objects.filter(seller_address=request.user.m_address)
	 print('seller')

	# 2. Status Filter: Only show contracts for the 'Active' tab.
	# Includes 'Pending' (activatable), 'Active', 'Ongoing', and 'In Transit'.
	contracts_queryset = contracts_base_query.filter(
		status__in=['Pending', 'Active', 'Ongoing', 'In Transit']
	).order_by('-start_date')
	try:
	 sellers = CustomUser.objects.filter(
	   role__iexact='seller'
	 ).exclude(
	   pk=request.user.pk
	 )
	except Exception as e:
	# Print error if the 'role' field does not exist on CustomUser
	  print(f"ERROR fetching sellers: {e}")
	  sellers = []
	
	# Add this print statement back to verify the query result
	print(f"Contracts Queryset Count: {contracts_queryset.count()}") 

	# 3. Assemble Context Data (simplified for clarity)
	active_contracts = []
	for contract_instance in contracts_queryset:
		# Check if buyer/seller fields are populated before accessing full_name
		buyer_name = getattr(contract_instance.buyer, 'full_name', contract_instance.buyer_address)
		seller_name = getattr(contract_instance.seller, 'full_name', contract_instance.seller_address)

		status = contract_instance.status
		status_class = 'warning' if status == 'Pending' else 'info'
		
		# Mock temperature for display
		temp_threshold_float = getattr(contract_instance, 'max_temp', 8.0)
		current_temp_str, _ = _get_current_temp(temp_threshold_float) 

		active_contracts.append({
			'contract': contract_instance, # Contains .pk, .product_name, .quantity
			'buyer_name': buyer_name,
			'seller_name': seller_name,
			'current_temp': current_temp_str, 
			'status': status,
			'status_class': status_class,
		})
	
	# 4. IoT Device Filter
	ready_iot_devices = IoTDevice.objects.filter(status='Available')
	
	context = {
		'contracts': active_contracts,
		'role': user_role,
		'iot_available': ready_iot_devices.exists(),
		'ready_iot_devices': ready_iot_devices,
		"sellers": sellers,
		'current_user': request.user,
		"iot_devices": ready_iot_devices,
	}
	
	# Add this print statement back to check the final context
	print(f"Final Context: {context['contracts'][:1]}") 
	
	return render(request, 'dashboard/active.html', context)


@csrf_exempt
@require_POST
@login_required(login_url='login')
def activate_contract_view(request, contract_id):
	iot_device_id = request.POST.get('iot_device_select') 
	
	# 2. Perform Database Linkage
	if iot_device_id:
		try:
			# Fetch the Contract and the IoTDevice objects
			contract_db = Contract.objects.get(pk=contract_id)
			iot_device = IoTDevice.objects.get(pk=iot_device_id)

			# Link the contract to the device (assuming the field is IoT_Assigned)
			contract_db.IoT_Assigned = iot_device 
			contract_db.save()
			
			messages.info(request, f"Contract {contract_id} linked to device {iot_device.device_name}.")

		except Contract.DoesNotExist:
			messages.error(request, "Error: Contract not found for IoT linkage.")
		except IoTDevice.DoesNotExist:
			messages.error(request, "Error: Selected IoT device not found.")
		except Exception as e:
			# Handle any other database errors without stopping the Web3 call
			messages.warning(request, f"Warning: Database linkage failed: {e}. Attempting contract activation...")
	else:
		# This occurs if the user didn't select a device (or there were no devices)
		messages.warning(request, "No IoT device was selected or available. Proceeding with contract activation only.")

		
	# 3. Call the core Web3 activation logic
	# This function takes only (request, contract_id) as confirmed by you.
	return activate_contract(request, contract_id)    
	

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

def fetch_adafruit_temp_for_live_display():
	cached = cache.get("adafruit_temp")
	if cached: 
		return cached
	try:
		latest = aio.receive(TEMP_FEED)
		val = float(latest.value)
		cache.set("adafruit_temp", val, timeout=5)
		return val
	
	except RequestError as e:
		# This catches errors like 'Feed not found' or 'No data' (404/204 status codes)
		print(f"adafruit IO Request Error (Check TEMP_FEED name/data): {e}")
		return None
	except AdafruitIO_Errors as e:
		# This is often an authentication error (401 Unauthorized)
		print(f"adafruit IO auth error (Check USERNAME/KEY): {e}")
		return None
	except Exception as e:
		print("Adafruit error:", e)
		return cached
		
@login_required(login_url='login')
def ongoing_view(request):
	user = request.user
	user_role = request.session.get("user_role", "").capitalize()

	# Filter contracts by status + role
	contracts = Contract.objects.filter(status__in=['Ongoing', 'Alert']).order_by('-start_date')
	if user_role == "Buyer":
		contracts = contracts.filter(buyer_address=user.m_address)
	elif user_role == "Seller":
		contracts = contracts.filter(seller_address=user.m_address)

	live_temp = fetch_adafruit_temp_for_live_display()
	if live_temp is not None:
		print(f"latest Temperature: {live_temp:.2f} °C")
	else:
		print(f"Could not retrieve live temperature from Adafruit IO.")

	ongoing_data = []
	for contract in contracts:
		device = contract.IoT_Assigned  
		gps_lat = gps_lon = None
		current_temp = "N/A"

		if device:
			latest_data = IoTData.objects.filter(device=device).order_by('-recorded_at').first()
			if latest_data:
				current_temp = latest_data.temperature if latest_data.temperature is not None else "N/A"
				gps_lat = latest_data.gps_lat
				gps_lon = latest_data.gps_long
				print(f"Contract {contract.contract_id}: GPS=({gps_lat}, {gps_lon})")
			else:
				print(f"Contract {contract.contract_id}: No IoTData found for device {device.device_name}")
		else:
			print(f"Contract {contract.contract_id}: No IoT_Assigned linked")

		ongoing_data.append({
			"contract_id": contract.contract_id,
			"product_name": contract.product_name,
			"status": contract.status,
			"max_temp": contract.max_temp,
			"buyer_address": contract.buyer_address,
			"seller_address": contract.seller_address,
			"current_temp": current_temp,
			"gps_lat": gps_lat,
			"gps_long": gps_lon,
			"current_location": (
				f"{gps_lat:.4f}, {gps_lon:.4f}"
				if (gps_lat is not None and gps_lon is not None)
				else "N/A"
			),
		})

	context = {
		"ongoing_data": ongoing_data,
		"role": user_role,
	}

	return render(request, "dashboard/ongoing.html", context)
	
@login_required(login_url='login')
def ongoing_data_json(request):
	user = request.user
	user_role = user.role.lower()

	if user_role == "buyer":
		contracts = Contract.objects.filter(buyer=user, status__in=["Ongoing", "In Transit"])
	elif user_role == "seller":
		contracts = Contract.objects.filter(seller=user, status__in=["Ongoing", "In Transit"])
	else:  # admin
		contracts = Contract.objects.filter(status__in=["Ongoing", "In Transit"])

	live_temp_float, live_temp_str, _ = _get_live_iot_data()
	
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
			"buyer_address": contract.buyer_address,
			"seller_address": contract.seller_address,
			#"buyer_name": contract.buyer. if hasattr(contract.buyer, 'full_name') else "—",
		   # "seller_name": contract.seller.full_name if hasattr(contract.seller, 'full_name') else "—",
		})

	return JsonResponse({"ongoing_data": ongoing_data_list})

@login_required(login_url='login')
def shipment_details_view(request, contract_id):
	try:
		contract = Contract.objects.select_related('buyer', 'seller').get(contract_id=contract_id)
	except Contract.DoesNotExist:
		raise Http404("Shipment not found")

	device = IoTDevice.objects.filter(contract_id=contract_id).first()
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

@login_required(login_url='login')
def completed_view(request):
    user = request.user
    user_role = request.session.get("user_role", "").lower()
    m_address = getattr(user, "m_address", None)

    try:
        if user_role == "buyer":
            contracts_queryset = Contract.objects.filter(
                buyer_address=m_address,
                status__in=['Completed', 'Refunded']
            ).order_by('-end_date', '-start_date')
        elif user_role == "seller":
            contracts_queryset = Contract.objects.filter(
                seller_address=m_address,
                status__in=['Completed', 'Refunded']
            ).order_by('-end_date', '-start_date')
        else:
            contracts_queryset = Contract.objects.filter(
                status__in=['Completed', 'Refunded']
            ).order_by('-end_date', '-start_date')
    except Exception as e:
        print(f"[ERROR] Contract query failed: {e}")
        contracts_queryset = []

    completed_contracts = []
    for contract_instance in contracts_queryset:
        iot_summary = IoTDataHistory.objects.filter(contract=contract_instance).aggregate(
            avg_temp=Avg('avg_temp'),
            min_temp=Min('min_temp'),
            max_temp=Max('max_temp')
        )

        final_temp_str = (
            f"{iot_summary['avg_temp']:.1f}°C"
            if iot_summary['avg_temp'] is not None else "N/A"
        )

        refunded = contract_instance.status == 'Refunded'
        status = 'Refunded' if refunded else 'Complete'
        status_class = 'danger' if refunded else 'primary'

        completed_contracts.append({
            'contract': contract_instance,
            'buyer_name': getattr(contract_instance.buyer, 'full_name', 'N/A'),
            'seller_name': getattr(contract_instance.seller, 'full_name', 'N/A'),
            'current_temp': final_temp_str,
            'status': status,
            'status_class': status_class,
            'refunded': refunded,
        })

    return render(request, 'dashboard/completed.html', {'contracts': completed_contracts})


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
