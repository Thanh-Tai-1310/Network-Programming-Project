import asyncio
import json
import sqlite3
import hashlib
from aiohttp import web, WSMsgType
from pathlib import Path

ROOT = Path(__file__).parent
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DB_PATH = ROOT / "chat.db"

def get_conn():
    return sqlite3.connect(DB_PATH)

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()

clients = set()  # set of (ws, username)

async def broadcast_json(obj, exclude_ws=None):
    data = json.dumps(obj)
    for ws, _ in list(clients):
        if ws.closed:
            clients.discard((ws, _))
            continue
        if ws is exclude_ws:
            continue
        try:
            await ws.send_str(data)
        except:
            clients.discard((ws, _))

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
    except sqlite3.IntegrityError:
        conn.close()
        return web.json_response({"ok": False, "error": "Username đã tồn tại"})
    conn.close()
    return web.json_response({"ok": True})

async def login(request):
    data = await request.json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
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
    ws = web.WebSocketResponse(max_msg_size=0)
    await ws.prepare(request)

    username = None
    clients.add((ws, None))
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    j = json.loads(msg.data)
                except:
                    continue
                t = j.get("type")

                if t == "auth":
                    username = j.get("username")
                    clients.discard((ws, None))
                    clients.add((ws, username))
                    await ws.send_str(json.dumps({"type":"auth_ok", "username": username}))
                    await broadcast_json({"type": "join", "username": username})

                elif t == "text":
                    text = j.get("text","")
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute("INSERT INTO messages (sender, type, content) VALUES (?, ?, ?)",
                                (username or "anon", "text", text))
                    conn.commit()
                    conn.close()
                    await broadcast_json({"type":"message","sender": username or "anon", "mtype":"text", "content": text})

                # --- Call signaling ---
                elif t in ["call-invite", "call-accept", "call-reject", "call-end"]:
                    j["from"] = username or "anon"
                    await broadcast_json(j)

                # --- WebRTC signaling ---
                elif t == "webrtc-offer":
                    await broadcast_json({"type":"webrtc-offer","from": username or "anon","offer": j.get("offer")}, exclude_ws=ws)
                elif t == "webrtc-answer":
                    await broadcast_json({"type":"webrtc-answer","from": username or "anon","answer": j.get("answer")}, exclude_ws=ws)
                elif t == "webrtc-ice":
                    await broadcast_json({"type":"webrtc-ice","from": username or "anon","candidate": j.get("candidate")}, exclude_ws=ws)

            elif msg.type == WSMsgType.BINARY:
                # Voice/file upload
                data = msg.data
                if len(data) < 4:
                    continue
                meta_len = int.from_bytes(data[0:4], 'big')
                if len(data) < 4 + meta_len:
                    continue
                meta_json = data[4:4+meta_len].decode('utf-8')
                meta = json.loads(meta_json)

                filename = meta.get("filename", "file.bin")
                sender = meta.get("sender", username or "anon")
                declared_type = meta.get("mtype", "file")

                safe_name = f"{int(asyncio.get_event_loop().time()*1000)}_{Path(filename).name}"
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
                    "type": "message",
                    "sender": sender,
                    "mtype": declared_type,
                    "content": safe_name,
                    "filename": filename
                })

            elif msg.type == WSMsgType.ERROR:
                print('ws connection closed with exception %s' % ws.exception())
    finally:
        clients.discard((ws, username))
        if username:
            await broadcast_json({"type": "leave", "username": username})
        await ws.close()
    return ws

app = web.Application()
app.router.add_static('/static/', path=ROOT / 'static', show_index=True)
app.router.add_static('/uploads/', path=UPLOAD_DIR, show_index=False)

app.router.add_post('/register', register)
app.router.add_post('/login', login)
app.router.add_get('/ws', websocket_handler)

async def index(request):
    return web.FileResponse(ROOT / 'static' / 'index.html')

app.router.add_get('/', index)

if __name__ == '__main__':
    print("Server running at http://localhost:8080")
    web.run_app(app, host='0.0.0.0', port=8080)
