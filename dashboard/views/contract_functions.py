import os
from datetime import datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv
import math
import traceback 
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponseRedirect, HttpResponse, Http404, JsonResponse
from django.urls import reverse
from django.db import models
from django.db import transaction
from django.db.models import Avg, Min, Max
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from web3 import Web3
from web3.exceptions import ContractLogicError
from eth_account import Account
from solcx import compile_source, install_solc, set_solc_version

from accounts.models import CustomUser 
from dashboard.models import Contract, IoTDevice, IoTDataHistory, Alert, IoTData, Product
from dashboard.forms import ProductForm 
load_dotenv()

install_solc('0.5.16')
set_solc_version('0.5.16')

GANACHE_URL = os.getenv("GANACHE_URL", "http://127.0.0.1:7545")
web3 = Web3(Web3.HTTPProvider(GANACHE_URL))
DEPLOYER_PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")
FIXED_ESCROW_FEE_ETH = 5.00
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
def parse_coords(coord_str):
	"""Parse 'lat,long' string (e.g. '52.0553813,-2.7151735') → (lat, long) floats."""
	if not coord_str:
		return None, None
	try:
		lat_str, lon_str = coord_str.split(',')
		return float(lat_str.strip()), float(lon_str.strip())
	except ValueError:
		return None, None
def haversine(lat1, lon1, lat2, lon2):
	R = 6371.0 
	lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
	lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
	dlon = lon2_rad - lon1_rad
	dlat = lat2_rad - lat1_rad
	a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
	c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
	return R * c
	
	
	
def get_deployer_key_and_address():
	try:
		deployer_user = CustomUser.objects.all()[9]
		deployer_user.private_key = os.getenv("DEPLOYER_PRIVATE_KEY")
		deployer_user.m_address = os.getenv("DEPLOYER_ADDRESS")
		if not deployer_user.m_address or not deployer_user.private_key:
			raise ValueError("10th user is missing 'm_address' or 'private_key' in the database.")			
		return deployer_user.m_address, deployer_user.private_key
	
	except IndexError:
		raise IndexError("Could not find the 10th user in CustomUser table. Ensure 10 accounts exist.")
	except Exception as e:
		raise Exception(f"Failed to fetch deployer credentials: {e}")


def send_eth_transaction(from_address, private_key, to_address, amount_eth):
    """
    Sends a simple ETH transfer using EIP-1559 fee settings.
    Returns (tx_hash_hex, receipt)
    Raises on failure.
    """

    if not web3.is_connected():
        raise ConnectionError("Web3 is not connected.")

    nonce = web3.eth.get_transaction_count(from_address)
    base_fee = web3.eth.fee_history(1, 'latest', [10]).baseFeePerGas[-1]

    tx = {
        'chainId': web3.eth.chain_id,
        'from': from_address,
        'to': to_address,
        'nonce': nonce,
        'value': web3.to_wei(amount_eth, 'ether'),
        'maxFeePerGas': int(base_fee * 2),
        'maxPriorityFeePerGas': web3.to_wei(2, 'gwei'),
        'gas': 21000
    }

    signed = web3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status != 1:
        raise Exception(f"Transaction failed. TX={tx_hash.hex()}. Status={receipt.status}")

    return tx_hash.hex(), receipt
    
@login_required(login_url='login')
def deny_contract(request, contract_id):
    if request.method != "POST":
        return redirect("active")

    try:
        contract = Contract.objects.get(contract_id=contract_id)
    except Contract.DoesNotExist:
        messages.error(request, "Contract not found.")
        return redirect("active")

    # Only seller can deny
    if contract.seller_address != request.user.m_address:
        messages.error(request, "You are not authorized to deny this contract.")
        return redirect("active")

    # Only Pending can be denied
    if contract.status != "Pending":
        messages.error(request, "Only pending contracts can be denied.")
        return redirect("active")

    # delete it
    contract.delete()

    messages.success(request, f"Contract {contract_id} has been denied and removed.")
    return redirect("active")

