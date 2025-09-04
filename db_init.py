import sqlite3
from pathlib import Path

DB = Path("chat.db")

def init_db():
    """Initialize database with basic schema"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # Create users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Create messages table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('text', 'file', 'image', 'voice')),
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Create indexes for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);")
    
    conn.commit()
    
    # Check number of tables created
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()
    
    conn.close()
    
    print("=" * 40)
    print("✅ DATABASE INITIALIZED")
    print("=" * 40)
    print(f"📍 Database: {DB.absolute()}")
    print(f"📊 Tables: {len(tables)}")
    for table in tables:
        print(f"   - {table[0]}")
    print("=" * 40)

def reset_db():
    """Delete and recreate database (careful!)"""
    if DB.exists():
        DB.unlink()
        print(f"🗑️ Deleted old database: {DB}")
    init_db()

def check_db():
    """Check database status"""
    if not DB.exists():
        print(f"❌ Database not found: {DB}")
        return False
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # Count users
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    
    # Count messages
    cur.execute("SELECT COUNT(*) FROM messages")
    message_count = cur.fetchone()[0]
    
    # Get latest message
    cur.execute("SELECT sender, type, created_at FROM messages ORDER BY created_at DESC LIMIT 1")
    latest = cur.fetchone()
    
    conn.close()
    
    print("=" * 40)
    print("📊 DATABASE STATUS")
    print("=" * 40)
    print(f"📍 Location: {DB.absolute()}")
    print(f"👥 Users: {user_count}")
    print(f"💬 Messages: {message_count}")
    if latest:
        print(f"🕒 Latest: {latest[0]} ({latest[1]}) at {latest[2]}")
    print("=" * 40)
    
    return True

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "reset":
            confirm = input("⚠️ This will DELETE all data. Continue? (yes/no): ")
            if confirm.lower() == "yes":
                reset_db()
            else:
                print("❌ Cancelled")
                
        elif command == "check":
            check_db()
            
        elif command == "help":
            print("Available commands:")
            print("  python db_init.py        - Initialize database")
            print("  python db_init.py reset  - Reset database (DELETE ALL)")  
            print("  python db_init.py check  - Check database status")
            print("  python db_init.py help   - Show this help")
            
        else:
            print(f"Unknown command: {command}")
            print("Use 'python db_init.py help' for available commands")
    else:
        init_db()