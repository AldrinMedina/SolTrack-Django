# dashboard/views/contract_functions.py
import json
import os
from pathlib import Path
from django.utils import timezone
import solcx
from solcx import install_solc, set_solc_version, compile_files
from web3 import Web3
from decimal import Decimal
from .notify_functions import create_alert
from django.db import transaction
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg, Min, Max 
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from ..models import Contract, IoTDevice, ContractAddresses, ShipmentLog, IoTData, IoTDataHistory
from .config import (
    web3,
    DEPLOYER_PRIVATE_KEY,
    DEPLOYER_ADDRESS,
    SOLC_VERSION,
    CHAIN_ID,
    GAS_PRICE_GWEI,
)
def toggle_other_reason(request):
    reason_code = request.GET.get("reason_code")

    if reason_code == "OTHER":
        html = render_to_string("dashboard/partials/other_reason_field.html")
        return HttpResponse(html)

    return HttpResponse("")
def collate_iot_data_to_history(contract):
    device = contract.IoT_Assigned
    if not device:
        return None
    queryset = IoTData.objects.filter(contract=contract)
  
    if queryset.exists():
        stats = queryset.aggregate(
            avg_t=Avg('temperature'),
            min_t=Min('temperature'),
            max_t=Max('temperature')
        )

        result_status = "Normal"
        if stats['max_t'] > contract.max_temp or stats['min_t'] < contract.min_temp:
            result_status = "Breached"

        history = IoTDataHistory.objects.create(
            contract=contract,
            avg_temp=round(stats['avg_t'], 2),
            min_temp=round(stats['min_t'], 2),
            max_temp=round(stats['max_t'], 2),
            result=result_status
        )
        return history
    
    return None  
     
def resolve_contract( contract_id: int, reason: str, action: str, source: str = "Manual", execute_chain: bool = False ):
    with transaction.atomic():
        contract = Contract.objects.select_for_update().get(pk=contract_id)
        assigned_device = contract.IoT_Assigned 

        if action == "reject":
            if contract.status != "Pending":
                raise ValueError("Only Pending contracts may be rejected.")

            contract.status = "Rejected"
            contract.rejection_refund_reason = reason
            contract.end_date = timezone.now()
            contract.save(update_fields=["status", "rejection_refund_reason", "end_date"])

            create_shipment_log(contract, f"Contract rejected. Reason: {reason}")
            create_alert(contract=contract, device=None, alert_type="Rejected", message=reason)
            return True

        elif action in ["refund", "complete"]:
            if contract.status != "Active":
                raise ValueError(f"Contract must be Active to {action}.")

            if execute_chain:
                success = execute_onchain_action(contract, action)
                if not success:
                    raise RuntimeError(f"On-chain {action} failed")    

            collate_iot_data_to_history(contract)
            contract.status = "Refunded" if action == "refund" else "Completed"
            contract.rejection_refund_reason = reason
            contract.end_date = timezone.now()
            contract.save(update_fields=["status", "rejection_refund_reason", "end_date"])
            detach_iot_device_from_contract(contract)

            log_msg = f"Contract {action}ed ({source}). Reason: {reason}"
            create_shipment_log(
                contract, 
                log_msg, 
                log_type="Critical" if action == "refund" else "System"
            )

            create_alert(
                contract=contract,
                device=assigned_device, # Use the handle we saved at the start
                alert_type=f"Contract {action.capitalize()}ed",
                message=reason,
                severity="Critical" if action == "refund" else "Info",
                category="Financial"
            )

            return True
        else:
            raise ValueError("Invalid contract resolution action.")
            