@login_required(login_url='login')
def activate_contract(request, contract_id):
    DEPLOYER_ADDRESS, _ = get_deployer_key_and_address()

    if request.method != 'POST':
        return HttpResponseRedirect(reverse('active'))

    try:
        contract = Contract.objects.get(contract_id=contract_id)
    except Contract.DoesNotExist:
        messages.error(request, f"Contract {contract_id} not found.")
        return HttpResponseRedirect(reverse('active'))

    # Authorization
    if contract.seller_address != request.user.m_address:
        messages.error(request, "Only the seller assigned to the contract can activate it.")
        return HttpResponseRedirect(reverse('active'))

    if contract.status != 'Pending':
        messages.error(request, "Only Pending contracts can be activated.")
        return HttpResponseRedirect(reverse('active'))

    # Buyer details
    buyer_address = contract.buyer_address
    try:
        buyer_user = CustomUser.objects.get(m_address=buyer_address)
    except CustomUser.DoesNotExist:
        messages.error(request, "Buyer record not found.")
        return HttpResponseRedirect(reverse('active'))

    buyer_private_key = buyer_user.private_key
    if not buyer_private_key:
        messages.error(request, "Buyer does not have a stored private key. Activation blocked.")
        return HttpResponseRedirect(reverse('active'))

    # Seller start coordinates
    seller_user = request.user
    if seller_user.latitude and seller_user.longitude:
        contract.start_coord = f"{seller_user.latitude},{seller_user.longitude}"
    else:
        contract.start_coord = None

    # EXECUTION PHASE
    status_report = []  # For popup message

    try:
        # Step 1: Service fee payment (Buyer -> Deployer)
        SERVICE_FEE_ETH = FIXED_ESCROW_FEE_ETH
        tx1_hash, _ = send_eth_transaction(
            from_address=buyer_address,
            private_key=buyer_private_key,
            to_address=DEPLOYER_ADDRESS,
            amount_eth=SERVICE_FEE_ETH
        )
        status_report.append(f"Service fee paid. TX: {tx1_hash}")

        # Step 2: Product payment (Buyer -> Seller)
        product_price_eth = float(contract.price)
        tx2_hash, _ = send_eth_transaction(
            from_address=buyer_address,
            private_key=buyer_private_key,
            to_address=contract.seller_address,
            amount_eth=product_price_eth
        )
        status_report.append(f"Product payment sent. TX: {tx2_hash}")

        # Step 3: Mark contract as ongoing
        contract.status = "Ongoing"
        contract.start_date = timezone.now()
        contract.save()

        status_report.append("Contract status updated to Ongoing.")

        # Success popup
        messages.success(request, "Activation complete. " + " ".join(status_report))

    except Exception as e:
        messages.error(request, f"Activation failed: {e}")
        return HttpResponseRedirect(reverse('active'))

    return HttpResponseRedirect(reverse('active'))

