from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone 
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.db import models
from django.db.models import Avg
import random 
import json 
import datetime
from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version
from dashboard.models import Contract, IoTDevice, IoTDataHistory, Alert, IoTData
from accounts.models import CustomUser
import os
from dotenv import load_dotenv # NEW
from eth_account import Account # NEW
from django.http import HttpResponse, Http404, JsonResponse
from accounts.models import CustomUser
from web3.exceptions import ContractLogicError
load_dotenv() 
from Adafruit_IO import Client 
from Adafruit_IO import RequestError



SEPOLIA_URL = os.getenv("SEPOLIA_RPC_URL")
DEPLOYER_PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")

# Make sure the version is installed
install_solc('0.5.16')

# Use Solidity 0.5.16 for compilation
set_solc_version('0.5.16')

# Solidity Code (SimpleTransfer Contract)
solidity_code = '''
pragma solidity 0.5.16;

contract SimpleTransfer {
event Transfer(address indexed from, address indexed to, uint256 value);

function Deposit(address payable _to) public payable {
require(msg.value > 0, "Must send some Ether");
_to.transfer(msg.value);
emit Transfer(msg.sender, _to, msg.value);
}

function Refund(address payable _to) public payable {
require(msg.value > 0, "Must send some Ether");
_to.transfer(msg.value);
emit Transfer(msg.sender, _to, msg.value);
}

}
'''

web3 = Web3(Web3.HTTPProvider(SEPOLIA_URL))

# Get the deployer account address from the private key
deployer_account = Account.from_key(DEPLOYER_PRIVATE_KEY)
DEPLOYER_ADDRESS = deployer_account.address # The address used for transactions
TEMP_FEED = 'text-feed'
TEMP_THRESHOLD = 20.0 	# Example threshold value (°C) - Kept from alpha.py for consistency
THRESHOLD_DURATION = 300 	# 5 minutes in seconds (5 * 60)


ADAFRUIT_IO_USERNAME = 'gabaguan'
ADAFRUIT_IO_KEY = 'aio_VLXh87gqjWUdvsuwvtm5QA8Hbeqf'

aio = Client(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)

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

