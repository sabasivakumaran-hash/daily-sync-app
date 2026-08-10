DROP TABLE IF EXISTS daily_activity;
DROP TABLE IF EXISTS activity_lookup;
DROP TABLE IF EXISTS category_lookup;

CREATE TABLE category_lookup (
    category_lookup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE,
    is_active INTEGER DEFAULT 1,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE activity_lookup (
    activity_lookup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_lookup_id INTEGER NOT NULL,
    activity_name TEXT NOT NULL UNIQUE,
    default_amount REAL DEFAULT 0.00,
    txn_type TEXT NOT NULL CHECK(txn_type IN ('INCOME', 'EXPENSE')),
    is_active INTEGER DEFAULT 1,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_lookup_id) REFERENCES category_lookup(category_lookup_id)
);

CREATE TABLE daily_activity (
    daily_activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_date TEXT NOT NULL,
    session_type TEXT DEFAULT 'AM',
    activity_lookup_id INTEGER NOT NULL,
    person_name TEXT,
    unit_price REAL DEFAULT 0.00,
    quantity INTEGER DEFAULT 1,
    total_amount REAL DEFAULT 0.00,
    payment_mode TEXT NOT NULL,
    remarks TEXT,
    is_active INTEGER DEFAULT 1,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (activity_lookup_id) REFERENCES activity_lookup(activity_lookup_id)
);
