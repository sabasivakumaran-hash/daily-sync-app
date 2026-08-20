import sqlite3
import os
from werkzeug.security import generate_password_hash

# 1. Use the exact same path logic as app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'daily_sync.db')

def setup_users():
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # 2. Create users table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. Seed default users (e.g., admin and standard user)
    # Customize usernames/passwords as needed
    default_users = [
        ('admin', generate_password_hash('admin123'), 'admin'),
        ('user', generate_password_hash('user123'), 'user')
    ]

    for username, pwd_hash, role in default_users:
        cursor.execute("""
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO NOTHING;
        """, (username, pwd_hash, role))

    conn.commit()
    conn.close()
    print("Users table successfully created and seeded!")

if __name__ == '__main__':
    setup_users()