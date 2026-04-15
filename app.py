from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import bcrypt
import os
import requests
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from functools import wraps
from werkzeug.utils import secure_filename
import uuid
import random

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Upload configuration
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Create upload folder if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# MongoDB Connection
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client[os.getenv('DB_NAME', 'fashionhub')]

# Collections
users_collection = db['users']
products_collection = db['products']
cart_collection = db['cart']
wishlist_collection = db['wishlist']
orders_collection = db['orders']

# Create unique index on product name to prevent duplicates
try:
    products_collection.create_index('name', unique=True)
except:
    pass

# Google OAuth Configuration
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account'
    }
)

# ============================================
# DELIVERY ESTIMATE FUNCTIONS
# ============================================

def get_order_progress_percentage(status):
    """Get progress percentage for order status"""
    progress_map = {
        'pending': 25,
        'confirmed': 50,
        'shipped': 75,
        'delivered': 100
    }
    return progress_map.get(status, 0)

def get_estimated_delivery_range(order_date):
    """Get estimated delivery date range"""
    if isinstance(order_date, str):
        order_date = datetime.fromisoformat(order_date)
    
    min_days = 3
    max_days = 7
    min_date = order_date + timedelta(days=min_days)
    max_date = order_date + timedelta(days=max_days)
    
    return f"{min_date.strftime('%b %d')} - {max_date.strftime('%b %d, %Y')}"

def calculate_delivery_estimate(order_date):
    """Calculate estimated delivery date"""
    if isinstance(order_date, str):
        order_date = datetime.fromisoformat(order_date)
    
    delivery_days = random.randint(3, 7)
    estimated_date = order_date + timedelta(days=delivery_days)
    return estimated_date.strftime('%B %d, %Y')

# ============================================
# CONTEXT PROCESSOR
# ============================================

@app.context_processor
def inject_counts():
    context = {'cart_count': 0, 'wishlist_count': 0}
    
    if session.get("user_id"):
        try:
            context['cart_count'] = cart_collection.count_documents({"user_id": session["user_id"]})
            context['wishlist_count'] = wishlist_collection.count_documents({"user_id": session["user_id"]})
        except:
            pass
    
    return context

# ============================================
# DECORATORS
# ============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login_page'))
        
        user_id = session.get('user_id')
        if user_id:
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            if not user or not user.get('is_admin', False):
                flash('Admin access required', 'danger')
                return redirect(url_for('index'))
        else:
            flash('Admin access required', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# GOOGLE OAUTH ROUTES
# ============================================

@app.route('/login/google')
def google_login():
    session['next'] = request.args.get('next') or url_for('index')
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    try:
        token = google.authorize_access_token()
        resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
        user_info = resp.json()
        
        email = user_info.get('email')
        name = user_info.get('name')
        
        if not email:
            flash('Could not retrieve email from Google', 'danger')
            return redirect(url_for('login_page'))
        
        user = users_collection.find_one({"email": email})
        
        if not user:
            user_id = users_collection.insert_one({
                "name": name,
                "email": email,
                "phone": "",
                "address": "",
                "created_at": datetime.now(),
                "last_login": datetime.now(),
                "total_orders": 0,
                "is_admin": False
            }).inserted_id
            session['user_id'] = str(user_id)
        else:
            users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"last_login": datetime.now()}}
            )
            session['user_id'] = str(user["_id"])
        
        session["user_email"] = email
        session["user_name"] = name
        session['logged_in'] = True
        
        flash("Login successful", "success")
        
        next_page = session.pop('next', url_for('index'))
        return redirect(next_page)
        
    except Exception as e:
        print(f"Google OAuth error: {e}")
        flash("Google login failed", "danger")
        return redirect(url_for("login_page"))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('index'))

@app.route('/admin/make-admin/<email>')
def make_admin(email):
    try:
        result = users_collection.update_one({"email": email}, {"$set": {"is_admin": True}})
        if result.modified_count > 0:
            flash(f"User {email} is now an admin", "success")
        else:
            flash(f"User {email} not found", "danger")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    return redirect(url_for('index'))

# ============================================
# PROFILE ROUTES
# ============================================

