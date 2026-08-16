import csv
import sqlite3
import os
from datetime import datetime

DB_PATH = 'daily_sync.db'
CSV_PATH = 'daily_activity_load.csv'

def parse_date(date_str):
    """Converts M/D/YYYY or MM/DD/YYYY to YYYY-MM-DD format."""
    date_str = date_str.strip()
    try:
        return datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
    except ValueError:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError:
            return date_str

def safe_float(val):
    """Parses float, returning None if empty, whitespace, or invalid."""
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    try:
        return float(val_str)
    except ValueError:
        return None

def safe_int(val, default=1):
    if val is None:
        return default
    val_str = str(val).strip()
    if not val_str:
        return default
    try:
        return int(float(val_str))
    except ValueError:
        return default

def seed_daily_activity():
    if not os.path.exists(CSV_PATH):
        print(f"❌ Error: Could not find '{CSV_PATH}' in {os.getcwd()}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear existing records for a fresh load
    cursor.execute("DELETE FROM daily_activity;")

    inserted_count = 0
    flagged_count = 0
    row_num = 1  # Header line is row 1

    with open(CSV_PATH, mode='r', encoding='utf-8-sig') as f:
        first_line = f.readline()
        delimiter = '\t' if '\t' in first_line else ','
        f.seek(0)
        
        reader = csv.DictReader(f, delimiter=delimiter)
        reader.fieldnames = [name.strip() for name in reader.fieldnames if name]
        
        print(f"Detected Delimiter: '{'Tab' if delimiter == '\t' else 'Comma'}'")
        print(f"Headers: {reader.fieldnames}\n")

        for row in reader:
            row_num += 1
            clean_row = {k.strip(): str(v).strip() for k, v in row.items() if k}

            txn_date = parse_date(clean_row.get('txn_date', ''))
            session_type = clean_row.get('session_type', 'AM') or 'AM'
            activity_lookup_id = safe_int(clean_row.get('activity_lookup_id'), default=0)
            person_name = clean_row.get('person_name', '')
            remarks = clean_row.get('remarks', '')
            is_active = safe_int(clean_row.get('is_active'), default=1)

            # 1. Validate Total Amount
            total_amount = safe_float(clean_row.get('total_amount'))
            
            if total_amount is None:
                flagged_count += 1
                print(f"⚠️ FLAG [Row {row_num}]: Missing or invalid total_amount on {txn_date} for '{person_name}'. Skipped/Flagged.")
                continue  # Skip row or insert with default depending on preference

            # 2. Parse Quantity
            quantity = safe_int(clean_row.get('quantity'), default=1)
            if quantity <= 0:
                quantity = 1

            # 3. Handle Unit Price Validation & Assignment
            unit_price = safe_float(clean_row.get('unit_price'))
            
            if unit_price is None or unit_price == 0.0:
                if quantity == 1:
                    unit_price = total_amount
                else:
                    unit_price = round(total_amount / quantity, 2)

            cursor.execute("""
                INSERT INTO daily_activity (
                    txn_date, session_type, activity_lookup_id, person_name,
                    unit_price, quantity, total_amount, remarks, is_active, updated_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (txn_date, session_type, activity_lookup_id, person_name,
                  unit_price, quantity, total_amount, remarks, is_active))

            inserted_count += 1

    conn.commit()
    conn.close()
    
    print("\n--------------------------------------------------")
    print(f"✅ Insertion Complete!")
    print(f"   - Total Rows Inserted: {inserted_count}")
    print(f"   - Flagged/Skipped Rows: {flagged_count}")
    print("--------------------------------------------------")

if __name__ == '__main__':
    seed_daily_activity()