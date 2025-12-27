# dashboard/views/download_logs.py

from django.http import HttpResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from django.shortcuts import get_object_or_404
from ..models import Contract, ShipmentLog 

def download_shipment_logs(request, contract_id):
    contract = get_object_or_404(Contract, contract_id=contract_id)
    logs = ShipmentLog.objects.filter(contract=contract).order_by('log_time')
    buffer = BytesIO()
    
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    p.setFont("Helvetica-Bold", 16)
    p.drawString(30, height - 30, f"Shipment Logs - Contract ID: {contract.contract_id}")
    p.setFont("Helvetica", 10)
    p.drawString(30, height - 50, f"Product: {contract.product_name} | Status: {contract.status}")
    y_position = height - 80 
    p.setFont("Helvetica-Bold", 10)
    p.drawString(30, y_position, "Timestamp")
    p.drawString(150, y_position, "Type")
    p.drawString(250, y_position, "Message")
    y_position -= 5

    p.line(30, y_position, width - 30, y_position)
    y_position -= 15

    p.setFont("Helvetica", 9)
    for log in logs:
        if y_position < 40:
            p.showPage()
            y_position = height - 30
            p.setFont("Helvetica-Bold", 10)
            p.drawString(30, y_position, "Timestamp")
            p.drawString(150, y_position, "Type")
            p.drawString(250, y_position, "Message")
            y_position -= 5
            p.line(30, y_position, width - 30, y_position)
            y_position -= 15
            p.setFont("Helvetica", 9)
        
        p.drawString(30, y_position, log.log_time.strftime('%Y-%m-%d %H:%M:%S'))
        p.drawString(150, y_position, log.log_type)
        message_lines = log.message.split('\n')
        line_y = y_position
        for line in message_lines:
            p.drawString(250, line_y, line)
            line_y -= 12
        
        y_position = line_y 
        y_position -= 5 

    p.showPage()
    p.save()
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="shipment_logs_C{contract_id}.pdf"'
    
    return response
