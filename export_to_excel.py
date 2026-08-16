import os
import sqlite3
import pandas as pd

# Define paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'daily_sync.db')
OUTPUT_FILE = os.path.join(BASE_DIR, 'daily_sync_export.xlsx')

def export_db_to_excel():
    conn = sqlite3.connect(DATABASE)
    
    tables = ['category_lookup', 'activity_lookup', 'daily_activity']
    
    # Write each table to a separate sheet in the same Excel file
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        for table in tables:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            df.to_excel(writer, sheet_name=table, index=False)
            print(f"Exported {len(df)} rows from '{table}'")

    conn.close()
    print(f"\nSuccessfully exported all tables to: {OUTPUT_FILE}")

if __name__ == '__main__':
    export_db_to_excel()