@login_required
def manual_refund_contract(request, contract_id):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=405)

    reason_code = request.POST.get("reason_code")
    reason_text = request.POST.get("reason_text", "")

    if reason_code == "other":
        reason = f"{reason_text}" if reason_text else "Not specified"
    else:
        label = reason_code.replace('_', ' ').title()
        reason = f"{label}: {reason_text}" if reason_text else label

    try:
        resolve_contract(
            contract_id=contract_id,
            action="refund",
            reason=reason,
            source="Manual",
            execute_chain=True  
        )
        contract = get_object_or_404(Contract, pk=contract_id)
        resp = render(request, "dashboard/partials/contract_card.html", {
            "contract": contract,
        })
        resp["HX-Toast"] = "Refund successful"
        resp["HX-Trigger"] = "closeModal, reloadOngoingList" # Refresh the lists
        return resp
    except Exception as e:
        return HttpResponse(f"Refund Error: {str(e)}", status=400)

    return JsonResponse({"ok": True})
    
@login_required
def reject_contract(request, contract_id):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=405)

    reason_code = request.POST.get("reason_code")
    reason_text = request.POST.get("reason_text", "")

    if reason_code == "other":
        reason = f"Reason: {reason_text}" if reason_text else "Reason: Not specified"
    else:
        label = reason_code.replace('_', ' ').title()
        reason = f"{label}: {reason_text}" if reason_text else label

    try:
        resolve_contract(
            contract_id=contract_id,
            reason=reason,      
            action="reject",
            source="Manual"
        )
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"ok": True})

def gas_dict(receipt):
    return {
        "used": receipt.gasUsed,
        "price": receipt.effectiveGasPrice,
        "cost": receipt.gasUsed * receipt.effectiveGasPrice
    }
    
def _load_solidity_contract(sol_path=None):
	if sol_path:
		sol_path = Path(sol_path)
	else:
		sol_path = Path(__file__).with_name("Contract.sol")

	if not sol_path.exists():
		raise FileNotFoundError(f"Solidity file missing: {sol_path}")

	try:
		set_solc_version(SOLC_VERSION)
	except Exception:
		install_solc(SOLC_VERSION)
		set_solc_version(SOLC_VERSION)

	compiled = compile_files([str(sol_path)], output_values=["abi", "bin"])
	print("Compiled keys:", compiled.keys())
	target_key = None
	for k in compiled.keys():
		if k.endswith(":ShipmentEscrow"):
			target_key = k
			break

	if not target_key:
		raise ValueError("ShipmentEscrow not found in compiled contracts!")
	abi = compiled[target_key]["abi"]
	bytecode = compiled[target_key]["bin"]
	return abi, bytecode

def create_shipment_log(contract, message, device=None, log_type="System"):
    try:
        ShipmentLog.objects.create(
            contract=contract,
            device=device,
            log_time=timezone.now(),
            message=message,
            log_type=log_type,
        )
    except Exception as e:
        print(f"[LOGGING ERROR] Could not create log for contract {contract.contract_id}: {e}")
def _get_contract_instance(contract_db: Contract):
	if not contract_db.contract_address or not contract_db.contract_abi:
		return None

	try:
		abi = json.loads(contract_db.contract_abi)
	except Exception:
		abi = contract_db.contract_abi

	return web3.eth.contract(
		address=Web3.to_checksum_address(contract_db.contract_address),
		abi=abi
	)

def _build_and_send_tx(function_call, priv_key, sender_addr, value_wei=0, gas_limit=None):
    try:
        sender = Web3.to_checksum_address(sender_addr)
        nonce = web3.eth.get_transaction_count(sender, 'pending')
        fee_history = web3.eth.fee_history(1, 'latest', [25.0])
        base_fee = fee_history['baseFeePerGas'][-1]
        priority_fee = web3.to_wei(2, 'gwei') 

        tx_params = {
            "from": sender,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "maxFeePerGas": (base_fee * 2) + priority_fee, 
            "maxPriorityFeePerGas": priority_fee,
        }

        if gas_limit:
            tx_params["gas"] = gas_limit
        else:
            try:
                tx_params["gas"] = function_call.estimate_gas({"from": sender, "value": value_wei}) + 5000
            except Exception:
                tx_params["gas"] = 500000

        if value_wei and value_wei > 0:
            tx_params["value"] = int(value_wei)

        tx = function_call.build_transaction(tx_params)
        signed = web3.eth.account.sign_transaction(tx, priv_key)
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)

        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        return receipt

    except Exception as e:
        print(f"[TX ERROR] Transaction failed or timed out: {e}")
        return None
		