def deploy_contract_and_save(BuyerAddress, SellerAddress, ProductName, PaymentAmount, Quantity):
    """
    Compiles, signs, and sends the deployment and initial Refund transactions 
    to the Sepolia testnet, then saves contract details using the Django ORM.
    """
    
    print("--- Starting Contract Deployment Process ---")
    
    # 1. Check Web3 Connection
    if not web3.is_connected():
        print("ERROR: Web3 not connected. Check RPC URL and network status.")
        raise ConnectionError("Could not connect to Sepolia RPC endpoint.")
    
    # 1. Compile and Deploy Contract (Web3 logic)
    compiled_sol = compile_source(solidity_code)
    contract_name, contract_interface = compiled_sol.popitem()
    abi = contract_interface['abi']
    bytecode = contract_interface['bin']
    SimpleTransfer = web3.eth.contract(abi=abi, bytecode=bytecode)
    
    # ------------------------------------------------------------------
    # 1. Prepare and Sign Contract Deployment Transaction
    # ------------------------------------------------------------------
    
    nonce = web3.eth.get_transaction_count(DEPLOYER_ADDRESS)
    print(f"1. Nonce for Deployment: {nonce}")

    # Build the constructor transaction
    construct_txn = SimpleTransfer.constructor().build_transaction({
        'chainId': web3.eth.chain_id,
        'from': DEPLOYER_ADDRESS,
        'nonce': nonce,
        'gasPrice': web3.eth.gas_price, 
        'gas':  65394 
    })
    
    # Sign the transaction locally with the private key
    signed_txn = web3.eth.account.sign_transaction(
        construct_txn, 
        private_key=DEPLOYER_PRIVATE_KEY
    )
    print("2. Contract deployment transaction signed.")
    
    # Send the signed transaction
    tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
    print(f"3. Deployment transaction sent. Hash: {tx_hash.hex()}")
    tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress
    print(f"4. Contract deployed successfully at: {contract_address}")
    
    # ------------------------------------------------------------------
    # 2. Prepare and Sign Initial Refund Transaction
    # ------------------------------------------------------------------
    contract = web3.eth.contract(address=contract_address, abi=abi)
    amount_eth = 0.05 
    amount_wei = web3.to_wei(amount_eth, 'ether')
    
    # Get the new nonce for the second transaction
    nonce = web3.eth.get_transaction_count(DEPLOYER_ADDRESS)
    print(f"5. Nonce for Refund: {nonce}")
    
    # Build the Refund function call
    refund_txn = contract.functions.Refund(SellerAddress).build_transaction({
        'chainId': web3.eth.chain_id,
        'from': DEPLOYER_ADDRESS,
        'nonce': nonce,
        'value': amount_wei,
        'gasPrice': web3.eth.gas_price,
        'gas':  65394
    })
    
    # Sign and send the second transaction
    signed_txn2 = web3.eth.account.sign_transaction(
        refund_txn, 
        private_key=DEPLOYER_PRIVATE_KEY
    )
    print("6. Refund transaction signed.")
    tx_hash2 = web3.eth.send_raw_transaction(signed_txn2.raw_transaction)
    print(f"7. Refund transaction sent. Hash: {tx_hash2.hex()}")

    web3.eth.wait_for_transaction_receipt(tx_hash2) 
    print("8. Refund transaction confirmed on chain.")

    # ------------------------------------------------------------------
    # 3. Save to Database using DJANGO ORM
    # ------------------------------------------------------------------
    MAX_INT_VALUE = 2147483647
    buyer_id_int = abs(hash(BuyerAddress)) % MAX_INT_VALUE
    seller_id_int = abs(hash(SellerAddress)) % MAX_INT_VALUE
    latest_iot_contract = IoTDevice.objects.aggregate(max_id=models.Max('contract_id'))['max_id']
    next_contract_id = (latest_iot_contract or 0) + 1
    print(f"10. Saving contract details to database (Attempting ID: {next_contract_id}).")
    
    new_contract = Contract.objects.create(
    contract_id=next_contract_id,
  
    buyer_address="0x13994f68615c9c578745339188cc165f4ef9959c",   # <-- CORRECT
    seller_address="0x1A947d2CfcF6a4EF915a4049077BfE9acc7Ddb0D", # <-- CORRECT 
    
    product_name=ProductName,
    quantity=Quantity, 
    price=PaymentAmount,
    start_date=timezone.now(),
    end_date=timezone.now() + timezone.timedelta(days=7),
    
      
    contract_address=contract_address,      
    contract_abi=abi,           # JSONField automatically handles the Python object 'abi'
    
    temperature_threshold=-8.0, 
    status='Active'
    )
    print("11. Database save complete. Process SUCCESSFUL.")
    
    
    return contract_address

