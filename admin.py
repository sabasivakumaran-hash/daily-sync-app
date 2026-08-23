import os
import csv
import io
import sqlite3
from datetime import datetime
from flask import Blueprint, send_file, request, Response, current_app, flash, redirect, url_for
from flask_login import login_required
from helpers import role_required

admin_bp = Blueprint('admin_bp', __name__)

def get_db():
    """Obtain SQLite database connection factory using application configuration."""
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    if current_app.config.get('SQLITE_FOREIGN_KEYS'):
        conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# ---------------------------------------------------------
# 1. ONE-CLICK SQLITE BACKUP ROUTE
# ---------------------------------------------------------
@admin_bp.route('/maintenance/backup_db', methods=['GET'])
@login_required
@role_required('admin')
def backup_sqlite():
    """Generates an instant timestamped copy of the SQLite database for local download."""
    db_path = current_app.config.get('DATABASE')
    
    if not db_path or not os.path.exists(db_path):
        flash('Database file not found for backup.', 'danger')
        return redirect(url_for('maintenance_data_page'))
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    download_filename = f"temple_sync_backup_{timestamp}.db"
    
    return send_file(
        db_path,
        as_attachment=True,
        download_name=download_filename,
        mimetype='application/x-sqlite3'
    )

# ---------------------------------------------------------
# 2. BATCH CSV DATA EXPORT ROUTE
# ---------------------------------------------------------
@admin_bp.route('/maintenance/export_csv', methods=['GET'])
@login_required
@role_required('admin')
def export_csv():
    """Exports raw daily activity records into a downloadable CSV file."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    conn = get_db()
    cursor = conn.cursor()
    
    query = """
        SELECT 
            da.daily_activity_id,
            da.txn_date,
            CASE WHEN CAST(COALESCE(da.session_type, 1) AS INTEGER) = 1 THEN 'AM' ELSE 'PM' END as session,
            al.activity_name,
            cl.category_name,
            CASE WHEN CAST(COALESCE(al.is_income, 1) AS INTEGER) = 1 THEN 'INCOME' ELSE 'EXPENSE' END as transaction_type,
            da.person_name,
            da.unit_price,
            da.quantity,
            da.total_amount,
            da.remarks,
            CASE WHEN CAST(COALESCE(da.is_active, 1) AS INTEGER) = 1 THEN 'Active' ELSE 'Inactive' END as status
        FROM daily_activity da
        LEFT JOIN activity_lookup al ON da.activity_lookup_id = al.activity_lookup_id
        LEFT JOIN category_lookup cl ON al.category_lookup_id = cl.category_lookup_id
        WHERE 1=1
    """
    params = []
    
    if start_date:
        query += " AND da.txn_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND da.txn_date <= ?"
        params.append(end_date)
        
    query += " ORDER BY da.txn_date DESC, da.daily_activity_id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    # Stream as CSV Response
    def generate():
        data = io.StringIO()
        writer = csv.writer(data)
        
        # Header Row
        writer.writerow([
            'Activity ID', 'Date', 'Session', 'Activity Name', 'Category', 
            'Type', 'Person Name', 'Unit Price', 'Quantity', 'Total Amount', 'Remarks', 'Status'
        ])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        
        # Data Rows
        for row in rows:
            writer.writerow(list(row))
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    filename_part = f"{start_date}_to_{end_date}" if (start_date and end_date) else "all_records"
    filename = f"daily_activity_export_{filename_part}.csv"
    
    return Response(
        generate(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )