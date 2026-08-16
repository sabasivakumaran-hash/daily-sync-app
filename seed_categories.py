import csv
import sqlite3
import os

DB_PATH = 'daily_sync.db'
CSV_PATH = 'category_lookup.csv'

def seed_categories():
    if not os.path.exists(CSV_PATH):
        print(f"Error: Could not find '{CSV_PATH}' in {os.getcwd()}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear existing category records
    cursor.execute("DELETE FROM category_lookup;")

    inserted_count = 0
    with open(CSV_PATH, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat_id = int(row['category_lookup_id'].strip())
            cat_name = row['category_name'].strip()
            is_active = int(row['is_active'].strip())

            cursor.execute("""
                INSERT INTO category_lookup (category_lookup_id, category_name, is_active)
                VALUES (?, ?, ?)
            """, (cat_id, cat_name, is_active))
            inserted_count += 1

    conn.commit()
    conn.close()
    print(f"Success! Inserted {inserted_count} categories into category_lookup table.")

if __name__ == '__main__':
    seed_categories()