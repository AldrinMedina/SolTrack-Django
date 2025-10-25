from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db.models import Avg, Min, Max
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from datetime import datetime
from dashboard.models import Contract, IoTDataHistory
from accounts.models import CustomUser

def download_contract_report(request, contract_id):
	# --- Retrieve Contract + Parties Info ---
	contract = get_object_or_404(Contract, pk=contract_id)
	buyer_name = contract.buyer.full_name if contract.buyer else "N/A"
	buyer_email = contract.buyer.email if contract.buyer else "N/A"
	buyer_wallet = contract.buyer.m_address if contract.buyer else "N/A"
	seller_name = contract.seller.full_name if contract.seller else "N/A"
	seller_email = contract.seller.email if contract.seller else "N/A"
	seller_wallet = contract.seller.m_address if contract.seller else "N/A"

	# --- IoT Summary (From IoTDataHistory for this contract) ---
	iot_summary = IoTDataHistory.objects.filter(contract=contract).aggregate(
		avg_temp=Avg('avg_temp'),
		min_temp=Min('min_temp'),
		max_temp=Max('max_temp')
	)

	# --- PDF Setup ---
	response = HttpResponse(content_type='application/pdf')
	filename = f"Soltrack_Contract_{contract.contract_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
	response['Content-Disposition'] = f'attachment; filename="{filename}"'

	doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=50, bottomMargin=40)
	styles = getSampleStyleSheet()

	# --- Style Definitions ---
	title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor("#2563eb"), alignment=TA_CENTER)
	subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#64748b"), alignment=TA_CENTER)
	section_header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor("#1e40af"), spaceBefore=15, spaceAfter=8)
	normal_text = ParagraphStyle('NormalText', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor("#1e293b"))

	content = []

	# --- Header ---
	try:
		logo = Image("static/img/logo_trans.png", width=1.2*inch, height=1.2*inch)
		header_table = Table([[logo, Paragraph("<b>SOLTRACK</b><br/><font size=9>Smart Logistics & Escrow Platform</font>", normal_text)]],
							 colWidths=[1.8*inch, 4.8*inch])
		header_table.setStyle(TableStyle([
			('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
			('ALIGN', (1, 0), (1, 0), 'RIGHT'),
		]))
		content.append(header_table)
	except Exception:
		content.append(Paragraph("<b>SOLTRACK</b>", title_style))
	content.append(Spacer(1, 10))

	# --- Title ---
	content.append(Paragraph("Contract Completion Report", title_style))
	content.append(Paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))
	content.append(Spacer(1, 15))

	# --- Contract Info ---
	content.append(Paragraph("Contract Overview", section_header))
	contract_data = [
		['Contract ID', f"#{contract.contract_id}"],
		['Product Name', contract.product_name],
		['Quantity', f"{contract.quantity} units"],
		['Total Value', f"{contract.price} ETH"],
		['Deployment Date', contract.start_date.strftime('%B %d, %Y') if contract.start_date else "N/A"],
		['Completion Date', contract.end_date.strftime('%B %d, %Y') if contract.end_date else "N/A"],
		['Status', contract.status],
	]
	contract_table = Table(contract_data, colWidths=[2.2*inch, 4.5*inch])
	contract_table.setStyle(TableStyle([
		('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
		('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#1e40af")),
		('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
		('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
		('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
		('TOPPADDING', (0, 0), (-1, -1), 6),
		('BOTTOMPADDING', (0, 0), (-1, -1), 6),
	]))
	content.append(contract_table)
	content.append(Spacer(1, 10))

	# --- Parties ---
	content.append(Paragraph("Parties Involved", section_header))
	buyer_user = seller_user = deployer_user = None
	buyer_org = seller_org = deployer_org = "N/A"
	buyer_wallet = seller_wallet = deployer_wallet = "N/A"
	try:
    # --- Buyer ---
		buyer_user = CustomUser.objects.filter(user_id=contract.buyer_id).first()
		if buyer_user:
			buyer_org = getattr(buyer_user, "organization", "N/A")
			buyer_wallet = getattr(buyer_user, "m_address", contract.buyer_address or "N/A")
		else:
			buyer_wallet = contract.buyer_address or "N/A"

    # --- Seller ---
		seller_user = CustomUser.objects.filter(user_id=contract.seller_id).first()
		if seller_user:
			seller_org = getattr(seller_user, "organization", "N/A")
			seller_wallet = getattr(seller_user, "m_address", contract.seller_address or "N/A")
		else:
			seller_wallet = contract.seller_address or "N/A"

    # --- Deployer (always 10th user by user_id order) ---
		deployer_user = CustomUser.objects.all().order_by('user_id')[9]  # 10th user (index 9)
		if deployer_user:
			deployer_org = getattr(deployer_user, "organization", "N/A")
			deployer_wallet = getattr(deployer_user, "m_address", "N/A")
	except Exception as e:
		print(f"[WARN] Could not fetch organization data: {e}")

		
	parties_data = [
		['Buyer', buyer_org],
		['Buyer Wallet', buyer_wallet],
		['Seller', seller_org],
		['Seller Wallet', seller_wallet],
		#['Deployer', deployer_org],
		#['Deployer Wallet', deployer_wallet],
	]

	parties_table = Table(parties_data, colWidths=[2.5*inch, 4.2*inch])
	parties_table.setStyle(TableStyle([
		('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f8fafc")),
		('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
		('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
		('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
		('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
		('TOPPADDING', (0, 0), (-1, -1), 6),
		('BOTTOMPADDING', (0, 0), (-1, -1), 6),
	]))
	content.append(parties_table)
	content.append(Spacer(1, 15))

	# --- IoT Summary ---
	content.append(Paragraph("Temperature Monitoring Summary", section_header))
	temp_status = "Optimal"
	temp_color = colors.HexColor("#10b981")
	if iot_summary.get('avg_temp') and (iot_summary['avg_temp'] < -20 or iot_summary['avg_temp'] > 8):
		temp_status = "Out of Range"
		temp_color = colors.HexColor("#e80505")
	final_temp = (
		f"{iot_summary['avg_temp']:.2f}°C" if iot_summary.get('avg_temp') else "N/A"
	)
	iot_data = [
		['Average Temperature', f"{iot_summary['avg_temp']:.2f}°C" if iot_summary.get('avg_temp') else "N/A"],
		['Minimum Temperature', f"{iot_summary['min_temp']:.2f}°C" if iot_summary.get('min_temp') else "N/A"],
		['Maximum Temperature', f"{iot_summary['max_temp']:.2f}°C" if iot_summary.get('max_temp') else "N/A"],
		['Final Temperature', final_temp],
		['Temperature Status', temp_status],
	]
	iot_table = Table(iot_data, colWidths=[2.7*inch, 4*inch])
	iot_table.setStyle(TableStyle([
		('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
		('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
		('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
		('BACKGROUND', (0, 4), (-1, 4), temp_color),
		('TEXTCOLOR', (0, 4), (-1, 4), colors.white),
	]))
	content.append(iot_table)
	content.append(Spacer(1, 20))

	# --- Footer ---
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

	# --- Build PDF ---
	doc.build(content)
	return response
