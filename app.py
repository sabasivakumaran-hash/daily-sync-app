import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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

# Register Modular Blueprints
from dynamic import dynamic_bp
from admin import admin_bp

app.register_blueprint(dynamic_bp)
app.register_blueprint(admin_bp)

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
# DATABASE CONNECTION FACTORY & AUTO-MIGRATION
# ---------------------------------------------------------
def get_db():
    """Direct database connection factory with Row factory enabled."""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    if app.config.get('SQLITE_FOREIGN_KEYS'):
        conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db_schema():
    """Ensure schema updates for is_cleared, app_config baseline, and assets exist."""
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Add is_cleared column if missing
    try:
        cursor.execute("ALTER TABLE daily_activity ADD COLUMN is_cleared INTEGER DEFAULT 0;")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # 2. Add app_config table for opening balance baseline
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            config_key TEXT PRIMARY KEY,
            config_value TEXT
        );
    """)
    
    # Set default Opening Balance baseline ($0.00) if not present
    cursor.execute("""
        INSERT OR IGNORE INTO app_config (config_key, config_value) 
        VALUES ('opening_balance', '0.00');
    """)

    # 3. Add assets_lookup table for CDs & Real Estate Property
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets_lookup (
            asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_name TEXT NOT NULL,
            asset_category TEXT NOT NULL,
            account_number TEXT,
            start_date TEXT,
            maturity_date TEXT,
            interest_rate REAL DEFAULT 0.0,
            asset_value REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1,
            notes TEXT,
            updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()

# Initialize schema structure at app launch
with app.app_context():
    init_db_schema()

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
# 2. DAILY ACTIVITY MODULE (VOLUNTEER ENTRY VIEW)
# ---------------------------------------------------------
@app.route('/daily_activity', methods=['GET'])
@login_required
def daily_activity_page():
    conn = get_db()
    
    # 1. Fetch Existing Person Names for Autocomplete
    name_rows = conn.execute("""
        SELECT DISTINCT person_name 
        FROM daily_activity 
        WHERE person_name IS NOT NULL AND person_name != '' 
        ORDER BY person_name ASC
    """).fetchall()
    existing_names = [r['person_name'] for r in name_rows]

    # 2. Fetch Active Activities
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

    # 3. Check for Edit ID
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

    # 4. Fetch Transactions for Daily Activity Table
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
        # EDIT EXISTING ENTRY: Retain existing is_cleared status
        existing = cursor.execute(
            "SELECT txn_date, is_cleared FROM daily_activity WHERE daily_activity_id = ?", 
            (daily_activity_id,)
        ).fetchone()

        parsed_new_date = parse_date_components(raw_date)
        txn_date = parsed_new_date if parsed_new_date else (existing['txn_date'] if existing else datetime.now().strftime('%Y-%m-%d'))
        
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
        # NEW ENTRY: Always default is_cleared to 0 (Pending deposit/check)
        txn_date = parse_date_components(raw_date) or datetime.now().strftime('%Y-%m-%d')
        is_cleared = 0  

        cursor.execute("""
            INSERT INTO daily_activity 
            (txn_date, session_type, activity_lookup_id, person_name, unit_price, quantity, total_amount, remarks, is_active, is_cleared, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (txn_date, session_type, activity_lookup_id, person_name, unit_price, quantity, total_amount, remarks, is_active, is_cleared))
        flash('New Daily Activity recorded successfully!', 'success')

    conn.commit()
    conn.close()
    return redirect(url_for('daily_activity_page'))