@app.route('/profile')
@login_required
def profile_page():
    try:
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        return render_template('profile.html', user=user)
    except Exception as e:
        flash('Error loading profile', 'danger')
        return redirect(url_for('index'))

@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_update_profile():
    try:
        data = request.json
        users_collection.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {'phone': data.get('phone', ''), 'address': data.get('address', '')}}
        )
        return jsonify({'success': True, 'message': 'Profile updated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================
# PRODUCT ROUTES
# ============================================

@app.route('/')
def index():
    try:
        featured_products = list(products_collection.find().sort('created_at', -1).limit(8))
        for product in featured_products:
            product['_id'] = str(product['_id'])
        return render_template('index.html', products=featured_products)
    except Exception as e:
        flash('Error loading products', 'danger')
        return render_template('index.html', products=[])

@app.route('/shop')
def shop_page():
    try:
        category = request.args.get('category', '')
        search = request.args.get('search', '')
        sort = request.args.get('sort', 'latest')
        page = int(request.args.get('page', 1))
        per_page = 12
        
        query = {}
        if category and category != '':
            query['category'] = category
        if search and search.strip() != '':
            query['name'] = {'$regex': search.strip(), '$options': 'i'}
        
        sort_options = {
            'latest': ('created_at', -1),
            'price_asc': ('price', 1),
            'price_desc': ('price', -1),
            'rating': ('rating', -1)
        }
        sort_field, sort_order = sort_options.get(sort, ('created_at', -1))
        
        total_products = products_collection.count_documents(query)
        total_pages = (total_products + per_page - 1) // per_page
        
        products = list(products_collection.find(query)
                       .sort(sort_field, sort_order)
                       .skip((page - 1) * per_page)
                       .limit(per_page))
        
        for product in products:
            product['_id'] = str(product['_id'])
        
        return render_template('shop.html', 
                             products=products,
                             total_products=total_products,
                             total_pages=total_pages,
                             current_page=page,
                             category=category,
                             search=search,
                             sort=sort)
    except Exception as e:
        flash('Error loading products', 'danger')
        return render_template('shop.html', products=[])

# ============================================
# CART ROUTES
# ============================================

@app.route("/cart")
@login_required
def cart_page():
    try:
        cart_items = list(cart_collection.find({"user_id": session["user_id"]}))
        items = []
        total = 0
        
        for item in cart_items:
            product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                item_data = {
                    "product_id": item["product_id"],
                    "name": product["name"],
                    "price": product["price"],
                    "image": product.get("image", "default.png"),
                    "quantity": item["quantity"],
                    "subtotal": product["price"] * item["quantity"]
                }
                items.append(item_data)
                total += item_data["subtotal"]
        
        return render_template("cart.html", cart=items, total=total)
    except Exception as e:
        flash(f"Error loading cart", "danger")
        return render_template("cart.html", cart=[], total=0)

@app.route("/api/cart/add", methods=["POST"])
@login_required
def add_to_cart():
    try:
        data = request.json
        product_id = data["product_id"]
        quantity = data.get("quantity", 1)
        product = products_collection.find_one({"_id": ObjectId(product_id)})
        
        if not product:
            return jsonify({"message": "Product not found"}), 404
        
        existing_item = cart_collection.find_one({"user_id": session["user_id"], "product_id": product_id})
        
        if existing_item:
            cart_collection.update_one({"_id": existing_item["_id"]}, {"$inc": {"quantity": quantity}})
        else:
            cart_item = {
                "user_id": session["user_id"],
                "product_id": product_id,
                "name": product["name"],
                "price": product["price"],
                "image": product.get("image", "default.png"),
                "quantity": quantity,
                "added_at": datetime.now()
            }
            cart_collection.insert_one(cart_item)
        
        return jsonify({"message": "Added to cart", "success": True})
    except Exception as e:
        return jsonify({"message": str(e), "success": False}), 500

@app.route("/api/cart/remove/<product_id>", methods=["DELETE"])
@login_required
def remove_from_cart(product_id):
    try:
        cart_collection.delete_one({"user_id": session["user_id"], "product_id": product_id})
        return jsonify({"message": "Removed from cart", "success": True})
    except Exception as e:
        return jsonify({"message": str(e), "success": False}), 500

@app.route("/api/cart/update", methods=["POST"])
@login_required
def update_cart_quantity():
    try:
        data = request.json
        product_id = data["product_id"]
        quantity = data.get("quantity", 1)
        
        if quantity <= 0:
            cart_collection.delete_one({"user_id": session["user_id"], "product_id": product_id})
        else:
            cart_collection.update_one(
                {"user_id": session["user_id"], "product_id": product_id},
                {"$set": {"quantity": quantity}}
            )
        
        return jsonify({"message": "Cart updated", "success": True})
    except Exception as e:
        return jsonify({"message": str(e), "success": False}), 500

@app.route("/api/cart", methods=["GET"])
@login_required
def get_cart():
    try:
        cart_items = list(cart_collection.find({"user_id": session["user_id"]}))
        items = []
        total = 0
        
        for item in cart_items:
            product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                items.append({
                    "product_id": item["product_id"],
                    "name": product["name"],
                    "price": product["price"],
                    "image": product.get("image", "default.png"),
                    "quantity": item["quantity"],
                    "subtotal": product["price"] * item["quantity"]
                })
                total += product["price"] * item["quantity"]
        
        return jsonify({"items": items, "total": total})
    except Exception as e:
        return jsonify({"items": [], "total": 0}), 500

# ============================================
# CHECKOUT ROUTES
# ============================================

@app.route('/checkout')
@login_required
def checkout_page():
    try:
        cart_items = list(cart_collection.find({"user_id": session["user_id"]}))
        items = []
        total = 0
        
        for item in cart_items:
            product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                item_data = {
                    "product_id": item["product_id"],
                    "name": product["name"],
                    "price": product["price"],
                    "image": product.get("image", "default.png"),
                    "quantity": item["quantity"],
                    "subtotal": product["price"] * item["quantity"]
                }
                items.append(item_data)
                total += item_data["subtotal"]
        
        return render_template("checkout.html", cart=items, total=total)
    except Exception as e:
        flash(f"Error loading checkout: {str(e)}", "danger")
        return redirect(url_for("cart_page"))

@app.route("/place-order", methods=["POST"])
@login_required
def place_order():
    """Place an order from cart"""
    try:
        mobile = request.form["mobile"]
        address = request.form["address"]
        payment_method = request.form.get("payment_method", "cod")
        
        cart_items = list(cart_collection.find({"user_id": session["user_id"]}))
        
        if not cart_items:
            flash("Your cart is empty", "danger")
            return redirect(url_for("cart_page"))
        
        items = []
        total = 0
        
        for item in cart_items:
            product = products_collection.find_one({"_id": ObjectId(item["product_id"])})
            if product:
                if product.get('stock', 0) < item["quantity"]:
                    flash(f"Insufficient stock for {product['name']}", "danger")
                    return redirect(url_for("cart_page"))
                
                items.append({
                    "product_id": item["product_id"],
                    "product_name": product["name"],
                    "price": product["price"],
                    "quantity": item["quantity"],
                    "image": product.get("image", "default.png")
                })
                total += product["price"] * item["quantity"]
        
        # IMPORTANT: Store user_id as STRING to match session
        order = {
            "user_id": str(session["user_id"]),  # Convert to string
            "user_email": session["user_email"],
            "user_name": session["user_name"],
            "items": items,
            "total_amount": total,
            "mobile": mobile,
            "address": address,
            "payment_method": payment_method,
            "order_status": "pending",
            "created_at": datetime.now(),
            "order_number": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        }
        
        result = orders_collection.insert_one(order)
        print(f"Order inserted with ID: {result.inserted_id}")
        print(f"Order user_id: {order['user_id']}")
        
        for item in cart_items:
            products_collection.update_one(
                {"_id": ObjectId(item["product_id"])},
                {"$inc": {"stock": -item["quantity"]}}
            )
        
        cart_collection.delete_many({"user_id": session["user_id"]})
        
        users_collection.update_one(
            {"_id": ObjectId(session["user_id"])},
            {"$inc": {"total_orders": 1}}
        )
        
        flash("Order placed successfully!", "success")
        return redirect("/orders")
        
    except Exception as e:
        print(f"Error placing order: {e}")
        flash(f"Error placing order: {str(e)}", "danger")
        return redirect(url_for("cart_page"))
# ============================================
# ORDER TRACKING ROUTES
# ============================================

@app.route('/orders')
@login_required
def orders_page():
    """Show user's orders"""
    try:
        user_id = session.get('user_id')
        
        print(f"Fetching orders for user_id: {user_id}")
        print(f"Type of user_id: {type(user_id)}")
        
        # Try both string and ObjectId formats
        orders = list(orders_collection.find({
            "$or": [
                {"user_id": user_id},
                {"user_id": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id},
                {"user_email": session.get('user_email')}
            ]
        }).sort('created_at', -1))
        
        print(f"Found {len(orders)} orders")
        
        # Also check all orders in database (for debugging)
        all_orders = list(orders_collection.find())
        print(f"Total orders in database: {len(all_orders)}")
        
        # Convert ObjectId to string for template
        for order in orders:
            order['_id'] = str(order['_id'])
            # Ensure date field exists
            if 'created_at' not in order:
                order['created_at'] = order.get('order_date', datetime.now())
        
        return render_template('orders.html', orders=orders)
    except Exception as e:
        print(f"Error loading orders: {e}")
        flash('Error loading orders', 'danger')
        return render_template('orders.html', orders=[])
@app.route('/order/<order_id>')
@login_required
def order_detail(order_id):
    try:
        order = orders_collection.find_one({'_id': ObjectId(order_id), 'user_id': session['user_id']})
        if not order:
            flash('Order not found', 'danger')
            return redirect(url_for('orders_page'))
        
        order['_id'] = str(order['_id'])
        order['progress_percentage'] = get_order_progress_percentage(order.get('order_status', 'pending'))
        order['delivery_estimate'] = get_estimated_delivery_range(order.get('created_at', datetime.now()))
        order['delivery_date'] = calculate_delivery_estimate(order.get('created_at', datetime.now()))
        
        return render_template('order_detail.html', order=order)
    except Exception as e:
        flash('Order not found', 'danger')
        return redirect(url_for('orders_page'))

@app.route('/api/order/update-status/<order_id>', methods=['POST'])
@login_required
def update_order_status(order_id):
    """Update order status"""
    try:
        data = request.json
        new_status = data.get('status')
        
        valid_statuses = ['pending', 'confirmed', 'shipped', 'delivered']
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
        result = orders_collection.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {'order_status': new_status}}
        )
        
        if result.modified_count > 0:
            return jsonify({
                'success': True, 
                'message': 'Order status updated',
                'progress_percentage': get_order_progress_percentage(new_status)
            })
        else:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
            
    except Exception as e:
        print(f"Error updating order status: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route("/buy/<product_id>")
@login_required
def order_page(product_id):
    """Show order page for a specific product"""
    try:
        product = products_collection.find_one({"_id": ObjectId(product_id)})
        if not product:
            flash("Product not found", "danger")
            return redirect(url_for("index"))
        
        product['_id'] = str(product['_id'])
        return render_template("order.html", product=product)
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("index"))

