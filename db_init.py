import sqlite3
from pathlib import Path

DB = Path("chat.db")

def init_db():
    """Khởi tạo database với schema đầy đủ"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # Tạo bảng users với đầy đủ thông tin
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        is_active BOOLEAN DEFAULT 1
    );
    """)
    
    # Tạo bảng messages với nhiều loại tin nhắn
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('text', 'file', 'image', 'voice', 'system')),
        content TEXT NOT NULL,
        filename TEXT,
        file_size INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender) REFERENCES users(username)
    );
    """)
    
    # Tạo bảng sessions để track user sessions (tùy chọn)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        session_end TIMESTAMP,
        ip_address TEXT,
        user_agent TEXT,
        FOREIGN KEY (username) REFERENCES users(username)
    );
    """)
    
    # Tạo index để tối ưu hiệu suất
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
    
    conn.commit()
    
    # Kiểm tra số lượng bảng đã tạo
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()
    
    conn.close()
    
    print("=" * 50)
    print("✅ DATABASE INITIALIZED SUCCESSFULLY")
    print("=" * 50)
    print(f"📍 Database location: {DB.absolute()}")
    print(f"📊 Tables created: {len(tables)}")
    for table in tables:
        print(f"   - {table[0]}")
    print("=" * 50)

def reset_db():
    """Xóa và tạo lại database (cẩn thận!)"""
    if DB.exists():
        DB.unlink()
        print(f"🗑️  Deleted old database: {DB}")
    init_db()

def check_db():
    """Kiểm tra trạng thái database"""
    if not DB.exists():
        print(f"❌ Database not found: {DB}")
        return False
    
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    # Đếm users
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    
    # Đếm messages
    cur.execute("SELECT COUNT(*) FROM messages")
    message_count = cur.fetchone()[0]
    
    # Lấy message gần nhất
    cur.execute("SELECT sender, type, created_at FROM messages ORDER BY created_at DESC LIMIT 1")
    latest = cur.fetchone()
    
    conn.close()
    
    print("=" * 50)
    print("📊 DATABASE STATUS")
    print("=" * 50)
    print(f"📍 Location: {DB.absolute()}")
    print(f"👥 Total users: {user_count}")
    print(f"💬 Total messages: {message_count}")
    if latest:
        print(f"🕒 Latest message: {latest[0]} ({latest[1]}) at {latest[2]}")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "reset":
            confirm = input("⚠️  This will DELETE all data. Continue? (yes/no): ")
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