from django.shortcuts import render
from django.utils import timezone 
from django.http import HttpResponseRedirect
from django.urls import reverse
import random 
import json 
import datetime
from web3 import Web3
from solcx import compile_source
from .models import Contract 
import os
from dotenv import load_dotenv # NEW
from eth_account import Account # NEW
load_dotenv() 

SEPOLIA_URL = os.getenv("SEPOLIA_RPC_URL")
DEPLOYER_PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY")
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
def _get_current_temp(threshold_float):
    """Mocks a live temperature reading based on the threshold."""
    current_temp_mock = random.uniform(threshold_float - 1, threshold_float + 2)
    return f"{current_temp_mock:.1f}°C", current_temp_mock


# --- CONTRACT DEPLOYMENT LOGIC (NOW USES CHAR(42) ADDRESSES) ---

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
        'gas': 2000000 
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
        'gas': 2000000 
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
    latest_iot_contract = iot_devices.objects.aggregate(max_id=models.Max('contract_id'))['max_id']
    next_contract_id = (latest_iot_contract or 0) + 1
    print(f"10. Saving contract details to database (Attempting ID: {next_contract_id}).")
    
    new_contract = Contract.objects.create(
    contract_id=next_contract_id,
    # PASS THE FULL STRING ADDRESSES DIRECTLY:
    buyer_address=BuyerAddress,   # <-- CORRECT
    seller_address=SellerAddress, # <-- CORRECT 
    
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
def overview_view(request):
    return render(request, "dashboard/overview.html")


def active_view(request):
    
    # --- Live Data Fetch from Supabase via Django ORM ---
    try:
        contracts_queryset = Contract.objects.filter(status='Active').all()
    except Exception as e:
        print(f"Database query error: {e}")
        contracts_queryset = []

    active_contracts = []
    
    for contract_instance in contracts_queryset:
        
        # 1. Get the temperature threshold (now a FloatField from the DB)
        temp_threshold_float = contract_instance.temperature_threshold
        
        # 2. Get/Mock the current temperature
        current_temp_str, current_temp_float = _get_current_temp(temp_threshold_float)
        
        # 3. Determine status
        status = 'Active'
        status_class = 'success'
        
        if current_temp_float > temp_threshold_float:
            status = 'Alert' 
            status_class = 'warning'
        
        # 4. Assemble final data object
        active_contracts.append({
            'contract': contract_instance,
            
   
            'current_temp': current_temp_str, 
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
            # 1. Get ALL required data from the POST request
            buyer_address = request.POST.get('buyer_address')
            seller_address = request.POST.get('seller_address')
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
            'gas': 2000000 
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
    
    
    
    
    
    
    
    
def ongoing_view(request):
    return render(request, 'dashboard/ongoing.html')

# In views.py

def completed_view(request):
    try:
        contracts_queryset = Contract.objects.filter(status='Completed').all()
    except Exception as e:
        print(f"Database query error: {e}")
        contracts_queryset = []

    completed_contracts = []
    
    for contract_instance in contracts_queryset:
        status = 'Complete'
        status_class = 'primary'
        temp_threshold_float = contract_instance.temperature_threshold
        final_temp_str = f"{temp_threshold_float - 0.5:.1f}°C" 

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

def alerts_view(request):
    return render(request, 'dashboard/alerts.html')

def analytics_view(request):
    return render(request, 'dashboard/analytics.html')