# ---------------------------------------------------------
# AJAX ROUTE: TOGGLE CLEARED STATUS INLINE (ADMIN/RECONCILIATION)
# ---------------------------------------------------------
@app.route('/daily_activity/toggle_cleared', methods=['POST'])
@login_required
@role_required('admin')
def toggle_cleared():
    data = request.get_json() or {}
    daily_activity_id = data.get('daily_activity_id')
    is_cleared = 1 if data.get('is_cleared') else 0

    if not daily_activity_id:
        return jsonify({'success': False, 'message': 'Invalid transaction ID'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE daily_activity 
        SET is_cleared = ?, updated_ts = CURRENT_TIMESTAMP 
        WHERE daily_activity_id = ?
    """, (is_cleared, daily_activity_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'daily_activity_id': daily_activity_id, 'is_cleared': is_cleared})

# ---------------------------------------------------------
# 3. FINANCIAL DASHBOARD & NET WORTH SUMMARY (ADMIN ONLY)
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

    # 1. Income & Expense KPIs for Selected Year
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

    # 2. Monthly Trend Data
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

    # 3. Category Distribution
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

    # 4. TEMPLE NET WORTH SUMMARY COMPUTATION
    config_row = conn.execute(
        "SELECT config_value FROM app_config WHERE config_key = 'opening_balance'"
    ).fetchone()
    opening_balance = float(config_row['config_value']) if config_row and config_row['config_value'] else 0.0

    all_time_net = conn.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN t.is_active = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 THEN t.total_amount ELSE 0 END), 0) -
            COALESCE(SUM(CASE WHEN t.is_active = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 0 THEN t.total_amount ELSE 0 END), 0) as book_net
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
    """).fetchone()

    operating_cash = opening_balance + float(all_time_net['book_net'] or 0.0)

    asset_totals = conn.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN asset_category = 'Term Deposit' THEN asset_value ELSE 0 END), 0) as total_cds,
            COALESCE(SUM(CASE WHEN asset_category = 'Real Estate' THEN asset_value ELSE 0 END), 0) as total_real_estate,
            COALESCE(SUM(CASE WHEN asset_category NOT IN ('Term Deposit', 'Real Estate') THEN asset_value ELSE 0 END), 0) as total_other_assets
        FROM assets_lookup
        WHERE is_active = 1 AND asset_value > 0
    """).fetchone()

    total_cds = float(asset_totals['total_cds'] or 0.0)
    total_real_estate = float(asset_totals['total_real_estate'] or 0.0)
    total_other_assets = float(asset_totals['total_other_assets'] or 0.0)
    
    total_net_worth = operating_cash + total_cds + total_real_estate + total_other_assets

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
        cat_values=cat_values,
        operating_cash=operating_cash,
        total_cds=total_cds,
        total_real_estate=total_real_estate,
        total_other_assets=total_other_assets,
        total_net_worth=total_net_worth
    )

# ---------------------------------------------------------
# BANK & CASH REGISTER (ADMIN ONLY)
# ---------------------------------------------------------
@app.route('/bank_ledger')
@login_required
@role_required('admin')
def bank_ledger_page():
    conn = get_db()
    
    # 1. Capture & Parse Date Range Parameters
    raw_start = request.args.get('start_date', '')
    raw_end = request.args.get('end_date', '')
    start_date = parse_date_components(raw_start) if raw_start else ''
    end_date = parse_date_components(raw_end) if raw_end else ''

    # 2. Fetch Opening Balance Baseline
    config_row = conn.execute(
        "SELECT config_value FROM app_config WHERE config_key = 'opening_balance'"
    ).fetchone()
    opening_balance = float(config_row['config_value']) if config_row and config_row['config_value'] else 0.0

    # 3. Compute All-Time Cumulative KPI Balances
    kpi_balances = conn.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN t.is_active = 1 AND t.is_cleared = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 THEN t.total_amount ELSE 0 END), 0) -
            COALESCE(SUM(CASE WHEN t.is_active = 1 AND t.is_cleared = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 0 THEN t.total_amount ELSE 0 END), 0) as cleared_net,

            COALESCE(SUM(CASE WHEN t.is_active = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 THEN t.total_amount ELSE 0 END), 0) -
            COALESCE(SUM(CASE WHEN t.is_active = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 0 THEN t.total_amount ELSE 0 END), 0) as book_net,

            COALESCE(SUM(CASE WHEN t.is_active = 1 AND t.is_cleared = 0 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 THEN t.total_amount ELSE 0 END), 0) as pending_deposits
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
    """).fetchone()

    bank_balance = opening_balance + float(kpi_balances['cleared_net'] or 0.0)
    book_balance = opening_balance + float(kpi_balances['book_net'] or 0.0)
    pending_deposits = float(kpi_balances['pending_deposits'] or 0.0)

    # 4. Fetch Transactions with Running Balance & Dynamic Date Filtering
    query = """
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
            CAST(COALESCE(t.is_cleared, 0) AS INTEGER) as is_cleared,
            a.activity_name,
            CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income,
            c.category_name,
            (? + SUM(
                CASE 
                    WHEN t.is_active = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 1 THEN t.total_amount 
                    WHEN t.is_active = 1 AND CAST(COALESCE(a.is_income, 1) AS INTEGER) = 0 THEN -t.total_amount 
                    ELSE 0 
                END
            ) OVER (
                ORDER BY t.txn_date ASC, t.daily_activity_id ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )) as running_balance
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE 1=1
    """
    params = [opening_balance]

    if start_date:
        query += " AND t.txn_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND t.txn_date <= ?"
        params.append(end_date)

    query += " ORDER BY t.txn_date DESC, t.daily_activity_id DESC"

    transactions = conn.execute(query, params).fetchall()

    # 5. Calculate Period-Specific Metrics if Filter is Active
    period_income = 0.0
    period_expense = 0.0
    for txn in transactions:
        if txn['is_active'] == 1:
            if txn['is_income'] == 1:
                period_income += float(txn['total_amount'] or 0.0)
            else:
                period_expense += float(txn['total_amount'] or 0.0)

    period_net = period_income - period_expense

    conn.close()

    return render_template(
        'bank_ledger.html',
        transactions=transactions,
        opening_balance=opening_balance,
        bank_balance=bank_balance,
        book_balance=book_balance,
        pending_deposits=pending_deposits,
        period_income=period_income,
        period_expense=period_expense,
        period_net=period_net,
        start_date=raw_start,
        end_date=raw_end
    )

