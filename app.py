from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import json
import qrcode
from PIL import Image
import pandas as pd
import csv
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

# Initialize Flask app
app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mr-white-pharmacy-secret-key-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///pharmacy.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['RECEIPT_FOLDER'] = 'receipts'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RECEIPT_FOLDER'], exist_ok=True)

# Initialize database
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ============================================
# DATABASE MODELS
# ============================================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='cashier')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price_nle = db.Column(db.Float, nullable=False)
    price_usd = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    manufacturer = db.Column(db.String(100))
    category = db.Column(db.String(50))
    barcode = db.Column(db.String(100), unique=True)
    image_file = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    low_stock_threshold = db.Column(db.Integer, default=10)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_person = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    products_supplied = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)
    items = db.Column(db.Text)
    subtotal_nle = db.Column(db.Float, nullable=False)
    subtotal_usd = db.Column(db.Float, nullable=False)
    tax_nle = db.Column(db.Float, default=0)
    tax_usd = db.Column(db.Float, default=0)
    total_nle = db.Column(db.Float, nullable=False)
    total_usd = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============================================
# HELPER FUNCTIONS
# ============================================
def get_product_status(product):
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

def generate_receipt_pdf(sale, items):
    filename = f"receipt_{sale.receipt_number}.pdf"
    filepath = os.path.join(app.config['RECEIPT_FOLDER'], filename)
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        alignment=1
    )
    story.append(Paragraph("PENINSULA HOSPITAL CENTRE", title_style))
    story.append(Paragraph("No. 1 Macarthy Drive, Off Peninsula Road Tokeh, Freetown", styles['Normal']))
    story.append(Paragraph("Tel: +23273475252", styles['Normal']))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"Receipt: {sale.receipt_number}", styles['Normal']))
    story.append(Paragraph(f"Date: {sale.created_at.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 0.3 * inch))
    
    table_data = [['Item', 'Qty', 'Price', 'Total']]
    for item in items:
        table_data.append([
            item['name'], str(item['quantity']),
            f"Nle {item['price_nle']:,.2f}",
            f"Nle {item['total_nle']:,.2f}"
        ])
    table_data.append(['', '', 'Subtotal:', f"Nle {sale.subtotal_nle:,.2f}"])
    table_data.append(['', '', 'Tax (0%):', "Nle 0.00"])
    table_data.append(['', '', 'Total:', f"Nle {sale.total_nle:,.2f}"])
    table_data.append(['', '', 'Total (USD):', f"${sale.total_usd:,.2f}"])
    
    table = Table(table_data, colWidths=[3*inch, 0.8*inch, 1.2*inch, 1.2*inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -4), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -3), (-1, -1), colors.HexColor('#f0f0f0')),
        ('FONTNAME', (0, -3), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Thank you for your purchase!", styles['Normal']))
    story.append(Paragraph("Please check expiry dates before use", styles['Normal']))
    doc.build(story)
    return filepath

# ============================================
# PAGE ROUTES
# ============================================
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('index.html', user=current_user)

@app.route('/inventory')
@login_required
def inventory():
    return render_template('inventory.html')

@app.route('/pos')
@login_required
def pos():
    return render_template('pos.html')

@app.route('/suppliers')
@login_required
def suppliers():
    return render_template('suppliers.html')

@app.route('/analytics')
@login_required
def analytics():
    return render_template('analytics.html')

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')

# ============================================
# API ROUTES – PRODUCTS
# ============================================
@app.route('/api/products', methods=['GET'])
@login_required
def get_products():
    products = Product.query.all()
    product_list = []
    for p in products:
        product_list.append({
            'id': p.id,
            'product_id': p.product_id,
            'name': p.name,
            'price_nle': p.price_nle,
            'price_usd': p.price_usd,
            'quantity': p.quantity,
            'expiry_date': p.expiry_date.strftime('%Y-%m-%d'),
            'manufacturer': p.manufacturer,
            'category': p.category,
            'barcode': p.barcode,
            'image_file': p.image_file,
            'status': get_product_status(p)
        })
    return jsonify(product_list)

@app.route('/api/products', methods=['POST'])
@login_required
def add_product():
    data = request.json
    usd_price = data['price_nle'] / 22
    barcode_value = data.get('barcode')
    if not barcode_value:
        barcode_value = f"PH{datetime.now().strftime('%Y%m%d%H%M%S')}"
    new_product = Product(
        product_id=data['product_id'],
        name=data['name'],
        price_nle=data['price_nle'],
        price_usd=round(usd_price, 2),
        quantity=data['quantity'],
        expiry_date=datetime.strptime(data['expiry_date'], '%Y-%m-%d').date(),
        manufacturer=data.get('manufacturer'),
        category=data.get('category'),
        barcode=barcode_value
    )
    db.session.add(new_product)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Product added successfully'})

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@login_required
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.json
    product.name = data.get('name', product.name)
    product.price_nle = data.get('price_nle', product.price_nle)
    product.price_usd = data.get('price_nle', product.price_nle) / 22
    product.quantity = data.get('quantity', product.quantity)
    if data.get('expiry_date'):
        product.expiry_date = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
    product.manufacturer = data.get('manufacturer', product.manufacturer)
    product.category = data.get('category', product.category)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Product updated successfully'})

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Product deleted successfully'})

@app.route('/api/search')
@login_required
def search_products():
    query = request.args.get('q', '')
    products = Product.query.filter(
        (Product.name.contains(query)) | 
        (Product.product_id.contains(query)) |
        (Product.barcode.contains(query))
    ).all()
    return jsonify([{
        'id': p.id,
        'product_id': p.product_id,
        'name': p.name,
        'price_nle': p.price_nle,
        'price_usd': p.price_usd,
        'quantity': p.quantity,
        'manufacturer': p.manufacturer,
        'category': p.category
    } for p in products])

# ============================================
# API ROUTES – STATISTICS
# ============================================
@app.route('/api/statistics')
@login_required
def get_statistics():
    products = Product.query.all()
    total_items = sum(p.quantity for p in products)
    total_value_nle = sum(p.price_nle * p.quantity for p in products)
    total_value_usd = total_value_nle / 22
    categories = {}
    for p in products:
        if p.category:
            categories[p.category] = categories.get(p.category, 0) + p.quantity
    expired_count = sum(1 for p in products if p.expiry_date < datetime.now().date())
    expiring_soon_count = sum(1 for p in products if 0 <= (p.expiry_date - datetime.now().date()).days <= 30)
    low_stock_count = sum(1 for p in products if p.quantity < p.low_stock_threshold)
    return jsonify({
        'total_products': len(products),
        'total_items': total_items,
        'total_value_nle': total_value_nle,
        'total_value_usd': round(total_value_usd, 2),
        'categories': categories,
        'expired_count': expired_count,
        'expiring_soon_count': expiring_soon_count,
        'low_stock_count': low_stock_count
    })

# ============================================
# API ROUTES – SALES (POS)
# ============================================
@app.route('/api/sales', methods=['POST'])
@login_required
def create_sale():
    try:
        data = request.json
        receipt_number = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        for item in data['items']:
            product = Product.query.filter_by(name=item['name']).first()
            if not product:
                return jsonify({'error': f'Product {item["name"]} not found'}), 400
            if product.quantity < item['quantity']:
                return jsonify({'error': f'Not enough stock for {product.name}. Available: {product.quantity}'}), 400
            product.quantity -= item['quantity']
        sale = Sale(
            receipt_number=receipt_number,
            items=json.dumps(data['items']),
            subtotal_nle=data['subtotal_nle'],
            subtotal_usd=data['subtotal_usd'],
            total_nle=data['total_nle'],
            total_usd=data['total_usd'],
            payment_method=data['payment_method'],
            user_id=current_user.id
        )
        db.session.add(sale)
        db.session.commit()
        generate_receipt_pdf(sale, data['items'])
        return jsonify({'success': True, 'receipt_number': receipt_number, 'message': 'Sale completed successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# API ROUTES – REPORTS
# ============================================
@app.route('/api/reports/<report_type>')
@login_required
def generate_report(report_type):
    format_type = request.args.get('format', 'json')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if report_type == 'inventory':
        data = generate_inventory_report()
    elif report_type == 'sales':
        data = generate_sales_report(start_date, end_date)
    elif report_type == 'expiry':
        data = generate_expiry_report()
    elif report_type == 'suppliers':
        data = generate_supplier_report()
    else:
        return jsonify({'error': 'Invalid report type'}), 400
    if format_type == 'csv':
        return export_to_csv(data, report_type)
    elif format_type == 'pdf':
        return export_to_pdf(data, report_type)
    elif format_type == 'excel':
        return export_to_excel(data, report_type)
    else:
        return jsonify(data)

def generate_inventory_report():
    products = Product.query.all()
    return [{
        'Product ID': p.product_id,
        'Name': p.name,
        'Price (Nle)': p.price_nle,
        'Price (USD)': p.price_usd,
        'Quantity': p.quantity,
        'Expiry Date': p.expiry_date.strftime('%Y-%m-%d'),
        'Manufacturer': p.manufacturer,
        'Category': p.category,
        'Status': get_product_status(p)
    } for p in products]

def generate_sales_report(start_date, end_date):
    query = Sale.query
    if start_date:
        query = query.filter(Sale.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(Sale.created_at <= datetime.strptime(end_date, '%Y-%m-%d'))
    sales = query.all()
    return [{
        'Receipt Number': s.receipt_number,
        'Date': s.created_at.strftime('%Y-%m-%d %H:%M'),
        'Total (Nle)': s.total_nle,
        'Total (USD)': s.total_usd,
        'Payment Method': s.payment_method,
        'Items': s.items
    } for s in sales]

def generate_expiry_report():
    today = datetime.now().date()
    thirty_days = today + timedelta(days=30)
    products = Product.query.filter(Product.expiry_date <= thirty_days).all()
    return [{
        'Product ID': p.product_id,
        'Name': p.name,
        'Expiry Date': p.expiry_date.strftime('%Y-%m-%d'),
        'Days Until Expiry': (p.expiry_date - today).days,
        'Quantity': p.quantity,
        'Status': 'Expired' if p.expiry_date < today else 'Expiring Soon'
    } for p in products]

def generate_supplier_report():
    suppliers = Supplier.query.all()
    return [{
        'Name': s.name,
        'Contact Person': s.contact_person,
        'Email': s.email,
        'Phone': s.phone,
        'Address': s.address
    } for s in suppliers]

def export_to_csv(data, filename):
    si = BytesIO()
    if data:
        cw = csv.writer(si)
        cw.writerow(data[0].keys())
        for row in data:
            cw.writerow(row.values())
    si.seek(0)
    return send_file(si, mimetype='text/csv', as_attachment=True, download_name=f'{filename}_report.csv')

def export_to_pdf(data, filename):
    buffer = BytesIO()
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, f"{filename.title()} Report")
    c.setFont("Helvetica", 10)
    y = height - 80
    if data:
        headers = list(data[0].keys())
        x = 50
        for header in headers:
            c.drawString(x, y, str(header)[:15])
            x += 100
        y -= 20
        for row in data:
            x = 50
            for header in headers:
                value = str(row[header])[:15]
                c.drawString(x, y, value)
                x += 100
            y -= 15
            if y < 50:
                c.showPage()
                y = height - 50
    c.save()
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f'{filename}_report.pdf')

def export_to_excel(data, filename):
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=filename)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=f'{filename}_report.xlsx')

# ============================================
# USER MANAGEMENT ROUTES
# ============================================
@app.route('/users')
@login_required
def users():
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('users.html')

@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    users = User.query.all()
    user_list = [{'id': u.id, 'username': u.username, 'role': u.role, 'is_current': u.id == current_user.id} for u in users]
    return jsonify(user_list)

@app.route('/api/users', methods=['POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'cashier')
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
    new_user = User(username=username, role=role)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'User created successfully'})

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    if current_user.role != 'admin' and current_user.id != user.id:
        return jsonify({'error': 'Access denied'}), 403
    data = request.json
    if data.get('username') and data['username'] != user.username:
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        user.username = data['username']
    if data.get('password'):
        user.set_password(data['password'])
    if data.get('role') and current_user.role == 'admin':
        user.role = data['role']
    db.session.commit()
    return jsonify({'success': True, 'message': 'User updated successfully'})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'User deleted successfully'})

