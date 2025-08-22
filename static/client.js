let ws = null;
let username = localStorage.getItem("chat_username") || null;

const $ = id => document.getElementById(id);

function showLogin() {
  $("login").style.display = "block";
  $("chat").style.display = "none";
}
function showChat() {
  $("login").style.display = "none";
  $("chat").style.display = "block";
  $("me").innerText = "Bạn: " + username;
}

async function postJSON(url, obj){
  const res = await fetch(url, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(obj)
  });
  return res.json();
}

async function setupWS(){
  if(ws) ws.close();
  ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.binaryType = "arraybuffer";

  ws.addEventListener("open", () => {
    ws.send(JSON.stringify({type:"auth", username}));
  });

  ws.addEventListener("message", e => {
    if(typeof e.data === "string"){
      try{
        const j = JSON.parse(e.data);
        if(j.type === "auth_ok"){
          console.log("Auth OK");
        } else if(j.type === "message" || j.type === "join" || j.type === "leave"){
          renderMessage(j);
        }
      }catch(err){
        console.error("Invalid JSON", err);
      }
    }
  });

  ws.addEventListener("close", () => {
    console.log("ws closed");
  });
}

function renderMessage(msg){
  const wrap = document.createElement("div");

  // --- thông báo join ---
  if(msg.type === "join"){
    wrap.className = "system";
    wrap.innerHTML = `<b>${msg.username}</b> đã tham gia phòng`;
    $("messages").appendChild(wrap);
    $("messages").scrollTop = $("messages").scrollHeight;
    return;
  }

  // --- thông báo leave ---
  if(msg.type === "leave"){
    wrap.className = "system";
    wrap.innerHTML = `<b>${msg.username}</b> đã rời phòng`;
    $("messages").appendChild(wrap);
    $("messages").scrollTop = $("messages").scrollHeight;
    return;
  }

  // --- tin nhắn thường ---
  wrap.className = "message";
  if(msg.sender === username){
    wrap.classList.add("me");    // căn phải
  } else {
    wrap.classList.add("other"); // căn trái
  }

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.innerText = `${msg.sender}${msg.time ? " • " + msg.time : ""}`;
  wrap.appendChild(meta);

  if(msg.mtype === "text"){
    const t = document.createElement("div");
    t.className = "text";
    t.innerText = msg.content;
    wrap.appendChild(t);
  } else if(msg.mtype === "file"){
    const a = document.createElement("a");
    a.className = "file";
    a.href = "/uploads/" + msg.content;
    a.target = "_blank";
    a.innerText = `File: ${msg.filename || msg.content}`;
    const ext = (msg.filename || "").split('.').pop().toLowerCase();
    if(["png","jpg","jpeg","gif","webp"].includes(ext)){
      const img = document.createElement("img");
      img.src = a.href;
      img.style.maxWidth = "320px";
      img.style.display = "block";
      wrap.appendChild(img);
    }
    wrap.appendChild(a);
  }

  $("messages").appendChild(wrap);
  $("messages").scrollTop = $("messages").scrollHeight;
}

window.addEventListener("DOMContentLoaded", () => {
  $("btnRegister").addEventListener("click", async () => {
    const u = $("username").value.trim();
    const p = $("password").value;
    if(!u || !p){ $("loginMsg").innerText = "Nhập username/password"; return; }
    const r = await postJSON("/register", {username:u, password:p});
    $("loginMsg").innerText = r.ok ? "Đăng ký thành công. Bạn có thể đăng nhập." : ("Lỗi: " + r.error);
  });

  $("btnLogin").addEventListener("click", async () => {
    const u = $("username").value.trim();
    const p = $("password").value;
    if(!u || !p){ $("loginMsg").innerText = "Nhập username/password"; return; }
    const r = await postJSON("/login", {username:u, password:p});
    if(r.ok){
      username = u;
      localStorage.setItem("chat_username", username);
      showChat();
      await setupWS();
    } else {
      $("loginMsg").innerText = "Lỗi: " + r.error;
    }
  });

  $("btnLogout").addEventListener("click", () => {
    localStorage.removeItem("chat_username");
    username = null;
    if(ws) ws.close();
    showLogin();
  });

  $("sendText").addEventListener("click", () => {
    const txt = $("textInput").value.trim();
    if(!txt || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({type:"text", text: txt}));
    $("textInput").value = "";
  });

  $("sendFile").addEventListener("click", async () => {
    const fileInput = $("fileInput");
    if(!fileInput.files || fileInput.files.length === 0) return alert("Chọn file");
    const file = fileInput.files[0];
    const arrayBuffer = await file.arrayBuffer();
    const meta = { filename: file.name, sender: username };
    const metaBytes = new TextEncoder().encode(JSON.stringify(meta));
    const header = new ArrayBuffer(4);
    new DataView(header).setUint32(0, metaBytes.length, false);
    const total = new Uint8Array(4 + metaBytes.length + arrayBuffer.byteLength);
    total.set(new Uint8Array(header), 0);
    total.set(new Uint8Array(metaBytes), 4);
    total.set(new Uint8Array(arrayBuffer), 4 + metaBytes.length);

    if(ws && ws.readyState === WebSocket.OPEN){
      ws.send(total.buffer);
    } else {
      alert("WebSocket chưa kết nối");
    }
  });

  if(username){
    $("username").value = username;
    showChat();
    setupWS();
  } else {
    showLogin();
  }
});
