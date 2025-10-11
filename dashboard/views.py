from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from django.utils import timezone 
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.db import models
from django.db.models import Avg, Min, Max
from django.http import HttpResponse, Http404, JsonResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.platypus import KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

import random 
import json 
from datetime import datetime
from web3 import Web3
from solcx import compile_source, install_solc, set_solc_version

from dashboard.models import Contract, IoTDevice, IoTDataHistory, Alert, IoTData, Product
from accounts.models import CustomUser
from dashboard.forms import ProductForm

import os
from dotenv import load_dotenv # NEW
from eth_account import Account # NEW
from accounts.models import CustomUser
from web3.exceptions import ContractLogicError
load_dotenv() 



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


def _get_current_temp(threshold_float):
    """Mocks a live temperature reading based on the threshold."""
    current_temp_mock = IoTData.objects.latest('recorded_at').temperature
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
    # PASS THE FULL STRING ADDRESSES DIRECTLY:
    buyer_address="0x13994f68615c9c578745339188cc165f4ef9959c",   # <-- CORRECT
    seller_address="0x1A947d2CfcF6a4EF915a4049077BfE9acc7Ddb0D", # <-- CORRECT 
    
    product_name=ProductName,
    quantity=Quantity, 
    price=PaymentAmount,
    start_date=timezone.now(),
    end_date=timezone.now() + timezone.timedelta(days=7),
    
      
    contract_address=contract_address,      
    contract_abi=abi,           # JSONField automatically handles the Python object 'abi'
    
    max_temp=5.0, 
    status='Active'
    )
    print("11. Database save complete. Process SUCCESSFUL.")
    
    
    return contract_address

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