@app.route("/place-single-order", methods=["POST"])
@login_required
def place_single_order():
    """Place an order for a single product (Buy Now)"""
    try:
        product_id = request.form["product_id"]
        quantity = int(request.form["quantity"])
        mobile = request.form["mobile"]
        address = request.form["address"]
        
        product = products_collection.find_one({"_id": ObjectId(product_id)})
        
        if not product:
            flash("Product not found", "danger")
            return redirect(url_for("index"))
        
        if product.get('stock', 0) < quantity:
            flash("Insufficient stock available", "danger")
            return redirect(url_for("index"))
        
        # IMPORTANT: Store user_id as STRING to match session
        order = {
            "user_id": str(session["user_id"]),  # Convert to string
            "user_email": session["user_email"],
            "user_name": session["user_name"],
            "product_id": product_id,
            "product_name": product["name"],
            "price": product["price"],
            "quantity": quantity,
            "total_amount": product["price"] * quantity,
            "mobile": mobile,
            "address": address,
            "image": product.get("image", "default.png"),
            "order_status": "pending",
            "created_at": datetime.now(),
            "order_number": f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        }
        
        orders_collection.insert_one(order)
        print(f"Single order placed for user: {session['user_id']}")
        
        products_collection.update_one(
            {"_id": ObjectId(product_id)},
            {"$inc": {"stock": -quantity}}
        )
        
        users_collection.update_one(
            {"_id": ObjectId(session["user_id"])},
            {"$inc": {"total_orders": 1}}
        )
        
        flash("Order placed successfully!", "success")
        return redirect("/orders")
        
    except Exception as e:
        print(f"Error placing order: {e}")
        flash(f"Error placing order: {str(e)}", "danger")
        return redirect(url_for("index"))