def deploy_contract_and_save(
    request,
    BuyerAddress,
    SellerAddress,
    BuyerID,
    SellerID,
    ProductName,
    PaymentAmount,
    Quantity,
    EndCoords,
    StartCoords,
    MaxTemp
):
    DEPLOYER_ADDRESS, DEPLOYER_PRIVATE_KEY = get_deployer_key_and_address()

    if not web3.is_connected():
        raise ConnectionError("Web3 connection failed. Check RPC.")

    # Compile
    compiled = compile_source(solidity_code)
    _, contract_interface = compiled.popitem()
    abi = contract_interface["abi"]
    bytecode = contract_interface["bin"]

    ContractObj = web3.eth.contract(abi=abi, bytecode=bytecode)

    # Get next contract ID
    latest = Contract.objects.aggregate(max_id=models.Max('contract_id'))['max_id']
    next_id = (latest or 0) + 1

    # Deploy transaction
    nonce = web3.eth.get_transaction_count(DEPLOYER_ADDRESS)
    base_fee = web3.eth.fee_history(1, "latest", [10]).baseFeePerGas[-1]

    deploy_txn = ContractObj.constructor().build_transaction({
        "chainId": web3.eth.chain_id,
        "from": DEPLOYER_ADDRESS,
        "nonce": nonce,
        "maxFeePerGas": int(base_fee * 2),
        "maxPriorityFeePerGas": web3.to_wei(2, "gwei"),
        "gas": 4_000_000,
    })

    signed = web3.eth.account.sign_transaction(deploy_txn, DEPLOYER_PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status != 1:
        raise Exception("Smart contract deployment failed on chain.")

    contract_address = receipt.contractAddress

    # Save to DB
    Contract.objects.create(
        contract_id=next_id,
        buyer_address=BuyerAddress,
        seller_address=SellerAddress,
        buyer_id=BuyerID,
        seller_id=SellerID,
        product_name=ProductName,
        quantity=Quantity,
        price=PaymentAmount,
        max_temp=MaxTemp,
        status="Pending",
        contract_address=contract_address,
        contract_abi=contract_interface["abi"],
        start_coord=StartCoords,
        end_coord=EndCoords,
        end_date=timezone.now() + timezone.timedelta(days=7),
    )

    return contract_address

def create_contract_view(request):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("active")

    try:
        buyer = request.user
        buyer_address = request.POST.get("buyer_address") or buyer.m_address
        user_id = request.POST.get("user_id") or buyer.user_id

        product_id = request.POST.get("selected_product")
        seller_id_input = request.POST.get("selected_seller")
        quantity_raw = request.POST.get("quantity")

        missing = []
        if not buyer_address: missing.append("buyer_address")
        if not user_id: missing.append("user_id")
        if not product_id: missing.append("selected_product")
        if not seller_id_input: missing.append("selected_seller")
        if not quantity_raw: missing.append("quantity")

        if missing:
            messages.error(request, "Missing fields: " + ", ".join(missing))
            return redirect("active")

        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                raise ValueError("Quantity must be > 0")
        except:
            messages.error(request, "Invalid quantity.")
            return redirect("active")

        # Get product
        try:
            product = Product.objects.get(product_id=product_id)
        except Product.DoesNotExist:
            messages.error(request, "Product not found.")
            return redirect("active")

        # Get seller
        try:
            seller_user = CustomUser.objects.get(pk=seller_id_input, role__iexact="seller")
        except CustomUser.DoesNotExist:
            messages.error(request, "Seller not found or not a seller.")
            return redirect("active")

        product_name = product.product_name
        payment_amount = product.price_eth * quantity
        max_temp = product.max_temp

        # Coordinates
        seller_lat = seller_user.latitude
        seller_lon = seller_user.longitude
        start_coords = f"{seller_lat},{seller_lon}" if seller_lat and seller_lon else None

        buyer_lat = buyer.latitude
        buyer_lon = buyer.longitude
        end_coords = f"{buyer_lat},{buyer_lon}" if buyer_lat and buyer_lon else None

        contract_address = deploy_contract_and_save(
            request,
            BuyerAddress=buyer_address,
            SellerAddress=seller_user.m_address,
            BuyerID=user_id,
            SellerID=seller_user.user_id,
            ProductName=product_name,
            PaymentAmount=payment_amount,
            Quantity=quantity,
            EndCoords=end_coords,
            StartCoords=start_coords,
            MaxTemp=max_temp
        )

        if not contract_address:
            messages.error(request, "Deployment failed.")
            return redirect("active")

        messages.success(
            request,
            f"Contract deployed at {contract_address}. Awaiting seller activation."
        )
        return redirect("active")

    except Exception as e:
        messages.error(request, f"Contract creation failed: {e}")
        return redirect("active")

def process_contract_action(request, contract_id):
	DEPLOYER_ADDRESS, DEPLOYER_PRIVATE_KEY = get_deployer_key_and_address() 
	action = request.POST.get('action')

	if request.method != 'POST':
		print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Invalid request method {request.method} for contract ID {contract_id}.")
		return HttpResponseRedirect(reverse('active'))

	print(f"[{datetime.now().strftime('%H:%M:%S')}] STARTING ACTION: {action.upper()} for Contract ID: {contract_id}")

	try:
		contract_db = Contract.objects.get(contract_id=contract_id)		
		amount_eth = Decimal(contract_db.price)
		AMOUNT_TO_SEND = web3.to_wei(amount_eth, 'ether')
		
		if AMOUNT_TO_SEND == 0:
			raise ValueError("Contract price is zero. Cannot perform payment action.")
		contract_address = contract_db.contract_address
		contract_abi = contract_db.contract_abi 		
		print(f"[{datetime.now().strftime('%H:%M:%S')}] -> DB Retrieved. Contract Address: {contract_address}")
		

		if not web3.is_connected():
			raise ConnectionError("Web3 not connected. Check RPC URL.")
			
		contract = web3.eth.contract(address=contract_address, abi=contract_abi)
		nonce = web3.eth.get_transaction_count(DEPLOYER_ADDRESS)
		
		print(f"[{datetime.now().strftime('%H:%M:%S')}] 2. Web3 Setup OK. Nonce: {nonce}. Deployer: {DEPLOYER_ADDRESS}")
		
		if action == 'complete':
			recipient_address = contract_db.seller_address
			contract_func = contract.functions.Deposit 
			new_status = 'Completed'
			print(f"[{datetime.now().strftime('%H:%M:%S')}] 3. ACTION: COMPLETE (Deposit). Payout to Seller: {recipient_address}")

		elif action == 'refund':
			recipient_address = contract_db.buyer_address
			contract_func = contract.functions.Refund 
			new_status = 'Refunded'
			print(f"[{datetime.now().strftime('%H:%M:%S')}] 3. ACTION: REFUND. Payout to Buyer: {recipient_address}")
			
		else:
			raise ValueError(f"Invalid contract action received: {action}")
		
		print(f"[{datetime.now().strftime('%H:%M:%S')}] 4. Building Tx data (Value: {amount_eth} ETH)") # <-- Now prints the actual price
		estimated_fees = web3.eth.fee_history(1, 'latest', [10]).baseFeePerGas[-1]
		max_fee = int(estimated_fees * 2)
		
		tx_data = contract_func(recipient_address).build_transaction({
			'chainId': web3.eth.chain_id,
			'from': DEPLOYER_ADDRESS,
			'nonce': nonce,
			'value': AMOUNT_TO_SEND,
			'maxFeePerGas': max_fee,
			'maxPriorityFeePerGas': web3.to_wei(2, 'gwei'),
			'gas':  100000
		})
		
		signed_txn = web3.eth.account.sign_transaction(tx_data, private_key=DEPLOYER_PRIVATE_KEY)
		print(f"[{datetime.now().strftime('%H:%M:%S')}] -> Transaction signed successfully.")
		
		tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
		print(f"[{datetime.now().strftime('%H:%M:%S')}] 5. Tx submitted to network. Hash: {tx_hash.hex()}")
		
		print(f"[{datetime.now().strftime('%H:%M:%S')}] -> Waiting for transaction receipt...")
		receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
		
		if receipt.status == 1:
			print(f"[{datetime.now().strftime('%H:%M:%S')}] 6. SUCCESS: Transaction confirmed on chain. Block: {receipt.blockNumber}")
		else:
			raise ContractLogicError(f"Transaction failed on-chain. Status: {receipt.status}")

		contract_db.status = new_status
		contract_db.save()
		print(f"[{datetime.now().strftime('%H:%M:%S')}] 7. DATABASE UPDATE: Contract ID {contract_id} status updated to {new_status}.")

		if getattr(contract_db, 'IoT_Assigned', None):
			record_and_delete_temperature_data(contract_id, contract_db.IoT_Assigned.device_id)
		
	except Contract.DoesNotExist:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Contract ID {contract_id} not found in database.")
	except ConnectionError as e:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] CRITICAL ERROR: Web3 connection failed. Details: {e}")
	except ContractLogicError as e:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Solidity contract execution failed. Details: {e}")
	except Exception as e:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] UNEXPECTED ERROR during contract action: {e}")
		
	print(f"[{datetime.now().strftime('%H:%M:%S')}] 8. Redirecting user back to active view.")
	return HttpResponseRedirect(reverse('active'))
	
