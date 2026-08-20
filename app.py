import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, 
    login_required, current_user
)
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = 'temple_sync_secret_key_change_in_production'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'daily_sync.db')

# ---------------------------------------------------------
# DATABASE CONNECTION FACTORY
# ---------------------------------------------------------
def get_db():
    """Direct database connection factory with Row factory enabled."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# ---------------------------------------------------------
# FLASK-LOGIN & USER MODEL SETUP (PHASE 2 AUTHENTICATION)
# ---------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = None  # Silences default Flask-Login message to prevent duplicates

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
# RBAC DECORATOR
# ---------------------------------------------------------
def role_required(role_name):
    """Decorator to enforce specific role permissions on routes."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role_name:
                flash('Unauthorized access privileges required.', 'danger')
                return redirect(url_for('daily_activity_page'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ---------------------------------------------------------
# DATE PARSER HELPER
# ---------------------------------------------------------
def parse_date_components(date_str):
    """Normalizes any incoming date string (MM/DD/YYYY, M/D/YYYY, YYYY-MM-DD) into YYYY-MM-DD."""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    try:
        if '/' in date_str:
            parts = date_str.split('/')
            if len(parts) == 3:
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{y:04d}-{m:02d}-{d:02d}"
        elif '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, IndexError):
        pass
    return None

# ---------------------------------------------------------
# CENTRALIZED JINJA TEMPLATE FILTERS
# ---------------------------------------------------------
@app.template_filter('currency')
def currency_filter(value):
    if value is None:
        value = 0.0
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

@app.template_filter('ui_date')
def ui_date_filter(value):
    """Converts DB date (YYYY-MM-DD) to UI display date (MM/DD/YYYY)."""
    if not value:
        return ""
    try:
        if '-' in str(value):
            parts = str(value).split('-')
            if len(parts) == 3:
                return f"{int(parts[1]):02d}/{int(parts[2]):02d}/{parts[0]}"
    except (ValueError, IndexError):
        pass
    return str(value)

@app.template_filter('badge_session')
def badge_session_filter(value):
    """Renders Session Badge (1 = AM, 0 = PM)."""
    try:
        val = int(value) if value is not None else 1
    except (ValueError, TypeError):
        val = 1
    if val == 1:
        return '<span class="badge bg-light text-dark border">AM</span>'
    return '<span class="badge bg-light text-dark border">PM</span>'

@app.template_filter('badge_type')
def badge_type_filter(value):
    """Renders Transaction Type Badge (1 = INCOME, 0 = EXPENSE)."""
    try:
        val = int(value) if value is not None else 1
    except (ValueError, TypeError):
        val = 1
    if val == 0:
        return '<span class="badge bg-danger-subtle text-danger border border-danger-subtle fw-semibold">EXPENSE</span>'
    return '<span class="badge bg-success-subtle text-success border border-success-subtle fw-semibold">INCOME</span>'

@app.template_filter('badge_status')
def badge_status_filter(value):
    """Renders Record Status Badge (1 = Active, 0 = Inactive)."""
    try:
        val = int(value) if value is not None else 1
    except (ValueError, TypeError):
        val = 1
    if val == 1:
        return '<span class="badge bg-success-subtle text-success border border-success-subtle">Active</span>'
    return '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle">Inactive</span>'

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
# 2. DAILY ACTIVITY MODULE (ACCESSIBLE BY ALL LOGGED-IN USERS)
# ---------------------------------------------------------
@app.route('/daily_activity', methods=['GET'])
@login_required
def daily_activity_page():
    conn = get_db()
    
    # Person names for autocompletion
    name_rows = conn.execute("""
        SELECT DISTINCT person_name 
        FROM daily_activity 
        WHERE person_name IS NOT NULL AND person_name != '' 
        ORDER BY person_name ASC
    """).fetchall()
    existing_names = [r['person_name'] for r in name_rows]

    # Active activities dropdown list (Sorted strictly by activity_name ASC)
    activities = conn.execute("""
        SELECT a.activity_lookup_id, a.activity_name, a.default_amount, 
               CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income, 
               a.is_active, c.category_name
        FROM activity_lookup a
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE a.is_active = 1
        ORDER BY a.activity_name ASC
    """).fetchall()

    # Pre-fill for edit mode
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

    # All transactions list
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
    session_type = int(request.form.get('session_type', 1))  # Default: 1 = AM
    activity_lookup_id = request.form.get('activity_lookup_id')
    person_name = request.form.get('person_name', '').strip()
    unit_price = float(request.form.get('unit_price', 0.0))
    quantity = int(request.form.get('quantity', 1))
    total_amount = float(request.form.get('total_amount', 0.0))
    remarks = request.form.get('remarks', '').strip()
    is_active = int(request.form.get('is_active', 1))  # Default: 1 = Active

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
# 4. REPORTS PAGE (ADMIN ONLY)
# ---------------------------------------------------------
@app.route('/reports')
@login_required
@role_required('admin')
def reports_page():
    conn = get_db()
    current_year_str = datetime.now().strftime('%Y')
    
    selected_report = request.args.get('report_type', 'income_expense')

    years_rows = conn.execute("""
        SELECT DISTINCT strftime('%Y', txn_date) as year 
        FROM daily_activity 
        WHERE is_active = 1 AND txn_date IS NOT NULL AND txn_date != ''
        ORDER BY year DESC
    """).fetchall()

    available_years = [r['year'] for r in years_rows if r['year']]
    
    selected_year = request.args.get('fiscal_year', request.args.get('year'))
    if not selected_year:
        selected_year = available_years[0] if available_years else current_year_str

    if current_year_str not in available_years:
        available_years.insert(0, current_year_str)

    start_date_raw = request.args.get('start_date')
    end_date_raw = request.args.get('end_date')

    start_date = parse_date_components(start_date_raw) or f"{selected_year}-01-01"
    end_date = parse_date_components(end_date_raw) or f"{selected_year}-12-31"

    income_categories, expense_categories = {}, {}
    income_monthly_totals = {m: 0.0 for m in range(1, 13)}
    expense_monthly_totals = {m: 0.0 for m in range(1, 13)}
    net_monthly_surplus = {m: 0.0 for m in range(1, 13)}
    
    total_income_year = 0.0
    total_expense_year = 0.0

    act_matrix, act_cat_subtotals = {}, {}
    act_grand_totals = {
        'INCOME': {m: 0.0 for m in range(1, 14)},
        'EXPENSE': {m: 0.0 for m in range(1, 14)},
        'NET': {m: 0.0 for m in range(1, 14)}
    }

    if selected_report in ['income_expense', 'fiscal_report']:
        cat_rows = conn.execute("""
            SELECT 
                c.category_name,
                CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income,
                CAST(strftime('%m', t.txn_date) AS INTEGER) as month_num,
                SUM(t.total_amount) as total_amount
            FROM daily_activity t
            JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
            JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
            WHERE t.is_active = 1 AND t.txn_date BETWEEN ? AND ?
            GROUP BY c.category_name, is_income, month_num
            ORDER BY c.category_name ASC
        """, (start_date, end_date)).fetchall()

        for r in cat_rows:
            cat = r['category_name'] if r['category_name'] else 'UNASSIGNED'
            is_inc = int(r['is_income'])
            m_num = r['month_num']
            amt = float(r['total_amount']) if r['total_amount'] else 0.0

            if not m_num or not (1 <= m_num <= 12):
                continue

            target_dict = expense_categories if is_inc == 0 else income_categories
            
            if cat not in target_dict:
                target_dict[cat] = {m: 0.0 for m in range(1, 13)}
                target_dict[cat]['total'] = 0.0

            target_dict[cat][m_num] += amt
            target_dict[cat]['total'] += amt

            if is_inc == 0:
                expense_monthly_totals[m_num] += amt
                total_expense_year += amt
            else:
                income_monthly_totals[m_num] += amt
                total_income_year += amt

        for m in range(1, 13):
            net_monthly_surplus[m] = income_monthly_totals[m] - expense_monthly_totals[m]

    if selected_report == 'activity_summary':
        activity_rows = conn.execute("""
            SELECT 
                c.category_name,
                a.activity_name,
                CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income,
                CAST(strftime('%m', t.txn_date) AS INTEGER) as month_num,
                SUM(t.total_amount) as total_amount
            FROM daily_activity t
            JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
            JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
            WHERE t.is_active = 1 AND t.txn_date BETWEEN ? AND ?
            GROUP BY c.category_name, a.activity_name, is_income, month_num
            ORDER BY c.category_name ASC, a.activity_name ASC
        """, (start_date, end_date)).fetchall()

        for r in activity_rows:
            cat = r['category_name'] if r['category_name'] else 'UNASSIGNED'
            act = r['activity_name']
            is_inc = int(r['is_income'])
            m_num = r['month_num']
            amt = float(r['total_amount']) if r['total_amount'] else 0.0

            if not m_num or not (1 <= m_num <= 12):
                continue

            if cat not in act_matrix:
                act_matrix[cat] = {}
                act_cat_subtotals[cat] = {
                    'INCOME': {m: 0.0 for m in range(1, 14)},
                    'EXPENSE': {m: 0.0 for m in range(1, 14)},
                    'NET': {m: 0.0 for m in range(1, 14)}
                }

            if act not in act_matrix[cat]:
                act_matrix[cat][act] = {
                    'is_income': is_inc,
                    'months': {m: 0.0 for m in range(1, 14)}
                }

            act_matrix[cat][act]['months'][m_num] += amt
            act_matrix[cat][act]['months'][13] += amt
            
            t_type_key = 'INCOME' if is_inc == 1 else 'EXPENSE'
            net_amt = amt if is_inc == 1 else -amt

            act_cat_subtotals[cat][t_type_key][m_num] += amt
            act_cat_subtotals[cat][t_type_key][13] += amt
            act_cat_subtotals[cat]['NET'][m_num] += net_amt
            act_cat_subtotals[cat]['NET'][13] += net_amt

            act_grand_totals[t_type_key][m_num] += amt
            act_grand_totals[t_type_key][13] += amt
            act_grand_totals['NET'][m_num] += net_amt
            act_grand_totals['NET'][13] += net_amt

    conn.close()

    return render_template(
        'reports.html',
        selected_report=selected_report,
        selected_year=selected_year,
        available_years=available_years,
        start_date=start_date,
        end_date=end_date,
        income_categories=income_categories,
        expense_categories=expense_categories,
        income_monthly_totals=income_monthly_totals,
        expense_monthly_totals=expense_monthly_totals,
        net_monthly_surplus=net_monthly_surplus,
        total_income_year=total_income_year,
        total_expense_year=total_expense_year,
        net_surplus_year=(total_income_year - total_expense_year),
        act_matrix=act_matrix,
        act_cat_subtotals=act_cat_subtotals,
        act_grand_totals=act_grand_totals
    )

# ---------------------------------------------------------
# 5. MAINTENANCE MODULE (ADMIN ONLY)
# ---------------------------------------------------------
@app.route('/maintenance/category')
@login_required
@role_required('admin')
def category_lookup_page():
    conn = get_db()
    edit_id = request.args.get('edit_id')
    editing_cat = None
    if edit_id:
        editing_cat = conn.execute("SELECT *, CAST(COALESCE(is_active, 1) AS INTEGER) as is_active FROM category_lookup WHERE category_lookup_id = ?", (edit_id,)).fetchone()
        
    categories = conn.execute("SELECT *, CAST(COALESCE(is_active, 1) AS INTEGER) as is_active FROM category_lookup ORDER BY category_name ASC").fetchall()
    conn.close()
    return render_template('category_lookup.html', categories=categories, editing_cat=editing_cat)

@app.route('/maintenance/category/save', methods=['POST'])
@login_required
@role_required('admin')
def category_lookup_save():
    cat_id = request.form.get('category_lookup_id')
    cat_name = request.form.get('category_name', '').strip()
    is_active = int(request.form.get('is_active', 1))

    conn = get_db()
    cursor = conn.cursor()
    if cat_id:
        cursor.execute("UPDATE category_lookup SET category_name = ?, is_active = ? WHERE category_lookup_id = ?",
                       (cat_name, is_active, cat_id))
        flash(f'Category "{cat_name}" updated successfully!', 'success')
    else:
        cursor.execute("INSERT INTO category_lookup (category_name, is_active) VALUES (?, ?)", (cat_name, is_active))
        flash(f'New category "{cat_name}" created successfully!', 'success')
        
    conn.commit()
    conn.close()
    return redirect(url_for('category_lookup_page'))

@app.route('/maintenance/activity')
@login_required
@role_required('admin')
def activity_lookup_page():
    conn = get_db()
    edit_id = request.args.get('edit_id')
    editing_act = None
    if edit_id:
        editing_act = conn.execute("""
            SELECT *, CAST(COALESCE(is_income, 1) AS INTEGER) as is_income, 
                      CAST(COALESCE(is_active, 1) AS INTEGER) as is_active 
            FROM activity_lookup 
            WHERE activity_lookup_id = ?
        """, (edit_id,)).fetchone()

    activities = conn.execute("""
        SELECT a.*, CAST(COALESCE(a.is_income, 1) AS INTEGER) as is_income, 
               CAST(COALESCE(a.is_active, 1) AS INTEGER) as is_active, c.category_name 
        FROM activity_lookup a 
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id 
        ORDER BY a.activity_name ASC
    """).fetchall()
    categories = conn.execute("SELECT * FROM category_lookup WHERE is_active = 1 ORDER BY category_name ASC").fetchall()
    conn.close()
    return render_template('activity_lookup.html', activities=activities, categories=categories, editing_act=editing_act)

@app.route('/maintenance/activity/save', methods=['POST'])
@login_required
@role_required('admin')
def activity_lookup_save():
    act_id = request.form.get('activity_lookup_id')
    cat_id = request.form.get('category_lookup_id')
    act_name = request.form.get('activity_name', '').strip()
    default_amount = float(request.form.get('default_amount', 0.0))
    is_income = int(request.form.get('is_income', 1))
    is_active = int(request.form.get('is_active', 1))

    conn = get_db()
    cursor = conn.cursor()

    if act_id:
        cursor.execute("""
            UPDATE activity_lookup 
            SET category_lookup_id = ?, activity_name = ?, default_amount = ?, is_income = ?, is_active = ? 
            WHERE activity_lookup_id = ?
        """, (cat_id, act_name, default_amount, is_income, act_id))
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
        categories = conn.execute('SELECT *, CAST(COALESCE(is_active, 1) AS INTEGER) as is_active FROM category_lookup ORDER BY category_lookup_id ASC').fetchall()
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)