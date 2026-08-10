-- 1. CATEGORY LOOKUP (Rollup Master Table)
CREATE TABLE IF NOT EXISTS category_lookup (
    category_lookup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE,
    is_active INTEGER DEFAULT 1,
    created_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. ACTIVITY LOOKUP (Activity Master Table)
CREATE TABLE IF NOT EXISTS activity_lookup (
    activity_lookup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_lookup_id INTEGER NOT NULL,
    activity_name TEXT NOT NULL UNIQUE,
    default_amount REAL DEFAULT 0.00,
    txn_type TEXT NOT NULL CHECK(txn_type IN ('INCOME', 'EXPENSE')),
    is_active INTEGER DEFAULT 1,
    created_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_lookup_id) REFERENCES category_lookup(category_lookup_id)
);

-- 3. DAILY ACTIVITY (Operational Log)
CREATE TABLE IF NOT EXISTS daily_activity (
    daily_activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_date TEXT NOT NULL,         -- Stores YYYY-MM-DD
    session_type TEXT DEFAULT 'AM',  -- AM (Morning) or PM (Evening)
    activity_lookup_id INTEGER NOT NULL,
    person_name TEXT,               -- Devotee / Person Name
    unit_price REAL DEFAULT 0.00,
    quantity INTEGER DEFAULT 1,
    total_amount REAL DEFAULT 0.00,
    payment_mode TEXT NOT NULL,     -- Cash, Cheque, Card, e-Transfer
    remarks TEXT,                   -- Combined Receipt # and operational notes
    is_active INTEGER DEFAULT 1,    -- 1 = Active, 0 = Inactive / Void
    created_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (activity_lookup_id) REFERENCES activity_lookup(activity_lookup_id)
);