import traceback
from django.utils import timezone
from django.db import transaction
from .contract_functions import (
    deploy_contract_on_chain,
    seller_activate_on_chain,
    attach_iot_device_to_contract,
  
    send_payment
)
from .contract_watchers import (
	start_watcher,
	start_iot_fetcher,
)
from ..models import Contract, IoTDevice, ContractAddresses
from .notify_functions import create_alert
from decimal import Decimal
from web3 import Web3

def activate_contract_task(contract_id, device_id):
    try:

        with transaction.atomic():
            contract = Contract.objects.select_for_update().get(pk=contract_id)

            if contract.status != "Pending":
                print(f"[TASK] Contract {contract_id} already activated")
                return "Already activated"

            device = IoTDevice.objects.select_for_update().get(pk=device_id)
            if device.status != "Available":
                raise Exception("IoT device is not available")

            buyer_pk = contract.buyer.private_key
            seller_pk = contract.seller.private_key

            if not buyer_pk or not seller_pk:
                raise Exception("Missing private keys")

 
        deployed_addr, abi_json, deploy_receipt = deploy_contract_on_chain(contract)

        price_wei = int(Decimal(contract.price) * 10**18)
        service_fee_wei = Web3.to_wei(5, "ether")
        total_escrow = price_wei + service_fee_wei

        escrow_receipt = send_payment(
            to_address=contract.buyer.m_address,
            amount_wei=total_escrow,
        )

 
        ok, seller_receipt = seller_activate_on_chain(contract, seller_pk)
        if not ok:
            raise Exception(seller_receipt)

        with transaction.atomic():
            contract = Contract.objects.select_for_update().get(pk=contract_id)
            device = IoTDevice.objects.select_for_update().get(pk=device_id)

            if contract.status == "Ongoing":
                return "Already activated"

            contract.contract_address = deployed_addr
            contract.contract_abi = abi_json
            contract.start_date = timezone.now()
            contract.status = "Ongoing"
            contract.save(update_fields=["contract_address", "contract_abi", "start_date", "status"])

            addr_rec, _ = ContractAddresses.objects.get_or_create(contract=contract)
            addr_rec.contract_address = deployed_addr
            addr_rec.contract_tx = deploy_receipt.transactionHash.hex()
            addr_rec.escrow_init_tx = escrow_receipt.transactionHash.hex()
            addr_rec.init_payment_add = seller_receipt.transactionHash.hex()
            addr_rec.save()

            attach_iot_device_to_contract(device, contract)

        start_watcher(contract.contract_id)
        start_iot_fetcher(contract.contract_id)

        create_alert(
            contract=contract,
            device=device,
            alert_type="Contract Activated",
            message="Contract successfully activated on-chain.",
            severity="Info",
            category="System",
        )

        print(f"[TASK] Contract {contract_id} activated successfully")
        return "Activated"

    except Exception as e:
        print(f"[TASK] Error activating contract {contract_id}: {e}")
        traceback.print_exc()
        create_alert(
            contract=Contract.objects.filter(pk=contract_id).first(),
            alert_type="Activation Failed",
            message=str(e),
            severity="Critical",
            category="System"
        )
        return None

def refund_contract_task(self, contract_id):
    contract = Contract.objects.get(pk=contract_id)
    execute_onchain_action(contract, "refund")
