import os

DB_NAME = "temple_sync.db"

def wipe_database():
    db_path = os.path.join(os.path.dirname(__file__), DB_NAME)
    
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"-> Successfully deleted '{DB_NAME}'.")
    else:
        print(f"-> File '{DB_NAME}' does not exist. Nothing to wipe.")

if __name__ == '__main__':
    wipe_database()