@login_required(login_url='login')
def overview_view(request):
    user = request.user  # The currently logged-in user

    # 🧠 Determine the user role (Buyer/Seller/Admin)
    user_role = user.role

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
    active_sensors = IoTDevice.objects.filter(
        contract__in=contracts.filter(status__in=["Active", "In Transit"])
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

def dashboard_data(request):
    user = request.user
    user_role = user.role

    # Filter contracts based on user role
    if user_role.lower() == "buyer":
        contracts = Contract.objects.filter(buyer=user)
    elif user_role.lower() == "seller":
        contracts = Contract.objects.filter(seller=user)
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


def active_view(request):
    
    # --- Live Data Fetch from Supabase via Django ORM ---
    try:
        contracts_queryset = Contract.objects.filter(status__in=['Active', 'Ongoing', 'In Transit']).all()
    except Exception as e:
        print(f"Database query error: {e}")
        contracts_queryset = []

    active_contracts = []
    
    for contract_instance in contracts_queryset:
        
     
        
        # 3. Determine status
        status = 'Active'
        status_class = 'success'
        
       
        
        # 4. Assemble final data object
        active_contracts.append({
            'contract': contract_instance,
            

            'status': status,
            'status_class': status_class,
        })
    
    context = {
        'contracts': active_contracts
    }
    
    return render(request, 'dashboard/active.html', context)

def create_contract_view(request):
    if request.method == 'POST':
        try:
            
            seller_id = int(request.POST.get('seller_id'))
            buyer_id = int(request.POST.get('buyer_id'))
            # 1. Get ALL required data from the POST request
            # buyer_address = request.POST.get('buyer_address')
            buyer = CustomUser.objects.get(user_id=buyer_id)
            seller = CustomUser.objects.get(user_id=seller_id)
            buyer_address = "0x13994f68615c9c578745339188cc165f4ef9959c"
            # seller_address = request.POST.get('seller_address')
            seller_address = "0x1A947d2CfcF6a4EF915a4049077BfE9acc7Ddb0D"
            product_name = request.POST.get('product_name')
            
            # Convert to correct types
            payment_amount = float(request.POST.get('payment_amount'))
            quantity = int(request.POST.get('quantity')) 
            
            # 2. Execute the deployment and database saving logic
            contract_address = deploy_contract_and_save(
                buyer_address, 
                seller_address, 
                product_name, 
                payment_amount,
                quantity
            )
            
            print(f"Contract deployed successfully at: {contract_address}")
            
        except Exception as e:
            print(f"Contract Creation Error: {e}")
            
        # 3. Redirect back to the active contracts view after submission
        return HttpResponseRedirect(reverse('active')) 
    
    return HttpResponseRedirect(reverse('active')) 
    
    
def process_contract_action(request, contract_id):
    """
    Handles contract completion (Deposit/ForwardPay) or refund by executing
    the corresponding Web3 transaction and updating the database status.
    """
    
    # --- 0. Initial Check and Request Parsing ---
    if request.method != 'POST':
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ERROR: Invalid request method {request.method} for contract ID {contract_id}.")
        return HttpResponseRedirect(reverse('active'))

    action = request.POST.get('action') # 'complete' or 'refund'
    print(f"\n===================================================================")
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] STARTING ACTION: {action.upper()} for Contract ID: {contract_id}")
    print(f"===================================================================")


    try:
        # --- 1. Retrieve Contract Data from Django DB ---
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 1. Retrieving data from database...")
        contract_db = Contract.objects.get(contract_id=contract_id)
        
        contract_address = contract_db.contract_address
        contract_abi = contract_db.contract_abi 
        
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] -> DB Retrieved. Contract Address: {contract_address}")
        
        # --- 2. Web3 Setup and Contract Instance ---
        if not web3.is_connected():
            raise ConnectionError("Web3 not connected. Check RPC URL.")
            
        contract = web3.eth.contract(address=contract_address, abi=contract_abi)
        nonce = web3.eth.get_transaction_count(DEPLOYER_ADDRESS)
        
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 2. Web3 Setup OK. Nonce: {nonce}. Deployer: {DEPLOYER_ADDRESS}")
        
        # --- 3. Determine Transaction Details ---
        if action == 'complete':
            recipient_address = contract_db.seller_address
            contract_func = contract.functions.Deposit 
            new_status = 'Completed'
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 3. ACTION: COMPLETE (Deposit). Payout to Seller: {recipient_address}")

        elif action == 'refund':
            recipient_address = contract_db.buyer_address
            contract_func = contract.functions.Refund 
            new_status = 'Refunded'
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 3. ACTION: REFUND. Payout to Buyer: {recipient_address}")
            
        else:
            raise ValueError(f"Invalid contract action received: {action}")

        # --- 4. Build and Sign Transaction ---
        AMOUNT_TO_SEND = web3.to_wei(0.001, 'ether') # Placeholder for transaction execution
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 4. Building Tx data (Value: {web3.from_wei(AMOUNT_TO_SEND, 'ether')} ETH)")
        
        tx_data = contract_func(recipient_address).build_transaction({
            'chainId': web3.eth.chain_id,
            'from': DEPLOYER_ADDRESS, 
            'nonce': nonce,
            'value': AMOUNT_TO_SEND,
            'gasPrice': web3.eth.gas_price, 
            'gas':  65394 
        })
        
        signed_txn = web3.eth.account.sign_transaction(tx_data, private_key=DEPLOYER_PRIVATE_KEY)
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] -> Transaction signed successfully.")
        
        # --- 5. Send Transaction and Wait for Receipt ---
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 5. Tx submitted to network. Hash: {tx_hash.hex()}")
        
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] -> Waiting for transaction receipt...")
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt.status == 1:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 6. SUCCESS: Transaction confirmed on chain. Block: {receipt.blockNumber}")
        else:
            raise ContractLogicError(f"Transaction failed on-chain. Status: {receipt.status}")

        # --- 7. Update Database Status ---
        contract_db.status = new_status
        contract_db.save()
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 7. DATABASE UPDATE: Contract ID {contract_id} status updated to {new_status}.")
        
    except Contract.DoesNotExist:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ERROR: Contract ID {contract_id} not found in database.")
    except ConnectionError as e:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] CRITICAL ERROR: Web3 connection failed. Details: {e}")
    except ContractLogicError as e:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ERROR: Solidity contract execution failed. Details: {e}")
    except Exception as e:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] UNEXPECTED ERROR during contract action: {e}")
        
    # --- 8. Final Redirect ---
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 8. Redirecting user back to active view.")
    print(f"===================================================================")
    return HttpResponseRedirect(reverse('active'))
    
    
    
    
    
    
    
    
