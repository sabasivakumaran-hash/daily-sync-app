import sqlite3
import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'temple_secret_key_bc_2026'

DB_NAME = "temple_sync.db"

def get_db_connection():
    db_path = os.path.join(os.path.dirname(__file__), DB_NAME)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# 1. DAILY ACTIVITY & DASHBOARD / REPORTS (NAVIGATION PAGES)
# ---------------------------------------------------------------------------
@app.route('/')
@app.route('/daily_activity')
def daily_activity_page():
    conn = get_db_connection()
    try:
        # Strict Filter: Only show active activities belonging to active categories
        lookups = conn.execute('''
            SELECT a.activity_name, a.default_amount, a.txn_type
            FROM activity_lookup a
            INNER JOIN category_lookup c ON a.category_id = c.id
            WHERE a.is_active = 1 AND c.is_active = 1
            ORDER BY a.activity_name ASC
        ''').fetchall()
        
        # Check if daily_activities table exists before querying
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_activities'"
        ).fetchone()

        if table_check:
            transactions = conn.execute(
                'SELECT seq_id, txn_date, am_pm, activity, quantity, txn_type, amount, name, notes FROM daily_activities ORDER BY updated_ts DESC'
            ).fetchall()
        else:
            transactions = []
    finally:
        conn.close()
    
    return render_template('daily_activity.html', lookups=lookups, transactions=transactions)


@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html')


@app.route('/reports')
def reports_page():
    return render_template('reports.html')


# ---------------------------------------------------------------------------
# 2. CATEGORY LOOKUP MASTER ROUTES (MAINTENANCE)
# ---------------------------------------------------------------------------
@app.route('/category_lookup')
def category_lookup_page():
    conn = get_db_connection()
    try:
        categories = conn.execute(
            'SELECT id, category_name, description, is_active FROM category_lookup ORDER BY is_active DESC, category_name ASC'
        ).fetchall()
    finally:
        conn.close()
    
    return render_template('category_lookup.html', categories=categories)


