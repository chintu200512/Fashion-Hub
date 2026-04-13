from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import bcrypt
import os
import requests
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

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
    pass  # Index already exists

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

# ============================================
# GOOGLE OAUTH ROUTES
# ============================================

@app.route('/login/google')
def google_login():
    """Initiate Google OAuth login"""
    session['next'] = request.args.get('next') or url_for('shop_page')
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    try:
        # Get access token
        token = google.authorize_access_token()
        
        # Get user info from Google
        resp = google.get('https://www.googleapis.com/oauth2/v2/userinfo')
        user_info = resp.json()
        
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0] if email else 'User')
        google_id = user_info.get('id')
        picture = user_info.get('picture', '')
        
        if not email:
            flash('Could not retrieve email from Google', 'danger')
            return redirect(url_for('login_page'))
        
        # Check if user exists
        existing_user = users_collection.find_one({'email': email})
        
        if existing_user:
            # Update user with Google info
            users_collection.update_one(
                {'_id': existing_user['_id']},
                {'$set': {
                    'google_id': google_id,
                    'picture': picture,
                    'auth_provider': 'google',
                    'last_login': datetime.now()
                }}
            )
            session['user_id'] = str(existing_user['_id'])
            session['user_name'] = existing_user['name']
            session['user_email'] = existing_user['email']
        else:
            # Create new user
            new_user = {
                'name': name,
                'email': email,
                'password': None,
                'google_id': google_id,
                'picture': picture,
                'phone': '',
                'address': '',
                'email_verified': True,
                'auth_provider': 'google',
                'created_at': datetime.now(),
                'last_login': datetime.now(),
                'is_admin': False,
                'total_orders': 0,
                'total_spent': 0
            }
            result = users_collection.insert_one(new_user)
            session['user_id'] = str(result.inserted_id)
            session['user_name'] = name
            session['user_email'] = email
        
        session['logged_in'] = True
        session['auth_provider'] = 'google'
        
        # Merge guest cart
        merge_guest_cart(session['user_id'])
        
        flash(f'Welcome back, {session["user_name"]}!', 'success')
        
        # Redirect to page user wanted or home
        next_page = session.pop('next', url_for('shop_page'))
        return redirect(next_page)
        
    except Exception as e:
        print(f"Google OAuth error: {e}")
        import traceback
        traceback.print_exc()
        flash('Google login failed. Please try again.', 'danger')
        return redirect(url_for('login_page'))

# ============================================
# AUTHENTICATION ROUTES
# ============================================

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    # Check if user already exists
    existing_user = users_collection.find_one({'email': email})
    if existing_user:
        return jsonify({'success': False, 'message': 'Email already registered'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
    
    # Hash password
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    # Create user
    user = {
        'name': name,
        'email': email,
        'password': hashed,
        'phone': '',
        'address': '',
        'email_verified': True,
        'auth_provider': 'email',
        'created_at': datetime.now(),
        'last_login': None,
        'is_admin': False,
        'total_orders': 0,
        'total_spent': 0
    }
    
    result = users_collection.insert_one(user)
    
    return jsonify({
        'success': True,
        'message': 'Registration successful! Please login.'
    })

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user = users_collection.find_one({'email': email})
    
    if user and user.get('password') and bcrypt.checkpw(password.encode('utf-8'), user['password']):
        users_collection.update_one(
            {'_id': user['_id']},
            {'$set': {'last_login': datetime.now()}}
        )
        
        session['user_id'] = str(user['_id'])
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['logged_in'] = True
        session['auth_provider'] = 'email'
        
        merge_guest_cart(str(user['_id']))
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {'name': user['name'], 'email': user['email']}
        })
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/session', methods=['GET'])
def api_get_session():
    if session.get('logged_in'):
        return jsonify({
            'logged_in': True,
            'user': {
                'id': session.get('user_id'),
                'name': session.get('user_name'),
                'email': session.get('user_email'),
                'auth_provider': session.get('auth_provider', 'email')
            }
        })
    return jsonify({'logged_in': False})

# ============================================
# PROFILE ROUTES
# ============================================

@app.route('/profile')
@login_required
def profile_page():
    user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
    return render_template('profile.html', user=user)

@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_update_profile():
    data = request.json
    users_collection.update_one(
        {'_id': ObjectId(session['user_id'])},
        {'$set': {
            'phone': data.get('phone', ''),
            'address': data.get('address', '')
        }}
    )
    return jsonify({'success': True, 'message': 'Profile updated'})

# ============================================
# PRODUCT ROUTES
# ============================================

@app.route('/api/products', methods=['GET'])
def api_get_products():
    query = {}
    category = request.args.get('category')
    if category and category != 'all':
        query['category'] = category
    
    search = request.args.get('search')
    if search:
        query['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'description': {'$regex': search, '$options': 'i'}}
        ]
    
    products = list(products_collection.find(query).limit(50))
    for product in products:
        product['_id'] = str(product['_id'])
    
    return jsonify(products)

