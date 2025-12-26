# download_report.py (upgraded)
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db.models import Avg, Min, Max
from django.templatetags.static import static
from django.contrib.staticfiles import finders
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_CENTER
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from django.conf import settings
import os
from dashboard.models import Contract, IoTData, IoTDataHistory
from accounts.models import CustomUser

# --- Helpers -----------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    """Approximate distance in km between two coords."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    # convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    km = 6371 * c
    return km

def format_duration_seconds(secs):
    if secs is None:
        return "N/A"
    if secs < 1:
        return "<1s"
    if secs < 60:
        return f"{int(secs)}s"
    if secs < 3600:
        return f"{int(secs//60)}m {int(secs%60)}s"
    return f"{int(secs//3600)}h {int((secs%3600)//60)}m"

def build_temperature_timeline(readings):
    """
    Build time-range timeline:
      each entry => {"start": datetime, "end": datetime, "temp": float}
    Only emits ranges when temperature changed (tolerance 0.1°C).
    """
    timeline = []
    if not readings:
        return timeline

    # convert to list and ensure ordered by recorded_at
    R = [r for r in readings if r.recorded_at is not None and r.temperature is not None]
    if not R:
        return timeline

    current_temp = R[0].temperature
    start_time = R[0].recorded_at

    for i in range(1, len(R)):
        r = R[i]
        if abs(r.temperature - current_temp) >= 0.1:
            # end previous at previous reading time
            prev_time = R[i-1].recorded_at
            timeline.append({"start": start_time, "end": prev_time, "temp": current_temp})
            current_temp = r.temperature
            start_time = r.recorded_at

    # final ongoing period
    last_time = R[-1].recorded_at
    timeline.append({"start": start_time, "end": last_time, "temp": current_temp})
    return timeline

def gps_summary_from_readings(readings):
    """
    Return a small GPS summary dict:
      {start_coord, end_coord, distance_km}
    """
    latlon = [(r.gps_lat, r.gps_long, r.recorded_at) for r in readings if r.gps_lat is not None and r.gps_long is not None]
    if not latlon:
        return {"start": None, "end": None, "distance_km": None, "points": 0}
    start = latlon[0]
    end = latlon[-1]
    dist = haversine_km(start[0], start[1], end[0], end[1])
    return {"start": (start[0], start[1]), "end": (end[0], end[1]), "distance_km": dist, "points": len(latlon)}

# --- Main report view -------------------------------------------------------

