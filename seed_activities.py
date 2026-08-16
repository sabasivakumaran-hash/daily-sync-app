import csv
import sqlite3
import os

DB_PATH = 'daily_sync.db'
CSV_PATH = 'activity_lookup.csv'

def seed_activities():
    if not os.path.exists(CSV_PATH):
        print(f"❌ Error: Could not find '{CSV_PATH}' in {os.getcwd()}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear existing activity records
    cursor.execute("DELETE FROM activity_lookup;")

    inserted_count = 0
    with open(CSV_PATH, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        # Strip any hidden whitespace or BOM chars from headers
        reader.fieldnames = [name.strip() for name in reader.fieldnames if name]
        print(f"Reading CSV Headers: {reader.fieldnames}")

        for row in reader:
            # Clean dictionary keys & values
            clean_row = {k.strip(): v.strip() for k, v in row.items() if k}
            
            act_id = int(clean_row['activity_lookup_id'])
            cat_id = int(clean_row['category_lookup_id'])
            act_name = clean_row['activity_name']
            
            default_amount_str = clean_row.get('default_amount', '0')
            default_amount = float(default_amount_str) if default_amount_str else 0.0
            
            raw_type = clean_row.get('txn_type', 'INPUT').upper()
            txn_type = 'EXPENSE' if raw_type in ['EXPENSE', 'OUTPUT'] else 'INCOME'

            is_active = int(clean_row.get('is_active', '1'))

            cursor.execute("""
                INSERT INTO activity_lookup (
                    activity_lookup_id, 
                    category_lookup_id, 
                    activity_name, 
                    default_amount, 
                    txn_type, 
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (act_id, cat_id, act_name, default_amount, txn_type, is_active))
            
            inserted_count += 1

    conn.commit()
    conn.close()
    print(f"✅ Success! Inserted {inserted_count} activities into activity_lookup table.")

if __name__ == '__main__':
    seed_activities()