# ============================================
# ADMIN PRODUCT CREATION
# ============================================

@app.route("/admin/add-product", methods=["GET", "POST"])
@admin_required
def admin_add_product():
    if request.method == "POST":
        try:
            name = request.form.get("name")
            price = request.form.get("price")
            category = request.form.get("category")
            description = request.form.get("description")
            stock = request.form.get("stock")
            
            if not name or not price or not stock:
                flash("Name, price, and stock are required", "danger")
                return redirect("/admin/add-product")
            
            existing = products_collection.find_one({"name": name})
            if existing:
                flash("Product with this name already exists!", "danger")
                return redirect("/admin/add-product")
            
            image = request.files.get("image")
            filename = None
            
            if image and image.filename != "" and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
                image.save(filepath)
                filename = unique_filename
            else:
                filename = "default.png"
            
            product = {
                "name": name,
                "price": float(price),
                "category": category,
                "description": description,
                "stock": int(stock),
                "image": filename,
                "rating": 4.5,
                "created_at": datetime.now(),
                "added_by": session.get('user_id'),
                "added_by_name": session.get('user_name')
            }
            
            products_collection.insert_one(product)
            flash("Product added successfully!", "success")
            return redirect("/shop")
            
        except DuplicateKeyError:
            flash("Product with this name already exists!", "danger")
            return redirect("/admin/add-product")
        except Exception as e:
            flash(f"Error adding product: {str(e)}", "danger")
            return redirect("/admin/add-product")
    
    return render_template("admin_add_product.html")

