import asyncio
import json
import sqlite3
import hashlib
from aiohttp import web, WSMsgType
from pathlib import Path

ROOT = Path(__file__).parent
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR = ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
DB_PATH = ROOT / "chat.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        type TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()
    print("Database initialized")

def get_conn():
    return sqlite3.connect(DB_PATH)

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()

def is_image_file(filename):
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}
    return Path(filename).suffix.lower() in image_extensions

clients = set()

async def broadcast_json(obj, exclude_ws=None):
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
        except:
            disconnected.append((ws, username_client))
    for client in disconnected:
        clients.discard(client)

async def register(request):
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not username or not password:
            return web.json_response({"ok": False, "error": "Missing username/password"})
        if len(username) < 3:
            return web.json_response({"ok": False, "error": "Username must be at least 3 characters"})
        if len(password) < 6:
            return web.json_response({"ok": False, "error": "Password must be at least 6 characters"})
        
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (username, hash_password(password)))
            conn.commit()
            return web.json_response({"ok": True})
        except sqlite3.IntegrityError:
            return web.json_response({"ok": False, "error": "Username already exists"})
        finally:
            conn.close()
    except Exception as e:
        print(f"Register error: {e}")
        return web.json_response({"ok": False, "error": "Server error"})

async def login(request):
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not username or not password:
            return web.json_response({"ok": False, "error": "Missing username/password"})
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        conn.close()
        
        if not row or row[0] != hash_password(password):
            return web.json_response({"ok": False, "error": "Invalid username or password"})
        
        return web.json_response({"ok": True})
    except Exception as e:
        print(f"Login error: {e}")
        return web.json_response({"ok": False, "error": "Server error"})

async def websocket_handler(request):
    ws = web.WebSocketResponse(max_msg_size=16 * 1024 * 1024)
    await ws.prepare(request)
    username = None
    clients.add((ws, None))
    
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    j = json.loads(msg.data)
                    msg_type = j.get("type")

                    if msg_type == "auth":
                        username = j.get("username", "").strip()
                        if username:
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
                                "type": "message", "sender": username, "mtype": "text", "content": text
                            })
                except json.JSONDecodeError:
                    pass

            elif msg.type == WSMsgType.BINARY:
                data = msg.data
                if len(data) >= 4:
                    try:
                        meta_len = int.from_bytes(data[0:4], 'big')
                        if len(data) >= 4 + meta_len:
                            meta_json = data[4:4+meta_len].decode('utf-8')
                            meta = json.loads(meta_json)
                            filename = meta.get("filename", "file.bin")
                            sender = meta.get("sender", username or "anon")
                            declared_type = meta.get("mtype", "file")
                            
                            if declared_type == "file" and is_image_file(filename):
                                declared_type = "image"

                            timestamp = int(asyncio.get_event_loop().time() * 1000)
                            safe_name = f"{timestamp}_{Path(filename).name}"
                            save_path = UPLOAD_DIR / safe_name

                            with open(save_path, "wb") as f:
                                f.write(data[4+meta_len:])

                            conn = get_conn()
                            cur = conn.cursor()
                            cur.execute("INSERT INTO messages (sender, type, content) VALUES (?, ?, ?)",
                                        (sender, declared_type, safe_name))
                            conn.commit()
                            conn.close()

                            await broadcast_json({
                                "type": "message", "sender": sender, "mtype": declared_type,
                                "content": safe_name, "filename": filename
                            })
                    except Exception as e:
                        print(f"Binary message error: {e}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        clients.discard((ws, username))
        clients.discard((ws, None))
        if username:
            await broadcast_json({"type": "leave", "username": username})
        if not ws.closed:
            await ws.close()
    return ws

async def init_app():
    init_db()
    app = web.Application()
    app.router.add_static('/uploads', path=str(UPLOAD_DIR), name='uploads')
    app.router.add_static('/static', path=str(STATIC_DIR), name='static')
    app.router.add_post('/register', register)
    app.router.add_post('/login', login)
    app.router.add_get('/ws', websocket_handler)
    
    async def index(request):
        index_path = STATIC_DIR / 'index.html'
        if index_path.exists():
            return web.FileResponse(index_path)
        return web.Response(text="index.html not found", status=404)
    
    app.router.add_get('/', index)
    return app

if __name__ == '__main__':
    print("🚀 Starting Chat Server...")
    app = asyncio.get_event_loop().run_until_complete(init_app())
    print("✅ Server ready at http://localhost:8080")
    web.run_app(app, host='0.0.0.0', port=8080)