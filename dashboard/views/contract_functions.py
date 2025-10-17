import os
from dotenv import load_dotenv # NEW
from eth_account import Account # NEW
from accounts.models import CustomUser
from web3.exceptions import ContractLogicError
from accounts.models import CustomUser
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone 
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.db import models
from django.db.models import Avg, Min, Max
from django.http import HttpResponse, Http404, JsonResponse
from dashboard.models import Contract, IoTDevice, IoTDataHistory, Alert, IoTData, Product
from accounts.models import CustomUser
from dashboard.forms import ProductForm
from accounts.models import CustomUser
from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version
from web3.exceptions import ContractLogicError
#from .main_view import get_latest_temperature
from datetime import datetime
from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version
load_dotenv() 
install_solc('0.5.16')
set_solc_version('0.5.16')
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
GANACHE_URL = os.getenv("GANACHE_URL", "http://127.0.0.1:7545")
web3 = Web3(Web3.HTTPProvider(GANACHE_URL))
DEPLOYER_PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY") # Still needed for signing
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

      
def get_contract_temperature(request, contract_id):
    """
    API endpoint to fetch the latest temperature for a single ongoing contract.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Removed .select_related('IoT_Assigned') to fix the Invalid Field error.
        contract = Contract.objects.get(contract_id=contract_id, status='Ongoing')
        
        # 2. Get the latest temperature using the helper function
        current_temp = get_latest_temperature(contract)

        return JsonResponse({
            'contract_id': contract_id,
            'current_temp': current_temp,
            # Convert Decimal/float to string for JSON serialization
            'max_temp': str(contract.max_temp) 
        })
        
    except Contract.DoesNotExist:
        return JsonResponse({'error': 'Contract not found or not ongoing'}, status=404)
    except Exception as e:
        print(f"Error fetching temperature: {e}")
        return JsonResponse({'error': 'Internal server error'}, status=500)
def get_deployer_key_and_address():
	try:
		# Assuming the 10th user in the table is the Deployer/Escrow account
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

@login_required(login_url='login')
def activate_contract(request, contract_id):
	# Fetch deployer address for use as the escrow address
	DEPLOYER_ADDRESS, _ = get_deployer_key_and_address() 

	if request.method != 'POST':
		# Redirect on non-POST request
		return HttpResponseRedirect(reverse('active'))

	try:
		contract_db = Contract.objects.get(contract_id=contract_id)		
		
		# 1. SECURITY CHECK: Ensure the user activating is the designated seller AND the contract is Pending.
		if contract_db.seller_address != request.user.m_address or contract_db.status != 'Pending':
			messages.error(request, "Authorization failed. Only the Seller can activate a Pending contract.")
			return HttpResponseRedirect(reverse('active'))

		# Buyer is the SENDER of the money (to the Deployer/Escrow)
		sender_address = contract_db.buyer_address 

		try:
			# Get the buyer's private key from the database (since the seller doesn't have it in their session)
			buyer_user = CustomUser.objects.get(m_address=sender_address)
			sender_private_key = buyer_user.private_key
		except CustomUser.DoesNotExist:
			raise ValueError(f"Buyer address {sender_address} not found in CustomUser table. Cannot sign transaction.")			
		if not sender_private_key:
			raise ValueError("Buyer (sender) does not have a private key in the database.")
			
		escrow_address = DEPLOYER_ADDRESS 
		
		# 2. Get Seller's location for start_coord (using the current user's location)
		seller_user = request.user 
		seller_lat = seller_user.latitude
		seller_lon = seller_user.longitude
		start_coords_str = f"{seller_lat},{seller_lon}" if seller_lat and seller_lon else None
		
		if not web3.is_connected():
			raise ConnectionError("Web3 not connected. Check RPC URL.")
			
		nonce = web3.eth.get_transaction_count(sender_address)
		price_eth = float(contract_db.price)
		
		# The full product price is what is sent here
		total_eth_to_send = price_eth 
		amount_to_send_wei = web3.to_wei(total_eth_to_send, 'ether')
		
		# --- ADDED/CONFIRMED PRINT STATEMENTS (Product Price Payment) ---
		print(f"\n[{timezone.now()}] STARTING ACTIVATION (Product Price Payment):")
		print(f"  AMOUNT: {total_eth_to_send} ETH")
		print(f"  FROM (Buyer): {sender_address}")
		print(f"  TO (Escrow/Deployer): {escrow_address}")
		
		estimated_fees = web3.eth.fee_history(1, 'latest', [10]).baseFeePerGas[-1]

		tx_data = {
			'chainId': web3.eth.chain_id,
			'from': sender_address, # Transaction 'from' the Buyer's wallet
			'to': escrow_address, 
			'nonce': nonce,
			'value': amount_to_send_wei,
			'maxFeePerGas': int(estimated_fees * 2), 
			'maxPriorityFeePerGas': web3.to_wei(2, 'gwei'), 
			'gas':  21000 # Standard ETH transfer gas limit
		}
		
		signed_txn = web3.eth.account.sign_transaction(tx_data, private_key=sender_private_key) 
		tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
		receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
		
		if receipt.status == 1:
			messages.success(request, f"Contract {contract_db.contract_id} successfully funded with {price_eth} ETH and shipment started.")
		else:
			raise Exception(f"Transaction failed on-chain. Status: {receipt.status}")

		# 4. Update status and start date/time 
		contract_db.status = 'Ongoing' 
		contract_db.start_date = timezone.now()
		contract_db.start_coord = start_coords_str # Seller's coordinates upon activation
		contract_db.save()
		
	except Contract.DoesNotExist:
		messages.error(request, f"Contract ID {contract_id} not found.")
	except Exception as e:
		messages.error(request, f"Contract activation failed: {e}")
		
	return HttpResponseRedirect(reverse('active'))

def deploy_contract_and_save(BuyerAddress, SellerAddress, ProductName, PaymentAmount, Quantity, EndCoords, StartCoords, MaxTemp):
	DEPLOYER_ADDRESS, DEPLOYER_PRIVATE_KEY = get_deployer_key_and_address() 
	
	print("--- Starting Contract Deployment Process (Pending Status) ---")
	if not web3.is_connected():
		print("ERROR: Web3 not connected. Check RPC URL and network status.")
		raise ConnectionError("Could not connect to Ganache RPC endpoint.")
	
	compiled_sol = compile_source(solidity_code)
	contract_name, contract_interface = compiled_sol.popitem()
	abi = contract_interface['abi']
	bytecode = contract_interface['bin']
	SimpleTransfer = web3.eth.contract(abi=abi, bytecode=bytecode)

	# prep and dep
	nonce = web3.eth.get_transaction_count(DEPLOYER_ADDRESS)
	print(f"1. Nonce for Deployment: {nonce}")
	estimated_fees = web3.eth.fee_history(1, 'latest', [10]).baseFeePerGas[-1] 
	max_fee = int(estimated_fees * 2)
	construct_txn = SimpleTransfer.constructor().build_transaction({
		'chainId': web3.eth.chain_id, 
		'from': DEPLOYER_ADDRESS, 
		'nonce': nonce,
		'maxFeePerGas': max_fee,
		'maxPriorityFeePerGas': web3.to_wei(2, 'gwei'),
		'gas':  4000000
	})
	
	signed_txn = web3.eth.account.sign_transaction(
		construct_txn, 
		private_key=DEPLOYER_PRIVATE_KEY
	)
	print("2. Contract deployment transaction signed.")
	
	tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
	print(f"3. Deployment transaction sent. Hash: {tx_hash.hex()}")
	tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
	contract_address = tx_receipt.contractAddress
	print(f"4. Contract deployed successfully at: {contract_address}")
	
	
	latest_contract = Contract.objects.aggregate(max_id=models.Max('contract_id'))['max_id']
	next_contract_id = (latest_contract or 0) + 1
	print(f"5. Saving contract details to database (Attempting ID: {next_contract_id}).")

	new_contract = Contract.objects.create(
		contract_id=next_contract_id,
		
		buyer_address=BuyerAddress,
		seller_address=SellerAddress, 
		
		product_name=ProductName,
		quantity=Quantity, 
		price=PaymentAmount,
		end_date=timezone.now() + timezone.timedelta(days=7),
		
		contract_address=contract_address,      
		contract_abi=contract_interface['abi'], 
		
		max_temp=MaxTemp, 
		status='Pending',
		end_coord=EndCoords, 
		start_coord=StartCoords, 
	)
	print("6. Database save complete. Process SUCCESSFUL. Status: Pending.")
	
	return contract_address


def create_contract_view(request):
	if request.method == 'POST':
		try:
			# 1. Get data from POST
			buyer = request.user 
			buyer_address = request.POST.get('buyer_address') 
			
			# Seller selection
			selected_seller_id = request.POST.get('selected_seller') 
			
			product_id = request.POST.get('selected_product') 
			quantity = int(request.POST.get('quantity'))

			if quantity <= 0:
				messages.error(request, "Quantity must be a positive number.")
				return HttpResponseRedirect(reverse('active'))

			# 2. Fetch Product data
			product = Product.objects.get(product_id=product_id)
			product_name = product.product_name
			payment_amount = product.price_eth * quantity
			max_temp = product.max_temp
			
			# 3. Fetch Seller data
			seller_user = CustomUser.objects.get(pk=selected_seller_id, role__iexact='seller')
			seller_address = seller_user.m_address # <--- SELLER'S ADDRESS
			seller_lat = seller_user.latitude 
			seller_lon = seller_user.longitude
			start_coords_str = f"{seller_lat},{seller_lon}" if seller_lat and seller_lon else None

			# 4. Get Buyer's Coordinates (EndCoords)
			buyer_lat = buyer.latitude 
			buyer_lon = buyer.longitude
			end_coords_str = f"{buyer_lat},{buyer_lon}" if buyer_lat and buyer_lon else None
			
			# 5. Deploy Contract
			contract_address = deploy_contract_and_save(
				BuyerAddress=buyer_address, 
				SellerAddress=seller_address, 
				ProductName=product_name, 
				PaymentAmount=payment_amount,
				Quantity=quantity,
				EndCoords=end_coords_str,
				StartCoords=start_coords_str, 
				MaxTemp=max_temp
			)
			
			# --- 6. ESCROW FEE PAYMENT (using Buyer's key from session) ---
			buyer_private_key = request.session.get("user_PK")
			buyer_address_from_user = request.user.m_address 

			if not buyer_private_key:
				messages.error(request, "Contract deployed. ERROR: Buyer private key not found in session. Escrow fee was NOT paid.")
				return HttpResponseRedirect(reverse('active'))

			DEPLOYER_ADDRESS, _ = get_deployer_key_and_address() # <--- DEPLOYER'S ADDRESS
			
			if buyer_address_from_user == DEPLOYER_ADDRESS:
				messages.error(request, "CRITICAL ERROR: Buyer and Deployer addresses are identical. Cannot perform escrow transfer. Please log in as a different user.")
				return HttpResponseRedirect(reverse('active'))
			
			amount_eth = FIXED_ESCROW_FEE_ETH
			amount_wei = web3.to_wei(amount_eth, 'ether')
			
			if not web3.is_connected():
				raise ConnectionError("Web3 not connected for escrow payment.")

			nonce = web3.eth.get_transaction_count(buyer_address_from_user)
			estimated_fees = web3.eth.fee_history(1, 'latest', [10]).baseFeePerGas[-1]
			
			# --- ADJUSTED PRINT STATEMENTS ---
			print(f"\n[{timezone.now()}] STARTING ESCROW PAYMENT (Contract Creation):")
			print(f"  AMOUNT: {amount_eth} ETH (FIXED_ESCROW_FEE_ETH)")
			print(f"  FROM (Buyer): {buyer_address_from_user}")
			print(f"  TO (Deployer/Escrow): {DEPLOYER_ADDRESS}")
			print(f"  CONTRACT SELLER ADDRESS: {seller_address}") # <-- NEW DEBUG LINE
			
			tx_data = {
				'chainId': web3.eth.chain_id,
				'from': buyer_address_from_user,
				# The recipient is explicitly set to the DEPLOYER/ESCROW address
				'to': DEPLOYER_ADDRESS, 
				'nonce': nonce,
				'value': amount_wei,
				'maxFeePerGas': int(estimated_fees * 2),
				'maxPriorityFeePerGas': web3.to_wei(2, 'gwei'),
				'gas': 21000 
			}
			
			signed_txn = web3.eth.account.sign_transaction(tx_data, private_key=buyer_private_key)
			tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
			receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

			if receipt.status == 1:
				messages.success(request, f"Contract deployed successfully at: {contract_address}. Escrow fee of {FIXED_ESCROW_FEE_ETH} ETH paid successfully (TX: {tx_hash.hex()}). Awaiting Seller activation.")
			else:
				raise Exception(f"Escrow fee payment failed on-chain. Contract deployed but unfunded.")
			
		except Product.DoesNotExist:
			messages.error(request, "Selected product not found.")
		except CustomUser.DoesNotExist:
			messages.error(request, "Selected seller not found or invalid.")
		except Exception as e:
			print(f"Contract Creation Error: {e}")
			messages.error(request, f"Contract creation failed: {e}")
			
		return HttpResponseRedirect(reverse('active')) 
	
	return HttpResponseRedirect(reverse('active'))

def process_contract_action(request, contract_id):
	DEPLOYER_ADDRESS, DEPLOYER_PRIVATE_KEY = get_deployer_key_and_address() 
	

	if request.method != 'POST':
		print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Invalid request method {request.method} for contract ID {contract_id}.")
		return HttpResponseRedirect(reverse('active'))

	action = request.POST.get('action') 
	print(f"[{datetime.now().strftime('%H:%M:%S')}] STARTING ACTION: {action.upper()} for Contract ID: {contract_id}")

	try:
		#get contract info
		contract_db = Contract.objects.get(contract_id=contract_id)		
		contract_address = contract_db.contract_address
		contract_abi = contract_db.contract_abi 		
		print(f"[{datetime.now().strftime('%H:%M:%S')}] -> DB Retrieved. Contract Address: {contract_address}")
		

		if not web3.is_connected():
			raise ConnectionError("Web3 not connected. Check RPC URL.")
			
		contract = web3.eth.contract(address=contract_address, abi=contract_abi)
		nonce = web3.eth.get_transaction_count(DEPLOYER_ADDRESS)
		
		print(f"[{datetime.now().strftime('%H:%M:%S')}] 2. Web3 Setup OK. Nonce: {nonce}. Deployer: {DEPLOYER_ADDRESS}")
		
		# --- Determine Action and Recipient ---
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

		# --- 4. Build and Sign Transaction ---
		# NOTE: This placeholder value will need to be the full amount in escrow
		# For now, we will use a small placeholder to demonstrate the function call
		AMOUNT_TO_SEND = web3.to_wei(0.001, 'ether') 
		print(f"[{datetime.now().strftime('%H:%M:%S')}] 4. Building Tx data (Value: {web3.from_wei(AMOUNT_TO_SEND, 'ether')} ETH)")
		
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
		
	except Contract.DoesNotExist:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Contract ID {contract_id} not found in database.")
	except ConnectionError as e:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] CRITICAL ERROR: Web3 connection failed. Details: {e}")
	except ContractLogicError as e:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: Solidity contract execution failed. Details: {e}")
	except Exception as e:
		print(f"[{datetime.now().strftime('%H:%M:%S')}] UNEXPECTED ERROR during contract action: {e}")
		
	# --- 8. Final Redirect ---
	print(f"[{datetime.now().strftime('%H:%M:%S')}] 8. Redirecting user back to active view.")
	print(f"===================================================================")
	return HttpResponseRedirect(reverse('active'))
    