# ============================================
# WISHLIST ROUTES
# ============================================

@app.route('/api/wishlist', methods=['GET'])
@login_required
def api_get_wishlist():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify([])
        
        wishlist_items = list(wishlist_collection.find({'user_id': user_id}))
        items = []
        
        for item in wishlist_items:
            product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                product['_id'] = str(product['_id'])
                items.append(product)
        
        return jsonify(items)
    except Exception as e:
        return jsonify([])

@app.route('/api/wishlist/toggle', methods=['POST'])
@login_required
def api_toggle_wishlist():
    try:
        data = request.json
        user_id = session.get('user_id')
        product_id = data.get('product_id')
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Please login'}), 401
        
        existing = wishlist_collection.find_one({'user_id': user_id, 'product_id': product_id})
        
        if existing:
            wishlist_collection.delete_one({'_id': existing['_id']})
            return jsonify({'success': True, 'action': 'removed'})
        else:
            wishlist_collection.insert_one({'user_id': user_id, 'product_id': product_id, 'added_at': datetime.now()})
            return jsonify({'success': True, 'action': 'added'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/wishlist')
@login_required
def wishlist_page():
    try:
        user_id = session.get('user_id')
        wishlist_items = list(wishlist_collection.find({'user_id': user_id}))
        products = []
        
        for item in wishlist_items:
            product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                product['_id'] = str(product['_id'])
                products.append(product)
        
        return render_template('wishlist.html', wishlist=products)
    except Exception as e:
        flash('Error loading wishlist', 'danger')
        return render_template('wishlist.html', wishlist=[])

# ============================================
# API SESSION ROUTE
# ============================================

@app.route('/api/session', methods=['GET'])
def api_get_session():
    if session.get('logged_in'):
        return jsonify({
            'logged_in': True,
            'user': {
                'id': session.get('user_id'),
                'name': session.get('user_name'),
                'email': session.get('user_email')
            }
        })
    return jsonify({'logged_in': False})



# ============================================
# PAGE ROUTES
# ============================================

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv('PORT', 5000)))