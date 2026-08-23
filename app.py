import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, 
    login_required, current_user
)
from werkzeug.security import check_password_hash

# Modular Configuration & Helpers Import
from config import config
from helpers import (
    role_required, admin_required, parse_date_components,
    format_currency, format_date, ui_date_filter,
    badge_session_filter, badge_type_filter, badge_status_filter
)

# Initialize Flask Application
app = Flask(__name__)
env = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[env])

# Register Modular Reporting Blueprint
from dynamic import dynamic_bp
app.register_blueprint(dynamic_bp)

# ---------------------------------------------------------
# REGISTER JINJA TEMPLATE FILTERS
# ---------------------------------------------------------
app.jinja_env.filters['currency'] = format_currency
app.jinja_env.filters['format_date'] = format_date
app.jinja_env.filters['ui_date'] = ui_date_filter
app.jinja_env.filters['badge_session'] = badge_session_filter
app.jinja_env.filters['badge_type'] = badge_type_filter
app.jinja_env.filters['badge_status'] = badge_status_filter

# ---------------------------------------------------------
# DATABASE CONNECTION FACTORY
# ---------------------------------------------------------
def get_db():
    """Direct database connection factory with Row factory enabled."""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    if app.config.get('SQLITE_FOREIGN_KEYS'):
        conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# ---------------------------------------------------------
# FLASK-LOGIN & USER MODEL SETUP
# ---------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = None

class User(UserMixin):
    def __init__(self, user_id, username, role):
        self.id = user_id
        self.username = username
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    user_row = conn.execute(
        "SELECT user_id, username, role FROM users WHERE user_id = ? AND is_active = 1", 
        (user_id,)
    ).fetchone()
    conn.close()
    
    if user_row:
        return User(user_row['user_id'], user_row['username'], user_row['role'])
    return None

# ---------------------------------------------------------
# AUTHENTICATION ROUTES (LOGIN / LOGOUT)
# ---------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('daily_activity_page'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db()
        user_row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", 
            (username,)
        ).fetchone()
        conn.close()

        if user_row and check_password_hash(user_row['password_hash'], password):
            user = User(user_row['user_id'], user_row['username'], user_row['role'])
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('daily_activity_page'))
        
        flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# ---------------------------------------------------------
# 1. HOME / INDEX
# ---------------------------------------------------------
@app.route('/')
def index():
    return redirect(url_for('daily_activity_page'))

# ---------------------------------------------------------
# 2. DAILY ACTIVITY MODULE
# ---------------------------------------------------------
@app.route('/daily_activity', methods=['GET'])
@login_required
def daily_activity_page():
    conn = get_db()
    
    name_rows = conn.execute("""
        SELECT DISTINCT person_name 
        FROM daily_activity 
        WHERE person_name IS NOT NULL AND person_name != '' 
        ORDER BY person_name ASC
    """).fetchall()
    existing_names = [r['person_name'] for r in name_rows]

    activities = conn.execute("""
        SELECT a.activity_lookup_id, a.activity_name, a.default_amount, 
               CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income, 
               CASE WHEN CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 THEN 'INCOME' ELSE 'EXPENSE' END as txn_type_label,
               a.is_active, c.category_name
        FROM activity_lookup a
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE a.is_active = 1
        ORDER BY activity_name ASC
    """).fetchall()

    edit_id = request.args.get('edit_id')
    editing_txn = None
    if edit_id:
        editing_txn = conn.execute("""
            SELECT t.daily_activity_id, t.txn_date, 
                   CAST(COALESCE(t.session_type, 1) AS INTEGER) as session_type, 
                   t.person_name, t.activity_lookup_id, t.unit_price, 
                   t.quantity, t.total_amount, t.remarks, 
                   CAST(COALESCE(t.is_active, 1) AS INTEGER) as is_active,
                   CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income
            FROM daily_activity t
            LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
            WHERE t.daily_activity_id = ?
        """, (edit_id,)).fetchone()

    transactions = conn.execute("""
        SELECT 
            t.daily_activity_id,
            t.txn_date,
            CAST(COALESCE(t.session_type, 1) AS INTEGER) as session_type,
            t.person_name,
            t.unit_price,
            t.quantity,
            t.total_amount,
            t.remarks,
            CAST(COALESCE(t.is_active, 1) AS INTEGER) as is_active,
            t.updated_ts,
            a.activity_name,
            CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income,
            c.category_name
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        ORDER BY t.updated_ts DESC, t.txn_date DESC, t.daily_activity_id DESC
    """).fetchall()

    conn.close()
    return render_template(
        'daily_activity.html',
        transactions=transactions,
        activities=activities,
        existing_names=existing_names,
        editing_txn=editing_txn
    )

