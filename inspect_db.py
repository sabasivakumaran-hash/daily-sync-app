import sqlite3

conn = sqlite3.connect('daily_sync.db')
cursor = conn.cursor()

print("=== SESSION TYPE VALUE COUNTS ===")
cursor.execute("SELECT session_type, COUNT(*) FROM daily_activity GROUP BY session_type;")
for row in cursor.fetchall():
    print(f"Raw Value in DB: {repr(row[0])} -> Count: {row[1]}")

print("\n=== SAMPLE ROWS ===")
cursor.execute("SELECT daily_activity_id, txn_date, session_type, person_name FROM daily_activity ORDER BY daily_activity_id DESC LIMIT 10;")
for row in cursor.fetchall():
    print(row)

conn.close()