@app.route('/api/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    if not current_user.check_password(old_password):
        return jsonify({'error': 'Current password is incorrect'}), 400
    if len(new_password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    current_user.set_password(new_password)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Password changed successfully'})

# ============================================
# ANALYTICS API ENDPOINTS
# ============================================
@app.route('/api/analytics/sales_trend')
@login_required
def sales_trend():
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)
    sales = Sale.query.filter(Sale.created_at >= start_date).all()
    dates = []
    amounts = []
    total_sales_30 = 0.0
    transactions_30 = len(sales)
    current = start_date
    while current <= end_date:
        dates.append(current.strftime('%Y-%m-%d'))
        day_amount = sum(s.total_nle for s in sales if s.created_at.date() == current)
        amounts.append(day_amount)
        total_sales_30 += day_amount
        current += timedelta(days=1)
    avg_transaction = total_sales_30 / transactions_30 if transactions_30 > 0 else 0
    return jsonify({
        'dates': dates,
        'amounts': amounts,
        'total_sales_30': round(total_sales_30, 2),
        'transactions_30': transactions_30,
        'avg_transaction': round(avg_transaction, 2)
    })

@app.route('/api/analytics/expiry_forecast')
@login_required
def expiry_forecast():
    from datetime import date, timedelta
    today = date.today()
    ninety_days = today + timedelta(days=90)
    products = Product.query.filter(Product.expiry_date <= ninety_days).all()
    forecast = []
    for p in products:
        days_left = (p.expiry_date - today).days
        projected_loss = p.price_nle * p.quantity if days_left <= 30 else p.price_nle * p.quantity * 0.5
        forecast.append({
            'name': p.name,
            'expiry_date': p.expiry_date.strftime('%Y-%m-%d'),
            'days_left': days_left,
            'quantity': p.quantity,
            'projected_loss': round(projected_loss, 2)
        })
    forecast.sort(key=lambda x: x['days_left'])
    return jsonify(forecast)

# ============================================
# MANUAL STOCK ALERT (Placeholder)
# ============================================
@app.route('/api/check_low_stock', methods=['POST'])
@login_required
def manual_stock_check():
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    # Email/SMS alerts are disabled for now.
    # You can re‑enable them later by adding flask_mail and Twilio credentials.
    return jsonify({'message': 'Stock check completed. (Email/SMS alerts are currently disabled; add credentials to enable.)'})

# ============================================
# INITIALIZE DATABASE & CREATE ADMIN
# ============================================
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin')
        admin.set_password('admin123')
        admin.role = 'admin'
        db.session.add(admin)
        db.session.commit()

# ============================================
# RUN THE APP
# ============================================
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=10000)