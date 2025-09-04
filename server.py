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

def get_conn():
    return sqlite3.connect(DB_PATH)

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()

def is_image_file(filename):
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
    return Path(filename).suffix.lower() in image_extensions

clients = set()  # set of (ws, username)

async def broadcast_json(obj, exclude_ws=None):
    data = json.dumps(obj)
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
            print(f"Error sending to client: {e}")
            disconnected.append((ws, username_client))
    
    # Remove disconnected clients
    for client in disconnected:
        clients.discard(client)

async def register(request):
    data = await request.json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return web.json_response({"ok": False, "error": "Chưa nhập username/password"})
    
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, hash_password(password)))
        conn.commit()
        conn.close()
        return web.json_response({"ok": True})
    except sqlite3.IntegrityError:
        conn.close()
        return web.json_response({"ok": False, "error": "Username đã tồn tại"})

async def login(request):
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
    
    return web.json_response({"ok": True})

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
                    continue
                
                msg_type = j.get("type")

                if msg_type == "auth":
                    username = j.get("username", "").strip()
                    if username:
                        # Remove old entry and add new one with username
                        clients.discard((ws, None))
                        clients.add((ws, username))
                        await ws.send_str(json.dumps({"type": "auth_ok", "username": username}))
                        await broadcast_json({"type": "join", "username": username}, exclude_ws=ws)

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
                    if declared_type == "file" and is_image_file(filename):
                        declared_type = "image"

                    # Tạo tên file an toàn
                    timestamp = int(asyncio.get_event_loop().time() * 1000)
                    safe_filename = Path(filename).name
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
        
        if not ws.closed:
            await ws.close()

    return ws

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
    
    # Serve index.html at root
    async def index(request):
        index_path = STATIC_DIR / 'index.html'
        if index_path.exists():
            return web.FileResponse(index_path)
        else:
            return web.Response(text="index.html not found in static directory", status=404)
    
    app.router.add_get('/', index)
    
    return app

if __name__ == '__main__':
    print("Initializing chat server...")
    print(f"Upload directory: {UPLOAD_DIR}")
    print(f"Static directory: {STATIC_DIR}")
    print(f"Database: {DB_PATH}")
    
    app = asyncio.get_event_loop().run_until_complete(init_app())
    print("Server running at http://localhost:8080")
    web.run_app(app, host='0.0.0.0', port=8080)