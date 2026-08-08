import sqlite3
import os

DB_NAME = "temple_sync.db"

def create_empty_tables():
    db_path = os.path.join(os.path.dirname(__file__), DB_NAME)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable Foreign Key enforcement in SQLite
    cursor.execute("PRAGMA foreign_keys = ON;")

    print("Building empty master tables...")

    # 1. CATEGORY LOOKUP MASTER
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS category_lookup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT UNIQUE NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1
        );
    ''')
    print("-> Table created: category_lookup")

    # 2. ACTIVITY LOOKUP MASTER
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_lookup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            activity_name TEXT UNIQUE NOT NULL,
            description TEXT,
            default_amount REAL DEFAULT 1.00,
            txn_type TEXT DEFAULT 'Income',
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES category_lookup(id)
        );
    ''')
    print("-> Table created: activity_lookup")

    conn.commit()
    conn.close()
    print("Database structure successfully created! Tables are empty and ready for data.")

if __name__ == '__main__':
    create_empty_tables()