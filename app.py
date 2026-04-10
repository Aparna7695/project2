from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
# A secret key is needed to keep the client-side sessions secure. 
app.config['SECRET_KEY'] = 'super-secret-agriculture-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
# If a user is not logged in and tries to access a protected page, redirect them to login page
login_manager.login_view = 'login'

# Database Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user') # 'user' or 'admin'
    is_active_account = db.Column(db.Boolean, default=True) # Use a custom name to avoid shadowing UserMixin property if needed, actually is_active is fine. Let's use is_active.
    last_login = db.Column(db.DateTime, nullable=True)
    orders = db.relationship('Order', backref='user', lazy=True, cascade='all, delete-orphan')
    
    @property
    def is_active(self):
        return self.is_active_account

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    crop_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    address = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        # Check if user exists and password is correct
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Your account has been deactivated by the admin.', 'danger')
                return redirect(url_for('login'))
                
            login_user(user)
            user.last_login = datetime.now()
            db.session.commit()
            
            flash('Logged in successfully!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if email is already taken
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email address already exists.', 'warning')
            return redirect(url_for('signup'))
            
        # Create new user, hashing the password for security
        new_user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password)
        )
        # For demonstration purposes, if the email contains 'admin', make them an admin
        if 'admin' in email.lower():
            new_user.role = 'admin'
            
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/crops')
@login_required
def crops():
    if current_user.role != 'user':
        flash('Unauthorized Access: Only farmers/users can access the marketplace.', 'warning')
        return redirect(url_for('admin'))
        
    # List of crops we will display
    crop_list = [
        {"name": "Rice", "price": "₹ 45 per kg", "image": "rice.png", "description": "High-quality basmati rice right from the farm."},
        {"name": "Wheat", "price": "₹ 30 per kg", "image": "wheat.png", "description": "Freshly harvested wheat grains."},
        {"name": "Maize", "price": "₹ 25 per kg", "image": "maize.png", "description": "Organic sweet corn varieties."},
        {"name": "Sugarcane", "price": "₹ 300 per quintal", "image": "sugarcane.png", "description": "Premium sugarcane for sugar production."},
        {"name": "Cotton", "price": "₹ 6000 per quintal", "image": "cotton.png", "description": "Fine long-staple cotton."},
        {"name": "Tomato", "price": "₹ 40 per kg", "image": "tomato.png", "description": "Juicy, ripe tomatoes direct from cultivation."},
        {"name": "Potato", "price": "₹ 20 per kg", "image": "potato.png", "description": "Farm fresh potatoes."},
        {"name": "Onion", "price": "₹ 35 per kg", "image": "onion.png", "description": "Crisp and flavorful onions."}
    ]
    return render_template('crops.html', crops=crop_list)

@app.route('/buy', methods=['POST'])
@login_required
def buy():
    if current_user.role != 'user':
        flash('Unauthorized Action.', 'danger')
        return redirect(url_for('dashboard'))
        
    crop_name = request.form.get('crop_name')
    price = request.form.get('price')
    quantity = request.form.get('quantity')
    address = request.form.get('address')
    
    if not all([crop_name, price, quantity, address]):
        flash('All fields are required to place an order.', 'warning')
        return redirect(url_for('crops'))
        
    new_order = Order(
        user_id=current_user.id,
        crop_name=crop_name,
        price=price,
        quantity=int(quantity),
        address=address
    )
    db.session.add(new_order)
    db.session.commit()
    
    flash(f'Order for {quantity}kg of {crop_name} placed successfully!', 'success')
    return redirect(url_for('crops'))

@app.route('/admin')
@login_required
def admin():
    # Authorization check - ONLY admin can access this page
    if current_user.role != 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))
        
    all_users = User.query.all()
    all_orders = Order.query.all()
    return render_template('admin.html', users=all_users, orders=all_orders)

@app.route('/admin/sales')
@login_required
def sell_details():
    if current_user.role != 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))
        
    all_orders = Order.query.all()
    return render_template('sell_details.html', orders=all_orders)

@app.route('/admin/delete/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))
        
    user_to_delete = User.query.get_or_404(user_id)
    if user_to_delete.id == current_user.id:
        flash('You cannot delete yourself!', 'danger')
        return redirect(url_for('admin'))
        
    db.session.delete(user_to_delete)
    db.session.commit()
    flash(f'User {user_to_delete.name} deleted successfully.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/toggle_status/<int:user_id>')
@login_required
def toggle_status(user_id):
    if current_user.role != 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))
        
    user_to_toggle = User.query.get_or_404(user_id)
    if user_to_toggle.id == current_user.id:
        flash('You cannot deactivate yourself!', 'danger')
        return redirect(url_for('admin'))
        
    user_to_toggle.is_active_account = not user_to_toggle.is_active_account
    db.session.commit()
    
    status = "activated" if user_to_toggle.is_active_account else "deactivated"
    flash(f'User {user_to_toggle.name} has been {status}.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/order/<int:order_id>/<action>')
@login_required
def modify_order(order_id, action):
    if current_user.role != 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))
        
    order = Order.query.get_or_404(order_id)
    if action == 'approve':
        order.status = 'Approved'
        flash(f'Order #{order.id} approved successfully.', 'success')
    elif action == 'reject':
        order.status = 'Rejected'
        flash(f'Order #{order.id} rejected.', 'info')
    else:
        flash('Invalid action.', 'danger')
        
    db.session.commit()
    return redirect(url_for('sell_details'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
