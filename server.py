import asyncio
import mimetypes
import json
import sqlite3
import hashlib
from aiohttp import web, WSMsgType
from pathlib import Path

ROOT = Path(__file__).parent
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Tạo thư mục static nếu chưa có
STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)

DB_PATH = ROOT / "chat.db"

def init_db():
    """Khởi tạo database schema"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Tạo bảng users
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tạo bảng messages
    cur.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")

def get_conn():
    return sqlite3.connect(DB_PATH)

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()

def is_image_file(filename):
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
    return Path(filename).suffix.lower() in image_extensions

def is_audio_file(filename):
    audio_extensions = {'.mp3', '.wav', '.webm', '.ogg', '.m4a', '.aac'}
    return Path(filename).suffix.lower() in audio_extensions

clients = set()  # set of (ws, username)

async def broadcast_json(obj, exclude_ws=None):
    """Broadcast JSON message to all connected clients"""
    data = json.dumps(obj, ensure_ascii=False)
    disconnected = []
    
    for ws, username_client in list(clients):
        if ws.closed:
            disconnected.append((ws, username_client))
            continue
        if ws is exclude_ws:
            continue
        try:
            await ws.send_str(data)
        except Exception as e:
            print(f"Error sending to client {username_client}: {e}")
            disconnected.append((ws, username_client))
    
    # Remove disconnected clients
    for client in disconnected:
        clients.discard(client)

async def register(request):
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        
        if not username or not password:
            return web.json_response({"ok": False, "error": "Chưa nhập username/password"})
        
        if len(username) < 3:
            return web.json_response({"ok": False, "error": "Username phải có ít nhất 3 ký tự"})
        
        if len(password) < 6:
            return web.json_response({"ok": False, "error": "Password phải có ít nhất 6 ký tự"})
        
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (username, hash_password(password)))
            conn.commit()
            print(f"New user registered: {username}")
            return web.json_response({"ok": True})
        except sqlite3.IntegrityError:
            return web.json_response({"ok": False, "error": "Username đã tồn tại"})
        finally:
            conn.close()
            
    except Exception as e:
        print(f"Register error: {e}")
        return web.json_response({"ok": False, "error": "Lỗi server"})

async def login(request):
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        
        if not username or not password:
            return web.json_response({"ok": False, "error": "Chưa nhập username/password"})
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return web.json_response({"ok": False, "error": "Không tìm thấy user"})
        
        if row[0] != hash_password(password):
            return web.json_response({"ok": False, "error": "Sai password"})
        
        print(f"User logged in: {username}")
        return web.json_response({"ok": True})
        
    except Exception as e:
        print(f"Login error: {e}")
        return web.json_response({"ok": False, "error": "Lỗi server"})

async def websocket_handler(request):
    ws = web.WebSocketResponse(max_msg_size=16 * 1024 * 1024)  # 16MB max
    await ws.prepare(request)

    username = None
    clients.add((ws, None))
    
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    j = json.loads(msg.data)
                except json.JSONDecodeError:
                    print("Invalid JSON received")
                    continue
                
                msg_type = j.get("type")

                if msg_type == "auth":
                    username = j.get("username", "").strip()
                    if username:
                        # Remove old entry and add new one with username
                        clients.discard((ws, None))
                        clients.add((ws, username))
                        await ws.send_str(json.dumps({
                            "type": "auth_ok", 
                            "username": username
                        }, ensure_ascii=False))
                        await broadcast_json({
                            "type": "join", 
                            "username": username
                        }, exclude_ws=ws)
                        print(f"User {username} connected")

                elif msg_type == "text" and username:
                    text = j.get("text", "").strip()
                    if text:
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute("INSERT INTO messages (sender, type, content) VALUES (?, ?, ?)",
                                    (username, "text", text))
                        conn.commit()
                        conn.close()
                        
                        await broadcast_json({
                            "type": "message",
                            "sender": username,
                            "mtype": "text",
                            "content": text
                        })

                # Call signaling
                elif msg_type in ["call-invite", "call-accept", "call-reject", "call-end"]:
                    j["from"] = username or "anon"
                    await broadcast_json(j, exclude_ws=ws)

                # WebRTC signaling
                elif msg_type == "webrtc-offer":
                    await broadcast_json({
                        "type": "webrtc-offer",
                        "from": username or "anon",
                        "offer": j.get("offer")
                    }, exclude_ws=ws)
                    
                elif msg_type == "webrtc-answer":
                    await broadcast_json({
                        "type": "webrtc-answer",
                        "from": username or "anon",
                        "answer": j.get("answer")
                    }, exclude_ws=ws)
                    
                elif msg_type == "webrtc-ice":
                    await broadcast_json({
                        "type": "webrtc-ice",
                        "from": username or "anon",
                        "candidate": j.get("candidate")
                    }, exclude_ws=ws)

            elif msg.type == WSMsgType.BINARY:
                # File/voice upload
                data = msg.data
                if len(data) < 4:
                    continue
                
                try:
                    meta_len = int.from_bytes(data[0:4], 'big')
                    if len(data) < 4 + meta_len:
                        continue
                    
                    meta_json = data[4:4+meta_len].decode('utf-8')
                    meta = json.loads(meta_json)

                    filename = meta.get("filename", "file.bin")
                    sender = meta.get("sender", username or "anon")
                    declared_type = meta.get("mtype", "file")
                    
                    # Tự động nhận diện loại file
                    if declared_type == "file":
                        if is_image_file(filename):
                            declared_type = "image"
                        elif is_audio_file(filename):
                            declared_type = "voice"

                    # Tạo tên file an toàn
                    timestamp = int(asyncio.get_event_loop().time() * 1000)
                    safe_filename = "".join(c for c in Path(filename).name if c.isalnum() or c in '._-')
                    safe_name = f"{timestamp}_{safe_filename}"
                    save_path = UPLOAD_DIR / safe_name

                    # Lưu file
                    with open(save_path, "wb") as f:
                        f.write(data[4+meta_len:])

                    # Lưu vào database
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute("INSERT INTO messages (sender, type, content) VALUES (?, ?, ?)",
                                (sender, declared_type, safe_name))
                    conn.commit()
                    conn.close()

                    # Broadcast message
                    await broadcast_json({
                        "type": "message",
                        "sender": sender,
                        "mtype": declared_type,
                        "content": safe_name,
                        "filename": filename
                    })
                    
                    print(f"File uploaded: {filename} by {sender} ({declared_type})")
                    
                except Exception as e:
                    print(f"Error processing binary message: {e}")

            elif msg.type == WSMsgType.ERROR:
                print(f'WebSocket connection closed with exception: {ws.exception()}')

    except Exception as e:
        print(f"WebSocket handler error: {e}")
    finally:
        # Clean up
        clients.discard((ws, username))
        clients.discard((ws, None))
        if username:
            await broadcast_json({"type": "leave", "username": username})
            print(f"User {username} disconnected")
        
        if not ws.closed:
            await ws.close()

    return ws

async def get_message_history(request):
    """API endpoint to get message history"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT sender, type, content, created_at 
            FROM messages 
            ORDER BY created_at DESC 
            LIMIT 50
        """)
        rows = cur.fetchall()
        conn.close()
        
        messages = []
        for row in rows:
            messages.append({
                "sender": row[0],
                "type": row[1], 
                "content": row[2],
                "created_at": row[3]
            })
        
        return web.json_response({"ok": True, "messages": messages[::-1]})  # Reverse to chronological order
    except Exception as e:
        print(f"Get history error: {e}")
        return web.json_response({"ok": False, "error": "Lỗi server"})

async def init_app():
    """Initialize the application"""
    init_db()
    
    app = web.Application()
    
    # Static file routes
    app.router.add_static('/uploads', path=str(UPLOAD_DIR), name='uploads')
    app.router.add_static('/static', path=str(STATIC_DIR), name='static')
    
    # API routes
    app.router.add_post('/register', register)
    app.router.add_post('/login', login)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_get('/api/history', get_message_history)
    
    # Serve index.html at root
    async def index(request):
        index_path = STATIC_DIR / 'index.html'
        if index_path.exists():
            return web.FileResponse(index_path)
        else:
            return web.Response(text="index.html not found in static directory. Please create static/index.html", status=404)
    
    app.router.add_get('/', index)
    
    return app

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 INITIALIZING CHAT SERVER")
    print("=" * 50)
    print(f"📁 Upload directory: {UPLOAD_DIR.absolute()}")
    print(f"📁 Static directory: {STATIC_DIR.absolute()}")
    print(f"💾 Database: {DB_PATH.absolute()}")
    
    app = asyncio.get_event_loop().run_until_complete(init_app())
    
    print("=" * 50)
    print("✅ SERVER READY")
    print("🌐 Access: http://localhost:8080")
    print("📝 Create static/index.html to get started")
    print("=" * 50)
    
    web.run_app(app, host='0.0.0.0', port=8080)