@app.route('/product/<product_id>')
def product_detail(product_id):
    try:
        product = products_collection.find_one({'_id': ObjectId(product_id)})
        if not product:
            flash('Product not found', 'danger')
            return redirect(url_for('shop_page'))
        
        product['_id'] = str(product['_id'])
        
        # Get related products
        related = list(products_collection.find({
            'category': product['category'],
            '_id': {'$ne': ObjectId(product_id)}
        }).limit(4))
        
        for p in related:
            p['_id'] = str(p['_id'])
        
        return render_template('product_detail.html', product=product, related_products=related)
    except:
        flash('Product not found', 'danger')
        return redirect(url_for('shop_page'))

# ============================================
# ADMIN PRODUCT CREATION
# ============================================

@app.route('/admin/add-product', methods=['GET', 'POST'])
def admin_add_product():
    if request.method == 'POST':
        name = request.form.get('name')
        price = float(request.form.get('price'))
        category = request.form.get('category')
        description = request.form.get('description')
        image = request.form.get('image')
        stock = int(request.form.get('stock'))
        
        # Check for duplicate product
        existing = products_collection.find_one({'name': name})
        if existing:
            flash('Product with this name already exists!', 'danger')
            return redirect(url_for('admin_add_product'))
        
        product = {
            'name': name,
            'price': price,
            'category': category,
            'description': description,
            'image': image,
            'rating': 4.5,
            'stock': stock,
            'created_at': datetime.now()
        }
        
        products_collection.insert_one(product)
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin_add_product'))
    
    return render_template('admin_add_product.html')

# ============================================
# CART ROUTES
# ============================================

def merge_guest_cart(user_id):
    guest_id = f"guest_{request.remote_addr}"
    guest_cart = list(cart_collection.find({'user_id': guest_id}))
    
    for guest_item in guest_cart:
        existing = cart_collection.find_one({
            'user_id': user_id,
            'product_id': guest_item['product_id']
        })
        
        if existing:
            cart_collection.update_one(
                {'_id': existing['_id']},
                {'$inc': {'quantity': guest_item['quantity']}}
            )
        else:
            guest_item['user_id'] = user_id
            cart_collection.insert_one(guest_item)
        
        cart_collection.delete_one({'_id': guest_item['_id']})

@app.route('/api/cart', methods=['GET'])
def api_get_cart():
    user_id = session.get('user_id', 'guest_' + request.remote_addr)
    cart_items = list(cart_collection.find({'user_id': user_id}))
    
    items = []
    total = 0
    for item in cart_items:
        product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
        if product:
            items.append({
                'id': str(item['_id']),
                'product_id': str(product['_id']),
                'name': product['name'],
                'price': product['price'],
                'image': product.get('image', 'placeholder.jpg'),
                'quantity': item['quantity']
            })
            total += product['price'] * item['quantity']
    
    return jsonify({'items': items, 'total': total})

@app.route('/api/cart/add', methods=['POST'])
def api_add_to_cart():
    data = request.json
    user_id = session.get('user_id', 'guest_' + request.remote_addr)
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    
    existing = cart_collection.find_one({
        'user_id': user_id,
        'product_id': product_id
    })
    
    if existing:
        cart_collection.update_one(
            {'_id': existing['_id']},
            {'$inc': {'quantity': quantity}}
        )
    else:
        cart_collection.insert_one({
            'user_id': user_id,
            'product_id': product_id,
            'quantity': quantity,
            'added_at': datetime.now()
        })
    
    return jsonify({'success': True})

@app.route('/api/cart/remove/<product_id>', methods=['DELETE'])
def api_remove_from_cart(product_id):
    user_id = session.get('user_id', 'guest_' + request.remote_addr)
    cart_collection.delete_one({'user_id': user_id, 'product_id': product_id})
    return jsonify({'success': True})

# ============================================
# WISHLIST ROUTES
# ============================================

@app.route('/api/wishlist', methods=['GET'])
def api_get_wishlist():
    user_id = session.get('user_id', 'guest_' + request.remote_addr)
    wishlist_items = list(wishlist_collection.find({'user_id': user_id}))
    
    items = []
    for item in wishlist_items:
        product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
        if product:
            product['_id'] = str(product['_id'])
            items.append(product)
    
    return jsonify(items)

@app.route('/api/wishlist/toggle', methods=['POST'])
def api_toggle_wishlist():
    data = request.json
    user_id = session.get('user_id', 'guest_' + request.remote_addr)
    product_id = data.get('product_id')
    
    existing = wishlist_collection.find_one({
        'user_id': user_id,
        'product_id': product_id
    })
    
    if existing:
        wishlist_collection.delete_one({'_id': existing['_id']})
        return jsonify({'success': True, 'action': 'removed'})
    else:
        wishlist_collection.insert_one({
            'user_id': user_id,
            'product_id': product_id,
            'added_at': datetime.now()
        })
        return jsonify({'success': True, 'action': 'added'})