def deploy_contract_on_chain(contract: Contract, sol_file_path=None, contract_name="ShipmentEscrow", solc_version=None):
    if solc_version:
        global SOLC_VERSION
        SOLC_VERSION = solc_version

    if not DEPLOYER_PRIVATE_KEY or not DEPLOYER_ADDRESS:
        raise EnvironmentError("Deployer private key / address not configured")

    abi, bytecode = _load_solidity_contract(sol_file_path)
    ContractFactory = web3.eth.contract(abi=abi, bytecode=bytecode)

    price_wei = int(Decimal(contract.price) * 10**18)

    buyer_addr = Web3.to_checksum_address(contract.buyer_address)
    seller_addr = Web3.to_checksum_address(contract.seller_address)

    constructor_args = (
        buyer_addr,
        seller_addr,
        price_wei,
        int(contract.min_temp),
        int(contract.max_temp),
        int(contract.temperature_time),
        contract.product_name,
        int(contract.quantity),
    )

    tx_dict = ContractFactory.constructor(*constructor_args).build_transaction({
        "from": Web3.to_checksum_address(DEPLOYER_ADDRESS),
        "nonce": web3.eth.get_transaction_count(Web3.to_checksum_address(DEPLOYER_ADDRESS)),
        "gas": 4_000_000,
        "gasPrice": web3.to_wei(GAS_PRICE_GWEI, "gwei"),
    })

    signed = web3.eth.account.sign_transaction(tx_dict, DEPLOYER_PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

    ContractAddresses.objects.update_or_create(
        contract=contract,
        defaults={
            "contract_address": receipt.contractAddress,
            "contract_tx": tx_hash.hex(),
            "contract_gas": gas_dict(receipt)
        }
    )

    contract_address = receipt.contractAddress
    abi_json = json.dumps(abi)

    return contract_address, abi_json, receipt


def seller_activate_on_chain(contract_db: Contract, seller_private_key: str):
    contract = _get_contract_instance(contract_db)
    if not contract:
        return False, "Missing ABI or contract address"

    seller_addr = Web3.to_checksum_address(contract_db.seller_address)

    try:
        func = contract.functions.activateShipment()
        receipt = _build_and_send_tx(func, seller_private_key, seller_addr)

        if receipt is None or receipt.status == 0:
            return False, "Activation failed on-chain"

        ContractAddresses.objects.update_or_create(
            contract_id=contract_db.contract_id,
            defaults={
                "escrow_init_tx": receipt.transactionHash.hex(),
                "escrow_init_gas": gas_dict(receipt)
            }
        )
        return True, receipt

    except Exception as e:
        print("Seller activation failed:", e)
        return False, str(e)
		
def execute_onchain_action(contract_db: Contract, action: str):
    contract = _get_contract_instance(contract_db)
    if not contract:
        print("[ERROR] Missing contract instance")
        return False

    addr_rec, _ = ContractAddresses.objects.get_or_create(contract=contract_db)
    price_wei = int(contract_db.price * (10**18)) 

    try:
        if action == "complete":
            func = contract.functions.completeShipment()
            receipt = _build_and_send_tx(func, DEPLOYER_PRIVATE_KEY, DEPLOYER_ADDRESS)
            if not receipt:
                return False 

            addr_rec.final_payment_add = receipt.transactionHash.hex()
            addr_rec.final_payment_gas = gas_dict(receipt)
            payout_receipt = send_payment(contract_db.seller_address, price_wei) # <-- Returns receipt or None
            
            if payout_receipt is None:
                return False
            create_shipment_log(contract_db, "Contract state set to COMPLETED on-chain.", log_type="TX")
            create_shipment_log(contract_db, f"Final settlement of {contract_db.price} ETH sent to Seller. TX: {payout_receipt.transactionHash.hex()}", log_type="Financial")
            
            addr_rec.escrow_final_tx = payout_receipt.transactionHash.hex()
            addr_rec.escrow_final_gas = gas_dict(payout_receipt)

            addr_rec.save(update_fields=["final_payment_add", "final_payment_gas", "escrow_final_tx", "escrow_final_gas"])
            contract_db.status = "Completed"
            contract_db.end_date = timezone.now()
            contract_db.save(update_fields=["status", "end_date"])
            create_alert(
             contract=contract_db,
             device=contract_db.IoT_Assigned,
             alert_type="Contract Completed",
             message=f"Contract {contract_db.pk} successfully completed.",
             severity="Info",
             category="System"
            )
            detach_iot_device_from_contract(contract_db)
            return True

        elif action == "refund":
            func = contract.functions.refundShipment()
            receipt = _build_and_send_tx(func, DEPLOYER_PRIVATE_KEY, DEPLOYER_ADDRESS)
            if not receipt:
                return False

            addr_rec.final_payment_add = receipt.transactionHash.hex()
            addr_rec.final_payment_gas = gas_dict(receipt)

            final_price_wei = int(contract_db.price * (10**18))
            refund_receipt = refund_payment(contract_db.buyer_address, final_price_wei) 
            
            if refund_receipt is None:
                return False

            create_shipment_log(contract_db, "Contract state set to REFUNDED on-chain.", log_type="TX")
            create_shipment_log(contract_db, f"Full refund of {contract_db.final_price} ETH sent to Buyer. TX: {refund_receipt.transactionHash.hex()}", log_type="Financial")
            addr_rec.escrow_final_tx = refund_receipt.transactionHash.hex()
            addr_rec.escrow_final_gas = gas_dict(refund_receipt)

            addr_rec.save(update_fields=["final_payment_add", "final_payment_gas", "escrow_final_tx", "escrow_final_gas"])

            contract_db.status = "Refunded"
            contract_db.end_date = timezone.now()
            contract_db.save(update_fields=["status", "end_date"])
            create_alert(
             contract=contract_db,
             device=contract_db.IoT_Assigned,
             alert_type="Contract Refunded",
             message=f"Contract {contract_db.pk} has been fully refunded.",
             severity="Critical",
             category="System"
            )
            detach_iot_device_from_contract(contract_db)
            return True

        else:
            print("[ERROR] Unknown action:", action)
            return False

    except Exception as e:
        print("execute_onchain_action error:", e)
        return False

def send_payment(to_address, amount_wei):
    try:
        sender = Web3.to_checksum_address(DEPLOYER_ADDRESS)
        to_addr = Web3.to_checksum_address(to_address)
        print(f"To {to_addr}")
        print(f"Amnt Send {amount_wei}")
        nonce = web3.eth.get_transaction_count(sender)

        tx = {
            "nonce": nonce,
            "to": to_addr,
            "value": int(amount_wei),
            "gas": 21000,
            "gasPrice": web3.to_wei(GAS_PRICE_GWEI, "gwei"),
            "chainId": CHAIN_ID
        }

        signed = web3.eth.account.sign_transaction(tx, DEPLOYER_PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
       
        return receipt

    except Exception as e:
        return None


def refund_payment(to_address, amount_wei):
    return send_payment(to_address, amount_wei)        
		
def attach_iot_device_to_contract(device: IoTDevice, contract_db: Contract):

    device.status = "Activated"
    device.contract_id = contract_db.contract_id 
    device.save(update_fields=["status", "contract_id"])
    contract_db.IoT_Assigned = device
    contract_db.save(update_fields=["IoT_Assigned"])
    

def detach_iot_device_from_contract(contract_db: Contract):
    device = contract_db.IoT_Assigned

    if device:
      
        d_name = device.device_name 
        device.status = "Available"
        device.contract_id = None
        device.save(update_fields=["status", "contract_id"])
        contract_db.IoT_Assigned = None
        contract_db.save(update_fields=["IoT_Assigned"])
        create_shipment_log(
            contract_db,
            f"IoT Device '{d_name}' detached and set back to 'Available'.",
            log_type="System"
        )
    else:
        print(f"[WARN] No device found to detach for contract {contract_db.contract_id}")
