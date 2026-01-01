#!/usr/bin/env python3
"""
VISHAL AUTH SYSTEM PRO 2025
ALL BUTTONS WORKING - Inline Keyboard Fixed
"""

import os
import sys
import requests
import threading
import time
import json
import sqlite3
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import html
import logging
import atexit
from functools import lru_cache
from typing import Optional, Tuple, List, Dict, Any
import queue

# ============================================================================
# CONFIGURATION
# ============================================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Bot Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8504965473:AAE9dn_5_ZhEQKdekcgi3chIBHRsJNfC-Ms')
CHANNEL = os.environ.get('CHANNEL', '@Vishalxnetwork4')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', '@vishalxtg45')

# Parse Admin IDs
ADMIN_IDS = []
admin_ids_str = os.environ.get('ADMIN_IDS', '6493515910,6361764073')
for admin_id in admin_ids_str.split(','):
    admin_id = admin_id.strip()
    if admin_id.isdigit():
        ADMIN_IDS.append(int(admin_id))

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
PORT = int(os.environ.get('PORT', 10000))

# System Configuration
SYSTEM_MODE = "ULTRA_FAST"
CHECK_INTERVAL_SECONDS = 1
AUTO_BLOCK_IF_LEFT = True
AUTO_RESTORE_ON_REJOIN = True

# ============================================================================
# LOGGING SETUP
# ============================================================================
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# SIMPLE DATABASE (NO LOCKS ISSUE)
# ============================================================================
class SimpleDatabase:
    def __init__(self):
        os.makedirs('database', exist_ok=True)
        self.db_path = 'database/auth_system.db'
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS authorized_ids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            display_name TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            UNIQUE(user_id, telegram_id)
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS channel_members (
            telegram_id INTEGER PRIMARY KEY,
            is_member INTEGER DEFAULT 0,
            last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    
    def execute(self, query, params=()):
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall()
            conn.commit()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"DB error: {e}")
            return []
    
    def execute_one(self, query, params=()):
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchone()
            conn.commit()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"DB error: {e}")
            return None

# Initialize database
db = SimpleDatabase()

# ============================================================================
# FLASK APP
# ============================================================================
app = Flask(__name__)

# ============================================================================
# 1-SECOND REAL-TIME CHECK
# ============================================================================
@lru_cache(maxsize=1000)
def check_membership_status(telegram_id: int) -> bool:
    """Check if user is channel member"""
    try:
        # Check cache
        result = db.execute_one(
            "SELECT is_member FROM channel_members WHERE telegram_id = ? AND last_check > datetime('now', '-2 seconds')",
            (telegram_id,)
        )
        
        if result and result['is_member']:
            return True
        
        # API call
        response = requests.post(
            f"{API_URL}/getChatMember",
            json={"chat_id": CHANNEL, "user_id": telegram_id},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                status = data["result"].get("status", "left")
                is_member = status in ["member", "administrator", "creator"]
                
                # Update database
                db.execute(
                    "INSERT OR REPLACE INTO channel_members (telegram_id, is_member, last_check) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (telegram_id, 1 if is_member else 0)
                )
                
                # Clear cache
                check_membership_status.cache_clear()
                
                return is_member
                
    except Exception as e:
        logger.error(f"Check error: {e}")
    
    return False

# ============================================================================
# ANTI-LEAVE MONITOR
# ============================================================================
def anti_leave_monitor():
    """Simple monitor"""
    logger.info("🛡️ Anti-leave monitor started")
    
    while True:
        try:
            if not AUTO_BLOCK_IF_LEFT:
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue
            
            # Get active users
            users = db.execute("SELECT DISTINCT telegram_id FROM authorized_ids WHERE status = 'active'")
            
            for row in users[:10]:  # Check 10 users at a time
                telegram_id = row['telegram_id']
                is_member = check_membership_status(telegram_id)
                
                if not is_member:
                    # Block IDs
                    db.execute(
                        "UPDATE authorized_ids SET status = 'blocked' WHERE telegram_id = ? AND status = 'active'",
                        (telegram_id,)
                    )
                    logger.warning(f"🚫 Blocked IDs for {telegram_id}")
            
            time.sleep(CHECK_INTERVAL_SECONDS)
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(5)

# ============================================================================
# TELEGRAM MESSAGING
# ============================================================================
def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[Dict] = None, silent: bool = False):
    """Send message with buttons"""
    try:
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "disable_notification": silent
        }
        
        # ✅ FIX: Add reply_markup properly
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        
        response = requests.post(
            f"{API_URL}/sendMessage",
            json=data,
            timeout=10
        )
        
        if response.status_code != 200:
            logger.error(f"Send failed: {response.text}")
        
        return response.status_code == 200
            
    except Exception as e:
        logger.error(f"Send error: {e}")
        return False