@app.route('/daily_activity/save', methods=['POST'])
@login_required
def daily_activity_save():
    daily_activity_id = request.form.get('daily_activity_id')
    raw_date = request.form.get('txn_date')
    session_type = int(request.form.get('session_type', 1))
    activity_lookup_id = request.form.get('activity_lookup_id')
    person_name = request.form.get('person_name', '').strip()
    unit_price = float(request.form.get('unit_price', 0.0))
    quantity = int(request.form.get('quantity', 1))
    total_amount = float(request.form.get('total_amount', 0.0))
    remarks = request.form.get('remarks', '').strip()
    is_active = int(request.form.get('is_active', 1))

    conn = get_db()
    cursor = conn.cursor()

    if daily_activity_id:
        existing = cursor.execute(
            "SELECT txn_date FROM daily_activity WHERE daily_activity_id = ?", 
            (daily_activity_id,)
        ).fetchone()

        parsed_new_date = parse_date_components(raw_date)
        if parsed_new_date:
            txn_date = parsed_new_date
        else:
            txn_date = existing['txn_date'] if existing else datetime.now().strftime('%Y-%m-%d')

        cursor.execute("""
            UPDATE daily_activity 
            SET txn_date = ?, 
                session_type = ?, 
                activity_lookup_id = ?, 
                person_name = ?, 
                unit_price = ?, 
                quantity = ?, 
                total_amount = ?, 
                remarks = ?, 
                is_active = ?, 
                updated_ts = CURRENT_TIMESTAMP
            WHERE daily_activity_id = ?
        """, (txn_date, session_type, activity_lookup_id, person_name, 
              unit_price, quantity, total_amount, remarks, is_active, daily_activity_id))
        flash(f'Daily Activity entry #{daily_activity_id} updated successfully!', 'success')
        
    else:
        txn_date = parse_date_components(raw_date) or datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            INSERT INTO daily_activity 
            (txn_date, session_type, activity_lookup_id, person_name, unit_price, quantity, total_amount, remarks, is_active, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (txn_date, session_type, activity_lookup_id, person_name, unit_price, quantity, total_amount, remarks, is_active))
        flash('New Daily Activity recorded successfully!', 'success')

    conn.commit()
    conn.close()
    return redirect(url_for('daily_activity_page'))

