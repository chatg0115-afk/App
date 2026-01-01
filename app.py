#!/usr/bin/env python3
# ============================================================
#     VISHAL X BOT - RAW OUTPUT v1.0
#     Public Raw Endpoint | Enhanced Bot UI
# ============================================================

import os, time, requests, threading, sqlite3, json
from datetime import datetime
from flask import Flask, jsonify, request, Response

# ===================== CONFIG ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8504965473:AAE0yYTi4DWvpdopOBkjA0AucJf0tknHDJE")
CHANNEL = os.getenv("CHANNEL", "@vishalxnetwork4")
ADMIN_KEY = os.getenv("ADMIN_KEY", "VISHAL2026")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
PORT = int(os.getenv("PORT", 8080))
SCAN_TIME = 1

# ===================== DATABASE =============================
os.makedirs("database", exist_ok=True)
db = sqlite3.connect("database/data.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    tg INTEGER,
    uid TEXT,
    status TEXT,
    joined TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(tg,uid)
)
""")
db.commit()

def add_id(tg, uid):
    cur.execute("INSERT OR IGNORE INTO users VALUES(?,?,?,datetime('now'))", (tg, uid, "active"))
    db.commit()

def delete_ids(tg):
    cur.execute("DELETE FROM users WHERE tg=?", (tg,))
    db.commit()

def restore_ids(tg):
    cur.execute("UPDATE users SET status='active', joined=datetime('now') WHERE tg=?", (tg,))
    db.commit()

def user_list():
    return cur.execute("SELECT DISTINCT tg FROM users").fetchall()

def get_stats():
    total = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    users = cur.execute("SELECT COUNT(DISTINCT tg) FROM users").fetchone()[0]
    today = cur.execute("SELECT COUNT(*) FROM users WHERE date(joined)=date('now')").fetchone()[0]
    return total, users, today

def get_all_ids():
    """Get all IDs in plain format"""
    data = cur.execute("SELECT uid FROM users ORDER BY rowid").fetchall()
    return [row[0] for row in data]

# ================= TELEGRAM API =============================
def send(tg, msg, reply_markup=None):
    try:
        payload = {"chat_id": tg, "text": msg, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=5)
        return r.status_code
    except Exception as e:
        print("SEND ERROR:", e)
        return False

def send_with_inline_keyboard(tg, msg, buttons):
    """Send message with inline keyboard"""
    keyboard = {"inline_keyboard": buttons}
    return send(tg, msg, keyboard)

def member(tg):
    try:
        r = requests.post(f"{API}/getChatMember",
                          json={"chat_id": CHANNEL, "user_id": tg}, timeout=5).json()
        status = r.get("result", {}).get("status", "left")
        return status in ["member", "administrator", "creator"]
    except:
        return False

# ================= MONITOR ==================================
def monitor():
    print("🔍 Anti-Leave Monitor Started")
    while True:
        for (tg,) in user_list():
            if not member(tg):
                delete_ids(tg)
                buttons = [[
                    {"text": "🔗 Join Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"},
                    {"text": "🔄 Restore Access", "callback_data": "restore_access"}
                ]]
                send_with_inline_keyboard(tg,
                    f"🚨 <b>ACCESS REVOKED</b>\n\n"
                    f"You left <code>{CHANNEL}</code>\n"
                    f"All your IDs have been deleted.\n\n"
                    f"<i>Rejoin to restore access</i>",
                    buttons)
                print(f"[ALERT] User {tg} left channel")
        time.sleep(SCAN_TIME)

# ================= MESSAGE HANDLER ==========================
def handler(update):
    # Handle callback queries (button clicks)
    if "callback_query" in update:
        callback = update["callback_query"]
        tg = callback["from"]["id"]
        data = callback["data"]
        
        if data == "check_status":
            is_member = member(tg)
            user_ids = cur.execute("SELECT COUNT(*) FROM users WHERE tg=?", (tg,)).fetchone()[0]
            
            buttons = [[{"text": "📊 View My Stats", "callback_data": "view_stats"}]]
            if is_member:
                buttons[0].append({"text": "➕ Add New ID", "callback_data": "add_id"})
            
            send_with_inline_keyboard(tg,
                f"📊 <b>YOUR STATUS</b>\n\n"
                f"👤 User ID: <code>{tg}</code>\n"
                f"📢 Channel: {CHANNEL}\n"
                f"✅ Member: {'Yes' if is_member else 'No'}\n"
                f"💾 Stored IDs: {user_ids}\n\n"
                f"<i>Tap buttons below for actions</i>",
                buttons)
        
        elif data == "view_stats":
            total, users, today = get_stats()
            user_count = cur.execute("SELECT COUNT(*) FROM users WHERE tg=?", (tg,)).fetchone()[0]
            
            send(tg,
                f"📈 <b>SYSTEM STATISTICS</b>\n\n"
                f"🌐 Total IDs: {total}\n"
                f"👥 Active Users: {users}\n"
                f"📅 Today Added: {today}\n"
                f"👤 Your IDs: {user_count}\n\n"
                f"🛡️ Protection: Active\n"
                f"⏱️ Scan Interval: {SCAN_TIME}s")
        
        elif data == "add_id":
            send(tg,
                f"📝 <b>ADD NEW ID</b>\n\n"
                f"Send your ID in next message.\n\n"
                f"<i>Example:</i>\n"
                f"<code>ABC123456789</code>\n\n"
                f"⚠️ <b>Note:</b> Stay in {CHANNEL}\n"
                f"to keep IDs protected.")
        
        elif data == "restore_access":
            if member(tg):
                restore_ids(tg)
                buttons = [[
                    {"text": "📊 Check Status", "callback_data": "check_status"},
                    {"text": "➕ Add ID", "callback_data": "add_id"}
                ]]
                send_with_inline_keyboard(tg,
                    f"✅ <b>ACCESS RESTORED</b>\n\n"
                    f"All your previous IDs have been restored!\n\n"
                    f"<i>You can now add new IDs</i>",
                    buttons)
            else:
                buttons = [[{"text": "🔗 Join Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"}]]
                send_with_inline_keyboard(tg,
                    f"❌ <b>STILL NOT JOINED</b>\n\n"
                    f"You haven't joined {CHANNEL} yet.\n"
                    f"Join first, then click Restore Access again.",
                    buttons)
        
        # Answer callback query to remove loading
        requests.post(f"{API}/answerCallbackQuery", 
                     json={"callback_query_id": callback["id"]})
        return

    # Handle regular messages
    msg = update.get("message")
    if not msg:
        return

    tg = msg["from"]["id"]
    txt = msg.get("text", "")
    if txt is None:
        return

    # START COMMAND with buttons
    if txt == "/start":
        if not member(tg):
            buttons = [[
                {"text": "🔗 Join Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"},
                {"text": "✅ Check Status", "callback_data": "check_status"}
            ]]
            send_with_inline_keyboard(tg,
                f"👋 <b>WELCOME TO VISHAL X BOT</b>\n\n"
                f"🔒 <b>Channel Membership Required</b>\n"
                f"Join: {CHANNEL}\n\n"
                f"<b>✨ FEATURES:</b>\n"
                f"• Auto ID Protection\n"
                f"• Instant Leave Detection\n"
                f"• Secure Storage\n\n"
                f"<i>Join channel then check status</i>",
                buttons)
            return
        
        restore_ids(tg)
        buttons = [[
            {"text": "📊 Check Status", "callback_data": "check_status"},
            {"text": "➕ Add ID", "callback_data": "add_id"}
        ]]
        send_with_inline_keyboard(tg,
            f"🎉 <b>ACCESS GRANTED</b>\n\n"
            f"✅ All your IDs restored\n"
            f"🛡️ Anti-leave protection active\n\n"
            f"<b>What would you like to do?</b>",
            buttons)
        return

    # HELP COMMAND
    if txt == "/help":
        buttons = [[
            {"text": "📊 Check Status", "callback_data": "check_status"},
            {"text": "🔗 Raw Data", "url": f"http://localhost:{PORT}/"}
        ]]
        send_with_inline_keyboard(tg,
            f"🆘 <b>HELP & COMMANDS</b>\n\n"
            f"<b>📋 Commands:</b>\n"
            f"/start - Start/restore access\n"
            f"/help - Show this help\n"
            f"/stats - System statistics\n\n"
            f"<b>🛡️ Protection:</b>\n"
            f"• IDs auto-delete if you leave channel\n"
            f"• Auto-restore when you rejoin\n"
            f"• Real-time monitoring\n\n"
            f"<b>📢 Channel:</b> {CHANNEL}",
            buttons)
        return

    # STATS COMMAND
    if txt == "/stats":
        total, users, today = get_stats()
        user_count = cur.execute("SELECT COUNT(*) FROM users WHERE tg=?", (tg,)).fetchone()[0]
        
        buttons = [[{"text": "🌐 Public Data", "url": f"http://localhost:{PORT}/"}]]
        send_with_inline_keyboard(tg,
            f"📊 <b>SYSTEM STATISTICS</b>\n\n"
            f"🌐 Total IDs: {total}\n"
            f"👥 Active Users: {users}\n"
            f"📅 Today Added: {today}\n"
            f"👤 Your IDs: {user_count}\n\n"
            f"🛡️ Protection: Active\n"
            f"⏱️ Scan Interval: {SCAN_TIME}s\n\n"
            f"<i>View public raw data:</i>",
            buttons)
        return

    # ADD ID (any non-command text)
    if txt and not txt.startswith("/"):
        if not member(tg):
            buttons = [[
                {"text": "🔗 Join Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"},
                {"text": "🔄 Restore Access", "callback_data": "restore_access"}
            ]]
            send_with_inline_keyboard(tg,
                f"❌ <b>ACCESS DENIED</b>\n\n"
                f"You left {CHANNEL}\n"
                f"Cannot save IDs while not a member.\n\n"
                f"<i>Rejoin to restore access</i>",
                buttons)
            return
        
        add_id(tg, txt)
        user_count = cur.execute("SELECT COUNT(*) FROM users WHERE tg=?", (tg,)).fetchone()[0]
        
        buttons = [[
            {"text": "➕ Add Another", "callback_data": "add_id"},
            {"text": "📊 View Stats", "callback_data": "check_status"}
        ]]
        send_with_inline_keyboard(tg,
            f"✅ <b>ID SAVED SUCCESSFULLY</b>\n\n"
            f"📝 ID: <code>{txt}</code>\n"
            f"👤 Your Total IDs: {user_count}\n"
            f"🛡️ Protected: Yes\n"
            f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"<i>What would you like to do next?</i>",
            buttons)
        return

# ================= POLLER ===================================
def poller():
    offset = 0
    print("🔄 Removing webhook...")
    requests.post(f"{API}/deleteWebhook", json={"drop_pending_updates": True})

    print("🤖 Bot Poller Started")
    while True:
        try:
            updates = requests.post(f"{API}/getUpdates",
                                   json={"offset": offset, "timeout": 30}).json()

            for upd in updates.get("result", []):
                offset = upd["update_id"] + 1
                handler(upd)

        except Exception as e:
            print("Poller Error:", e)
            time.sleep(2)

# ================= FLASK APP ================================
app = Flask(__name__)

# PUBLIC RAW ENDPOINT - PLAIN TEXT ONLY
@app.route("/")
def raw_output():
    """Public raw text endpoint - one ID per line"""
    ids = get_all_ids()
    
    if not ids:
        return Response("No data available", mimetype='text/plain')
    
    # Create plain text response - ONE ID PER LINE
    response_text = "\n".join(ids)
    
    # Add minimal headers for clean raw output
    return Response(response_text, 
                   mimetype='text/plain',
                   headers={
                       'Content-Type': 'text/plain; charset=utf-8',
                       'Cache-Control': 'no-cache',
                       'Access-Control-Allow-Origin': '*'
                   })

@app.route("/stats")
def public_stats():
    """Public statistics in plain text"""
    total, users, today = get_stats()
    
    stats_text = f"""VISHAL X BOT STATISTICS
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total IDs: {total}
Active Users: {users}
Today Added: {today}
Channel: {CHANNEL}
Endpoint: /
Format: One ID per line"""
    
    return Response(stats_text, mimetype='text/plain')

@app.route("/count")
def count():
    """Just the count of IDs"""
    ids = get_all_ids()
    return Response(str(len(ids)), mimetype='text/plain')

@app.route("/admin")
def admin_panel():
    """Admin access - requires key parameter"""
    key = request.args.get("key")
    if key != ADMIN_KEY:
        return Response("Unauthorized", mimetype='text/plain', status=403)
    
    total, users, today = get_stats()
    admin_text = f"""ADMIN PANEL - VISHAL X BOT
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total IDs: {total}
Active Users: {users}
Today Added: {today}
RAW Endpoint: /
Admin Export: /export?key={ADMIN_KEY}"""
    
    return Response(admin_text, mimetype='text/plain')

@app.route("/export")
def admin_export():
    """Admin export with metadata"""
    key = request.args.get("key")
    if key != ADMIN_KEY:
        return Response("Unauthorized", mimetype='text/plain', status=403)
    
    ids = get_all_ids()
    total = len(ids)
    
    export_text = f"""# VISHAL X BOT EXPORT
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# Total IDs: {total}
# Format: One ID per line

"""
    export_text += "\n".join(ids)
    
    return Response(export_text, mimetype='text/plain')

@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "total_ids": len(get_all_ids()),
        "endpoint": "/"
    })

# ================= RUN ======================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 VISHAL X BOT - RAW OUTPUT SERVER")
    print("="*70)
    print(f"🌐 PUBLIC RAW ENDPOINT: http://localhost:{PORT}/")
    print(f"📊 STATS: http://localhost:{PORT}/stats")
    print(f"🔢 COUNT: http://localhost:{PORT}/count")
    print(f"🔐 ADMIN: http://localhost:{PORT}/admin?key={ADMIN_KEY}")
    print(f"📁 EXPORT: http://localhost:{PORT}/export?key={ADMIN_KEY}")
    print("="*70)
    print("📋 OUTPUT FORMAT: One ID per line (plain text)")
    print("🔗 Example: id1\\nid2\\nid3")
    print("="*70 + "\n")
    
    threading.Thread(target=monitor, daemon=True).start()
    threading.Thread(target=poller, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)