def download_contract_report(request, contract_id):
    # --- Retrieve Contract + Parties Info ---
    contract = get_object_or_404(Contract, pk=contract_id)
    address_record = getattr(contract, "address_record", None)
    init_payment_add = getattr(address_record, "init_payment_add", None) if address_record else None
    final_payment_add = getattr(address_record, "final_payment_add", None) if address_record else None

    buyer_name = getattr(contract, "buyer_name", None) or (contract.buyer.full_name if getattr(contract, "buyer", None) else None) or "N/A"
    buyer_email = getattr(contract, "buyer_email", None) or (contract.buyer.email if getattr(contract, "buyer", None) else None) or "N/A"
    buyer_wallet = getattr(contract, "buyer_address", None) or (getattr(contract.buyer, "m_address", None) if getattr(contract, "buyer", None) else None) or "N/A"

    seller_name = getattr(contract, "seller_name", None) or (contract.seller.full_name if getattr(contract, "seller", None) else None) or "N/A"
    seller_email = getattr(contract, "seller_email", None) or (contract.seller.email if getattr(contract, "seller", None) else None) or "N/A"
    seller_wallet = getattr(contract, "seller_address", None) or (getattr(contract.seller, "m_address", None) if getattr(contract, "seller", None) else None) or "N/A"

    # --- IoT data: prefer live IoTData; fallback to IoTDataHistory aggregation if needed ---
    live_readings = list(IoTData.objects.filter(device__device_id=contract.IoT_Assigned.device_id if getattr(contract, "IoT_Assigned", None) else None).order_by('recorded_at')) if getattr(contract, "IoT_Assigned", None) else []
    use_hist = False
    if not live_readings:
        # fallback to history (older pipeline)
        iot_summary = IoTDataHistory.objects.filter(contract=contract).aggregate(
            avg_temp=Avg('avg_temp'),
            min_temp=Min('min_temp'),
            max_temp=Max('max_temp')
        )
        use_hist = True
    else:
        temps = [r.temperature for r in live_readings if r.temperature is not None]
        iot_summary = {
            "avg_temp": (sum(temps)/len(temps)) if temps else None,
            "min_temp": min(temps) if temps else None,
            "max_temp": max(temps) if temps else None
        }

    # --- PDF Setup ---
    response = HttpResponse(content_type='application/pdf')
    filename = f"Soltrack_Contract_{getattr(contract, 'contract_id', contract_id)}_{datetime.now().strftime('%Y%m%d')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    doc = SimpleDocTemplate(response, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=50, bottomMargin=40)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor("#2563eb"), alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor("#64748b"), alignment=TA_CENTER)
    section_header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor("#1e40af"), spaceBefore=12, spaceAfter=6)
    normal_text = ParagraphStyle('NormalText', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor("#0f172a"))

    content = []

    # --- Header (logo) ---
    try:
        logo_path = finders.find("img/logo_trans.png")  # Get actual full path

        if logo_path:
            logo = Image(logo_path, width=1.1*inch, height=1.1*inch)
            header_table = Table([
                [
                    logo,
                    Paragraph("<b>SOLTRACK</b><br/><font size=9>Smart Logistics & Escrow Platform</font>", normal_text)
                ]
            ], colWidths=[1.4*inch, 4.0*inch])
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ]))
            content.append(header_table)
        else:
            raise Exception("Logo not found")

    except Exception as e:
        print("Logo load error:", e)
    content.append(Paragraph("<b>SOLTRACK</b>", title_style))

    content.append(Spacer(1, 10))

    # --- Title ---
    content.append(Paragraph("Contract Completion Report", title_style))
    content.append(Paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", subtitle_style))
    content.append(Spacer(1, 12))

    # --- Contract Info ---
    content.append(Paragraph("Contract Overview", section_header))
    contract_data = [
        ['Contract ID', f"#{getattr(contract, 'contract_id', contract_id)}"],
        ['Product', getattr(contract, 'product_name', 'N/A') or "N/A"],
        ['Quantity', f"{getattr(contract, 'quantity', 'N/A')}"],
        ['Total Value', f"{getattr(contract, 'price', 'N/A')}"],
        ['Deployment Date', getattr(contract, 'start_date', None).strftime('%B %d, %Y') if getattr(contract, 'start_date', None) else "N/A"],
        ['Completion Date', getattr(contract, 'end_date', None).strftime('%B %d, %Y') if getattr(contract, 'end_date', None) else "N/A"],
        ['Status', getattr(contract, 'status', 'N/A')],
        ['Contract Address', getattr(contract, 'contract_address', 'N/A') or "N/A"],
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
    buyer_user = CustomUser.objects.filter(user_id=getattr(contract, 'buyer_id', None)).first() if getattr(contract, 'buyer_id', None) else None
    seller_user = CustomUser.objects.filter(user_id=getattr(contract, 'seller_id', None)).first() if getattr(contract, 'seller_id', None) else None

    buyer_org = getattr(buyer_user, "organization", "N/A") if buyer_user else "N/A"
    seller_org = getattr(seller_user, "organization", "N/A") if seller_user else "N/A"

    parties_data = [
        ['Buyer', buyer_org],
        ['Buyer Wallet', buyer_wallet],
        ['Seller', seller_org],
        ['Seller Wallet', seller_wallet],
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
    content.append(Spacer(1, 12))
    content.append(Paragraph("Blockchain Payment Records", section_header))
    def shorten(tx):
     return f"{tx[:12]}…{tx[-8:]}" if tx and len(tx) > 26 else tx
    init_display = shorten(init_payment_add) if init_payment_add else "Not available"
    final_display = shorten(final_payment_add) if final_payment_add else "Not available"
    payment_data = [
     ["Initial Payment TX", init_display],
     ["Final Payment TX", final_display],
    ]

    payment_table = Table(payment_data, colWidths=[2.7*inch, 4*inch])
    payment_table.setStyle(TableStyle([
     ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
     ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
     ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
     ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    content.append(payment_table)
    content.append(Spacer(1, 12))


    # --- IoT Summary (aggregate) ---
    content.append(Paragraph("Temperature Monitoring Summary", section_header))
    avg_t = iot_summary.get('avg_temp') if iot_summary else None
    min_t = iot_summary.get('min_temp') if iot_summary else None
    max_t = iot_summary.get('max_temp') if iot_summary else None

    iot_data = [
        ['Average Temperature', f"{avg_t:.2f}°C" if avg_t is not None else "N/A"],
        ['Lowest Temp Recorded', f"{min_t:.2f}°C" if min_t is not None else "N/A"],
        ['Highest Temp Recorded', f"{max_t:.2f}°C" if max_t is not None else "N/A"],
        ['Final Temp Recorded', f"{(live_readings[-1].temperature):.2f}°C" if live_readings and live_readings[-1].temperature is not None else "N/A"],
    ]
    iot_table = Table(iot_data, colWidths=[2.7*inch, 4*inch])
    iot_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
    ]))
    content.append(iot_table)
    content.append(Spacer(1, 12))

   

  

    # --- Footer ---
    footer_text = f"""
    <para alignment="center">
    <font size=9 color="#64748b">
    <b>This report is automatically generated by Soltrack Smart Logistics Platform</b><br/>
    Verified and secured by blockchain technology<br/>
    Document ID: SLT-{getattr(contract, 'contract_id', contract_id)}-{datetime.now().strftime('%Y%m%d%H%M')}<br/>
    © {datetime.now().year} Soltrack. All rights reserved.
    </font>
    </para>
    """
    content.append(Paragraph(footer_text, normal_text))

    # --- Build PDF ---
    doc.build(content)
    return response
