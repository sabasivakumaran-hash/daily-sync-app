import sqlite3
import os

DB_NAME = "temple_sync.db"

def update_db():
    db_path = os.path.join(os.path.dirname(__file__), DB_NAME)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add description column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE category_lookup ADD COLUMN description TEXT;")
        conn.commit()
        print("Successfully added description column to category_lookup.")
    except sqlite3.OperationalError:
        print("Column 'description' already exists.")

    conn.close()

if __name__ == '__main__':
    update_db()