# ============================================================================
# BOT COMMAND HANDLERS - BUTTONS WORKING
# ============================================================================
def handle_start_command(telegram_id: int, user_name: str, username: Optional[str] = None):
    """Handle /start command with WORKING buttons"""
    try:
        # Log activity
        db.execute(
            "INSERT INTO user_activity (telegram_id, action) VALUES (?, ?)",
            (telegram_id, "start")
        )
        
        # Check membership
        is_member = check_membership_status(telegram_id)
        
        # Auto-restore
        if is_member and AUTO_RESTORE_ON_REJOIN:
            result = db.execute_one(
                "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'blocked'",
                (telegram_id,)
            )
            if result and result['count'] > 0:
                db.execute(
                    "UPDATE authorized_ids SET status = 'active' WHERE telegram_id = ? AND status = 'blocked'",
                    (telegram_id,)
                )
        
        if is_member:
            # Get user's ID count
            result = db.execute_one(
                "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'active'",
                (telegram_id,)
            )
            user_id_count = result['count'] if result else 0
            
            # ✅ FIX: Working inline keyboard
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "➕ Add ID", "callback_data": "add_id"},
                        {"text": "📊 My Stats", "callback_data": "my_stats"}
                    ],
                    [
                        {"text": "📋 My IDs", "callback_data": "my_ids"},
                        {"text": "🔄 Check Now", "callback_data": "check_now"}
                    ],
                    [
                        {"text": "❓ Help", "callback_data": "help"}
                    ]
                ]
            }
            
            message = f"""🌟 <b>WELCOME, {html.escape(user_name)}!</b>

✅ <b>Status:</b> VERIFIED MEMBER
📊 <b>Your IDs:</b> {user_id_count}
⚡ <b>System:</b> Real-time 1s monitoring

🛡️ <b>Protection Active:</b>
• Anti-leave security
• Auto-restore
• 24/7 monitoring

🚀 <b>Tap buttons below for quick actions!</b>

<code>🕐 {datetime.now().strftime('%H:%M:%S')}</code>"""
            
            send_telegram_message(telegram_id, message, keyboard)
            
        else:
            # ✅ FIX: Working join button with URL
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Join Channel", "url": f"https://t.me/{CHANNEL[1:]}"},
                        {"text": "🔄 Check Again", "callback_data": "check_again"}
                    ]
                ]
            }
            
            message = f"""🔐 <b>ACCESS REQUIRED</b>

Hello {html.escape(user_name)}!

📢 <b>Channel:</b> {CHANNEL}

Tap the button below to join, then tap "Check Again".

🎁 <b>After joining:</b>
• Add unlimited IDs
• Real-time monitoring
• Premium features

<code>Status: NOT A MEMBER</code>"""
            
            send_telegram_message(telegram_id, message, keyboard)
            
    except Exception as e:
        logger.error(f"Start error: {e}")
        send_telegram_message(telegram_id, "❌ <b>Error</b>\n\nPlease try /start again.")

def handle_id_addition(telegram_id: int, user_name: str, user_id: str, username: Optional[str] = None):
    """Add ID to database"""
    user_id = user_id.strip()
    
    if not user_id or len(user_id) < 3:
        send_telegram_message(
            telegram_id,
            "❌ <b>Invalid ID</b>\n\nMinimum 3 characters."
        )
        return
    
    # Check membership
    if not check_membership_status(telegram_id):
        send_telegram_message(
            telegram_id,
            f"🔒 <b>Join Required</b>\n\nJoin {CHANNEL} first!"
        )
        return
    
    # Check duplicate
    result = db.execute_one(
        "SELECT user_id FROM authorized_ids WHERE user_id = ? AND status = 'active'",
        (user_id,)
    )
    
    if result:
        send_telegram_message(
            telegram_id,
            f"⚠️ <b>ID Exists</b>\n\n<code>{html.escape(user_id)}</code> already authorized."
        )
        return
    
    # Add ID
    try:
        db.execute(
            "INSERT INTO authorized_ids (user_id, telegram_id, username, display_name) VALUES (?, ?, ?, ?)",
            (user_id, telegram_id, username, user_name)
        )
        
        # ✅ FIX: Success message with buttons
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "➕ Add Another", "callback_data": "add_another"},
                    {"text": "📋 My IDs", "callback_data": "my_ids"}
                ],
                [
                    {"text": "🏠 Main Menu", "callback_data": "main_menu"}
                ]
            ]
        }
        
        # Get updated count
        result = db.execute_one(
            "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'active'",
            (telegram_id,)
        )
        user_total = result['count'] if result else 1
        
        success_msg = f"""✅ <b>ID AUTHORIZED!</b>

🎯 <b>ID:</b> <code>{html.escape(user_id)}</code>
👤 <b>User:</b> {html.escape(user_name)}
📊 <b>Your Total IDs:</b> {user_total}

⚡ <b>Processed instantly!</b>

<i>Stay in {CHANNEL} to keep access.</i>"""
        
        send_telegram_message(telegram_id, success_msg, keyboard)
        
    except Exception as e:
        logger.error(f"ID error: {e}")
        send_telegram_message(telegram_id, "❌ <b>Error adding ID</b>")

