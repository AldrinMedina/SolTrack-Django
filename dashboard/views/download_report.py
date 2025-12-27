# dashboard/utils/download_report.py
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import inch
from django.http import HttpResponse
from django.utils import timezone

from dashboard.models import Contract, ContractAddresses, IoTDataHistory
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="ReceiptTitle",
    fontSize=18,
    alignment=TA_CENTER,
    spaceAfter=16
))
styles.add(ParagraphStyle(
    name="SectionHeader",
    fontSize=13,
    spaceBefore=18,
    spaceAfter=8,
    textColor=colors.HexColor("#1f2937")
))
styles.add(ParagraphStyle(
    name="Body",
    fontSize=9,
    leading=13,
    alignment=TA_LEFT
))
styles.add(ParagraphStyle(
    name="Small",
    fontSize=8,
    leading=11,
    textColor=colors.grey
))

def kv_table(rows):
    return Table(
        rows,
        colWidths=[2.3 * inch, 4.7 * inch],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )

def download_contract_report(request, contract_id):
    contract = Contract.objects.select_related("buyer", "seller").get(pk=contract_id)
    addr = ContractAddresses.objects.filter(contract=contract).first()
    history = IoTDataHistory.objects.filter(contract=contract).first()
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=SolTrack_Receipt_{contract.contract_id}.pdf"

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=48,
        bottomMargin=48,
    )

    story = []
    story.append(Paragraph("SolTrack – Smart Contract Transaction Receipt", styles["ReceiptTitle"]))
    story.append(Paragraph(
        f"Generated on {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        styles["Small"]
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Contract Overview", styles["SectionHeader"]))
    story.append(kv_table([
        ["Contract ID", contract.contract_id],
        ["Product", contract.product_name],
        ["Quantity", contract.quantity],
        ["Price (ETH)", f"{contract.price} ETH"],
        ["Buyer", f"{contract.buyer}"],
        ["Buyer Address", f"({contract.buyer_address})"],
        ["Seller", f"{contract.seller}"],
        ["Seller Address", f"({contract.seller_address})"],
        ["Smart Contract Address", contract.contract_address or "—"],
        ["Status", contract.status],
       
    ] + ([["Refund Reason", contract.rejection_refund_reason]] if contract.status == 'Refunded' else [])))

    story.append(Paragraph("On-Chain Transaction Receipts", styles["SectionHeader"]))

    def tx_block(title,action, tx_hash, value_eth, gas_info, payer):
     gas_used = None
     gas_price_gwei = None
     gas_cost_eth = "—"

     if gas_info and isinstance(gas_info, dict):
        gas_used = gas_info.get("used")
        raw_price = gas_info.get("price")
        if raw_price:
            gas_price_gwei = raw_price / 1e9
        
        raw_cost = gas_info.get("cost")
        if raw_cost:
            gas_cost_eth = f"{raw_cost / 1e18:.6f} ETH"

     return KeepTogether([
        Paragraph(title, styles["Body"]),
        kv_table([
			["Description", action],
            ["Transaction Hash", tx_hash or "—"],
            ["Transferred Value", f"{value_eth} ETH" if value_eth else "0 ETH"],
            ["Gas Cost", gas_cost_eth],
            ["Gas Paid By", payer],
        ])
     ])

    story.append(tx_block(
     "Receipt A – Buyer Escrow Funding",
     f"Buyer sends {contract.final_price} ETH to Deployer",
     addr.init_payment_add if addr else None,
     contract.final_price,
     addr.init_payment_gas if addr else None, # Pass the whole dict
     "Buyer"
    ))

    if contract.status == "Completed":
     story.append(tx_block(
      "Receipt B – Escrow Release to Seller",
      f"Deployer forwards {contract.price} ETH to Seller",
      addr.escrow_final_tx if addr else None,
      contract.price,
      addr.final_payment_gas if addr else None, # Pass the whole dict
      "Deployer (Escrow)"
     ))

    elif contract.status == "Refunded":
     story.append(tx_block(
      "Receipt C – Escrow Refund to Buyer",
      f"Deployer returns {contract.price} ETH to Buyer",

      addr.escrow_final_tx if addr else None,
      contract.price,
      addr.final_payment_gas if addr else None, # Pass the whole dict
      "Deployer (Escrow)"
     ))

    story.append(Paragraph("Gas Fee Responsibility Statement", styles["SectionHeader"]))
    story.append(Paragraph(
        "Each blockchain transaction incurs a network transaction fee (\"Gas Fee\"). "
        "Gas fees are operational costs paid to the blockchain network and are independent "
        "from the principal transaction value held in escrow.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "• Buyer-funded transactions: Gas fees paid directly by the Buyer at time of escrow funding.<br/>"
        "• Escrow-executed transactions: Gas fees paid by the Deployer acting as Escrow Agent.<br/>"
        "• Gas fees are non-refundable and do not alter the escrowed principal amount.",
        styles["Body"]
    ))

    story.append(PageBreak())
    story.append(Paragraph("Transaction Glossary", styles["SectionHeader"]))

    glossary = [
        ("Escrow", "A temporary holding mechanism ensuring conditional transfer of funds."),
        ("Gas", "A blockchain transaction processing fee paid to network validators."),
        ("Gas Cost", "Gas Used × Gas Price; paid separately from transferred value."),
        ("Transaction Hash", "A unique cryptographic identifier for an on-chain transaction."),
        ("Principal Amount", "The escrowed ETH value exclusive of gas fees."),
    ]

    story.append(kv_table([[k, v] for k, v in glossary]))
    #story.append(Spacer(1, 25))
   # story.append(Paragraph("Environmental Monitoring Summary", styles["SectionHeader"]))

    #if history:
        # Prepare the summary data
      #  iot_summary = [
       #     ["Average Temperature", f"{history.avg_temp:.2f}°C"],
        #    ["Minimum Temperature", f"{history.min_temp:.2f}°C"],
         #   ["Maximum Temperature", f"{history.max_temp:.2f}°C"],
          #  ["SLA Compliance Result", history.result],
           # ["Data Aggregated At", history.recorded_at.strftime('%Y-%m-%d %H:%M:%S')]
        #]
        
        # Style the summary table
        #t_history = Table(iot_summary, colWidths=[2.5 * inch, 4.0 * inch])
        #t_history.setStyle(TableStyle([
         #   ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f8fafc")), # Match your blue/grey style
          #  ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
           # ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            #('FONTNAME', (0, 1), (1, -1), 'Helvetica'),
            #('TEXTCOLOR', (1, 3), (1, 3), colors.green if history.result == 'Normal' else colors.red),
            #('LEFTPADDING', (0, 0), (-1, -1), 12),
            #('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            #('TOPPADDING', (0, 0), (-1, -1), 8),
        #]))
       # story.append(t_history)
    #else:
     #   story.append(Paragraph("No aggregated environmental history available for this contract.", styles["Body"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "This document constitutes a full transactional disclosure for academic, legal, "
        "and accounting verification purposes.",
        styles["Small"]
    ))

    doc.build(story)
    return response