def record_and_delete_temperature_data(contract_id: int, device_id: int):
	from dashboard.views.main_view import push_iot_to_supabase
	try:
		contract_obj = Contract.objects.get(pk=contract_id)
	except Contract.DoesNotExist:
		print(f"[AUTO] Contract {contract_id} not found.")
		return
	if IoTDataHistory.objects.filter(contract=contract_obj).exists():
		print(f"[AUTO] IoTDataHistory already exists for contract {contract_id}, skipping.")
		return
	data_to_aggregate = IoTData.objects.filter(device_id=device_id)

	if not data_to_aggregate.exists():
		print(f"[AUTO] No IoT records found for device {device_id}.")
		return

	# --- Aggregate stats ---
	aggregation_results = data_to_aggregate.aggregate(
		avg_temp=Avg('temperature'),
		min_temp=Min('temperature'),
		max_temp=Max('temperature'),
	)

	avg_t = aggregation_results.get('avg_temp', 0.0)
	min_t = aggregation_results.get('min_temp', 0.0)
	max_t = aggregation_results.get('max_temp', 0.0)

	# --- Determine contract result/status ---
	result_status = contract_obj.status if contract_obj.status in ['Completed', 'Refunded'] else 'Unknown'
	recorded_time = timezone.now()

	try:
		with transaction.atomic():
			# --- Record summary locally ---
			IoTDataHistory.objects.create(
				contract=contract_obj,
				avg_temp=avg_t,
				min_temp=min_t,
				max_temp=max_t,
				result=result_status,
				recorded_at=recorded_time,
			)

			deleted_count, _ = data_to_aggregate.delete()

			print(f"IoTDataHistory recorded for contract {contract_id} ({result_status}).")
			print(f"Deleted {deleted_count} IoTData records for device {device_id}.")

			# --- Push summary to Supabase ---
			try:
				push_iot_to_supabase(
					temperature=avg_t,
					battery_voltage=None,
					gps_lat=None,
					gps_long=None,
					device_id=device_id,  # ✅ pass the real device_id
				)
				print(f"Summary uploaded:{contract_id} ({result_status}).")
			except Exception as e:
				print(f"Upload faiked: {contract_id}: {e}")

	except Exception as e:
		print(f"[AUTO] Failed to record/delete IoTData for contract {contract_id}: {e}")