def send_user_stats(telegram_id: int, user_name: str):
    """Send user statistics with buttons"""
    try:
        # Get user's ID count
        result = db.execute_one(
            "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'active'",
            (telegram_id,)
        )
        user_ids = result['count'] if result else 0
        
        # Get system stats
        result = db.execute_one(
            "SELECT COUNT(*) as total FROM authorized_ids WHERE status = 'active'",
        )
        total_ids = result['total'] if result else 0
        
        # Check membership
        is_member = check_membership_status(telegram_id)
        
        # ✅ FIX: Stats with buttons
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📋 My IDs", "callback_data": "my_ids"},
                    {"text": "🔄 Check Status", "callback_data": "check_now"}
                ],
                [
                    {"text": "➕ Add ID", "callback_data": "add_id"},
                    {"text": "🏠 Main Menu", "callback_data": "main_menu"}
                ]
            ]
        }
        
        message = f"""📊 <b>YOUR STATISTICS</b>

👤 <b>Profile:</b>
• Name: {html.escape(user_name)}
• Status: {'✅ VERIFIED' if is_member else '❌ NOT MEMBER'}

📈 <b>Your Data:</b>
• Authorized IDs: {user_ids}

🌐 <b>System Stats:</b>
• Total IDs: {total_ids}

<code>Updated: {datetime.now().strftime('%H:%M:%S')}</code>"""
        
        send_telegram_message(telegram_id, message, keyboard)
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        send_telegram_message(telegram_id, "❌ <b>Error loading stats</b>")

def send_user_ids(telegram_id: int):
    """Send user's IDs"""
    try:
        result = db.execute(
            "SELECT user_id FROM authorized_ids WHERE telegram_id = ? AND status = 'active' ORDER BY added_at DESC LIMIT 20",
            (telegram_id,)
        )
        
        if result:
            ids_list = "\n".join([f"• <code>{row['user_id']}</code>" for row in result])
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🏠 Main Menu", "callback_data": "main_menu"}],
                    [{"text": "➕ Add More", "callback_data": "add_id"}]
                ]
            }
            
            message = f"""📋 <b>YOUR IDs ({len(result)})</b>

{ids_list}

<code>Tap buttons below for more actions.</code>"""
            
            send_telegram_message(telegram_id, message, keyboard)
        else:
            keyboard = {
                "inline_keyboard": [
                    [{"text": "➕ Add First ID", "callback_data": "add_id"}]
                ]
            }
            send_telegram_message(telegram_id, "📭 <b>No IDs yet!</b>\n\nAdd your first ID.", keyboard)
            
    except Exception as e:
        logger.error(f"IDs error: {e}")
        send_telegram_message(telegram_id, "❌ <b>Error fetching IDs</b>")

