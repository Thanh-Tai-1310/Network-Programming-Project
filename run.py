#!/usr/bin/env python3
"""
Simple setup and run script for Chat App
Auto-creates files and runs server
"""

import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check and install dependencies"""
    try:
        import aiohttp
        print("✅ aiohttp already installed")
        return True
    except ImportError:
        print("📦 Installing aiohttp...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp==3.8.5"])
            print("✅ aiohttp installed successfully")
            return True
        except subprocess.CalledProcessError:
            print("❌ Failed to install aiohttp")
            print("💡 Try: pip install aiohttp")
            return False

def create_directories():
    """Create necessary directories"""
    dirs = ["uploads", "static"]
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
        print(f"📁 Created directory: {dir_name}")

def check_files():
    """Check if required files exist"""
    required_files = {
        "server.py": "Main server file",
        "static/index.html": "Frontend HTML file", 
        "static/client.js": "Frontend JavaScript file",
        "db_init.py": "Database initialization script"
    }
    
    missing_files = []
    for file_path, description in required_files.items():
        if not Path(file_path).exists():
            missing_files.append((file_path, description))
    
    if missing_files:
        print("❌ Missing required files:")
        for file_path, description in missing_files:
            print(f"   - {file_path} ({description})")
        print("\n💡 Make sure all files are in the correct locations:")
        print("   server.py")
        print("   db_init.py") 
        print("   static/index.html")
        print("   static/client.js")
        return False
    
    print("✅ All required files found")
    return True

def init_database():
    """Initialize database"""
    try:
        from db_init import init_db
        init_db()
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

def main():
    """Main setup function"""
    print("=" * 50)
    print("🚀 CHAT APP SETUP")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        return False
    
    # Create directories
    create_directories()
    
    # Check files
    if not check_files():
        return False
    
    # Initialize database
    if not init_database():
        return False
    
    print("\n" + "=" * 50)
    print("✅ SETUP COMPLETE!")
    print("=" * 50)
    print("📋 FEATURES:")
    print("   ✅ User registration & login")
    print("   ✅ Real-time text messaging")
    print("   ✅ File & image sharing")
    print("   ✅ Voice message recording")
    print("   ✅ Responsive web design")
    print("   ✅ Auto-reconnect WebSocket")
    print("\n🏃 TO RUN:")
    print("   python server.py")
    print("\n🌐 THEN VISIT:")
    print("   http://localhost:8080")
    print("=" * 50)
    
    # Ask if user wants to run now
    try:
        run_now = input("\n🚀 Run server now? (y/N): ").lower().strip()
        if run_now in ['y', 'yes']:
            print("\n🔥 Starting server...")
            os.system("python server.py")
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    
    return True

if __name__ == "__main__":
    main()