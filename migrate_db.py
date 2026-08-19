import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'daily_sync.db')

def migrate():
    if not os.path.exists(DATABASE):
        print(f"Error: Database file not found at {DATABASE}")
        return

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    print("Starting local database migration...")

    # 1. ADD 'is_income' COLUMN TO activity_lookup IF MISSING
    cursor.execute("PRAGMA table_info(activity_lookup);")
    cols = [column[1] for column in cursor.fetchall()]
    if 'is_income' not in cols:
        print("-> Adding 'is_income' column to activity_lookup table...")
        cursor.execute("ALTER TABLE activity_lookup ADD COLUMN is_income INTEGER DEFAULT 1;")

    # Convert legacy text 'txn_type' ('INCOME'/'EXPENSE') to is_income (1/0)
    if 'txn_type' in cols:
        print("-> Mapping legacy text txn_type to integer is_income...")
        cursor.execute("UPDATE activity_lookup SET is_income = 1 WHERE UPPER(txn_type) = 'INCOME' OR txn_type IS NULL;")
        cursor.execute("UPDATE activity_lookup SET is_income = 0 WHERE UPPER(txn_type) = 'EXPENSE';")

    # 2. STANDARDIZE session_type IN daily_activity (1 = AM, 0 = PM)
    print("-> Standardizing session_type (1 = AM, 0 = PM)...")
    cursor.execute("UPDATE daily_activity SET session_type = 1 WHERE session_type IN ('AM', '1', 1) OR session_type IS NULL;")
    cursor.execute("UPDATE daily_activity SET session_type = 0 WHERE session_type IN ('PM', 'Noon', '0', 0);")

    # 3. STANDARDIZE is_active IN ALL TABLES (1 = Active, 0 = Inactive)
    print("-> Standardizing is_active flags across all tables...")
    cursor.execute("UPDATE daily_activity SET is_active = 1 WHERE is_active IS NULL OR is_active NOT IN (0, 1);")
    cursor.execute("UPDATE activity_lookup SET is_active = 1 WHERE is_active IS NULL OR is_active NOT IN (0, 1);")
    cursor.execute("UPDATE category_lookup SET is_active = 1 WHERE is_active IS NULL OR is_active NOT IN (0, 1);")

    # 4. CONVERT ALL txn_date VALUES TO YYYY-MM-DD
    print("-> Converting legacy MM/DD/YYYY dates to ISO YYYY-MM-DD...")
    rows = cursor.execute("SELECT daily_activity_id, txn_date FROM daily_activity WHERE txn_date LIKE '%/%/____';").fetchall()
    for row_id, date_str in rows:
        parts = date_str.split('/')
        if len(parts) == 3:
            m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
            iso_date = f"{y:04d}-{m:02d}-{d:02d}"
            cursor.execute("UPDATE daily_activity SET txn_date = ? WHERE daily_activity_id = ?;", (iso_date, row_id))

    conn.commit()
    conn.close()
    print("\nSUCCESS: Local database migration completed successfully!")

if __name__ == '__main__':
    migrate()