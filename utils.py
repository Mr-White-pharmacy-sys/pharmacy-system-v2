from datetime import datetime, timedelta
import json
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import csv
from io import BytesIO

def get_product_status(product):
    """Determine product status based on expiry and stock"""
    today = datetime.now().date()
    days_to_expiry = (product.expiry_date - today).days
    
    if today > product.expiry_date:
        return 'expired'
    elif days_to_expiry <= 30:
        return 'expiring_soon'
    elif product.quantity < product.low_stock_threshold:
        return 'low_stock'
    else:
        return 'normal'

def generate_receipt_pdf(sale, items, receipt_folder):
    """Generate PDF receipt for a sale"""
    filename = f"receipt_{sale.receipt_number}.pdf"
    filepath = os.path.join(receipt_folder, filename)
    
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter
    
    # Header
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "Mr. White Pharmacy")
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 70, f"Receipt Number: {sale.receipt_number}")
    c.drawString(50, height - 85, f"Date: {sale.created_at.strftime('%Y-%m-%d %H:%M')}")
    
    # Items
    y = height - 120
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Item")
    c.drawString(250, y, "Qty")
    c.drawString(300, y, "Price (Nle)")
    c.drawString(400, y, "Total (Nle)")
    
    y -= 20
    c.setFont("Helvetica", 10)
    
    for item in items:
        c.drawString(50, y, item['name'][:30])
        c.drawString(250, y, str(item['quantity']))
        c.drawString(300, y, f"{item['price_nle']:,.0f}")
        c.drawString(400, y, f"{item['total_nle']:,.0f}")
        y -= 15
    
    # Totals
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(300, y, f"Total (Nle): {sale.total_nle:,.0f}")
    y -= 15
    c.drawString(300, y, f"Total (USD): ${sale.total_usd:,.2f}")
    
    c.save()
    return filepath

def export_to_csv(data, filename):
    """Export data to CSV"""
    si = BytesIO()
    cw = csv.writer(si)
    if data:
        cw.writerow(data[0].keys())
        for row in data:
            cw.writerow(row.values())
    si.seek(0)
    return si