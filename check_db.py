import sqlite3

conn = sqlite3.connect('daily_sync.db')
cursor = conn.cursor()

tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
count = cursor.execute("SELECT COUNT(*) FROM daily_activity").fetchone()[0]

print(f"Tables: {tables}")
print(f"Total Activity Records: {count}")

conn.close()