# ============================================================================
# CALLBACK QUERY HANDLER - BUTTONS WORKING
# ============================================================================
def handle_callback_query(callback_data: str, telegram_id: int, user_name: str):
    """Handle button presses"""
    try:
        logger.info(f"🔘 Button pressed: {callback_data} by {telegram_id}")
        
        if callback_data == "add_id":
            send_telegram_message(
                telegram_id,
                "📝 <b>Send any ID to add it!</b>\n\n"
                "Just type and send any ID (3+ characters).\n"
                "Example: <code>ABC123XYZ</code>"
            )
            
        elif callback_data == "my_stats":
            send_user_stats(telegram_id, user_name)
            
        elif callback_data == "check_now":
            is_member = check_membership_status(telegram_id)
            status = "✅ VERIFIED MEMBER" if is_member else "❌ NOT A MEMBER"
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔄 Check Again", "callback_data": "check_now"}],
                    [{"text": "🏠 Main Menu", "callback_data": "main_menu"}]
                ]
            }
            
            send_telegram_message(
                telegram_id,
                f"🔄 <b>REAL-TIME CHECK</b>\n\n"
                f"Status: <b>{status}</b>\n"
                f"Channel: {CHANNEL}\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}",
                keyboard
            )
            
        elif callback_data == "check_again":
            handle_start_command(telegram_id, user_name)
            
        elif callback_data == "my_ids":
            send_user_ids(telegram_id)
            
        elif callback_data == "add_another":
            send_telegram_message(
                telegram_id,
                "📝 <b>Send another ID to add!</b>\n\n"
                "Just type and send any ID."
            )
            
        elif callback_data == "main_menu":
            handle_start_command(telegram_id, user_name)
            
        elif callback_data == "help":
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🏠 Main Menu", "callback_data": "main_menu"}],
                    [{"text": "➕ Add ID", "callback_data": "add_id"}]
                ]
            }
            
            send_telegram_message(
                telegram_id,
                "❓ <b>HELP</b>\n\n"
                "<b>How to use:</b>\n"
                "1. Join " + CHANNEL + "\n"
                "2. Send /start\n"
                "3. Send any ID to add it\n\n"
                "<b>Commands:</b>\n"
                "/start - Start bot\n"
                "/stats - View statistics\n\n"
                "<b>Buttons:</b>\n"
                "• Tap buttons for quick actions\n"
                "• All features work instantly",
                keyboard
            )
            
    except Exception as e:
        logger.error(f"Callback error: {e}")
        send_telegram_message(telegram_id, "❌ <b>Button error</b>\n\nPlease try again.")

# ============================================================================
# TELEGRAM BOT POLLING - WITH CALLBACK SUPPORT
# ============================================================================
def telegram_bot_poller():
    """Main bot polling with callback support"""
    logger.info("🤖 Telegram bot poller started")
    offset = 0
    
    while True:
        try:
            response = requests.post(
                f"{API_URL}/getUpdates",
                json={
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"]  # ✅ Get callbacks
                },
                timeout=35
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    updates = data.get("result", [])
                    
                    for update in updates:
                        offset = update["update_id"] + 1
                        
                        # Handle text messages
                        if "message" in update:
                            msg = update["message"]
                            telegram_id = msg.get("from", {}).get("id")
                            user_name = msg.get("from", {}).get("first_name", "User")
                            username = msg.get("from", {}).get("username")
                            text = msg.get("text", "").strip()
                            
                            if not telegram_id or not text:
                                continue
                            
                            logger.info(f"📨 {telegram_id}: {text[:30]}")
                            
                            if text == "/start":
                                threading.Thread(
                                    target=handle_start_command,
                                    args=(telegram_id, user_name, username),
                                    daemon=True
                                ).start()
                            
                            elif text == "/stats":
                                threading.Thread(
                                    target=send_user_stats,
                                    args=(telegram_id, user_name),
                                    daemon=True
                                ).start()
                            
                            elif not text.startswith('/'):
                                threading.Thread(
                                    target=handle_id_addition,
                                    args=(telegram_id, user_name, text, username),
                                    daemon=True
                                ).start()
                        
                        # ✅ FIX: Handle callback queries (button presses)
                        elif "callback_query" in update:
                            callback = update["callback_query"]
                            callback_data = callback.get("data")
                            telegram_id = callback.get("from", {}).get("id")
                            user_name = callback.get("from", {}).get("first_name", "User")
                            
                            if telegram_id and callback_data:
                                # Answer callback query (important!)
                                try:
                                    requests.post(
                                        f"{API_URL}/answerCallbackQuery",
                                        json={
                                            "callback_query_id": callback["id"],
                                            "text": "Processing...",
                                            "show_alert": False
                                        },
                                        timeout=3
                                    )
                                except:
                                    pass
                                
                                # Handle the callback
                                threading.Thread(
                                    target=handle_callback_query,
                                    args=(callback_data, telegram_id, user_name),
                                    daemon=True
                                ).start()
            
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)