def execute_onchain_action(contract_db, action):
	DEPLOYER_ADDRESS, DEPLOYER_PRIVATE_KEY = get_deployer_key_and_address()
	try:
		if contract_db is None:
			print("[AUTO] No contract provided to execute_onchain_action")
			return False

		amount_eth = Decimal(contract_db.price)
		AMOUNT_TO_SEND = web3.to_wei(amount_eth, 'ether')

		contract_address = contract_db.contract_address
		contract_abi = contract_db.contract_abi

		if not web3.is_connected():
			print("[AUTO] Web3 not connected")
			return False

		contract = web3.eth.contract(address=contract_address, abi=contract_abi)
		nonce = web3.eth.get_transaction_count(DEPLOYER_ADDRESS)

		if action == 'complete':
			recipient_address = contract_db.seller_address
			contract_func = contract.functions.Deposit
			new_status = 'Completed'
		elif action == 'refund':
			recipient_address = contract_db.buyer_address
			contract_func = contract.functions.Refund
			new_status = 'Refunded'
		else:
			print(f"[AUTO] Unknown action: {action}")
			return False

		estimated_fees = web3.eth.fee_history(1, 'latest', [10]).baseFeePerGas[-1]
		max_fee = int(estimated_fees * 2)

		tx_data = contract_func(recipient_address).build_transaction({
			'chainId': web3.eth.chain_id,
			'from': DEPLOYER_ADDRESS,
			'nonce': nonce,
			'value': AMOUNT_TO_SEND,
			'maxFeePerGas': max_fee,
			'maxPriorityFeePerGas': web3.to_wei(2, 'gwei'),
			'gas': 100000
		})

		signed_txn = web3.eth.account.sign_transaction(tx_data, private_key=DEPLOYER_PRIVATE_KEY)
		tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
		receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

		if receipt.status == 1:
			with transaction.atomic():
				contract_db.status = new_status
				if new_status == 'Completed':
					contract_db.end_date = timezone.now()
				contract_db.save()

			print(f"{action} succeeded for contract {contract_db.contract_id} (tx {tx_hash.hex()}) status: {new_status}")

			try:
				if getattr(contract_db, 'IoT_Assigned', None):
					record_and_delete_temperature_data(contract_db.contract_id, contract_db.IoT_Assigned.device_id)
					print(f"[AUTO] IoT data collated and purged for contract {contract_db.contract_id}.")
				else:
					print(f"[AUTO] No IoT_Assigned device for contract {contract_db.contract_id}, skipping IoT collation.")
			except Exception as e:
				print(f"[AUTO] Failed to record/delete IoT data for contract {contract_db.contract_id}: {e}")

			return True
		else:
			print(f"{action} failed {contract_db.contract_id} status: {receipt.status}")
			return False

	except Exception as e:
		print(f"[AUTO] execute_onchain_action exception for contract {getattr(contract_db, 'contract_id', 'unknown')}: {e}")
		return False