def download_contract_report(request, contract_id):
    # Get contract and related IoT data
    contract = get_object_or_404(Contract, pk=contract_id)
    buyer_name=contract.buyer.full_name if contract.buyer else "N/A"
    buyer_email=contract.buyer.email if contract.buyer else "N/A"
    buyer_wallet=contract.buyer.m_address if contract.buyer else "N/A"
    seller_name=contract.seller.full_name if contract.seller else "N/A"
    seller_email=contract.seller.email if contract.seller else "N/A"
    seller_wallet=contract.seller.m_address if contract.seller else "N/A"

    iot_summary = IoTData.objects.filter(device_id=1).aggregate(
        avg_temp=Avg('temperature'),
        min_temp=Min('temperature'),
        max_temp=Max('temperature')
    )

    # Prepare response
    response = HttpResponse(content_type='application/pdf')
    filename = f"Soltrack_Contract_{contract.contract_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Create PDF with margins
    doc = SimpleDocTemplate(
        response, 
        pagesize=A4,
        rightMargin=40, 
        leftMargin=40,
        topMargin=50, 
        bottomMargin=40
    )

    # Enhanced Styles
    styles = getSampleStyleSheet()
    
    # Title style with modern color
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        textColor=colors.HexColor("#2563eb"),
        alignment=TA_CENTER,
        spaceAfter=8,
        spaceBefore=10
    )
    
    # Subtitle style
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=colors.HexColor("#64748b"),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    # Section header with modern styling
    section_header = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        textColor=colors.HexColor("#1e40af"),
        spaceBefore=18,
        spaceAfter=10,
        borderColor=colors.HexColor("#3b82f6"),
        borderWidth=0,
        borderPadding=5,
        leftIndent=0
    )
    
    # Info box style
    info_box_style = ParagraphStyle(
        'InfoBox',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor("#475569"),
        alignment=TA_RIGHT,
        spaceAfter=10
    )
    
    # Normal text
    normal_text = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1e293b")
    )

    # Content list
    content = []

    # Header Section with Logo
    header_data = []
    try:
        logo_path = "static/img/logo_trans.png"
        logo = Image(logo_path, width=1.2*inch, height=1.2*inch)
        header_data = [[logo, Paragraph("<b>SOLTRACK</b><br/><font size=9>Smart Logistics & Escrow Platform</font>", 
                                       ParagraphStyle('LogoText', parent=normal_text, fontSize=14, 
                                                     textColor=colors.HexColor("#2563eb"), alignment=TA_RIGHT))]]
        header_table = Table(header_data, colWidths=[2*inch, 4*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        content.append(header_table)
        content.append(Spacer(1, 10))
    except Exception:
        content.append(Paragraph("<b>SOLTRACK</b>", title_style))
        content.append(Paragraph("Smart Logistics & Escrow Platform", subtitle_style))

    # Title
    content.append(Paragraph("Contract Completion Report", title_style))
    content.append(Paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))
    
    # Divider line
    content.append(Spacer(1, 5))
    divider = Table([['']], colWidths=[6.7*inch])
    divider.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 2, colors.HexColor("#3b82f6")),
    ]))
    content.append(divider)
    content.append(Spacer(1, 15))

    # Status Badge
    status_color = colors.HexColor("#10b981") if contract.status == "Complete" else colors.HexColor("#ef4444")
    status_badge = Table([[Paragraph(f"<b>Status: {contract.status}</b>", 
                                    ParagraphStyle('Status', parent=normal_text, 
                                                  textColor=colors.white, alignment=TA_CENTER))]], 
                        colWidths=[2*inch])
    status_badge.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), status_color),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', (0, 0), (-1, -1), 5),
    ]))
    content.append(status_badge)
    content.append(Spacer(1, 20))

    # Section 1: Contract Overview
    content.append(Paragraph("📋 Contract Overview", section_header))
    contract_data = [
        ['Contract ID', f"#{contract.contract_id}"],
        ['Product Name', contract.product_name],
        ['Quantity', f"{contract.quantity} units"],
        ['Total Value', f"{contract.price} ETH"],
        ['Deployment Date', contract.start_date.strftime('%B %d, %Y') if hasattr(contract, 'start_date') else "N/A"],
        ['Completion Date', contract.end_date.strftime('%B %d, %Y') if hasattr(contract, 'end_date') else "N/A"],
    ]
    contract_table = Table(contract_data, colWidths=[2*inch, 4.7*inch])
    contract_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#1e40af")),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    content.append(contract_table)
    content.append(Spacer(1, 15))

    # Section 2: Blockchain Information
    content.append(Paragraph("⛓️ Blockchain Information", section_header))
    blockchain_data = [
        ['Contract Address', contract.contract_address or "Not Deployed"],
        ['Network', getattr(contract, 'network', 'Sepolia Testnet')],
    ]
    blockchain_table = Table(blockchain_data, colWidths=[2*inch, 4.7*inch])
    blockchain_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#1e40af")),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Courier'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    content.append(blockchain_table)
    content.append(Spacer(1, 15))

    # Section 3: Parties Involved
    content.append(Paragraph("👥 Parties Involved", section_header))
    
    # Buyer Section
    buyer_header = Table([['BUYER INFORMATION']], colWidths=[6.7*inch])
    buyer_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#dbeafe")),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor("#1e40af")),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    content.append(buyer_header)
    
    buyer_data = [
        ['Name', buyer_name],
        ['Email', buyer_email],
        ['Wallet Address', buyer_wallet],
    ]
    buyer_table = Table(buyer_data, colWidths=[2*inch, 4.7*inch])
    buyer_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    content.append(buyer_table)
    content.append(Spacer(1, 10))
    
    # Seller Section
    seller_header = Table([['SELLER INFORMATION']], colWidths=[6.7*inch])
    seller_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#dcfce7")),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor("#166534")),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    content.append(seller_header)
    
    seller_data = [
        ['Name', seller_name],
        ['Email', seller_email],
        ['Wallet Address', seller_wallet],
    ]
    seller_table = Table(seller_data, colWidths=[2*inch, 4.7*inch])
    seller_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    content.append(seller_table)
    content.append(Spacer(1, 15))

    # Section 4: IoT Monitoring Summary
    content.append(Paragraph("🌡️ Temperature Monitoring Summary", section_header))
    
    # Determine temperature status
    temp_status = "✅ Optimal"
    temp_color = colors.HexColor("#10b981")
    if iot_summary.get('avg_temp'):
        if iot_summary['avg_temp'] < -20 or iot_summary['avg_temp'] > 8:
            temp_status = "⚠️ Out of Range"
            temp_color = colors.HexColor("#f59e0b")
    
    iot_data = [
        ['Average Temperature', f"{iot_summary['avg_temp']:.2f}°C" if iot_summary.get('avg_temp') else "N/A"],
        ['Minimum Temperature', f"{iot_summary['min_temp']:.2f}°C" if iot_summary.get('min_temp') else "N/A"],
        ['Maximum Temperature', f"{iot_summary['max_temp']:.2f}°C" if iot_summary.get('max_temp') else "N/A"],
        ['Final Temperature', f"{getattr(contract, 'current_temp', 'N/A')}"],
        ['Temperature Status', temp_status],
    ]
    iot_table = Table(iot_data, colWidths=[2.5*inch, 4.2*inch])
    iot_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#1e40af")),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('BACKGROUND', (0, 4), (-1, 4), temp_color),
        ('TEXTCOLOR', (0, 4), (-1, 4), colors.white),
    ]))
    content.append(iot_table)
    content.append(Spacer(1, 20))

    # Footer Section
    content.append(Spacer(1, 20))
    footer_divider = Table([['']], colWidths=[6.7*inch])
    footer_divider.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
    ]))
    content.append(footer_divider)
    content.append(Spacer(1, 10))
    
    footer_text = f"""
    <para alignment="center">
    <font size=9 color="#64748b">
    <b>This report is automatically generated by Soltrack Smart Logistics Platform</b><br/>
    Verified and secured by blockchain technology on Ethereum Sepolia Testnet<br/>
    Document ID: SLT-{contract.contract_id}-{datetime.now().strftime('%Y%m%d%H%M')}<br/>
    © {datetime.now().year} Soltrack. All rights reserved.
    </font>
    </para>
    """
    content.append(Paragraph(footer_text, normal_text))

    # Build PDF
    doc.build(content)
    return response

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



