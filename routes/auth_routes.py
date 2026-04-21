from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from models.user import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    # If user is already logged in, redirect based on role
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin.admin_dashboard'))
        return redirect(url_for('product.index'))
    
    if request.method == 'GET':
        return render_template('login.html')
    
    # POST request - handle login form submission
    data = request.get_json() if request.is_json else request.form
    email = data.get('email')
    password = data.get('password')
    
    # Validate input
    if not email or not password:
        error_msg = 'Email and password are required'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        return render_template('login.html', error=error_msg)
    
    # Authenticate user
    user = User.authenticate(email, password)
    
    if user:
        # Set session variables
        session['user_id'] = user['user_id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['is_admin'] = user.get('is_admin', False)
        session['logged_in'] = True
        
        # Check for redirect URL from query parameter
        next_url = request.args.get('next')
        
        # Redirect based on user role or next parameter
        if next_url:
            redirect_url = next_url
        elif session['is_admin']:
            redirect_url = url_for('admin.admin_dashboard')
        else:
            redirect_url = url_for('product.index')
        
        if request.is_json:
            return jsonify({'success': True, 'redirect': redirect_url})
        return redirect(redirect_url)
    
    # Authentication failed
    error_msg = 'Invalid email or password'
    if request.is_json:
        return jsonify({'success': False, 'message': error_msg}), 401
    return render_template('login.html', error=error_msg)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration"""
    # If user is already logged in, redirect to home
    if 'user_id' in session:
        return redirect(url_for('product.index'))
    
    if request.method == 'GET':
        return render_template('signup.html')
    
    # POST request - handle signup form submission
    data = request.get_json() if request.is_json else request.form
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    address = data.get('address')
    phone = data.get('phone')
    confirm_password = data.get('confirm_password')
    
    # Validation
    if not email or not password or not name:
        error_msg = 'Name, email and password are required'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        return render_template('signup.html', error=error_msg)
    
    if password != confirm_password:
        error_msg = 'Passwords do not match'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        return render_template('signup.html', error=error_msg)
    
    if len(password) < 6:
        error_msg = 'Password must be at least 6 characters'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        return render_template('signup.html', error=error_msg)
    
    # Create user
    user, message = User.create_user(email, password, name, address, phone)
    
    if user:
        # Set session variables
        session['user_id'] = user['user_id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['is_admin'] = False
        session['logged_in'] = True
        
        if request.is_json:
            return jsonify({'success': True, 'redirect': url_for('product.index')})
        return redirect(url_for('product.index'))
    
    # User creation failed
    if request.is_json:
        return jsonify({'success': False, 'message': message}), 400
    return render_template('signup.html', error=message)

@auth_bp.route('/logout')
def logout():
    """Handle user logout and redirect to login page"""
    # Clear all session data
    session.clear()
    
    # Redirect to login page with logout message
    return redirect(url_for('auth.login', logout='success'))

@auth_bp.route('/profile')
def profile():
    """View user profile"""
    if 'user_id' not in session:
        # Save the requested URL to redirect back after login
        return redirect(url_for('auth.login', next=request.url))
    
    user = User.get_user_by_id(session['user_id'])
    return render_template('profile.html', user=user)

@auth_bp.route('/update-profile', methods=['POST'])
def update_profile():
    """Update user profile"""
    if 'user_id' not in session:
        if request.is_json:
            return jsonify({'success': False, 'message': 'Please login first'}), 401
        return redirect(url_for('auth.login'))
    
    data = request.get_json() if request.is_json else request.form
    
    update_data = {}
    if data.get('name'):
        update_data['name'] = data.get('name')
        session['user_name'] = data.get('name')
    if data.get('address'):
        update_data['address'] = data.get('address')
    if data.get('phone'):
        update_data['phone'] = data.get('phone')
    
    if update_data:
        User.update_user(session['user_id'], update_data)
    
    if request.is_json:
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
    return redirect(url_for('auth.profile'))

@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    """Change user password"""
    if 'user_id' not in session:
        if request.is_json:
            return jsonify({'success': False, 'message': 'Please login first'}), 401
        return redirect(url_for('auth.login'))
    
    data = request.get_json() if request.is_json else request.form
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    # Validate passwords
    if not old_password or not new_password:
        error_msg = 'All password fields are required'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        return render_template('profile.html', error=error_msg)
    
    if new_password != confirm_password:
        error_msg = 'New passwords do not match'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        return render_template('profile.html', error=error_msg)
    
    if len(new_password) < 6:
        error_msg = 'New password must be at least 6 characters'
        if request.is_json:
            return jsonify({'success': False, 'message': error_msg}), 400
        return render_template('profile.html', error=error_msg)
    
    # Verify old password and update
    user = User.get_user_by_id(session['user_id'])
    if user and User.authenticate(user['email'], old_password):
        from werkzeug.security import generate_password_hash
        new_hash = generate_password_hash(new_password)
        User.get_collection().update_one(
            {'user_id': str(session['user_id'])},
            {'$set': {'password_hash': new_hash}}
        )
        if request.is_json:
            return jsonify({'success': True, 'message': 'Password changed successfully'})
        return redirect(url_for('auth.profile'))
    
    error_msg = 'Current password is incorrect'
    if request.is_json:
        return jsonify({'success': False, 'message': error_msg}), 400
    return render_template('profile.html', error=error_msg)