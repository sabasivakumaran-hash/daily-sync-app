import sqlite3
import os

DB_NAME = "temple_sync.db"

def init_db():
    db_path = os.path.join(os.path.dirname(__file__), DB_NAME)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Create Lookup Table (activity_lookup - Singular)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_lookup (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_name TEXT NOT NULL UNIQUE,
        category TEXT NOT NULL,         -- 'Income' or 'Expense'
        description TEXT,
        default_amount REAL,
        is_active INTEGER DEFAULT 1
    );
    """)

    # 2. Create Daily Activities Table (daily_activities)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_activities (
        seq_id TEXT PRIMARY KEY,
        txn_date TEXT NOT NULL,
        am_pm TEXT NOT NULL DEFAULT 'AM',
        activity TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        txn_type TEXT NOT NULL DEFAULT 'Income',
        amount REAL NOT NULL,
        name TEXT,
        notes TEXT,
        updated_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Seed Initial Lookup Data
    initial_lookups = [
        ("Archana", "Income", "General Archana service", 21.00, 1),
        ("Abhishekam", "Income", "Special deity Abhishekam", 51.00, 1),
        ("Special Pooja", "Income", "Special Pooja sponsorship", 101.00, 1),
        ("General Donation", "Income", "General temple donation", None, 1),
        ("Hall Rental", "Income", "Facility rental income", 500.00, 1),
        ("Utilities Expense", "Expense", "Electricity and water expenses", None, 1),
        ("Supplies Expense", "Expense", "Temple maintenance supplies", None, 1),
        ("Priest Honorarium", "Expense", "Monthly priest honorarium", None, 1)
    ]

    cursor.executemany("""
    INSERT INTO activity_lookup (activity_name, category, description, default_amount, is_active)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(activity_name) DO UPDATE SET
        category=excluded.category,
        description=excluded.description,
        default_amount=excluded.default_amount,
        is_active=excluded.is_active;
    """, initial_lookups)

    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' initialized successfully!")

if __name__ == "__main__":
    init_db()