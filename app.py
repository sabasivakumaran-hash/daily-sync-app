import sqlite3
import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'temple_secret_key_bc_2026'  # Enables flash messaging

DB_NAME = "temple_sync.db"

def get_db_connection():
    db_path = os.path.join(os.path.dirname(__file__), DB_NAME)
    conn = sqlite3.connect(db_path, timeout=10)  # Waits up to 10s if DB is busy
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# 1. DEFAULT HOMEPAGE & DAILY ACTIVITY ROUTES
# ---------------------------------------------------------------------------
@app.route('/')
@app.route('/daily_activity')
def daily_activity_page():
    conn = get_db_connection()
    try:
        # Fetch active lookup options for transaction dropdowns
        lookups = conn.execute(
            'SELECT activity_name, category FROM activity_lookup WHERE is_active = 1 ORDER BY activity_name ASC'
        ).fetchall()
        
        # Fetch daily transactions sorted by newest update timestamp
        transactions = conn.execute(
            'SELECT seq_id, txn_date, am_pm, activity, quantity, txn_type, amount, name, notes FROM daily_activities ORDER BY updated_ts DESC'
        ).fetchall()
    finally:
        conn.close()
    
    # Renders the DAILY ACTIVITY template
    return render_template('daily_activity.html', lookups=lookups, transactions=transactions)


@app.route('/daily_activity/save', methods=['POST'])
def save_daily_activity():
    seq_id = request.form.get('seq_id')
    txn_date = request.form.get('txn_date')
    am_pm = request.form.get('am_pm', 'AM')
    txn_type = request.form.get('txn_type', 'Income')
    activity = request.form.get('activity')
    quantity = request.form.get('quantity', 1)
    amount = request.form.get('amount', 0.0)
    name = request.form.get('name')
    notes = request.form.get('notes')

    conn = get_db_connection()
    try:
        if seq_id:  # Update existing transaction
            conn.execute('''
                UPDATE daily_activities
                SET txn_date = ?, am_pm = ?, txn_type = ?, activity = ?, quantity = ?, amount = ?, name = ?, notes = ?, updated_ts = CURRENT_TIMESTAMP
                WHERE seq_id = ?
            ''', (txn_date, am_pm, txn_type, activity, quantity, amount, name, notes, seq_id))
        else:  # Create new transaction
            new_seq_id = f"SEQ-{uuid.uuid4().hex[:6].upper()}"
            conn.execute('''
                INSERT INTO daily_activities (seq_id, txn_date, am_pm, activity, quantity, txn_type, amount, name, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (new_seq_id, txn_date, am_pm, activity, quantity, txn_type, amount, name, notes))

        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Error saving transaction: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('daily_activity_page'))


# ---------------------------------------------------------------------------
# 2. ACTIVITY LOOKUP MASTER ROUTES (MAINTENANCE)
# ---------------------------------------------------------------------------
@app.route('/activity_lookup')
def activity_lookup_page():
    conn = get_db_connection()
    try:
        # Sorted by Status (Active first) then Activity Name
        activities = conn.execute(
            'SELECT id, category, activity_name, description, is_active FROM activity_lookup ORDER BY is_active DESC, activity_name ASC'
        ).fetchall()
    finally:
        conn.close()
    
    # Renders the ACTIVITY LOOKUP template
    return render_template('activity_lookup.html', activities=activities)


@app.route('/activity_lookup/save', methods=['POST'])
def save_activity():
    activity_id = request.form.get('activity_id')
    category = request.form.get('category')
    activity_name = request.form.get('activity_name', '').strip()
    description = request.form.get('description', '').strip()
    is_active = request.form.get('is_active', 1)

    conn = get_db_connection()
    try:
        if activity_id:  # UPDATE
            dup_check = conn.execute(
                'SELECT id FROM activity_lookup WHERE LOWER(activity_name) = LOWER(?) AND id != ?',
                (activity_name, activity_id)
            ).fetchone()

            if dup_check:
                flash(f"Cannot update: Activity '{activity_name}' already exists!", "danger")
            else:
                conn.execute('''
                    UPDATE activity_lookup 
                    SET category = ?, activity_name = ?, description = ?, is_active = ?
                    WHERE id = ?
                ''', (category, activity_name, description, is_active, activity_id))
                conn.commit()

        else:  # INSERT
            dup_check = conn.execute(
                'SELECT id FROM activity_lookup WHERE LOWER(activity_name) = LOWER(?)',
                (activity_name,)
            ).fetchone()

            if dup_check:
                flash(f"Cannot add: Activity '{activity_name}' already exists in the system!", "danger")
            else:
                conn.execute('''
                    INSERT INTO activity_lookup (category, activity_name, description, is_active)
                    VALUES (?, ?, ?, ?)
                ''', (category, activity_name, description, is_active))
                conn.commit()

    except sqlite3.IntegrityError:
        conn.rollback()
        flash(f"Database error: Duplicate record for '{activity_name}' blocked.", "danger")
    except Exception as e:
        conn.rollback()
        flash(f"An unexpected error occurred: {str(e)}", "danger")
    finally:
        conn.close()
    
    return redirect(url_for('activity_lookup_page'))


# ---------------------------------------------------------------------------
# APPLICATION ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)