import os
import sqlite3

DATABASE = 'temple_sync.db'

def init_db():
    if os.path.exists(DATABASE):
        os.remove(DATABASE)
        print(f"Removed outdated {DATABASE}")

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON;")

    with open('schema.sql', 'r') as f:
        schema = f.read()
    cursor.executescript(schema)
    print("Database tables created successfully from schema.sql.")

    # Seed Categories
    cursor.execute("INSERT INTO category_lookup (category_name, is_active) VALUES ('Pooja Services', 1)")
    pooja_cat_id = cursor.lastrowid

    cursor.execute("INSERT INTO category_lookup (category_name, is_active) VALUES ('General Donations', 1)")
    donation_cat_id = cursor.lastrowid

    # Seed Activities
    cursor.execute("""
        INSERT INTO activity_lookup (category_lookup_id, activity_name, default_amount, txn_type, is_active)
        VALUES (?, 'Special Archana', 31.00, 'INCOME', 1)
    """, (pooja_cat_id,))

    cursor.execute("""
        INSERT INTO activity_lookup (category_lookup_id, activity_name, default_amount, txn_type, is_active)
        VALUES (?, 'Vehicle Pooja', 51.00, 'INCOME', 1)
    """, (pooja_cat_id,))

    conn.commit()
    conn.close()
    print("Database initialized and seeded successfully!")

if __name__ == '__main__':
    init_db()