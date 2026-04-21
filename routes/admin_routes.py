from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from models.user import User
from models.product import Product
from models.order import Order
from database.mongodb_connection import MongoDB
from bson import ObjectId
from datetime import datetime

admin_bp = Blueprint('admin', __name__)

# Admin middleware
def admin_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        user = User.get_user_by_id(session['user_id'])
        if not user or not user.get('is_admin', False):
            return "Access denied. Admin only.", 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    db = MongoDB.get_collection('products')
    users_collection = MongoDB.get_collection('users')
    orders_collection = MongoDB.get_collection('orders')
    
    # Statistics
    total_products = db.count_documents({})
    total_users = users_collection.count_documents({})
    total_orders = orders_collection.count_documents({})
    
    # Recent orders
    recent_ list(orders_collection.find().sort('created_at', -1).limit(5))
    for order in recent_orders:
        order['_id'] = str(order['_id'])
    
    # Low stock products
    low_stock = list(db.find({'stock': {'$lt': 10}}).limit(5))
    for product in low_stock:
        product['_id'] = str(product['_id'])
    
    return render_template('admin/dashboard.html',
                         total_products=total_products,
                         total_users=total_users,
                         total_orders=total_orders,
                         recent_orders=recent_orders,
                         low_stock=low_stock)

@admin_bp.route('/admin/products')
@admin_required
def admin_products():
    """Manage products"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    db = MongoDB.get_collection('products')
    total = db.count_documents({})
    products = list(db.find().skip((page-1)*per_page).limit(per_page))
    
    for product in products:
        product['_id'] = str(product['_id'])
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('admin/products.html',
                         products=products,
                         current_page=page,
                         total_pages=total_pages)

@admin_bp.route('/admin/products/edit/<product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    """Edit product"""
    db = MongoDB.get_collection('products')
    
    if request.method == 'POST':
        update_data = {
            'name': request.form.get('name'),
            'price': int(request.form.get('price')),
            'category': request.form.get('category'),
            'subcategory': request.form.get('subcategory'),
            'description': request.form.get('description'),
            'stock': int(request.form.get('stock')),
            'rating': float(request.form.get('rating')),
            'updated_at': datetime.utcnow()
        }
        
        db.update_one({'_id': ObjectId(product_id)}, {'$set': update_data})
        return redirect(url_for('admin.admin_products'))
    
    product = db.find_one({'_id': ObjectId(product_id)})
    product['_id'] = str(product['_id'])
    return render_template('admin/edit_product.html', product=product)

@admin_bp.route('/admin/products/delete/<product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    """Delete product"""
    db = MongoDB.get_collection('products')
    result = db.delete_one({'_id': ObjectId(product_id)})
    
    if result.deleted_count > 0:
        return jsonify({'success': True, 'message': 'Product deleted'})
    return jsonify({'success': False, 'message': 'Product not found'})

@admin_bp.route('/admin/users')
@admin_required
def admin_users():
    """Manage users"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    db = MongoDB.get_collection('users')
    total = db.count_documents({})
    users = list(db.find().skip((page-1)*per_page).limit(per_page))
    
    for user in users:
        user['_id'] = str(user['_id'])
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('admin/users.html',
                         users=users,
                         current_page=page,
                         total_pages=total_pages)

@admin_bp.route('/admin/orders')
@admin_required
def admin_orders():
    """Manage orders"""
    db = MongoDB.get_collection('orders')
    orders = list(db.find().sort('created_at', -1))
    
    for order in orders:
        order['_id'] = str(order['_id'])
    
    return render_template('admin/orders.html', orders=orders)

@admin_bp.route('/admin/orders/update-status/<order_id>', methods=['POST'])
@admin_required
def update_order_status(order_id):
    """Update order status"""
    data = request.json
    status = data.get('status')
    
    db = MongoDB.get_collection('orders')
    result = db.update_one(
        {'order_id': order_id},
        {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
    )
    
    if result.modified_count > 0:
        return jsonify({'success': True, 'message': 'Order status updated'})
    return jsonify({'success': False, 'message': 'Failed to update status'})