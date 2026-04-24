from flask import Flask, render_template, redirect, url_for, request, flash, g
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import sqlite3
import re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__) # FIXED: name ആക്കി
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-key-only-for-local')
DATABASE = 'database.db'

ADMIN_SECRET_CODE = 'AGRI-SECRET-2026'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_active_account INTEGER DEFAULT 1,
        created_at TIMESTAMP,
        last_login TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS "order" (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        crop_name TEXT NOT NULL,
        price TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        address TEXT NOT NULL,
        payment_method TEXT,
        status TEXT NOT NULL DEFAULT 'Pending',
        created_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user (id)
    );

    CREATE TABLE IF NOT EXISTS notification (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user (id)
    );
    ''')
    conn.commit()
    conn.close()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, name, email, password_hash, role, is_active_account): # FIXED: init
        self.id = id
        self.name = name
        self.email = email
        self.password_hash = password_hash
        self.role = role
        self.is_active_account = bool(is_active_account)

    @property
    def is_active(self):
        return self.is_active_account

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user_row = conn.execute('SELECT * FROM user WHERE id =?', (user_id,)).fetchone()
    conn.close()
    if user_row:
        return User(user_row['id'], user_row['name'], user_row['email'],
                    user_row['password_hash'], user_row['role'], user_row['is_active_account'])
    return None

@app.context_processor
def inject_notification_count():
    if current_user.is_authenticated and current_user.role == 'user':
        conn = get_db_connection()
        notifications = conn.execute('SELECT * FROM notification WHERE user_id =? ORDER BY created_at DESC LIMIT 5',
                                   (current_user.id,)).fetchall()
        count = conn.execute('SELECT COUNT(*) FROM notification WHERE user_id =? AND is_read = 0',
                           (current_user.id,)).fetchone()[0]
        conn.close()
        return dict(notifications=notifications, notif_count=count)
    return dict(notifications=[], notif_count=0)

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %I:%M %p'):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            if '.' in value:
                value = value.split('.')[0]
            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            return dt.strftime(format)
        except Exception:
            try:
                dt = datetime.fromisoformat(value)
                return dt.strftime(format)
            except Exception:
                return value
    return value.strftime(format)

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST': # FIXED: Indentation
        email = request.form.get('email')
        password = request.form.get('password')

        email_regex = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        if not re.match(email_regex, email or '', re.I):
            flash('Please enter a valid email address.', 'warning')
            return redirect(url_for('login'))
        conn = get_db_connection()
        user_row = conn.execute('SELECT * FROM user WHERE email=?', (email,)).fetchone()

        if not user_row:
            conn.close()
            flash('Email not registered! Please register first.', 'warning')
            return redirect(url_for('signup'))

        if check_password_hash(user_row['password_hash'], password):
            user = User(user_row['id'], user_row['name'], user_row['email'],
                        user_row['password_hash'], user_row['role'], user_row['is_active_account'])

            if not user.is_active:
                conn.close()
                flash('Your account has been deactivated by the admin.', 'danger')
                return redirect(url_for('login'))

            login_user(user)
            conn.execute('UPDATE user SET last_login =? WHERE id =?', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user.id))
            conn.commit()
            conn.close()

            flash('Logged in successfully!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin'))
            return redirect(url_for('dashboard'))
        else:
            conn.close()
            flash('Invalid password!', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        admin_code = request.form.get('admin_code', '').strip()

        role = request.form.get('role')
        if role == 'admin':
            if admin_code!= ADMIN_SECRET_CODE:
                flash('Invalid Secret Code! Admin registration failed.', 'danger')
                return redirect(url_for('signup'))
        else:
            role = 'user'

        email_regex = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
        if not re.match(email_regex, email or '', re.I):
            flash('Please enter a valid email address.', 'warning')
            return redirect(url_for('signup'))

        conn = get_db_connection()
        existing_user = conn.execute('SELECT id FROM user WHERE email =?', (email,)).fetchone()

        if existing_user:
            conn.close()
            flash('Email address already exists.', 'warning')
            return redirect(url_for('signup'))

        conn.execute('INSERT INTO user (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)',
                     (name, email, generate_password_hash(password), role, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

        # Auto login after signup
        new_user = conn.execute('SELECT * FROM user WHERE email =?', (email,)).fetchone()
        user_obj = User(new_user['id'], new_user['name'], new_user['email'],
                       new_user['password_hash'], new_user['role'], new_user['is_active_account'])
        login_user(user_obj)
        conn.close()

        flash('Registration successful! You are now logged in.', 'success')
        return redirect(url_for('dashboard'))

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
    if current_user.role!= 'user':
        flash('Unauthorized Access: Only farmers can access the marketplace.', 'warning')
        return redirect(url_for('admin'))
    crop_list = [
        {"name": "Rice", "price": "₹ 45 per kg", "image": "rice.png", "description": "High-quality basmati rice."},
        {"name": "Wheat", "price": "₹ 30 per kg", "image": "wheat.png", "description": "Freshly harvested wheat grains."},
        {"name": "Maize", "price": "₹ 25 per kg", "image": "maize.png", "description": "Organic sweet corn varieties."},
        {"name": "Sugarcane", "price": "₹ 300 per quintal", "image": "sugarcane.png", "description": "Premium sugarcane."},
        {"name": "Cotton", "price": "₹ 6000 per quintal", "image": "cotton.png", "description": "Fine long-staple cotton."},
        {"name": "Tomato", "price": "₹ 40 per kg", "image": "tomato.png", "description": "Juicy, ripe tomatoes."},
        {"name": "Potato", "price": "₹ 20 per kg", "image": "potato.png", "description": "Farm fresh potatoes."},
        {"name": "Onion", "price": "₹ 35 per kg", "image": "onion.png", "description": "Crisp and flavorful onions."}
    ]
    return render_template('crops.html', crops=crop_list)

@app.route('/buy', methods=['POST'])
@login_required
def buy():
    if current_user.role!= 'user':
        flash('Unauthorized Action.', 'danger')
        return redirect(url_for('dashboard'))

    crop_name = request.form.get('crop_name')
    price = request.form.get('price')
    quantity = request.form.get('quantity')
    address = request.form.get('address')
    payment_method = request.form.get('payment_method')

    if not all([crop_name, price, quantity, address, payment_method]):
        flash('All fields are required.', 'warning')
        return redirect(url_for('crops'))

    conn = get_db_connection()
    conn.execute('INSERT INTO "order" (user_id, crop_name, price, quantity, address, payment_method, created_at) VALUES (?,?,?,?,?,?,?)',
                 (current_user.id, crop_name, price, int(quantity), address, payment_method, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

    flash(f'Order for {quantity}kg of {crop_name} placed successfully! Waiting for admin approval.', 'success')
    return redirect(url_for('crops'))

@app.route('/admin')
@login_required
def admin():
    if current_user.role!= 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    all_users = conn.execute('SELECT * FROM user ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin.html', users=all_users)

@app.route('/admin/sales')
@login_required
def sell_details():
    if current_user.role!= 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    all_orders = conn.execute('''
        SELECT o.*, u.name as user_name
        FROM "order" o
        JOIN user u ON o.user_id = u.id
        ORDER BY o.id DESC
    ''').fetchall()
    conn.close()
    return render_template('selldetails.html', orders=all_orders)

@app.route('/admin/delete/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.role!= 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    if user_id == current_user.id:
        flash('You cannot delete yourself!', 'danger')
        return redirect(url_for('admin'))

    conn = get_db_connection()
    conn.execute('DELETE FROM notification WHERE user_id =?', (user_id,))
    conn.execute('DELETE FROM "order" WHERE user_id =?', (user_id,))
    conn.execute('DELETE FROM user WHERE id =?', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully.', 'success')
    return redirect(url_for('admin'))
@app.route('/admin/toggle_status/<int:user_id>')
@login_required
def toggle_status(user_id):
    if current_user.role!= 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    if user_id == current_user.id:
        flash('You cannot deactivate yourself!', 'danger')
        return redirect(url_for('admin'))
    conn = get_db_connection()
    user_row = conn.execute('SELECT is_active_account FROM user WHERE id =?', (user_id,)).fetchone()
    if user_row:
        new_status = 0 if user_row['is_active_account'] else 1
        conn.execute('UPDATE user SET is_active_account =? WHERE id =?', (new_status, user_id))
        conn.commit()
        status_text = "activated" if new_status else "deactivated"
        flash(f'User status updated to {status_text}.', 'success')
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/order/<int:order_id>/<action>')
@login_required
def modify_order(order_id, action):
    if current_user.role!= 'admin':
        flash('Unauthorized Access: Admins only.', 'danger')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    order = conn.execute('SELECT * FROM "order" WHERE id =?', (order_id,)).fetchone()

    # FIXED: Single UPDATE + correct status values + notification logic
    if action.lower() == 'approve':
        status = 'Approved'
        msg = f'✅ Your order #{order_id} for {order["quantity"]}kg {order["crop_name"]} has been approved by admin'
    elif action.lower() == 'reject':
        status = 'Rejected'
        msg = f'❌ Your order #{order_id} for {order["quantity"]}kg {order["crop_name"]} has been rejected by admin'
    else:
        conn.close()
        flash('Invalid action.', 'danger')
        return redirect(url_for('sell_details'))

    conn.execute('UPDATE "order" SET status =? WHERE id =?', (status, order_id))
    if order:
        conn.execute('INSERT INTO notification (user_id, message, is_read, created_at) VALUES (?,?,0,?)',
                     (order['user_id'], msg, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    conn.commit()
    conn.close()
    flash(f'Order #{order_id} {action}d successfully.', 'success')
    return redirect(url_for('sell_details'))

@app.route('/mark_read/<int:notif_id>')
@login_required
def mark_read(notif_id):
    conn = get_db_connection()
    conn.execute('UPDATE notification SET is_read = 1 WHERE id =? AND user_id =?',
                (notif_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__': 
    init_db()
    app.run(debug=True)
