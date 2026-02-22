import sqlite3
import os

DB_NAME = "secure_vote.db"

def get_db():
    """Returns a database connection."""
    conn = sqlite3.connect(DB_NAME)
    return conn

def init_db():
    """Initializes the database tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Voters Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aadhaar_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            face_encoding BLOB,
            has_voted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Votes Audit Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voter_id INTEGER,
            candidate TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(voter_id) REFERENCES voters(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully.")

if __name__ == "__main__":
    init_db()