# ============================================================================
# WEB DASHBOARD
# ============================================================================
@app.route('/')
def dashboard():
    """Simple dashboard"""
    try:
        result = db.execute("SELECT COUNT(*) as total FROM authorized_ids WHERE status = 'active'")
        total_ids = result[0]['total'] if result else 0
        
        result = db.execute("SELECT COUNT(DISTINCT telegram_id) as users FROM authorized_ids WHERE status = 'active'")
        unique_users = result[0]['users'] if result else 0
        
        # Get IDs for export
        result = db.execute("SELECT user_id FROM authorized_ids WHERE status = 'active' ORDER BY added_at DESC")
        ids_list = "\n".join([row['user_id'] for row in result]) if result else ""
        
        html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Auth System</title>
    <style>
        body {{
            font-family: Arial;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            padding: 30px;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            margin-bottom: 20px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 2.5rem;
            font-weight: bold;
            margin: 10px 0;
        }}
        .export-box {{
            background: rgba(0,0,0,0.2);
            padding: 20px;
            border-radius: 15px;
            margin-top: 20px;
            max-height: 400px;
            overflow-y: auto;
        }}
        pre {{
            color: white;
            font-family: monospace;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .btn {{
            background: #10b981;
            color: white;
            padding: 12px 25px;
            border-radius: 10px;
            border: none;
            cursor: pointer;
            margin: 10px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛡️ Auth System</h1>
            <p>All Buttons Working • Real-time 1s monitoring</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{total_ids}</div>
                <div>Authorized IDs</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{unique_users}</div>
                <div>Active Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{CHECK_INTERVAL_SECONDS}s</div>
                <div>Check Interval</div>
            </div>
        </div>
        
        <div>
            <button class="btn" onclick="copyIDs()">📋 Copy IDs</button>
            <button class="btn" onclick="downloadTXT()">📥 Download TXT</button>
            <a href="/auth" target="_blank" style="color: white; margin-left: 20px;">🔗 Raw API</a>
        </div>
        
        <div class="export-box">
            <pre id="allIDs">{ids_list}</pre>
        </div>
        
        <div style="text-align: center; margin-top: 30px; color: rgba(255,255,255,0.8);">
            <p>✅ All Telegram buttons are now working!</p>
            <p>➕ Add ID • 📊 Stats • 📋 My IDs • 🔄 Check Now</p>
        </div>
    </div>
    
    <script>
        function copyIDs() {{
            const ids = document.getElementById('allIDs').textContent;
            navigator.clipboard.writeText(ids)
                .then(() => alert('✅ IDs copied!'))
                .catch(() => alert('❌ Failed to copy'));
        }}
        
        function downloadTXT() {{
            const ids = document.getElementById('allIDs').textContent;
            const blob = new Blob([ids], {{ type: 'text/plain' }});
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'ids.txt';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }}
    </script>
</body>
</html>'''
        
        return html_content
        
    except Exception as e:
        return f"<h2>Dashboard Error</h2><pre>{str(e)}</pre>"

@app.route('/auth')
def get_authorized_ids():
    """Return clean text IDs"""
    try:
        result = db.execute("SELECT user_id FROM authorized_ids WHERE status = 'active' ORDER BY added_at DESC")
        
        if result:
            ids_only = "\n".join([row['user_id'] for row in result])
            return ids_only, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        else:
            return "", 200, {'Content-Type': 'text/plain'}
            
    except Exception as e:
        logger.error(f"API error: {e}")
        return "Error", 500

# ============================================================================
# STARTUP
# ============================================================================
def initialize_system():
    """Start all system components"""
    print("\n" + "="*80)
    print("🌟 AUTH SYSTEM - ALL BUTTONS WORKING".center(80))
    print("="*80)
    print(f"✅ Database: Simple SQLite (No locks)")
    print(f"✅ Buttons: ✅ WORKING (Inline keyboard fixed)")
    print(f"✅ Channel: {CHANNEL}")
    print(f"✅ Web Dashboard: http://localhost:{PORT}")
    print(f"✅ Raw API: http://localhost:{PORT}/auth")
    print("="*80)
    print("🎯 TEST THESE BUTTONS:")
    print("• Add ID • My Stats • My IDs • Check Now • Help")
    print("="*80)
    
    # Start services
    threading.Thread(target=telegram_bot_poller, daemon=True).start()
    threading.Thread(target=anti_leave_monitor, daemon=True).start()
    
    # Start Flask
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=False,
        threaded=True,
        use_reloader=False
    )

if __name__ == "__main__":
    initialize_system()