def contract_temp_out_of_range_for(contract_db, window_seconds=300):

	if not contract_db or not getattr(contract_db, 'IoT_Assigned', None):
		print(f"no iot assigned{getattr(contract_db, 'contract_id', '?')}")
		return False

	device = contract_db.IoT_Assigned
	now = timezone.now()
	window_start = now - timedelta(seconds=window_seconds + 60)  # small buffer
	max_t = getattr(contract_db, "max_temp", None)
	min_t = getattr(contract_db, "min_temp", None)

	if max_t is None or min_t is None:
		print(f"{contract_db.contract_id} missing min/max temperature.")
		return False

	readings = IoTData.objects.filter(
		device=device,
		recorded_at__gte=window_start
	).order_by('recorded_at').values('temperature', 'recorded_at')

	if not readings.exists():
		print(f"no recent temp reads{contract_db.contract_id}.")
		return False

	violation_start = None
	violation_duration = 0
	last_ts = None

	for r in readings:
		temp = r['temperature']
		ts = r['recorded_at']

		if temp is None:
			continue

		out_of_range = (temp > max_t) or (temp < min_t)

		if out_of_range:
			if violation_start is None:
				violation_start = ts
			last_ts = ts
		else:
			# Close current violation segment if we go back in range
			if violation_start and last_ts:
				segment_duration = (last_ts - violation_start).total_seconds()
				violation_duration = max(violation_duration, segment_duration)
				violation_start = None
				last_ts = None

	# Final open segment
	if violation_start and last_ts:
		segment_duration = (last_ts - violation_start).total_seconds()
		violation_duration = max(violation_duration, segment_duration)

	if violation_duration > 0:
		percent = (violation_duration / window_seconds) * 100
		print(f"{contract_db.contract_id}  temp breached {violation_duration:.1f} / {window_seconds} secs ({percent:.1f}%).")

	if violation_duration >= window_seconds:
		print(f"{contract_db.contract_id} temp breached{violation_duration:.1f}s refunding")
		return True

	return False