# ============================================
# ORDER ROUTES
# ============================================

@app.route('/orders')
@login_required
def orders_page():
    user_orders = list(orders_collection.find({'user_id': session['user_id']}).sort('created_at', -1))
    for order in user_orders:
        order['_id'] = str(order['_id'])
    return render_template('orders.html', orders=user_orders)

@app.route('/order/<order_id>')
@login_required
def order_detail(order_id):
    try:
        order = orders_collection.find_one({
            '_id': ObjectId(order_id),
            'user_id': session['user_id']
        })
        if not order:
            flash('Order not found', 'danger')
            return redirect(url_for('orders_page'))
        
        order['_id'] = str(order['_id'])
        return render_template('order_detail.html', order=order)
    except:
        flash('Order not found', 'danger')
        return redirect(url_for('orders_page'))

@app.route('/api/place-order', methods=['POST'])
@login_required
def api_place_order():
    user_id = session['user_id']
    cart_items = list(cart_collection.find({'user_id': user_id}))
    
    if not cart_items:
        return jsonify({'success': False, 'message': 'Cart is empty'})
    
    items = []
    total = 0
    
    for item in cart_items:
        product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
        if product:
            items.append({
                'product_id': str(product['_id']),
                'name': product['name'],
                'price': product['price'],
                'quantity': item['quantity'],
                'image': product.get('image', '')
            })
            total += product['price'] * item['quantity']
    
    order = {
        'user_id': user_id,
        'order_number': f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'items': items,
        'total_amount': total,
        'status': 'pending',
        'created_at': datetime.now(),
        'shipping_address': users_collection.find_one({'_id': ObjectId(user_id)}).get('address', '')
    }
    
    result = orders_collection.insert_one(order)
    
    # Clear cart
    cart_collection.delete_many({'user_id': user_id})
    
    # Update user stats
    users_collection.update_one(
        {'_id': ObjectId(user_id)},
        {'$inc': {'total_orders': 1, 'total_spent': total}}
    )
    
    return jsonify({
        'success': True,
        'order_id': str(result.inserted_id),
        'order_number': order['order_number']
    })

# ============================================
# FETCH PRODUCTS FROM API
# ============================================

@app.route('/admin/fetch-products', methods=['GET', 'POST'])
def admin_fetch_products():
    if request.method == 'POST':
        source = request.form.get('source')
        new_count = 0
        
        if source == 'fakestore':
            url = 'https://fakestoreapi.com/products'
            response = requests.get(url)
            api_products = response.json()
            
            for p in api_products:
                product = {
                    'name': p['title'][:100],
                    'price': p['price'],
                    'category': p['category'].replace("'", "").title(),
                    'description': p['description'],
                    'image': p['image'],
                    'rating': p['rating']['rate'],
                    'stock': 50,
                    'created_at': datetime.now()
                }
                try:
                    products_collection.insert_one(product)
                    new_count += 1
                except:
                    pass
            
            flash(f'Added {new_count} new products from FakeStore!', 'success')
        
        elif source == 'dummyjson':
            url = 'https://dummyjson.com/products?limit=30'
            response = requests.get(url)
            data = response.json()
            
            for p in data['products']:
                product = {
                    'name': p['title'],
                    'price': p['price'],
                    'category': p['category'].title(),
                    'description': p['description'],
                    'image': p['thumbnail'],
                    'rating': p['rating'],
                    'stock': p['stock'],
                    'created_at': datetime.now()
                }
                try:
                    products_collection.insert_one(product)
                    new_count += 1
                except:
                    pass
            
            flash(f'Added {new_count} new products from DummyJSON!', 'success')
        
        return redirect(url_for('admin_fetch_products'))
    
    product_count = products_collection.count_documents({})
    return render_template('admin_fetch.html', product_count=product_count)

# ============================================
# PAGE ROUTES (FIXED - No duplicates)
# ============================================

@app.route('/')
def home():
    """Homepage - shows featured products"""
    products = list(products_collection.find().limit(8))
    for product in products:
        product['_id'] = str(product['_id'])
    return render_template('index.html', products=products)

@app.route('/shop')
def shop_page():
    """Shop page - shows all products with filters"""
    # Get filter parameters
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'latest')
    page = int(request.args.get('page', 1))
    per_page = 12
    
    # Build query
    query = {}
    if category:
        query['category'] = category
    if search:
        query['name'] = {'$regex': search, '$options': 'i'}
    
    # Sort options
    sort_options = {
        'latest': ('created_at', -1),
        'price_asc': ('price', 1),
        'price_desc': ('price', -1),
        'rating': ('rating', -1)
    }
    sort_field, sort_order = sort_options.get(sort, ('created_at', -1))
    
    # Get total count for pagination
    total_products = products_collection.count_documents(query)
    total_pages = (total_products + per_page - 1) // per_page
    
    # Get products
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

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

if __name__ == '__main__':
    app.run(debug=True, port=int(os.getenv('PORT', 5000)))