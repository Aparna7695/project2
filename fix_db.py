import sqlite3
import os

DATABASE = 'database.db'

def reset_db():
    if os.path.exists(DATABASE):
        print(f"Removing existing database: {DATABASE}")
        os.remove(DATABASE)
    
    # Simple way to re-init is to import init_db from app and call it
    # But since we want to be explicit here:
    conn = sqlite3.connect(DATABASE)
    print("Recreating all tables...")
    conn.executescript('''
    CREATE TABLE user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_active_account INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    );

    CREATE TABLE "order" (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        crop_name TEXT NOT NULL,
        price TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        address TEXT NOT NULL,
        payment_method TEXT,
        status TEXT NOT NULL DEFAULT 'Pending',
        FOREIGN KEY (user_id) REFERENCES user (id)
    );
    ''')
    conn.commit()
    conn.close()
    print("Database reset successfully with raw SQLite!")

if __name__ == '__main__':
    reset_db()
