import sqlite3
import os

DB_NAME = "temple_sync.db"

def migrate():
    db_path = os.path.join(os.path.dirname(__file__), DB_NAME)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Starting migration...")

    # 1. Add category_id column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE activity_lookup ADD COLUMN category_id INTEGER REFERENCES category_lookup(id);")
        print("-> Added 'category_id' column to activity_lookup.")
    except sqlite3.OperationalError:
        print("-> 'category_id' column already exists in activity_lookup.")

    # 2. Map existing category text names to category_lookup IDs
    # Fetch all activities that have a text category but no category_id yet
    activities = cursor.execute("SELECT id, category FROM activity_lookup WHERE category IS NOT NULL").fetchall()

    updated_count = 0
    for act_id, cat_name in activities:
        if cat_name:
            # Find matching category_lookup ID (case-insensitive)
            cat_row = cursor.execute(
                "SELECT id FROM category_lookup WHERE LOWER(category_name) = LOWER(?)", 
                (cat_name.strip(),)
            ).fetchone()

            if cat_row:
                cat_id = cat_row[0]
                cursor.execute("UPDATE activity_lookup SET category_id = ? WHERE id = ?", (cat_id, act_id))
                updated_count += 1
            else:
                # If category doesn't exist in category_lookup yet, insert it automatically
                cursor.execute("INSERT INTO category_lookup (category_name, is_active) VALUES (?, 1)", (cat_name.strip().upper(),))
                new_cat_id = cursor.lastrowid
                cursor.execute("UPDATE activity_lookup SET category_id = ? WHERE id = ?", (new_cat_id, act_id))
                print(f"-> Created missing category '{cat_name.strip().upper()}' with ID {new_cat_id}")
                updated_count += 1

    conn.commit()
    conn.close()
    print(f"Migration complete! Updated {updated_count} activity record(s) with foreign key category_id.")

if __name__ == '__main__':
    migrate()