def contract_within_end_coords_for(contract_db, radius_km=0.01, window_seconds=180):

	if not contract_db or not getattr(contract_db, 'IoT_Assigned', None):
		print(f"no IoT device assigned for contract {getattr(contract_db, 'contract_id', '?')}")
		return False

	if not getattr(contract_db, 'end_coord', None):
		print(f"{contract_db.contract_id} has no end_coord.")
		return False

	try:
		end_lat_str, end_lon_str = str(contract_db.end_coord).split(',')
		end_lat = float(end_lat_str.strip())
		end_lon = float(end_lon_str.strip())
	except Exception as e:
		print(f"invalid end_coord for contract {contract_db.contract_id}: {contract_db.end_coord} — {e}")
		return False

	device = contract_db.IoT_Assigned
	now = timezone.now()
	window_start = now - timedelta(seconds=window_seconds + 180)  # small buffer

	readings = IoTData.objects.filter(
		device=device,
		recorded_at__gte=window_start
	).order_by('recorded_at').values('gps_lat', 'gps_long', 'recorded_at')

	if not readings.exists():
		print(f"no recent gps reads {contract_db.contract_id}.")
		return False

	segments = []
	current_seg_start = None
	last_ts = None

	for r in readings:
		lat = r['gps_lat']
		lon = r['gps_long']
		ts = r['recorded_at']

		if lat is None or lon is None:
			inside = False
		else:
			dist_km = haversine(lat, lon, end_lat, end_lon)
			inside = (dist_km <= radius_km)

			print(f"{contract_db.contract_id} — distance {dist_km*1000:.2f} m from destination at {ts}")

		if inside:
			if current_seg_start is None:
				current_seg_start = ts
			last_ts = ts
		else:
			if current_seg_start is not None:
				segments.append((current_seg_start, last_ts))
				current_seg_start = None
				last_ts = None

	if current_seg_start is not None and last_ts is not None:
		segments.append((current_seg_start, last_ts))

	for (s, e) in segments:
		duration = (e - s).total_seconds()
		if duration >= window_seconds:
			print(f"{contract_db.contract_id} within {radius_km*1000:.1f}m for {duration:.1f}s success")
			return True

	print(f"{contract_db.contract_id} not yet within end_coords {window_seconds}s.")
	return False

def run_auto_checks_for_all_contracts(check_temp_seconds=300, check_location_seconds=180, location_radius_km=0.01):

	summary = {'refunds': [], 'completions': [], 'skipped': []}

	target_statuses = ['Ongoing', 'In Transit']
	contracts = Contract.objects.filter(status__in=target_statuses).select_related('IoT_Assigned')

	for c in contracts:
		try:
			if not getattr(c, 'IoT_Assigned', None):
				summary['skipped'].append((c.contract_id, "No device"))
				continue

	  
		#refund check
			if contract_temp_out_of_range_for(c, window_seconds=check_temp_seconds):
				c.refresh_from_db()
				if c.status in target_statuses:
					ok = execute_onchain_action(c, 'refund')
					if ok:
						summary['refunds'].append(c.contract_id)
						try:
							iot_device = c.IoT_Assigned
							iot_device.status = "Available"
							iot_device.contract_id = None
							iot_device.save()
							print(f"[IOT RESET] IoT '{iot_device.device_name}' released from refunded Contract {c.contract_id}.")
						except Exception as e:
							print(f"[IOT RESET] Failed to reset IoT for refunded Contract {c.contract_id}: {e}")

					else:
						summary['skipped'].append((c.contract_id, "refund_failed"))
					continue
			#check loc for success
			if contract_within_end_coords_for(c, radius_km=location_radius_km, window_seconds=check_location_seconds):
				c.refresh_from_db()
				if c.status in target_statuses:
					ok = execute_onchain_action(c, 'complete')
					if ok:
						summary['completions'].append(c.contract_id)
						try:
							iot_device = c.IoT_Assigned
							iot_device.status = "Available"
							iot_device.contract_id = None
							iot_device.save()
							print(f"[IOT RESET] IoT '{iot_device.device_name}' released from completed Contract {c.contract_id}.")
						except Exception as e:
							print(f"[IOT RESET] Failed to reset IoT for completed Contract {c.contract_id}: {e}")
					else:
						summary['skipped'].append((c.contract_id, "complete_failed"))
					continue
			#walay happens
			summary['skipped'].append((c.contract_id, "no_condition_met"))

		except Exception as e:
			print(f"[AUTO] error checking contract {c.contract_id}: {e}")
			summary['skipped'].append((c.contract_id, f"error:{e}"))

	return summary