# ---------------------------------------------------------
# 3. FINANCIAL DASHBOARD (ADMIN ONLY)
# ---------------------------------------------------------
@app.route('/dashboard')
@login_required
@role_required('admin')
def dashboard_page():
    conn = get_db()
    current_year_str = datetime.now().strftime('%Y')

    years_rows = conn.execute("""
        SELECT DISTINCT strftime('%Y', txn_date) as year 
        FROM daily_activity 
        WHERE is_active = 1 AND txn_date IS NOT NULL AND txn_date != ''
        ORDER BY year DESC
    """).fetchall()

    available_years = [r['year'] for r in years_rows if r['year']]
    
    selected_year = request.args.get('year')
    if not selected_year:
        selected_year = available_years[0] if available_years else current_year_str

    if current_year_str not in available_years:
        available_years.insert(0, current_year_str)

    kpi = conn.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 THEN t.total_amount ELSE 0 END), 0) as total_income,
            COALESCE(SUM(CASE WHEN CAST(COALESCE(a.is_income, 1) AS INTEGER) = 0 THEN t.total_amount ELSE 0 END), 0) as total_expense
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        WHERE t.is_active = 1 AND strftime('%Y', t.txn_date) = ?
    """, (selected_year,)).fetchone()

    total_income = float(kpi['total_income']) if kpi and kpi['total_income'] else 0.0
    total_expense = float(kpi['total_expense']) if kpi and kpi['total_expense'] else 0.0
    net_surplus = total_income - total_expense

    monthly_rows = conn.execute("""
        SELECT 
            strftime('%m', t.txn_date) as month_num,
            COALESCE(SUM(CASE WHEN CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 THEN t.total_amount ELSE 0 END), 0) as income,
            COALESCE(SUM(CASE WHEN CAST(COALESCE(a.is_income, 1) AS INTEGER) = 0 THEN t.total_amount ELSE 0 END), 0) as expense
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        WHERE t.is_active = 1 AND strftime('%Y', t.txn_date) = ?
        GROUP BY month_num
        ORDER BY month_num ASC
    """, (selected_year,)).fetchall()

    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    income_data = [0.0] * 12
    expense_data = [0.0] * 12

    for r in monthly_rows:
        if r['month_num']:
            try:
                idx = int(r['month_num']) - 1
                if 0 <= idx < 12:
                    income_data[idx] = float(r['income'])
                    expense_data[idx] = float(r['expense'])
            except ValueError:
                pass

    category_dist = conn.execute("""
        SELECT c.category_name, SUM(t.total_amount) as amount
        FROM daily_activity t
        JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE t.is_active = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 AND strftime('%Y', t.txn_date) = ?
        GROUP BY c.category_name
        ORDER BY amount DESC
    """, (selected_year,)).fetchall()

    cat_labels = [r['category_name'] for r in category_dist]
    cat_values = [float(r['amount']) for r in category_dist]

    conn.close()

    return render_template(
        'dashboard.html',
        selected_year=selected_year,
        available_years=available_years,
        total_income=total_income,
        total_expense=total_expense,
        net_surplus=net_surplus,
        months=months,
        income_data=income_data,
        expense_data=expense_data,
        cat_labels=cat_labels,
        cat_values=cat_values
    )

# ---------------------------------------------------------
# 4. MAINTENANCE MODULE (ADMIN ONLY)
# ---------------------------------------------------------
@app.route('/maintenance/category_lookup')
@login_required
@role_required('admin')
def category_lookup_page():
    conn = get_db()
    categories = conn.execute(
        "SELECT *, CAST(COALESCE(is_active, 1) AS INTEGER) as is_active FROM category_lookup ORDER BY category_name ASC"
    ).fetchall()
    conn.close()
    return render_template('category_lookup.html', category_lookups=categories)

@app.route('/maintenance/category_lookup/save', methods=['POST'])
@login_required
@role_required('admin')
def category_lookup_save():
    cat_id = request.form.get('category_lookup_id')
    cat_name = request.form.get('category_name', '').strip()
    is_active = int(request.form.get('is_active', 1))

    if not cat_name:
        flash('Category Name cannot be empty.', 'danger')
        return redirect(url_for('category_lookup_page'))

    conn = get_db()
    cursor = conn.cursor()

    if cat_id:
        duplicate = cursor.execute(
            "SELECT category_lookup_id FROM category_lookup WHERE LOWER(category_name) = LOWER(?) AND category_lookup_id != ?",
            (cat_name, cat_id)
        ).fetchone()
    else:
        duplicate = cursor.execute(
            "SELECT category_lookup_id FROM category_lookup WHERE LOWER(category_name) = LOWER(?)",
            (cat_name,)
        ).fetchone()

    if duplicate:
        conn.close()
        flash(f'Category name "{cat_name}" already exists. Please use a unique name.', 'danger')
        return redirect(url_for('category_lookup_page'))

    if cat_id:
        cursor.execute(
            "UPDATE category_lookup SET category_name = ?, is_active = ? WHERE category_lookup_id = ?",
            (cat_name, is_active, cat_id)
        )
        flash(f'Category "{cat_name}" updated successfully!', 'success')
    else:
        cursor.execute(
            "INSERT INTO category_lookup (category_name, is_active) VALUES (?, ?)", 
            (cat_name, is_active)
        )
        flash(f'New category "{cat_name}" created successfully!', 'success')
        
    conn.commit()
    conn.close()
    return redirect(url_for('category_lookup_page'))

@app.route('/maintenance/activity_lookup')
@login_required
@role_required('admin')
def activity_lookup_page():
    conn = get_db()
    activities = conn.execute("""
        SELECT a.*, CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income, 
               CAST(COALESCE(a.is_active, 1) AS INTEGER) as is_active, c.category_name 
        FROM activity_lookup a 
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id 
        ORDER BY a.activity_name ASC
    """).fetchall()
    categories = conn.execute(
        "SELECT * FROM category_lookup WHERE is_active = 1 ORDER BY category_name ASC"
    ).fetchall()
    conn.close()
    return render_template('activity_lookup.html', activity_lookups=activities, category_lookups=categories)

@app.route('/maintenance/activity_lookup/save', methods=['POST'])
@login_required
@role_required('admin')
def activity_lookup_save():
    act_id = request.form.get('activity_lookup_id')
    cat_id = request.form.get('category_lookup_id')
    act_name = request.form.get('activity_name', '').strip()
    default_amount = float(request.form.get('default_amount', 0.0))
    is_income = int(request.form.get('is_income', 1))
    is_active = int(request.form.get('is_active', 1))

    if not act_name:
        flash('Activity Name cannot be empty.', 'danger')
        return redirect(url_for('activity_lookup_page'))

    conn = get_db()
    cursor = conn.cursor()

    if act_id:
        duplicate = cursor.execute(
            "SELECT activity_lookup_id FROM activity_lookup WHERE LOWER(activity_name) = LOWER(?) AND activity_lookup_id != ?",
            (act_name, act_id)
        ).fetchone()
    else:
        duplicate = cursor.execute(
            "SELECT activity_lookup_id FROM activity_lookup WHERE LOWER(activity_name) = LOWER(?)",
            (act_name,)
        ).fetchone()

    if duplicate:
        conn.close()
        flash(f'Activity name "{act_name}" already exists. Please use a unique name.', 'danger')
        return redirect(url_for('activity_lookup_page'))

    if act_id:
        cursor.execute("""
            UPDATE activity_lookup 
            SET category_lookup_id = ?, activity_name = ?, default_amount = ?, is_income = ?, is_active = ? 
            WHERE activity_lookup_id = ?
        """, (cat_id, act_name, default_amount, is_income, is_active, act_id))
        flash(f'Activity "{act_name}" updated successfully!', 'success')
    else:
        cursor.execute("""
            INSERT INTO activity_lookup (category_lookup_id, activity_name, default_amount, is_income, is_active) 
            VALUES (?, ?, ?, ?, ?)
        """, (cat_id, act_name, default_amount, is_income, is_active))
        flash(f'New activity "{act_name}" created successfully!', 'success')

    conn.commit()
    conn.close()
    return redirect(url_for('activity_lookup_page'))

@app.route('/maintenance/data')
@login_required
@role_required('admin')
def maintenance_data_page():
    active_tab = request.args.get('table', 'daily')
    conn = get_db()
    
    categories, activities, daily_activities = [], [], []
    
    if active_tab == 'category':
        categories = conn.execute(
            'SELECT *, CAST(COALESCE(is_active, 1) AS INTEGER) as is_active FROM category_lookup ORDER BY category_lookup_id ASC'
        ).fetchall()
    elif active_tab == 'activity':
        activities = conn.execute('''
            SELECT al.*, CAST(COALESCE(al.is_income, 1) AS INTEGER) as is_income, 
                   CAST(COALESCE(al.is_active, 1) AS INTEGER) as is_active, cl.category_name 
            FROM activity_lookup al
            LEFT JOIN category_lookup cl ON al.category_lookup_id = cl.category_lookup_id
            ORDER BY al.activity_name ASC
        ''').fetchall()
    elif active_tab == 'daily':
        daily_activities = conn.execute('''
            SELECT da.*, CAST(COALESCE(da.session_type, 1) AS INTEGER) as session_type, 
                   CAST(COALESCE(da.is_active, 1) AS INTEGER) as is_active,
                   al.activity_name, CAST(COALESCE(al.is_income, 1) AS INTEGER) as is_income, cl.category_name
            FROM daily_activity da
            LEFT JOIN activity_lookup al ON da.activity_lookup_id = al.activity_lookup_id
            LEFT JOIN category_lookup cl ON al.category_lookup_id = cl.category_lookup_id
            ORDER BY da.updated_ts DESC, da.txn_date DESC, da.daily_activity_id DESC
        ''').fetchall()
        
    conn.close()
    return render_template('maintenance_data.html', 
                           active_tab=active_tab,
                           categories=categories,
                           activities=activities,
                           daily_activities=daily_activities)

# ---------------------------------------------------------
# APPLICATION ENTRY POINT
# ---------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)