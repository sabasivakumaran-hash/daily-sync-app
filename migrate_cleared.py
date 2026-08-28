import sqlite3
import os

DB_PATH = 'daily_sync.db'  # Replace with your actual db filename if different

def run_migration():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file '{DB_PATH}' not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Add is_cleared column to daily_activity if it doesn't exist
    try:
        cursor.execute("ALTER TABLE daily_activity ADD COLUMN is_cleared INTEGER DEFAULT 0;")
        print("Successfully added 'is_cleared' column to daily_activity.")
    except sqlite3.OperationalError:
        print("'is_cleared' column already exists.")

    # 2. Create app_config table for opening balance baseline
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_config (
            config_key TEXT PRIMARY KEY,
            config_value TEXT
        );
    """)

    # 3. Set default Jan 1 Opening Balance baseline if not present
    cursor.execute("""
        INSERT OR IGNORE INTO app_config (config_key, config_value) 
        VALUES ('opening_balance', '0.00');
    """)

    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == '__main__':
    run_migration()