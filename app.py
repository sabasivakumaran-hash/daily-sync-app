import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'daily_sync.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------
# 1. HOME / INDEX
# ---------------------------------------------------------
@app.route('/')
def index():
    return redirect(url_for('daily_activity_page'))

# ---------------------------------------------------------
# 2. DAILY ACTIVITY LIST & SAVE
# ---------------------------------------------------------
@app.route('/daily_activity', methods=['GET'])
def daily_activity_page():
    conn = get_db()
    
    name_rows = conn.execute("""
        SELECT DISTINCT name 
        FROM daily_activity 
        WHERE name IS NOT NULL AND name != '' 
        ORDER BY name ASC
    """).fetchall()
    existing_names = [r['name'] for r in name_rows]

    activities = conn.execute("""
        SELECT a.activity_lookup_id, a.activity_name, c.category_name
        FROM activity_lookup a
        JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE a.is_active = 1
        ORDER BY c.category_name, a.activity_name
    """).fetchall()

    transactions = conn.execute("""
        SELECT 
            t.daily_activity_id,
            t.txn_date,
            t.name,
            t.unit_price,
            t.quantity,
            t.entry_type,
            t.total_amount,
            t.remarks,
            a.activity_name,
            c.category_name
        FROM daily_activity t
        JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE t.is_active = 1
        ORDER BY t.txn_date DESC, t.daily_activity_id DESC
    """).fetchall()

    conn.close()
    return render_template(
        'daily_activity.html',
        transactions=transactions,
        activities=activities,
        existing_names=existing_names
    )

@app.route('/daily_activity/save', methods=['POST'])
def daily_activity_save():
    daily_activity_id = request.form.get('daily_activity_id')
    txn_date = request.form.get('txn_date')
    activity_lookup_id = request.form.get('activity_lookup_id')
    person_name = request.form.get('person_name') or request.form.get('name')
    unit_price = float(request.form.get('unit_price', 0.0))
    quantity = int(request.form.get('quantity', 1))
    entry_type = request.form.get('entry_type', 'INCOME')
    total_amount = float(request.form.get('total_amount', 0.0))
    remarks = request.form.get('remarks')
    is_active = 1

    conn = get_db()
    cursor = conn.cursor()

    if daily_activity_id:
        cursor.execute("""
            UPDATE daily_activity 
            SET txn_date = ?, activity_lookup_id = ?, name = ?, 
                unit_price = ?, quantity = ?, entry_type = ?, total_amount = ?, remarks = ?, 
                is_active = ?, updated_ts = CURRENT_TIMESTAMP
            WHERE daily_activity_id = ?
        """, (txn_date, activity_lookup_id, person_name, unit_price, quantity, 
              entry_type, total_amount, remarks, is_active, daily_activity_id))
    else:
        cursor.execute("""
            INSERT INTO daily_activity 
            (txn_date, activity_lookup_id, name, unit_price, quantity, entry_type, total_amount, remarks, is_active, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        """, (txn_date, activity_lookup_id, person_name, unit_price, quantity, entry_type, total_amount, remarks))

    conn.commit()
    conn.close()
    return redirect(url_for('daily_activity_page'))

