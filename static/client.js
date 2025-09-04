// Simplified Chat Client JavaScript
class ChatClient {
    constructor() {
        this.ws = null;
        this.username = localStorage.getItem("chat_username") || null;
        this.mediaRecorder = null;
        this.chunks = [];
        this.isRecording = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        
        this.init();
    }
    
    $(id) {
        return document.getElementById(id);
    }
    
    init() {
        this.bindEvents();
        if (this.username) {
            this.$("username").value = this.username;
            this.showChat();
            this.setupWS();
        } else {
            this.showLogin();
        }
    }
    
    showLogin() {
        this.$("login").style.display = "block";
        this.$("chat").style.display = "none";
    }
    
    showChat() {
        this.$("login").style.display = "none";
        this.$("chat").style.display = "block";
        this.$("me").innerText = "You: " + this.username;
    }
    
    isImageFile(filename) {
        const imageExtensions = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'];
        const ext = filename.split('.').pop().toLowerCase();
        return imageExtensions.includes(ext);
    }
    
    async postJSON(url, obj) {
        try {
            const res = await fetch(url, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(obj)
            });
            return await res.json();
        } catch (error) {
            console.error("API Error:", error);
            return {ok: false, error: "Connection error"};
        }
    }
    
    async setupWS() {
        if (this.ws) {
            this.ws.close();
        }
        
        const protocol = location.protocol === "https:" ? "wss://" : "ws://";
        this.ws = new WebSocket(protocol + location.host + "/ws");
        this.ws.binaryType = "arraybuffer";

        this.ws.addEventListener("open", () => {
            console.log("WebSocket connected");
            this.reconnectAttempts = 0;
            this.ws.send(JSON.stringify({type: "auth", username: this.username}));
            this.showStatus("Connected", "success");
        });

        this.ws.addEventListener("message", async (e) => {
            if (typeof e.data === "string") {
                try {
                    const j = JSON.parse(e.data);
                    this.handleWSMessage(j);
                } catch (err) {
                    console.error("Invalid JSON:", err);
                }
            }
        });

        this.ws.addEventListener("close", () => {
            console.log("WebSocket closed");
            this.showStatus("Disconnected", "error");
            
            if (this.username && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                console.log(`Reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
                setTimeout(() => {
                    this.setupWS();
                }, 3000);
            }
        });

        this.ws.addEventListener("error", (error) => {
            console.error("WebSocket error:", error);
            this.showStatus("Connection error", "error");
        });
    }
    
    showStatus(message, type = "info") {
        const statusEl = this.$("status");
        if (statusEl) {
            statusEl.textContent = message;
            statusEl.className = `status ${type}`;
            setTimeout(() => {
                statusEl.textContent = "";
                statusEl.className = "status";
            }, 3000);
        }
    }
    
    async handleWSMessage(msg) {
        switch (msg.type) {
            case "auth_ok":
                console.log("Authentication successful");
                this.showStatus("Login successful", "success");
                break;
                
            case "join":
                this.renderSystemMessage(`${msg.username} joined the chat`);
                break;
                
            case "leave":
                this.renderSystemMessage(`${msg.username} left the chat`);
                break;
                
            case "message":
                this.renderMessage(msg);
                break;
        }
    }
    
    renderSystemMessage(text) {
        const wrap = document.createElement("div");
        wrap.className = "system";
        wrap.innerHTML = `<b>${text}</b>`;
        this.$("messages").appendChild(wrap);
        this.scrollToBottom();
    }
    
    renderMessage(msg) {
        const wrap = document.createElement("div");
        wrap.className = "message";
        
        if (msg.sender === this.username) {
            wrap.classList.add("me");
        } else {
            wrap.classList.add("other");
        }

        const meta = document.createElement("div");
        meta.className = "meta";
        meta.innerText = `${msg.sender}`;
        wrap.appendChild(meta);

        if (msg.mtype === "text") {
            const textDiv = document.createElement("div");
            textDiv.className = "text";
            textDiv.innerText = msg.content;
            wrap.appendChild(textDiv);
            
        } else if (msg.mtype === "file" || msg.mtype === "image") {
            const a = document.createElement("a");
            a.className = "file";
            a.href = "/uploads/" + msg.content;
            a.target = "_blank";
            a.innerText = `📎 ${msg.filename || msg.content}`;
            wrap.appendChild(a);
            
            // Show image preview if it's an image
            if (msg.mtype === "image" || (msg.filename && this.isImageFile(msg.filename))) {
                const img = document.createElement("img");
                img.src = "/uploads/" + msg.content;
                img.style.maxWidth = "280px";
                img.style.display = "block";
                img.style.marginTop = "4px";
                img.style.borderRadius = "8px";
                img.onerror = () => {
                    img.style.display = "none";
                };
                wrap.appendChild(img);
            }
            
        } else if (msg.mtype === "voice") {
            const audioDiv = document.createElement("div");
            audioDiv.innerHTML = `🎵 Voice message`;
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.src = "/uploads/" + msg.content;
            audio.style.marginTop = "4px";
            audio.style.width = "100%";
            audio.style.maxWidth = "280px";
            wrap.appendChild(audioDiv);
            wrap.appendChild(audio);
        }

        this.$("messages").appendChild(wrap);
        this.scrollToBottom();
    }
    
    scrollToBottom() {
        const messages = this.$("messages");
        messages.scrollTop = messages.scrollHeight;
    }
    
    sendText() {
        const txt = this.$("textInput").value.trim();
        if (!txt || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        
        this.ws.send(JSON.stringify({type: "text", text: txt}));
        this.$("textInput").value = "";
    }
    
    async sendFile() {
        const fileInput = this.$("fileInput");
        if (!fileInput.files || fileInput.files.length === 0) {
            alert("Please select a file");
            return;
        }
        
        const file = fileInput.files[0];
        
        // Check file size (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
            alert("File too large! Max 10MB");
            return;
        }
        
        this.showStatus("Sending file...", "info");
        
        const arrayBuffer = await file.arrayBuffer();
        
        const meta = { 
            filename: file.name, 
            sender: this.username,
            mtype: this.isImageFile(file.name) ? "image" : "file"
        };
        
        const metaBytes = new TextEncoder().encode(JSON.stringify(meta));
        const header = new ArrayBuffer(4);
        new DataView(header).setUint32(0, metaBytes.length, false);
        
        const total = new Uint8Array(4 + metaBytes.length + arrayBuffer.byteLength);
        total.set(new Uint8Array(header), 0);
        total.set(new Uint8Array(metaBytes), 4);
        total.set(new Uint8Array(arrayBuffer), 4 + metaBytes.length);

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(total.buffer);
            fileInput.value = "";
            this.showStatus("File sent", "success");
        } else {
            alert("WebSocket not connected");
        }
    }
    
    // Voice recording functions
    async toggleRecording() {
        if (!this.isRecording) {
            await this.startRecording();
        } else {
            this.stopRecording();
        }
    }
    
    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({audio: true});
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });
            this.chunks = [];
            
            this.mediaRecorder.ondataavailable = e => this.chunks.push(e.data);
            this.mediaRecorder.onstop = async () => {
                const blob = new Blob(this.chunks, {type: "audio/webm"});
                await this.sendVoiceMessage(blob);
                stream.getTracks().forEach(track => track.stop());
            };
            
            this.mediaRecorder.start();
            this.isRecording = true;
            this.$("recBtn").innerText = "⏹️ Stop Recording";
            this.$("recStatus").innerText = "Recording...";
            this.showStatus("Recording audio", "info");
            
        } catch (error) {
            console.error("Error starting recording:", error);
            alert("Cannot access microphone");
            this.showStatus("Microphone error", "error");
        }
    }
    
    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state === "recording") {
            this.mediaRecorder.stop();
            this.isRecording = false;
            this.$("recBtn").innerText = "🎙️ Record";
            this.$("recStatus").innerText = "";
            this.showStatus("Recording stopped", "success");
        }
    }
    
    async sendVoiceMessage(blob) {
        const buffer = await blob.arrayBuffer();
        const meta = {
            filename: `voice_${Date.now()}.webm`,
            sender: this.username,
            mtype: "voice"
        };
        
        const metaBytes = new TextEncoder().encode(JSON.stringify(meta));
        const header = new ArrayBuffer(4);
        new DataView(header).setUint32(0, metaBytes.length, false);
        
        const total = new Uint8Array(4 + metaBytes.length + buffer.byteLength);
        total.set(new Uint8Array(header), 0);
        total.set(new Uint8Array(metaBytes), 4);
        total.set(new Uint8Array(buffer), 4 + metaBytes.length);
        
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(total.buffer);
            this.showStatus("Voice message sent", "success");
        }
    }
    
    handleTextKeyPress(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendText();
        }
    }
    
    // Event binding
    bindEvents() {
        // Login/Register events
        this.$("btnRegister").addEventListener("click", async () => {
            const u = this.$("username").value.trim();
            const p = this.$("password").value;
            if (!u || !p) {
                this.$("loginMsg").innerText = "Enter username/password";
                return;
            }
            
            const r = await this.postJSON("/register", {username: u, password: p});
            this.$("loginMsg").innerText = r.ok ? 
                "Registration successful. You can now login." : 
                ("Error: " + r.error);
        });

        this.$("btnLogin").addEventListener("click", async () => {
            const u = this.$("username").value.trim();
            const p = this.$("password").value;
            if (!u || !p) {
                this.$("loginMsg").innerText = "Enter username/password";
                return;
            }
            
            const r = await this.postJSON("/login", {username: u, password: p});
            if (r.ok) {
                this.username = u;
                localStorage.setItem("chat_username", this.username);
                this.showChat();
                await this.setupWS();
            } else {
                this.$("loginMsg").innerText = "Error: " + r.error;
            }
        });

        this.$("btnLogout").addEventListener("click", () => {
            localStorage.removeItem("chat_username");
            this.username = null;
            if (this.ws) this.ws.close();
            this.showLogin();
            this.$("loginMsg").innerText = "";
            this.$("messages").innerHTML = "";
        });

        // Chat events
        this.$("sendText").addEventListener("click", () => this.sendText());
        this.$("sendFile").addEventListener("click", () => this.sendFile());
        
        // Only add voice recording if elements exist
        if (this.$("recBtn")) {
            this.$("recBtn").addEventListener("click", () => this.toggleRecording());
        }
        
        // Keyboard events
        this.$("textInput").addEventListener("keypress", (e) => this.handleTextKeyPress(e));
        this.$("password").addEventListener("keypress", (e) => {
            if (e.key === 'Enter') {
                this.$("btnLogin").click();
            }
        });
    }
}

// Initialize when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
    window.chatClient = new ChatClient();
});