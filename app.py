import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "temple_sync_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'temple_sync.db')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# 1. DAILY ACTIVITY MODULE (HOME)
# ==========================================
@app.route('/')
@app.route('/daily_activity', methods=['GET'])
def daily_activity_page():
    conn = get_db()
    
    # Active activities for dropdown
    act_rows = conn.execute("""
        SELECT * FROM activity_lookup 
        WHERE is_active = 1 
        ORDER BY activity_name ASC
    """).fetchall()
    activities = [dict(r) for r in act_rows]

    # Unique devotee names for auto-suggest list
    name_rows = conn.execute("""
        SELECT DISTINCT person_name 
        FROM daily_activity 
        WHERE person_name IS NOT NULL AND person_name != '' 
        ORDER BY person_name ASC
    """).fetchall()
    existing_names = [r['person_name'] for r in name_rows]

    # Daily activity records sorted by updated_ts descending
    txn_rows = conn.execute("""
        SELECT t.*, a.activity_name, c.category_name 
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        ORDER BY t.updated_ts DESC
    """).fetchall()
    transactions = [dict(r) for r in txn_rows]
    
    conn.close()
    
    return render_template(
        'daily_activity.html', 
        activities=activities, 
        existing_names=existing_names, 
        transactions=transactions
    )

@app.route('/daily_activity/save', methods=['POST'])
def daily_activity_save():
    daily_activity_id = request.form.get('daily_activity_id')
    txn_date = request.form.get('txn_date')
    session_type = request.form.get('session_type', 'AM')
    activity_lookup_id = request.form.get('activity_lookup_id')
    person_name = request.form.get('person_name', '').strip()
    
    try:
        unit_price = float(request.form.get('unit_price') or 0.00)
    except ValueError:
        unit_price = 0.00
        
    try:
        quantity = int(request.form.get('quantity') or 1)
    except ValueError:
        quantity = 1
        
    entry_type = request.form.get('entry_type', 'INCOME')
    
    # Calculate Total with Expense Multiplier (-1.0)
    multiplier = -1.0 if entry_type == 'EXPENSE' else 1.0
    total_amount = abs(unit_price * quantity) * multiplier

    remarks = request.form.get('remarks', '').strip()
    is_active = request.form.get('is_active', 1)

    conn = get_db()
    if daily_activity_id:
        conn.execute("""
            UPDATE daily_activity 
            SET txn_date = ?, session_type = ?, activity_lookup_id = ?, person_name = ?, 
                unit_price = ?, quantity = ?, entry_type = ?, total_amount = ?, remarks = ?, is_active = ?,
                updated_ts = CURRENT_TIMESTAMP
            WHERE daily_activity_id = ?
        """, (txn_date, session_type, activity_lookup_id, person_name, unit_price, quantity, entry_type, total_amount, remarks, is_active, daily_activity_id))
        flash('Daily Activity updated successfully!', 'success')
    else:
        conn.execute("""
            INSERT INTO daily_activity (txn_date, session_type, activity_lookup_id, person_name, unit_price, quantity, entry_type, total_amount, remarks, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (txn_date, session_type, activity_lookup_id, person_name, unit_price, quantity, entry_type, total_amount, remarks, is_active))
        flash('Daily Activity recorded successfully!', 'success')
    
    conn.commit()
    conn.close()
    return redirect(url_for('daily_activity_page'))


# ==========================================
# 2. CATEGORY LOOKUP MODULE
# ==========================================
@app.route('/category_lookup', methods=['GET'])
def category_lookup_page():
    conn = get_db()
    rows = conn.execute("SELECT * FROM category_lookup ORDER BY category_name ASC").fetchall()
    categories = [dict(r) for r in rows]
    conn.close()
    return render_template('category_lookup.html', categories=categories)

@app.route('/category_lookup/save', methods=['POST'])
def category_lookup_save():
    category_lookup_id = request.form.get('category_lookup_id')
    category_name = request.form.get('category_name', '').strip()
    is_active = request.form.get('is_active', 1)

    conn = get_db()
    if category_lookup_id:
        conn.execute("""
            UPDATE category_lookup 
            SET category_name = ?, is_active = ?, updated_ts = CURRENT_TIMESTAMP
            WHERE category_lookup_id = ?
        """, (category_name, is_active, category_lookup_id))
        flash('Category updated successfully!', 'success')
    else:
        conn.execute("""
            INSERT INTO category_lookup (category_name, is_active) 
            VALUES (?, ?)
        """, (category_name, is_active))
        flash('Category created successfully!', 'success')
    
    conn.commit()
    conn.close()
    return redirect(url_for('category_lookup_page'))


# ==========================================
# 3. ACTIVITY LOOKUP MODULE
# ==========================================
@app.route('/activity_lookup', methods=['GET'])
def activity_lookup_page():
    conn = get_db()
    cat_rows = conn.execute("SELECT * FROM category_lookup WHERE is_active = 1 ORDER BY category_name ASC").fetchall()
    categories = [dict(r) for r in cat_rows]

    act_rows = conn.execute("""
        SELECT a.*, c.category_name 
        FROM activity_lookup a
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        ORDER BY a.activity_name ASC
    """).fetchall()
    activities = [dict(r) for r in act_rows]
    conn.close()

    return render_template('activity_lookup.html', categories=categories, activities=activities)

@app.route('/activity_lookup/save', methods=['POST'])
def activity_lookup_save():
    activity_lookup_id = request.form.get('activity_lookup_id')
    activity_name = request.form.get('activity_name', '').strip()
    category_lookup_id = request.form.get('category_lookup_id')
    default_amount = request.form.get('default_amount') or 0.00
    txn_type = request.form.get('txn_type')
    is_active = request.form.get('is_active', 1)

    conn = get_db()
    if activity_lookup_id:
        conn.execute("""
            UPDATE activity_lookup 
            SET activity_name = ?, category_lookup_id = ?, default_amount = ?, txn_type = ?, is_active = ?, updated_ts = CURRENT_TIMESTAMP
            WHERE activity_lookup_id = ?
        """, (activity_name, category_lookup_id, default_amount, txn_type, is_active, activity_lookup_id))
        flash('Activity updated successfully!', 'success')
    else:
        conn.execute("""
            INSERT INTO activity_lookup (activity_name, category_lookup_id, default_amount, txn_type, is_active)
            VALUES (?, ?, ?, ?, ?)
        """, (activity_name, category_lookup_id, default_amount, txn_type, is_active))
        flash('Activity created successfully!', 'success')
    
    conn.commit()
    conn.close()
    return redirect(url_for('activity_lookup_page'))

from datetime import datetime

# ==========================================
# 4. DASHBOARD & REPORTS MODULES
# ==========================================
@app.route('/dashboard', methods=['GET'])
def dashboard_page():
    return render_template('dashboard.html')

@app.route('/reports', methods=['GET', 'POST'])
def reports_page():
    # Read report type (defaults to 'income_expense')
    selected_report = request.values.get('report_type', 'income_expense')
    
    # Calculate current year dynamically (CCYY)
    current_year = datetime.now().year
    default_start = f"{current_year}-01-01"
    default_end = f"{current_year}-12-31"

    # User-selectable Date Pickers (Defaults to Current Year Jan 1 -> Dec 31)
    start_date = request.values.get('start_date', default_start)
    end_date = request.values.get('end_date', default_end)

    conn = get_db()

    query = """
        SELECT 
            c.category_name,
            t.entry_type,
            t.txn_date,
            t.total_amount
        FROM daily_activity t
        LEFT JOIN activity_lookup a ON t.activity_lookup_id = a.activity_lookup_id
        LEFT JOIN category_lookup c ON a.category_lookup_id = c.category_lookup_id
        WHERE t.txn_date BETWEEN ? AND ? AND t.is_active = 1
        ORDER BY c.category_name ASC, t.txn_date ASC
    """
    rows = conn.execute(query, (start_date, end_date)).fetchall()
    conn.close()

    months_list = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    income_matrix = {}
    expense_matrix = {}
    
    income_totals = {m: 0.0 for m in months_list}
    expense_totals = {m: 0.0 for m in months_list}
    
    grand_total_income = 0.0
    grand_total_expense = 0.0

    for r in rows:
        cat_name = r['category_name'] or 'Uncategorized'
        entry_type = r['entry_type'] or ('EXPENSE' if (r['total_amount'] or 0) < 0 else 'INCOME')
        amount = abs(r['total_amount'] or 0.0)
        
        if r['txn_date']:
            dt = datetime.strptime(r['txn_date'], '%Y-%m-%d')
            m_name = months_list[dt.month - 1]
        else:
            continue

        if entry_type == 'INCOME':
            if cat_name not in income_matrix:
                income_matrix[cat_name] = {m: 0.0 for m in months_list}
            income_matrix[cat_name][m_name] += amount
            income_totals[m_name] += amount
            grand_total_income += amount
        else:
            if cat_name not in expense_matrix:
                expense_matrix[cat_name] = {m: 0.0 for m in months_list}
            expense_matrix[cat_name][m_name] += amount
            expense_totals[m_name] += amount
            grand_total_expense += amount

    net_totals = {m: income_totals[m] - expense_totals[m] for m in months_list}
    net_grand_total = grand_total_income - grand_total_expense

    return render_template(
        'reports.html',
        selected_report=selected_report,
        start_date=start_date,
        end_date=end_date,
        months_list=months_list,
        income_matrix=income_matrix,
        expense_matrix=expense_matrix,
        income_totals=income_totals,
        expense_totals=expense_totals,
        grand_total_income=grand_total_income,
        grand_total_expense=grand_total_expense,
        net_totals=net_totals,
        net_grand_total=net_grand_total
    )


if __name__ == '__main__':
    app.run(debug=True)