@app.route('/opening_balance/save', methods=['POST'])
@login_required
@role_required('admin')
def save_opening_balance():
    new_bal = float(request.form.get('opening_balance', 0.0))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO app_config (config_key, config_value)
        VALUES ('opening_balance', ?)
    """, (str(new_bal),))
    conn.commit()
    conn.close()
    flash('Opening Bank Balance updated successfully!', 'success')
    return redirect(url_for('bank_ledger_page'))

# ---------------------------------------------------------
# ASSET MANAGEMENT MODULE (ADMIN ONLY)
# ---------------------------------------------------------
@app.route('/assets')
@login_required
@role_required('admin')
def assets_page():
    conn = get_db()
    assets = conn.execute("""
        SELECT asset_id, asset_name, asset_category, account_number,
               start_date, maturity_date, interest_rate, asset_value,
               CAST(COALESCE(is_active, 1) AS INTEGER) as is_active, notes
        FROM assets_lookup
        WHERE is_active = 1 AND asset_value > 0
        ORDER BY asset_category ASC, asset_name ASC
    """).fetchall()
    
    editing_asset = None
    edit_id = request.args.get('edit_id')
    if edit_id:
        editing_asset = conn.execute(
            "SELECT * FROM assets_lookup WHERE asset_id = ?", (edit_id,)
        ).fetchone()
        
    conn.close()
    return render_template('assets.html', assets=assets, editing_asset=editing_asset)

@app.route('/assets/save', methods=['POST'])
@login_required
@role_required('admin')
def assets_save():
    asset_id = request.form.get('asset_id')
    asset_name = request.form.get('asset_name', '').strip()
    asset_category = request.form.get('asset_category', 'Term Deposit')
    account_number = request.form.get('account_number', '').strip()
    raw_start = request.form.get('start_date', '')
    raw_maturity = request.form.get('maturity_date', '')
    interest_rate = float(request.form.get('interest_rate', 0.0))
    asset_value = float(request.form.get('asset_value', 0.0))
    notes = request.form.get('notes', '').strip()
    is_active = int(request.form.get('is_active', 1))

    start_date = parse_date_components(raw_start) if raw_start else None
    maturity_date = parse_date_components(raw_maturity) if raw_maturity else None

    conn = get_db()
    cursor = conn.cursor()

    if asset_id:
        cursor.execute("""
            UPDATE assets_lookup
            SET asset_name = ?, asset_category = ?, account_number = ?,
                start_date = ?, maturity_date = ?, interest_rate = ?,
                asset_value = ?, notes = ?, is_active = ?, updated_ts = CURRENT_TIMESTAMP
            WHERE asset_id = ?
        """, (asset_name, asset_category, account_number, start_date, maturity_date,
              interest_rate, asset_value, notes, is_active, asset_id))
        flash(f'Asset "{asset_name}" updated successfully!', 'success')
    else:
        cursor.execute("""
            INSERT INTO assets_lookup 
            (asset_name, asset_category, account_number, start_date, maturity_date, interest_rate, asset_value, notes, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (asset_name, asset_category, account_number, start_date, maturity_date, interest_rate, asset_value, notes, is_active))
        flash(f'New asset "{asset_name}" created successfully!', 'success')

    conn.commit()
    conn.close()
    return redirect(url_for('assets_page'))

# ---------------------------------------------------------
# 4. MAINTENANCE MODULE (LOOKUPS & DATA INSPECTOR)
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
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT d.daily_activity_id, d.txn_date, d.session_type, d.person_name,
               a.activity_name, c.category_name, a.is_income,
               d.unit_price, d.quantity, d.total_amount, d.remarks, d.is_active,
               d.is_cleared
        FROM daily_activity d
        LEFT JOIN activity_lookup a ON d.activity_lookup_id = a.activity_lookup_id
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        ORDER BY d.txn_date DESC, d.daily_activity_id DESC
    """
    cursor.execute(query)
    data_rows = cursor.fetchall()
    conn.close()

    return render_template('maintenance_data.html', data_rows=data_rows)

# ---------------------------------------------------------
# APPLICATION ENTRY POINT
# ---------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)