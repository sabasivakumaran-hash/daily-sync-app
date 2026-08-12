import csv
import sqlite3
import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'daily_sync.db')
CSV_PATH = os.path.join(BASE_DIR, 'temple_data.csv')

def clean_amount(val):
    if not val:
        return 0.0
    cleaned = re.sub(r'[^\d.-]', '', str(val))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def clean_qty(val):
    if not val:
        return 1
    cleaned = re.sub(r'\D', '', str(val))
    return int(cleaned) if cleaned else 1

def parse_date_to_iso(date_str):
    date_str = str(date_str).strip()
    for fmt in ('%m/%d/%Y', '%n/%e/%Y', '%Y-%m-%d', '%m-%d-%Y'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return date_str

def init_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_lookup (
            category_lookup_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 1
        );
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_lookup (
            activity_lookup_id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_name TEXT NOT NULL,
            category_lookup_id INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (category_lookup_id) REFERENCES category_lookup (category_lookup_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_activity (
            daily_activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_date TEXT NOT NULL,
            activity_lookup_id INTEGER NOT NULL,
            name TEXT,
            session TEXT DEFAULT 'AM',
            entry_type TEXT DEFAULT 'INCOME',
            quantity INTEGER DEFAULT 1,
            unit_price REAL DEFAULT 0.0,
            total_amount REAL DEFAULT 0.0,
            remarks TEXT,
            is_active INTEGER DEFAULT 1,
            updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (activity_lookup_id) REFERENCES activity_lookup (activity_lookup_id)
        );
    """)

def reset_and_reload():
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: Cannot find CSV file at '{CSV_PATH}'. Please ensure 'temple_data.csv' is placed in '{BASE_DIR}'.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("--- 1. Resetting Database Schema & Dropping Existing Tables ---")
    cursor.execute("PRAGMA foreign_keys = OFF;")
    cursor.execute("DROP TABLE IF EXISTS daily_activity;")
    cursor.execute("DROP TABLE IF EXISTS activity_lookup;")
    cursor.execute("DROP TABLE IF EXISTS category_lookup;")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('daily_activity', 'activity_lookup', 'category_lookup');")
    conn.commit()

    init_tables(cursor)
    cursor.execute("PRAGMA foreign_keys = ON;")

    print("--- 2. Cleansing and Importing Data from temple_data.csv ---")

    cat_cache = {}
    act_cache = {}
    inserted_count = 0

    with open(CSV_PATH, mode='r', encoding='utf-8-sig') as f:
        sample = f.read(2048)
        f.seek(0)
        delimiter = '\t' if '\t' in sample else ','
        
        reader = csv.DictReader(f, delimiter=delimiter)

        for row in reader:
            clean_row = { (k.strip() if k else ''): v for k, v in row.items() if k }

            raw_date = clean_row.get('DATE', '')
            if not raw_date or not raw_date.strip():
                continue

            txn_date = parse_date_to_iso(raw_date)
            session = str(clean_row.get('AM', 'AM')).strip().upper()
            raw_act = str(clean_row.get('CATEGORY 1', 'GENERAL')).strip().upper()
            raw_cat = str(clean_row.get('CATEGORY 2', 'POOJA')).strip().upper()
            receipt = str(clean_row.get('RECEIPT #', '')).strip()
            person_name = str(clean_row.get('NAME', '')).strip()
            raw_qty = clean_row.get('Qty', '1')
            raw_income = clean_row.get('INCOME', clean_row.get('INCOME\xa0', '0'))

            if raw_income == '0':
                for k, v in clean_row.items():
                    if 'INCOME' in k:
                        raw_income = v
                        break

            qty = clean_qty(raw_qty)
            total_amount = clean_amount(raw_income)
            unit_price = round(total_amount / qty, 2) if qty > 0 else total_amount

            entry_type = 'EXPENSE' if raw_cat == 'UTILITY' or total_amount < 0 else 'INCOME'
            total_amount = abs(total_amount)

            if raw_cat not in cat_cache:
                cursor.execute("SELECT category_lookup_id FROM category_lookup WHERE category_name = ?", (raw_cat,))
                c_row = cursor.fetchone()
                if c_row:
                    cat_cache[raw_cat] = c_row[0]
                else:
                    cursor.execute("INSERT INTO category_lookup (category_name, is_active) VALUES (?, 1)", (raw_cat,))
                    cat_cache[raw_cat] = cursor.lastrowid

            cat_id = cat_cache[raw_cat]

            act_key = (raw_act, cat_id)
            if act_key not in act_cache:
                cursor.execute(
                    "SELECT activity_lookup_id FROM activity_lookup WHERE activity_name = ? AND category_lookup_id = ?",
                    (raw_act, cat_id)
                )
                a_row = cursor.fetchone()
                if a_row:
                    act_cache[act_key] = a_row[0]
                else:
                    cursor.execute(
                        "INSERT INTO activity_lookup (activity_name, category_lookup_id, is_active) VALUES (?, ?, 1)",
                        (raw_act, cat_id)
                    )
                    act_cache[act_key] = cursor.lastrowid

            act_id = act_cache[act_key]

            cursor.execute("""
                INSERT INTO daily_activity 
                (txn_date, activity_lookup_id, name, session, entry_type, quantity, unit_price, total_amount, remarks, is_active, updated_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            """, (txn_date, act_id, person_name, session, entry_type, qty, unit_price, total_amount, receipt))

            inserted_count += 1

    conn.commit()
    conn.close()
    print(f"--- SUCCESS: {inserted_count} rows cleansed and loaded with updated_ts across 3 tables! ---")

if __name__ == '__main__':
    reset_and_reload()