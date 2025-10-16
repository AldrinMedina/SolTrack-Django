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
