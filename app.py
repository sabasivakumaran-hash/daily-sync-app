import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash

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

# Jinja template filter for thousands currency formatting ($131,863.54)
@app.template_filter('currency')
def currency_filter(value):
    if value is None:
        value = 0.0
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

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

    # Active activities dropdown list
    activities = conn.execute("""
        SELECT a.activity_lookup_id, a.activity_name, a.default_amount, 
               COALESCE(a.txn_type, 'INCOME') as txn_type, a.is_active, c.category_name
        FROM activity_lookup a
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE a.is_active = 1
        ORDER BY c.category_name, a.activity_name
    """).fetchall()

    # Pre-fill for edit mode
    edit_id = request.args.get('edit_id')
    editing_txn = None
    if edit_id:
        editing_txn = conn.execute("""
            SELECT t.daily_activity_id, t.txn_date, t.session_type, 
                   t.person_name, t.activity_lookup_id, t.unit_price, 
                   t.quantity, t.total_amount, t.remarks, t.is_active,
                   COALESCE(a.txn_type, 'INCOME') as txn_type
            FROM daily_activity t
            LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
            WHERE t.daily_activity_id = ?
        """, (edit_id,)).fetchone()

    # All transactions list - Ordered by updated_ts DESC, txn_date DESC
    transactions = conn.execute("""
        SELECT 
            t.daily_activity_id,
            t.txn_date,
            COALESCE(t.session_type, 'AM') as session_type,
            t.person_name,
            t.unit_price,
            t.quantity,
            t.total_amount,
            t.remarks,
            t.is_active,
            t.updated_ts,
            a.activity_name,
            COALESCE(a.txn_type, 'INCOME') as txn_type,
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
def daily_activity_save():
    daily_activity_id = request.form.get('daily_activity_id')
    txn_date = request.form.get('txn_date')
    session_type = request.form.get('session_type', 'AM')
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
        cursor.execute("""
            UPDATE daily_activity 
            SET txn_date = ?, session_type = ?, activity_lookup_id = ?, person_name = ?, 
                unit_price = ?, quantity = ?, total_amount = ?, remarks = ?, 
                is_active = ?, updated_ts = CURRENT_TIMESTAMP
            WHERE daily_activity_id = ?
        """, (txn_date, session_type, activity_lookup_id, person_name, 
              unit_price, quantity, total_amount, remarks, is_active, daily_activity_id))
        flash(f'Daily Activity entry #{daily_activity_id} updated successfully!', 'success')
    else:
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
# 3. FINANCIAL DASHBOARD
# ---------------------------------------------------------
@app.route('/dashboard')
def dashboard_page():
    conn = get_db()
    current_year_str = datetime.now().strftime('%Y')
    selected_year = request.args.get('year', current_year_str)

    years_rows = conn.execute("""
        SELECT DISTINCT strftime('%Y', txn_date) as year 
        FROM daily_activity 
        WHERE is_active = 1 AND txn_date IS NOT NULL
        ORDER BY year DESC
    """).fetchall()
    available_years = [r['year'] for r in years_rows if r['year']]
    if current_year_str not in available_years:
        available_years.insert(0, current_year_str)

    kpi = conn.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN COALESCE(a.txn_type, 'INCOME') = 'INCOME' THEN t.total_amount ELSE 0 END), 0) as total_income,
            COALESCE(SUM(CASE WHEN a.txn_type = 'EXPENSE' THEN t.total_amount ELSE 0 END), 0) as total_expense
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        WHERE t.is_active = 1 AND strftime('%Y', t.txn_date) = ?
    """, (selected_year,)).fetchone()

    total_income = float(kpi['total_income'])
    total_expense = float(kpi['total_expense'])
    net_surplus = total_income - total_expense

    monthly_rows = conn.execute("""
        SELECT 
            strftime('%m', t.txn_date) as month_num,
            COALESCE(SUM(CASE WHEN COALESCE(a.txn_type, 'INCOME') = 'INCOME' THEN t.total_amount ELSE 0 END), 0) as income,
            COALESCE(SUM(CASE WHEN a.txn_type = 'EXPENSE' THEN t.total_amount ELSE 0 END), 0) as expense
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
            idx = int(r['month_num']) - 1
            if 0 <= idx < 12:
                income_data[idx] = float(r['income'])
                expense_data[idx] = float(r['expense'])

    category_dist = conn.execute("""
        SELECT c.category_name, SUM(t.total_amount) as amount
        FROM daily_activity t
        JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE t.is_active = 1 AND COALESCE(a.txn_type, 'INCOME') = 'INCOME' AND strftime('%Y', t.txn_date) = ?
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
# 4. REPORTS PAGE
# ---------------------------------------------------------
@app.route('/reports')
def reports_page():
    conn = get_db()
    current_year_str = datetime.now().strftime('%Y')
    
    selected_report = request.args.get('report_type', 'income_expense')
    selected_year = request.args.get('fiscal_year', request.args.get('year', current_year_str))

    years_rows = conn.execute("""
        SELECT DISTINCT strftime('%Y', txn_date) as year 
        FROM daily_activity 
        WHERE is_active = 1 AND txn_date IS NOT NULL 
        ORDER BY year DESC
    """).fetchall()
    available_years = [r['year'] for r in years_rows if r['year']]
    if current_year_str not in available_years:
        available_years.insert(0, current_year_str)

    start_date = request.args.get('start_date', f"{selected_year}-01-01")
    end_date = request.args.get('end_date', f"{selected_year}-12-31")

    # Data structures
    income_categories = {}
    expense_categories = {}
    income_monthly_totals = {m: 0.0 for m in range(1, 13)}
    expense_monthly_totals = {m: 0.0 for m in range(1, 13)}
    net_monthly_surplus = {m: 0.0 for m in range(1, 13)}
    
    total_income_year = 0.0
    total_expense_year = 0.0

    matrix, category_subtotals = {}, {}
    monthly_grand_totals = {m: 0.0 for m in range(1, 13)}
    year_grand_total = 0.0

    act_matrix = {}
    act_cat_subtotals = {}
    act_grand_totals = {
        'INCOME': {m: 0.0 for m in range(1, 14)},
        'EXPENSE': {m: 0.0 for m in range(1, 14)},
        'NET': {m: 0.0 for m in range(1, 14)}
    }

    if selected_report in ['income_expense', 'fiscal_report']:
        cat_rows = conn.execute("""
            SELECT 
                c.category_name,
                COALESCE(a.txn_type, 'INCOME') as txn_type,
                CAST(strftime('%m', t.txn_date) AS INTEGER) as month_num,
                SUM(t.total_amount) as total_amount
            FROM daily_activity t
            JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
            JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
            WHERE t.is_active = 1 
              AND strftime('%Y', t.txn_date) = ?
            GROUP BY c.category_name, txn_type, month_num
            ORDER BY c.category_name ASC
        """, (selected_year,)).fetchall()

        for r in cat_rows:
            cat = r['category_name'] if r['category_name'] else 'UNASSIGNED'
            t_type = r['txn_type']
            m_num = r['month_num']
            amt = float(r['total_amount'])

            target_dict = expense_categories if t_type == 'EXPENSE' else income_categories
            
            if cat not in target_dict:
                target_dict[cat] = {m: 0.0 for m in range(1, 13)}
                target_dict[cat]['total'] = 0.0

            target_dict[cat][m_num] += amt
            target_dict[cat]['total'] += amt

            if t_type == 'EXPENSE':
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
                COALESCE(a.txn_type, 'INCOME') as txn_type,
                CAST(strftime('%m', t.txn_date) AS INTEGER) as month_num,
                SUM(t.total_amount) as total_amount
            FROM daily_activity t
            JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
            JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
            WHERE t.is_active = 1 
              AND strftime('%Y', t.txn_date) = ?
            GROUP BY c.category_name, a.activity_name, txn_type, month_num
            ORDER BY c.category_name ASC, a.activity_name ASC
        """, (selected_year,)).fetchall()

        for r in activity_rows:
            cat = r['category_name']
            act = r['activity_name']
            t_type = r['txn_type']
            m_num = r['month_num']
            amt = float(r['total_amount'])

            if cat not in act_matrix:
                act_matrix[cat] = {}
                act_cat_subtotals[cat] = {
                    'INCOME': {m: 0.0 for m in range(1, 14)},
                    'EXPENSE': {m: 0.0 for m in range(1, 14)},
                    'NET': {m: 0.0 for m in range(1, 14)}
                }

            if act not in act_matrix[cat]:
                act_matrix[cat][act] = {
                    'txn_type': t_type,
                    'months': {m: 0.0 for m in range(1, 14)}
                }

            act_matrix[cat][act]['months'][m_num] += amt
            act_matrix[cat][act]['months'][13] += amt
            
            net_amt = amt if t_type == 'INCOME' else -amt

            act_cat_subtotals[cat][t_type][m_num] += amt
            act_cat_subtotals[cat][t_type][13] += amt
            act_cat_subtotals[cat]['NET'][m_num] += net_amt
            act_cat_subtotals[cat]['NET'][13] += net_amt

            act_grand_totals[t_type][m_num] += amt
            act_grand_totals[t_type][13] += amt
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
        matrix=matrix,
        category_subtotals=category_subtotals,
        monthly_grand_totals=monthly_grand_totals,
        year_grand_total=year_grand_total,
        act_matrix=act_matrix,
        act_cat_subtotals=act_cat_subtotals,
        act_grand_totals=act_grand_totals
    )

# ---------------------------------------------------------
# 5. MAINTENANCE MODULE
# ---------------------------------------------------------
@app.route('/maintenance/category')
def category_lookup_page():
    conn = get_db()
    edit_id = request.args.get('edit_id')
    editing_cat = None
    if edit_id:
        editing_cat = conn.execute("SELECT * FROM category_lookup WHERE category_lookup_id = ?", (edit_id,)).fetchone()
        
    categories = conn.execute("SELECT * FROM category_lookup ORDER BY category_name ASC").fetchall()
    conn.close()
    return render_template('category_lookup.html', categories=categories, editing_cat=editing_cat)

@app.route('/maintenance/category/save', methods=['POST'])
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
def activity_lookup_page():
    conn = get_db()
    edit_id = request.args.get('edit_id')
    editing_act = None
    if edit_id:
        editing_act = conn.execute("SELECT * FROM activity_lookup WHERE activity_lookup_id = ?", (edit_id,)).fetchone()

    activities = conn.execute("""
        SELECT a.*, c.category_name 
        FROM activity_lookup a 
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id 
        ORDER BY c.category_name, a.activity_name
    """).fetchall()
    categories = conn.execute("SELECT * FROM category_lookup WHERE is_active = 1 ORDER BY category_name ASC").fetchall()
    conn.close()
    return render_template('activity_lookup.html', activities=activities, categories=categories, editing_act=editing_act)

@app.route('/maintenance/activity/save', methods=['POST'])
def activity_lookup_save():
    act_id = request.form.get('activity_lookup_id')
    cat_id = request.form.get('category_lookup_id')
    act_name = request.form.get('activity_name', '').strip()
    default_amount = float(request.form.get('default_amount', 0.0))
    txn_type = request.form.get('txn_type', 'INCOME')
    is_active = int(request.form.get('is_active', 1))

    conn = get_db()
    cursor = conn.cursor()

    if act_id:
        cursor.execute("""
            UPDATE activity_lookup 
            SET category_lookup_id = ?, activity_name = ?, default_amount = ?, txn_type = ?, is_active = ? 
            WHERE activity_lookup_id = ?
        """, (cat_id, act_name, default_amount, txn_type, is_active, act_id))
        flash(f'Activity "{act_name}" updated successfully!', 'success')
    else:
        cursor.execute("""
            INSERT INTO activity_lookup (category_lookup_id, activity_name, default_amount, txn_type, is_active) 
            VALUES (?, ?, ?, ?, ?)
        """, (cat_id, act_name, default_amount, txn_type, is_active))
        flash(f'New activity "{act_name}" created successfully!', 'success')

    conn.commit()
    conn.close()
    return redirect(url_for('activity_lookup_page'))

@app.route('/maintenance/data')
def maintenance_data_page():
    active_tab = request.args.get('table', 'daily')
    conn = get_db()
    
    categories, activities, daily_activities = [], [], []
    
    if active_tab == 'category':
        categories = conn.execute('SELECT * FROM category_lookup ORDER BY category_lookup_id ASC').fetchall()
    elif active_tab == 'activity':
        activities = conn.execute('''
            SELECT al.*, cl.category_name 
            FROM activity_lookup al
            LEFT JOIN category_lookup cl ON al.category_lookup_id = cl.category_lookup_id
            ORDER BY al.activity_lookup_id ASC
        ''').fetchall()
    elif active_tab == 'daily':
        daily_activities = conn.execute('''
            SELECT da.*, al.activity_name, COALESCE(al.txn_type, 'INCOME') as txn_type, cl.category_name
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