@app.route('/category_lookup/save', methods=['POST'])
def save_category():
    category_id = request.form.get('category_id')
    category_name = request.form.get('category_name', '').strip()
    description = request.form.get('description', '').strip()
    is_active = int(request.form.get('is_active', 1))

    if not category_name:
        flash("Category Name is required!", "danger")
        return redirect(url_for('category_lookup_page'))

    conn = get_db_connection()
    try:
        if category_id:  # UPDATE
            if is_active == 0:
                cat_row = conn.execute('SELECT category_name FROM category_lookup WHERE id = ?', (category_id,)).fetchone()
                if cat_row:
                    current_cat_name = cat_row['category_name']
                    active_count = conn.execute(
                        'SELECT COUNT(*) FROM activity_lookup WHERE category_id = ? AND is_active = 1',
                        (category_id,)
                    ).fetchone()[0]

                    if active_count > 0:
                        flash(f"Cannot deactivate Category '{current_cat_name}': It is linked to {active_count} active Activity item(s). Please reassign or set those activities to Inactive first.", "danger")
                        return redirect(url_for('category_lookup_page'))

            dup_check = conn.execute(
                'SELECT id FROM category_lookup WHERE LOWER(category_name) = LOWER(?) AND id != ?',
                (category_name, category_id)
            ).fetchone()

            if dup_check:
                flash(f"Cannot update: A Category named '{category_name}' already exists!", "danger")
            else:
                conn.execute('''
                    UPDATE category_lookup 
                    SET category_name = ?, description = ?, is_active = ?
                    WHERE id = ?
                ''', (category_name, description, is_active, category_id))
                conn.commit()

        else:  # INSERT
            dup_check = conn.execute(
                'SELECT id FROM category_lookup WHERE LOWER(category_name) = LOWER(?)',
                (category_name,)
            ).fetchone()

            if dup_check:
                flash(f"Cannot add: A Category named '{category_name}' already exists!", "danger")
            else:
                conn.execute('''
                    INSERT INTO category_lookup (category_name, description, is_active)
                    VALUES (?, ?, ?)
                ''', (category_name, description, is_active))
                conn.commit()

    except Exception as e:
        conn.rollback()
        flash(f"An unexpected error occurred: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('category_lookup_page'))


# ---------------------------------------------------------------------------
# 3. ACTIVITY LOOKUP MASTER ROUTES (MAINTENANCE)
# ---------------------------------------------------------------------------
@app.route('/activity_lookup')
def activity_lookup_page():
    conn = get_db_connection()
    try:
        activities = conn.execute('''
            SELECT 
                a.id, 
                a.category_id, 
                c.category_name, 
                a.activity_name, 
                a.description, 
                a.default_amount,
                a.txn_type,
                a.is_active 
            FROM activity_lookup a
            INNER JOIN category_lookup c ON a.category_id = c.id
            ORDER BY a.is_active DESC, a.activity_name ASC
        ''').fetchall()
        
        categories = conn.execute(
            'SELECT id, category_name FROM category_lookup WHERE is_active = 1 ORDER BY category_name ASC'
        ).fetchall()
    finally:
        conn.close()
    
    return render_template('activity_lookup.html', activities=activities, categories=categories)


@app.route('/activity_lookup/save', methods=['POST'])
def save_activity():
    activity_id = request.form.get('activity_id')
    category_id = request.form.get('category_id')
    activity_name = request.form.get('activity_name', '').strip()
    default_amount = request.form.get('default_amount', 1.00)
    txn_type = request.form.get('txn_type', 'Income')
    description = request.form.get('description', '').strip()
    is_active = int(request.form.get('is_active', 1))

    if not activity_name:
        flash("Activity Name is required!", "danger")
        return redirect(url_for('activity_lookup_page'))

    if not category_id:
        flash("Please select a valid Category from the list.", "danger")
        return redirect(url_for('activity_lookup_page'))

    conn = get_db_connection()
    try:
        cat_check = conn.execute(
            'SELECT is_active FROM category_lookup WHERE id = ?', (category_id,)
        ).fetchone()

        if not cat_check:
            flash("Selected Category does not exist in the system!", "danger")
            return redirect(url_for('activity_lookup_page'))
        elif cat_check['is_active'] == 0:
            flash("Cannot link activity: Selected Category is Inactive!", "danger")
            return redirect(url_for('activity_lookup_page'))

        try:
            default_amount = float(default_amount)
            if default_amount < 0:
                default_amount = 0.00
        except ValueError:
            default_amount = 1.00

        if activity_id:  # UPDATE
            dup_check = conn.execute(
                'SELECT id FROM activity_lookup WHERE LOWER(activity_name) = LOWER(?) AND id != ?',
                (activity_name, activity_id)
            ).fetchone()

            if dup_check:
                flash(f"Cannot update: An Activity named '{activity_name}' already exists!", "danger")
            else:
                conn.execute('''
                    UPDATE activity_lookup 
                    SET category_id = ?, activity_name = ?, default_amount = ?, txn_type = ?, description = ?, is_active = ?
                    WHERE id = ?
                ''', (category_id, activity_name, default_amount, txn_type, description, is_active, activity_id))
                conn.commit()

        else:  # INSERT
            dup_check = conn.execute(
                'SELECT id FROM activity_lookup WHERE LOWER(activity_name) = LOWER(?)',
                (activity_name,)
            ).fetchone()

            if dup_check:
                flash(f"Cannot add: An Activity named '{activity_name}' already exists!", "danger")
            else:
                conn.execute('''
                    INSERT INTO activity_lookup (category_id, activity_name, default_amount, txn_type, description, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (category_id, activity_name, default_amount, txn_type, description, is_active))
                conn.commit()

    except Exception as e:
        conn.rollback()
        flash(f"An unexpected error occurred: {str(e)}", "danger")
    finally:
        conn.close()
    
    return redirect(url_for('activity_lookup_page'))


if __name__ == '__main__':
    app.run(debug=True)