@login_required(login_url='login')
@login_required(login_url='login')
def ongoing_view(request):
    user = request.user
    user_role = user.role.lower()

    # FIX 1: Ensure contract filtering matches JSON view (as noted in the previous answer)
    if user_role == "buyer":
        contracts = Contract.objects.filter(buyer=user, status__in=["Ongoing", "In Transit"])
    elif user_role == "seller":
        contracts = Contract.objects.filter(seller=user, status__in=["Ongoing", "In Transit"])
    else:  # admin
        contracts = Contract.objects.filter(status__in=["Ongoing", "In Transit"])

    # --- NEW: Fetch Live Adafruit IO Data ONCE ---
    live_temp_float, live_temp_str, _ = _get_live_iot_data()

    # 🌡️ Prepare ongoing shipment data
    ongoing_data = []
    for contract in contracts:
        # FIX 2: Use the live_temp_str instead of the DB query
        
        # Determine temperature display (use "N/A" if the fetch failed)
        current_temp_display = live_temp_str if live_temp_float != -100.0 else "N/A" 


        ongoing_data.append({
            "contract_id": contract.contract_id,
            "product_name": contract.product_name,
            # Use the live temperature string
            "temperature": current_temp_display, 
            "status": contract.status,
            "min_temp": contract.min_temp,
            "max_temp": contract.max_temp,
            "buyer_name": contract.buyer.full_name if contract.buyer else "—",
            "seller_name": contract.seller.full_name if contract.seller else "—",
        })

    context = {
        "ongoing_data": ongoing_data,
        "user_role": user_role,
    }

    return render(request, "dashboard/ongoing.html", context)


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
def completed_view(request):
    user = request.user
    user_role = request.session.get("user_role", "").lower()

    try:
        # Filter contracts by role
        if user_role == "buyer":
            contracts_queryset = Contract.objects.filter(status='Completed')
        elif user_role == "seller":
            contracts_queryset = Contract.objects.filter(status='Completed')
        else:  # Admin sees all
            contracts_queryset = Contract.objects.filter(status='Completed')
    except Exception as e:
        print(f"Database query error: {e}")
        contracts_queryset = []

    completed_contracts = []
    
    for contract_instance in contracts_queryset:
        status = 'Complete'
        status_class = 'primary'
        temp_threshold_float = contract_instance.temperature_threshold or 0
        # final_temp_str = f"{temp_threshold_float - 0.5:.1f}°C" 
        final_temp_str = f"{IoTData.objects.latest('recorded_at').temperature:.1f}°C"
        completed_contracts.append({
            'contract': contract_instance,
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
    user_role = user.role.lower()

    # Filter contracts based on user role
    if user_role == "buyer":
        contracts = Contract.objects.filter(buyer=user)
    elif user_role == "seller":
        contracts = Contract.objects.filter(seller=user)
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