def active_view(request):
    
    # --- Live Data Fetch from Supabase via Django ORM ---
    try:
        contracts_queryset = Contract.objects.filter(status__in=['Active', 'Ongoing', 'In Transit']).all()
    except Exception as e:
        print(f"Database query error: {e}")
        contracts_queryset = []

    active_contracts = []
    
    for contract_instance in contracts_queryset:
        
        # 1. Get the temperature threshold (now a FloatField from the DB)
        temp_threshold_float = contract_instance.max_temp
        
        # 2. Get/Mock the current temperature
        current_temp_str, current_temp_float = _get_current_temp(temp_threshold_float)
        
        # 3. Determine status
        if contract_instance.status == 'Ongoing':
            status = 'Ongoing'
            status_class = 'info'
        elif contract_instance.status == 'In Transit':
            status = 'In Transit'
            status_class = 'warning'
        else:
            status = 'Active'
            status_class = 'success'
        
        if current_temp_float > temp_threshold_float:
            status = 'Alert' 
            status_class = 'warning'
        
        # 4. Assemble final data object
        active_contracts.append({
            'contract': contract_instance,
            
            'buyer_name': contract_instance.buyer.full_name if contract_instance.buyer else "N/A",
            'seller_name': contract_instance.seller.full_name if contract_instance.seller else "N/A",
   
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
def product_manager_view(request):
    if request.user.role.lower() != "seller":
        messages.error(request, "Access denied. Only sellers can manage products.")
        return redirect("overview")

    products = Product.objects.filter(seller=request.user).order_by("-created_at")
    return render(request, "dashboard/product_manager.html", {"products": products})


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
    return render(request, "dashboard/product_form.html", {"form": form, "title": "Add Product"})


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
    return render(request, "dashboard/product_form.html", {"form": form, "title": "Edit Product"})


@login_required(login_url='login')
def product_delete_view(request, pk):
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    product.delete()
    messages.success(request, "🗑️ Product deleted successfully.")
    return redirect("product_manager")
    
    
    
    
    
@login_required(login_url='login')
def ongoing_view(request):
    user = request.user
    user_role = request.session.get("user_role", "").lower()
    user_id = request.session.get("user_id")
    # 🧩 Filter contracts based on role
    if user_role == "buyer":
        contracts = Contract.objects.filter(status__in=["Ongoing", "In Transit"], buyer_id=user_id)
    elif user_role == "seller":
        contracts = Contract.objects.filter( status__in=["Ongoing", "In Transit"], seller_id=user_id)
    else:  # admin
        contracts = Contract.objects.filter(status__in=["Ongoing", "In Transit"])

    # 🌡️ Prepare ongoing shipment data
    ongoing_data = []
    for contract in contracts:
        latest_temp = (
            IoTData.objects.filter(device_id=1).latest('recorded_at').temperature
        )

        ongoing_data.append({
            "contract_id": contract.contract_id,
            "product_name": contract.product_name,
            "temperature": latest_temp,
            "status": contract.status,
            "threshold": contract.max_temp,
            "buyer_name": contract.buyer.full_name if contract.buyer else "—",
            "seller_name": contract.seller.full_name if contract.seller else "—",
        })

    context = {
        "ongoing_data": ongoing_data,
        "user_role": user_role,
    }

    return render(request, "dashboard/ongoing.html", context)

# In views.py

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