# ---------------------------------------------------------
# 3. FINANCIAL DASHBOARD
# ---------------------------------------------------------
@app.route('/dashboard')
def dashboard_page():
    conn = get_db()
    selected_year = request.args.get('year', datetime.now().strftime('%Y'))

    years_rows = conn.execute("""
        SELECT DISTINCT strftime('%Y', txn_date) as year 
        FROM daily_activity 
        WHERE is_active = 1 AND txn_date IS NOT NULL
        ORDER BY year DESC
    """).fetchall()
    available_years = [r['year'] for r in years_rows if r['year']]
    if not available_years:
        available_years = [datetime.now().strftime('%Y')]

    kpi = conn.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN entry_type = 'INCOME' THEN total_amount ELSE 0 END), 0) as total_income,
            COALESCE(SUM(CASE WHEN entry_type = 'EXPENSE' THEN total_amount ELSE 0 END), 0) as total_expense
        FROM daily_activity
        WHERE is_active = 1 AND strftime('%Y', txn_date) = ?
    """, (selected_year,)).fetchone()

    total_income = kpi['total_income']
    total_expense = kpi['total_expense']
    net_surplus = total_income - total_expense

    monthly_rows = conn.execute("""
        SELECT 
            strftime('%m', txn_date) as month_num,
            COALESCE(SUM(CASE WHEN entry_type = 'INCOME' THEN total_amount ELSE 0 END), 0) as income,
            COALESCE(SUM(CASE WHEN entry_type = 'EXPENSE' THEN total_amount ELSE 0 END), 0) as expense
        FROM daily_activity
        WHERE is_active = 1 AND strftime('%Y', txn_date) = ?
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
        WHERE t.is_active = 1 AND t.entry_type = 'INCOME' AND strftime('%Y', t.txn_date) = ?
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
# 4. REPORTS PAGE (CRA COMPLIANT 12-MONTH FISCAL PERIODS)
# ---------------------------------------------------------
@app.route('/reports')
def reports_page():
    conn = get_db()
    
    selected_report = request.args.get('report_type', 'income_expense')
    selected_fy = request.args.get('fiscal_year', str(datetime.now().year))

    # Fetch available fiscal years
    fy_rows = conn.execute("""
        SELECT DISTINCT strftime('%Y', txn_date) as year 
        FROM daily_activity 
        WHERE is_active = 1 AND txn_date IS NOT NULL 
        ORDER BY year DESC
    """).fetchall()
    available_fys = [r['year'] for r in fy_rows if r['year']]
    if not available_fys:
        available_fys = [str(datetime.now().year)]

    income_matrix = {}
    expense_matrix = {}
    income_totals = {m: 0.0 for m in range(1, 13)}
    expense_totals = {m: 0.0 for m in range(1, 13)}

    # Determine Date Range
    if selected_report == 'fiscal_report':
        start_date = f"{selected_fy}-01-01"
        end_date = f"{selected_fy}-12-31"
    else:
        start_date = request.args.get('start_date', f"{datetime.now().year}-01-01")
        end_date = request.args.get('end_date', f"{datetime.now().year}-12-31")

    # Fetch 12-Month Matrix
    matrix_rows = conn.execute("""
        SELECT 
            c.category_name,
            t.entry_type,
            CAST(strftime('%m', t.txn_date) AS INTEGER) as month_num,
            SUM(t.total_amount) as total_amount
        FROM daily_activity t
        JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE t.is_active = 1 
          AND date(t.txn_date) >= date(?) 
          AND date(t.txn_date) <= date(?)
        GROUP BY c.category_name, t.entry_type, month_num
        ORDER BY c.category_name ASC
    """, (start_date, end_date)).fetchall()

    for r in matrix_rows:
        cat = r['category_name']
        etype = r['entry_type']
        m_num = r['month_num']
        amt = float(r['total_amount'])

        if etype == 'INCOME':
            if cat not in income_matrix:
                income_matrix[cat] = {m: 0.0 for m in range(1, 13)}
            income_matrix[cat][m_num] += amt
            income_totals[m_num] += amt
        else:
            if cat not in expense_matrix:
                expense_matrix[cat] = {m: 0.0 for m in range(1, 13)}
            expense_matrix[cat][m_num] += amt
            expense_totals[m_num] += amt

    grand_total_income = sum(income_totals.values())
    grand_total_expense = sum(expense_totals.values())
    net_grand_total = grand_total_income - grand_total_expense

    conn.close()
    return render_template(
        'reports.html',
        selected_report=selected_report,
        selected_fy=selected_fy,
        available_fys=available_fys,
        start_date=start_date,
        end_date=end_date,
        income_matrix=income_matrix,
        expense_matrix=expense_matrix,
        income_totals=income_totals,
        expense_totals=expense_totals,
        grand_total_income=grand_total_income,
        grand_total_expense=grand_total_expense,
        net_grand_total=net_grand_total
    )

# ---------------------------------------------------------
# 5. MAINTENANCE LOOKUP ROUTES & ENDPOINTS
# ---------------------------------------------------------
@app.route('/maintenance/category')
def category_lookup_page():
    conn = get_db()
    categories = conn.execute("SELECT * FROM category_lookup ORDER BY category_name ASC").fetchall()
    conn.close()
    return render_template('category_lookup.html', categories=categories)

@app.route('/maintenance/category/save', methods=['POST'])
def category_lookup_save():
    cat_id = request.form.get('category_lookup_id')
    cat_name = request.form.get('category_name')
    is_active = 1 if request.form.get('is_active') else 0

    conn = get_db()
    cursor = conn.cursor()
    if cat_id:
        cursor.execute("UPDATE category_lookup SET category_name = ?, is_active = ? WHERE category_lookup_id = ?",
                       (cat_name, is_active, cat_id))
    else:
        cursor.execute("INSERT INTO category_lookup (category_name, is_active) VALUES (?, 1)", (cat_name,))
    conn.commit()
    conn.close()
    return redirect(url_for('category_lookup_page'))

@app.route('/maintenance/activity')
def activity_lookup_page():
    conn = get_db()
    activities = conn.execute("""
        SELECT a.*, c.category_name 
        FROM activity_lookup a 
        JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id 
        ORDER BY c.category_name, a.activity_name
    """).fetchall()
    categories = conn.execute("SELECT * FROM category_lookup WHERE is_active = 1 ORDER BY category_name ASC").fetchall()
    conn.close()
    return render_template('activity_lookup.html', activities=activities, categories=categories)

@app.route('/maintenance/activity/save', methods=['POST'])
def activity_lookup_save():
    act_id = request.form.get('activity_lookup_id')
    cat_id = request.form.get('category_lookup_id')
    act_name = request.form.get('activity_name')
    is_active = 1 if request.form.get('is_active') else 0

    conn = get_db()
    cursor = conn.cursor()
    if act_id:
        cursor.execute("UPDATE activity_lookup SET category_lookup_id = ?, activity_name = ?, is_active = ? WHERE activity_lookup_id = ?",
                       (cat_id, act_name, is_active, act_id))
    else:
        cursor.execute("INSERT INTO activity_lookup (category_lookup_id, activity_name, is_active) VALUES (?, ?, 1)",
                       (cat_id, act_name))
    conn.commit()
    conn.close()
    return redirect(url_for('activity_lookup_page'))

@app.route('/maintenance/person')
def person_lookup_page():
    conn = get_db()
    persons = conn.execute("SELECT DISTINCT name FROM daily_activity WHERE name IS NOT NULL ORDER BY name ASC").fetchall()
    conn.close()
    return render_template('person_lookup.html', persons=persons)

@app.route('/maintenance/session')
def session_lookup_page():
    return render_template('session_lookup.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)