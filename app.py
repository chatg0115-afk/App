#!/usr/bin/env python3
# ============================================================
# VISHAL X BOT - ENTERPRISE PROTECTION v2.2
# Critical Fixes Applied
# ============================================================
import os, time, requests, threading, sqlite3, json
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, Response
import queue

# ===================== CONFIG ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8504965473:AAE0yYTi4DWvpdopOBkjA0AucJf0tknHDJE")
CHANNEL = os.getenv("CHANNEL", "@vishalxnetwork4")
ADMIN_KEY = os.getenv("ADMIN_KEY", "VISHAL2026")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
PORT = int(os.getenv("PORT", 8080))
SCAN_TIME = 30
MAX_STRIKES = 3
SUSPEND_DURATION = 3600
DOUBLE_CHECK_DELETE = True

# ===================== DATABASE =============================
os.makedirs("database", exist_ok=True)

# Thread-safe database connection pool
class Database:
    def __init__(self):
        self.connections = {}
        self.lock = threading.Lock()
    
    def get_connection(self, thread_id):
        """Get thread-specific database connection"""
        with self.lock:
            if thread_id not in self.connections:
                conn = sqlite3.connect("database/data.db", check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self.connections[thread_id] = conn
            return self.connections[thread_id]
    
    def close_all(self):
        """Close all connections"""
        with self.lock:
            for conn in self.connections.values():
                conn.close()
            self.connections.clear()

# Global database manager
db_manager = Database()

def get_db():
    """Get database connection for current thread"""
    thread_id = threading.get_ident()
    return db_manager.get_connection(thread_id)

def init_database():
    """Initialize database tables"""
    db = get_db()
    cur = db.cursor()
    
    # Main users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            tg INTEGER,
            uid TEXT,
            status TEXT DEFAULT 'active',
            added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(tg,uid)
        )
    """)
    
    # Enhanced user state table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_states(
            tg INTEGER PRIMARY KEY,
            strike_count INTEGER DEFAULT 0,
            last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            suspended_until TIMESTAMP,
            status TEXT DEFAULT 'active',
            last_member_status TEXT DEFAULT 'member',
            last_notified_status TEXT,
            notifications_sent INTEGER DEFAULT 0,
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Deleted users log (for audit)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deleted_users_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg INTEGER,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT,
            ids_count INTEGER
        )
    """)
    
    db.commit()
    print("✅ Database initialized")

# Initialize database
init_database()

# ===================== DATABASE FUNCTIONS ====================
def ensure_user_state(tg):
    """CRITICAL FIX #1: Ensure user has entry in user_states"""
    db = get_db()
    cur = db.cursor()
    
    # Check if user exists
    cur.execute("SELECT 1 FROM user_states WHERE tg=?", (tg,))
    if not cur.fetchone():
        # Create entry if doesn't exist
        cur.execute("""
            INSERT OR IGNORE INTO user_states 
            (tg, status, strike_count, last_member_status) 
            VALUES(?,?,?,?)
        """, (tg, 'active', 0, 'member'))
        db.commit()
        print(f"[USER_STATE] Created entry for user {tg}")

def add_id(tg, uid):
    """Add ID for user"""
    # CRITICAL: Ensure user state exists first
    ensure_user_state(tg)
    
    db = get_db()
    cur = db.cursor()
    
    # Use transaction for safety
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("""
            INSERT OR IGNORE INTO users VALUES(?,?,?,datetime('now'))
        """, (tg, uid, 'active'))
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error adding ID for {tg}: {e}")
        return False

def suspend_user(tg):
    """Temporarily suspend user access"""
    db = get_db()
    cur = db.cursor()
    
    try:
        cur.execute("BEGIN IMMEDIATE")
        
        # Check if already suspended
        cur.execute("SELECT status FROM user_states WHERE tg=?", (tg,))
        current_status = cur.fetchone()
        
        if current_status and current_status['status'] == 'suspended':
            return
        
        # Suspend user
        suspend_time = datetime.now() + timedelta(seconds=SUSPEND_DURATION)
        cur.execute("""
            UPDATE user_states 
            SET strike_count=?, suspended_until=?, status=?, 
                last_member_status='left', last_notified_status='suspended'
            WHERE tg=?
        """, (MAX_STRIKES, suspend_time, 'suspended', tg))
        
        # Update all user's IDs to suspended
        cur.execute("""
            UPDATE users SET status='suspended' WHERE tg=?
        """, (tg,))
        
        db.commit()
        
    except Exception as e:
        db.rollback()
        print(f"Error suspending user {tg}: {e}")

def delete_user_ids(tg):
    """Permanently delete user's IDs with double-check and logging"""
    db = get_db()
    cur = db.cursor()
    
    try:
        cur.execute("BEGIN IMMEDIATE")
        
        # CRITICAL FIX #2: Get count before deletion (for logging)
        cur.execute("SELECT COUNT(*) as count FROM users WHERE tg=?", (tg,))
        ids_count = cur.fetchone()['count']
        
        # Enterprise feature: Double-check before deletion
        if DOUBLE_CHECK_DELETE:
            # Final verification before deletion
            is_member = check_member(tg)
            if is_member:
                print(f"[ENTERPRISE] User {tg} rejoined at last moment, cancelling deletion")
                
                # Restore user
                cur.execute("""
                    UPDATE user_states 
                    SET strike_count=0, status='active', suspended_until=NULL,
                        last_member_status='member'
                    WHERE tg=?
                """, (tg,))
                
                cur.execute("""
                    UPDATE users SET status='active' WHERE tg=?
                """, (tg,))
                
                db.commit()
                return False
        
        # CRITICAL FIX #2: Log deletion first
        cur.execute("""
            INSERT INTO deleted_users_log (tg, reason, ids_count)
            VALUES(?,?,?)
        """, (tg, 'channel_leave', ids_count))
        
        # CRITICAL FIX #2: Update status to 'deleted' before actual deletion
        cur.execute("""
            UPDATE user_states SET status='deleted' WHERE tg=?
        """, (tg,))
        db.commit()
        
        # Now delete the data
        cur.execute("DELETE FROM users WHERE tg=?", (tg,))
        cur.execute("DELETE FROM user_states WHERE tg=?", (tg,))
        
        db.commit()
        print(f"[DELETE] User {tg} deleted with {ids_count} IDs")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"Error deleting user {tg}: {e}")
        return False

def restore_user(tg):
    """Restore user access after rejoining"""
    db = get_db()
    cur = db.cursor()
    
    try:
        cur.execute("BEGIN IMMEDIATE")
        
        # Check if user was deleted but still in log
        cur.execute("SELECT status FROM user_states WHERE tg=?", (tg,))
        state = cur.fetchone()
        
        if state and state['status'] == 'deleted':
            # User was marked as deleted but data might still exist
            # Just create new entry
            cur.execute("""
                INSERT OR REPLACE INTO user_states 
                (tg, strike_count, status, last_member_status) 
                VALUES(?,?,?,?)
            """, (tg, 0, 'active', 'member'))
        else:
            # Normal restore
            cur.execute("""
                UPDATE user_states 
                SET strike_count=0, status='active', suspended_until=NULL, 
                    last_member_status='member', last_notified_status='restored'
                WHERE tg=?
            """, (tg,))
        
        # Reactivate all suspended IDs
        cur.execute("""
            UPDATE users SET status='active' WHERE tg=? AND status='suspended'
        """, (tg,))
        
        db.commit()
        return True
        
    except Exception as e:
        db.rollback()
        print(f"Error restoring user {tg}: {e}")
        return False

def update_strike(tg, is_member):
    """Update strike count based on membership check"""
    db = get_db()
    cur = db.cursor()
    
    try:
        cur.execute("BEGIN IMMEDIATE")
        
        # Get current state
        cur.execute("SELECT * FROM user_states WHERE tg=?", (tg,))
        state = cur.fetchone()
        
        if not state:
            # Create entry if doesn't exist
            cur.execute("""
                INSERT INTO user_states 
                (tg, last_member_status, last_check) 
                VALUES(?,?,?)
            """, (tg, 'member' if is_member else 'left', datetime.now()))
            db.commit()
            return 0, 'active'
        
        # CRITICAL FIX #4: Update last_check even if API error
        cur.execute("""
            UPDATE user_states SET last_check=? WHERE tg=?
        """, (datetime.now(), tg))
        
        # Check if user is suspended and time has passed
        if state['status'] == 'suspended' and state['suspended_until']:
            suspend_time = datetime.strptime(state['suspended_until'], '%Y-%m-%d %H:%M:%S')
            if datetime.now() > suspend_time:
                deleted = delete_user_ids(tg)
                if deleted:
                    return -1, 'deleted'
                else:
                    # Deletion cancelled, user restored
                    return 0, 'active'
        
        # If already deleted
        if state['status'] == 'deleted':
            return -1, 'deleted'
        
        if is_member:
            # Reset strikes if member
            cur.execute("""
                UPDATE user_states 
                SET strike_count=0, status='active', last_member_status='member'
                WHERE tg=?
            """, (tg,))
            db.commit()
            return 0, 'active'
        else:
            # Increment strike
            new_strikes = state['strike_count'] + 1
            new_status = state['status']
            
            # Suspend if max strikes reached
            if new_strikes >= MAX_STRIKES and state['status'] != 'suspended':
                new_status = 'suspended'
                suspend_time = datetime.now() + timedelta(seconds=SUSPEND_DURATION)
                cur.execute("""
                    UPDATE user_states 
                    SET strike_count=?, status=?, suspended_until=?, last_member_status='left'
                    WHERE tg=?
                """, (new_strikes, new_status, suspend_time, tg))
            else:
                cur.execute("""
                    UPDATE user_states 
                    SET strike_count=?, last_member_status='left'
                    WHERE tg=?
                """, (new_strikes, tg))
            
            db.commit()
            return new_strikes, new_status
            
    except Exception as e:
        db.rollback()
        print(f"Error updating strike for {tg}: {e}")
        return 0, 'error'

def get_user_status(tg):
    """Get user's current status"""
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT status FROM user_states WHERE tg=?", (tg,))
    result = cur.fetchone()
    return result['status'] if result else 'active'

def get_active_users():
    """Get ONLY active users for monitoring"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT tg FROM user_states 
        WHERE status='active' 
        ORDER BY last_check
    """)
    return [row['tg'] for row in cur.fetchall()]

def get_suspended_users():
    """Get suspended users (for admin panel)"""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT tg, suspended_until FROM user_states 
        WHERE status='suspended'
        ORDER BY suspended_until
    """)
    return cur.fetchall()

def should_send_notification(tg, notification_type):
    """Check if notification should be sent (prevents spam)"""
    db = get_db()
    cur = db.cursor()
    
    cur.execute("""
        SELECT last_notified_status, notifications_sent 
        FROM user_states WHERE tg=?
    """, (tg,))
    result = cur.fetchone()
    
    if not result:
        return True
    
    last_notified, sent_count = result['last_notified_status'], result['notifications_sent']
    
    # If same notification was already sent, don't send again
    if last_notified == notification_type:
        return False
    
    # Update notification tracking
    cur.execute("""
        UPDATE user_states 
        SET last_notified_status=?, notifications_sent=notifications_sent+1
        WHERE tg=?
    """, (notification_type, tg))
    db.commit()
    
    return True

def get_stats():
    """Get system statistics"""
    db = get_db()
    cur = db.cursor()
    
    total = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active_users = cur.execute("""
        SELECT COUNT(DISTINCT tg) FROM users WHERE status='active'
    """).fetchone()[0]
    suspended_users = cur.execute("""
        SELECT COUNT(DISTINCT tg) FROM users WHERE status='suspended'
    """).fetchone()[0]
    today = cur.execute("""
        SELECT COUNT(*) FROM users WHERE date(added)=date('now')
    """).fetchone()[0]
    deleted_count = cur.execute("SELECT COUNT(*) FROM deleted_users_log").fetchone()[0]
    
    return total, active_users, suspended_users, today, deleted_count

def get_all_ids():
    """Get all active IDs in plain format"""
    db = get_db()
    cur = db.cursor()
    data = cur.execute("""
        SELECT uid FROM users 
        WHERE status='active' 
        ORDER BY rowid
    """).fetchall()
    return [row['uid'] for row in data]

# ================= TELEGRAM API =============================
def send(tg, msg, reply_markup=None):
    """Send message to user"""
    try:
        payload = {"chat_id": tg, "text": msg, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"SEND ERROR to {tg}:", e)
        return False

def send_with_inline_keyboard(tg, msg, buttons):
    """Send message with inline keyboard"""
    keyboard = {"inline_keyboard": buttons}
    return send(tg, msg, keyboard)

def check_member(tg):
    """Check if user is channel member (with error handling)"""
    try:
        r = requests.post(
            f"{API}/getChatMember",
            json={"chat_id": CHANNEL, "user_id": tg},
            timeout=10
        ).json()
        
        if not r.get("ok"):
            print(f"API Error for user {tg}:", r.get("description"))
            return None  # Unknown status
        
        status = r.get("result", {}).get("status", "left")
        return status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"Network/API Error for user {tg}:", e)
        return None  # Unknown status

# ================= ENHANCED MONITOR =========================
def monitor():
    """Enhanced anti-leave monitor with thread safety"""
    print("🛡️ ENTERPRISE ANTI-LEAVE MONITOR STARTED")
    print(f"📊 Config: {MAX_STRIKES} strikes | {SUSPEND_DURATION//3600} hour suspension")
    print(f"🔒 Double-check delete: {DOUBLE_CHECK_DELETE}")
    
    while True:
        try:
            # Get ONLY active users (not suspended ones)
            active_users = get_active_users()
            print(f"👥 Monitoring {len(active_users)} active users")
            
            for tg in active_users:
                try:
                    # Check membership with error handling
                    is_member = check_member(tg)
                    
                    # CRITICAL FIX #4: Update last_check even on API error
                    if is_member is None:
                        print(f"⚠️ API Error for {tg}, updating last_check only")
                        # Update last_check but no strikes
                        db = get_db()
                        cur = db.cursor()
                        cur.execute("BEGIN IMMEDIATE")
                        cur.execute("UPDATE user_states SET last_check=? WHERE tg=?", 
                                  (datetime.now(), tg))
                        db.commit()
                        continue
                    
                    # Update strike count based on membership
                    strikes, new_status = update_strike(tg, is_member)
                    current_status = get_user_status(tg)
                    
                    # Handle status changes with notifications
                    if strikes == -1:
                        # User deleted - send notification only once
                        if should_send_notification(tg, 'deleted'):
                            buttons = [[
                                {"text": "📢 Join Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"},
                                {"text": "🔓 Restore Access", "callback_data": "restore_access"}
                            ]]
                            send_with_inline_keyboard(tg,
                                f"🚫 <b>ACCESS PERMANENTLY REVOKED</b>\n\n"
                                f"All your IDs have been deleted.\n"
                                f"Reason: Left {CHANNEL}\n\n"
                                f"<i>Rejoin and click Restore Access</i>",
                                buttons
                            )
                            print(f"[DELETE] User {tg} permanently removed")
                    
                    elif new_status == 'suspended' and current_status != 'suspended':
                        # Status changed to suspended - send notification only once
                        if should_send_notification(tg, 'suspended'):
                            remaining_time = SUSPEND_DURATION
                            hours = remaining_time // 3600
                            minutes = (remaining_time % 3600) // 60
                            
                            buttons = [[
                                {"text": "📢 Rejoin Now", "url": f"https://t.me/{CHANNEL.replace('@', '')}"},
                                {"text": "🔄 Check Status", "callback_data": "check_status"}
                            ]]
                            send_with_inline_keyboard(tg,
                                f"⏸️ <b>ACCESS TEMPORARILY SUSPENDED</b>\n\n"
                                f"You left <code>{CHANNEL}</code>\n"
                                f"⚠️ Final Warning: {strikes}/{MAX_STRIKES}\n"
                                f"⏳ IDs will be deleted in {hours}h {minutes}m\n\n"
                                f"<i>Rejoin now to restore all IDs</i>",
                                buttons
                            )
                            print(f"[SUSPEND] User {tg} suspended ({strikes} strikes)")
                    
                    elif strikes > 0 and strikes < MAX_STRIKES:
                        # Warning strikes - send notification only once per strike level
                        if should_send_notification(tg, f'warning_{strikes}'):
                            buttons = [[
                                {"text": "📢 Stay in Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"},
                                {"text": "📊 Check Status", "callback_data": "check_status"}
                            ]]
                            send_with_inline_keyboard(tg,
                                f"⚠️ <b>WARNING: {strikes}/{MAX_STRIKES}</b>\n\n"
                                f"Leaving {CHANNEL} detected.\n"
                                f"Next violation will suspend access.\n\n"
                                f"<i>Stay in channel to avoid suspension</i>",
                                buttons
                            )
                            print(f"[WARNING] User {tg}: {strikes}/{MAX_STRIKES} strikes")
                    
                except Exception as e:
                    print(f"Error processing user {tg}:", e)
                    continue
            
            print(f"✅ Scan completed, next in {SCAN_TIME}s")
            time.sleep(SCAN_TIME)
            
        except Exception as e:
            print("Monitor loop error:", e)
            time.sleep(30)

# ================= MESSAGE HANDLER ==========================
def handler(update):
    """Handle Telegram updates"""
    # Handle callback queries
    if "callback_query" in update:
        callback = update["callback_query"]
        tg = callback["from"]["id"]
        data = callback["data"]
        
        # CRITICAL FIX #1: Ensure user state exists
        ensure_user_state(tg)
        
        if data == "check_status":
            is_member = check_member(tg)
            db = get_db()
            cur = db.cursor()
            
            cur.execute("SELECT COUNT(*) as count FROM users WHERE tg=? AND status='active'", (tg,))
            user_ids = cur.fetchone()['count']
            
            cur.execute("SELECT strike_count, status FROM user_states WHERE tg=?", (tg,))
            strike_result = cur.fetchone()
            strikes = strike_result['strike_count'] if strike_result else 0
            user_status = strike_result['status'] if strike_result else 'active'
            
            buttons = [[{"text": "📊 View Stats", "callback_data": "view_stats"}]]
            
            if is_member and user_status == 'active':
                buttons[0].append({"text": "➕ Add ID", "callback_data": "add_id"})
            
            status_msg = "✅ Active" if user_status == 'active' else f"⏸️ Suspended ({strikes}/{MAX_STRIKES})"
            
            send_with_inline_keyboard(tg,
                f"📊 <b>YOUR STATUS</b>\n\n"
                f"👤 User ID: <code>{tg}</code>\n"
                f"📢 Channel: {CHANNEL}\n"
                f"✅ Member: {'Yes' if is_member else 'No'}\n"
                f"🛡️ Status: {status_msg}\n"
                f"💾 Active IDs: {user_ids}\n\n"
                f"<i>Tap buttons for actions</i>",
                buttons
            )
        
        elif data == "view_stats":
            total, active_users, suspended_users, today, deleted_count = get_stats()
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT COUNT(*) as count FROM users WHERE tg=? AND status='active'", (tg,))
            user_count = cur.fetchone()['count']
            
            send(tg,
                f"📈 <b>SYSTEM STATISTICS</b>\n\n"
                f"💾 Total IDs: {total}\n"
                f"👥 Active Users: {active_users}\n"
                f"⏸️ Suspended Users: {suspended_users}\n"
                f"🗑️ Deleted Users: {deleted_count}\n"
                f"📅 Today Added: {today}\n"
                f"👤 Your IDs: {user_count}\n\n"
                f"🛡️ Protection: Enhanced Strike System\n"
                f"⏱️ Scan Interval: {SCAN_TIME}s\n"
                f"⚠️ Max Strikes: {MAX_STRIKES}"
            )
        
        elif data == "add_id":
            send(tg,
                f"📝 <b>ADD NEW ID</b>\n\n"
                f"Send your ID in next message.\n\n"
                f"<i>Example:</i>\n"
                f"<code>ABC123456789</code>\n\n"
                f"⚠️ <b>Note:</b> Stay in {CHANNEL}\n"
                f"to avoid suspension."
            )
        
        elif data == "restore_access":
            is_member = check_member(tg)
            if is_member:
                restore_user(tg)
                db = get_db()
                cur = db.cursor()
                cur.execute("SELECT COUNT(*) as count FROM users WHERE tg=? AND status='active'", (tg,))
                user_count = cur.fetchone()['count']
                
                buttons = [[
                    {"text": "📊 Check Status", "callback_data": "check_status"},
                    {"text": "➕ Add ID", "callback_data": "add_id"}
                ]]
                send_with_inline_keyboard(tg,
                    f"✅ <b>ACCESS RESTORED</b>\n\n"
                    f"Welcome back to {CHANNEL}!\n"
                    f"All your IDs ({user_count}) have been restored.\n"
                    f"Strikes reset to 0.\n\n"
                    f"<i>Protection is now active</i>",
                    buttons
                )
            else:
                buttons = [[
                    {"text": "📢 Join Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"}
                ]]
                send_with_inline_keyboard(tg,
                    f"❌ <b>NOT JOINED YET</b>\n\n"
                    f"You haven't joined {CHANNEL}.\n"
                    f"Join first, then click Restore Access again.",
                    buttons
                )
        
        # Answer callback query
        requests.post(f"{API}/answerCallbackQuery", 
                     json={"callback_query_id": callback["id"]})
        return
    
    # Handle regular messages
    msg = update.get("message")
    if not msg:
        return
    
    tg = msg["from"]["id"]
    txt = msg.get("text", "")
    
    if not txt:
        return
    
    # START command
    if txt == "/start":
        # CRITICAL FIX #1: Ensure user state exists
        ensure_user_state(tg)
        
        is_member = check_member(tg)
        user_status = get_user_status(tg)
        
        if not is_member:
            buttons = [[
                {"text": "📢 Join Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"},
                {"text": "✅ Check Status", "callback_data": "check_status"}
            ]]
            send_with_inline_keyboard(tg,
                f"👋 <b>WELCOME TO VISHAL X BOT</b>\n\n"
                f"📢 <b>Channel Membership Required</b>\n"
                f"Join: {CHANNEL}\n\n"
                f"🛡️ <b>ENTERPRISE PROTECTION:</b>\n"
                f"• {MAX_STRIKES}-Strike System\n"
                f"• No Spam Notifications\n"
                f"• Double-Confirm Deletion\n\n"
                f"<i>Join channel then check status</i>",
                buttons
            )
            return
        
        # User is member
        if user_status == 'suspended':
            restore_user(tg)
        
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) as count FROM users WHERE tg=? AND status='active'", (tg,))
        user_count = cur.fetchone()['count']
        
        buttons = [[
            {"text": "📊 Check Status", "callback_data": "check_status"},
            {"text": "➕ Add ID", "callback_data": "add_id"}
        ]]
        send_with_inline_keyboard(tg,
            f"🎉 <b>ACCESS GRANTED</b>\n\n"
            f"✅ You're in {CHANNEL}\n"
            f"💾 Your IDs: {user_count}\n"
            f"🛡️ Protection: Active\n\n"
            f"<b>What would you like to do?</b>",
            buttons
        )
        return
    
    # HELP command
    if txt == "/help":
        buttons = [[
            {"text": "📊 Check Status", "callback_data": "check_status"},
            {"text": "📄 Raw Data", "url": f"http://localhost:{PORT}/"}
        ]]
        send_with_inline_keyboard(tg,
            f"❓ <b>HELP & COMMANDS</b>\n\n"
            f"📋 <b>Commands:</b>\n"
            f"/start - Start/Restore access\n"
            f"/help - Show this help\n"
            f"/stats - System statistics\n\n"
            f"🛡️ <b>Enhanced Protection:</b>\n"
            f"• {MAX_STRIKES}-strike system\n"
            f"• One notification per event\n"
            f"• Final verification before deletion\n\n"
            f"📢 <b>Channel:</b> {CHANNEL}",
            buttons
        )
        return
    
    # STATS command
    if txt == "/stats":
        total, active_users, suspended_users, today, deleted_count = get_stats()
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) as count FROM users WHERE tg=? AND status='active'", (tg,))
        user_count = cur.fetchone()['count']
        
        buttons = [[{"text": "📄 Public Data", "url": f"http://localhost:{PORT}/"}]]
        send_with_inline_keyboard(tg,
            f"📈 <b>SYSTEM STATISTICS</b>\n\n"
            f"💾 Total IDs: {total}\n"
            f"👥 Active Users: {active_users}\n"
            f"⏸️ Suspended Users: {suspended_users}\n"
            f"🗑️ Deleted Users: {deleted_count}\n"
            f"📅 Today Added: {today}\n"
            f"👤 Your IDs: {user_count}\n\n"
            f"🛡️ Protection: Enterprise Grade\n"
            f"⏱️ Scan: {SCAN_TIME}s\n\n"
            f"<i>View public raw data:</i>",
            buttons
        )
        return
    
    # ADD ID (any non-command text)
    if not txt.startswith("/"):
        # CRITICAL FIX #1: Ensure user state exists
        ensure_user_state(tg)
        
        is_member = check_member(tg)
        user_status = get_user_status(tg)
        
        if not is_member or user_status == 'suspended':
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT strike_count FROM user_states WHERE tg=?", (tg,))
            strike_result = cur.fetchone()
            strike_count = strike_result['strike_count'] if strike_result else 0
            
            buttons = [[
                {"text": "📢 Join Channel", "url": f"https://t.me/{CHANNEL.replace('@', '')}"},
                {"text": "🔄 Restore Access", "callback_data": "restore_access"}
            ]]
            
            if user_status == 'suspended':
                msg_text = f"⏸️ <b>ACCESS SUSPENDED</b>\n\n"
                msg_text += f"Strikes: {strike_count}/{MAX_STRIKES}\n"
                msg_text += f"Rejoin to restore all IDs.\n\n"
            else:
                msg_text = f"❌ <b>ACCESS DENIED</b>\n\n"
                msg_text += f"You're not in {CHANNEL}\n"
                msg_text += f"Cannot save IDs while not a member.\n\n"
            
            msg_text += "<i>Rejoin to restore access</i>"
            send_with_inline_keyboard(tg, msg_text, buttons)
            return
        
        # Add ID
        if add_id(tg, txt):
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT COUNT(*) as count FROM users WHERE tg=? AND status='active'", (tg,))
            user_count = cur.fetchone()['count']
            
            buttons = [[
                {"text": "➕ Add Another", "callback_data": "add_id"},
                {"text": "📊 View Stats", "callback_data": "check_status"}
            ]]
            send_with_inline_keyboard(tg,
                f"✅ <b>ID SAVED SUCCESSFULLY</b>\n\n"
                f"📝 ID: <code>{txt}</code>\n"
                f"👤 Your Total IDs: {user_count}\n"
                f"🛡️ Protected: Enterprise Grade\n"
                f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"<i>What would you like to do next?</i>",
                buttons
            )
        else:
            send(tg, "❌ Error saving ID. Please try again.")

# ================= POLLER ===================================
def poller():
    """Telegram update poller"""
    offset = 0
    print("🔄 Removing webhook...")
    requests.post(f"{API}/deleteWebhook", json={"drop_pending_updates": True})
    print("🤖 Bot Poller Started")
    
    while True:
        try:
            updates = requests.post(
                f"{API}/getUpdates",
                json={"offset": offset, "timeout": 30}
            ).json()
            
            for upd in updates.get("result", []):
                offset = upd["update_id"] + 1
                handler(upd)
                
        except Exception as e:
            print("Poller Error:", e)
            time.sleep(5)

# ================= FLASK APP ================================
app = Flask(__name__)

@app.route("/")
def raw_output():
    """Public raw text endpoint - one ID per line"""
    ids = get_all_ids()
    if not ids:
        return Response("No data available", mimetype='text/plain')
    
    response_text = "\n".join(ids)
    return Response(response_text, mimetype='text/plain', headers={
        'Content-Type': 'text/plain; charset=utf-8',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*'
    })

@app.route("/stats")
def public_stats():
    """Public statistics"""
    total, active_users, suspended_users, today, deleted_count = get_stats()
    stats_text = f"""VISHAL X BOT - ENTERPRISE PROTECTION v2.2
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 STATISTICS:
Total IDs: {total}
Active Users: {active_users}
Suspended Users: {suspended_users}
Deleted Users: {deleted_count}
Today Added: {today}

⚙️ CONFIGURATION:
Max Strikes: {MAX_STRIKES}
Suspension: {SUSPEND_DURATION//3600} hour(s)
Double-check Delete: {DOUBLE_CHECK_DELETE}
Scan Interval: {SCAN_TIME}s

📢 Channel: {CHANNEL}
🔗 Endpoint: / (One ID per line)"""
    return Response(stats_text, mimetype='text/plain')

@app.route("/count")
def count():
    """Just the count of active IDs"""
    ids = get_all_ids()
    return Response(str(len(ids)), mimetype='text/plain')

@app.route("/admin")
def admin_panel():
    """Admin access - requires key parameter"""
    key = request.args.get("key")
    if key != ADMIN_KEY:
        return Response("Unauthorized", mimetype='text/plain', status=403)
    
    total, active_users, suspended_users, today, deleted_count = get_stats()
    
    # Get suspended users list
    suspended = get_suspended_users()
    
    # Get recent deletions
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT tg, deleted_at, ids_count 
        FROM deleted_users_log 
        ORDER BY deleted_at DESC 
        LIMIT 10
    """)
    recent_deletions = cur.fetchall()
    
    admin_text = f"""ADMIN PANEL - VISHAL X BOT (ENTERPRISE v2.2)
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 STATS:
Total IDs: {total}
Active Users: {active_users}
Suspended Users: {suspended_users}
Deleted Users: {deleted_count}
Today Added: {today}

⚙️ PROTECTION CONFIG:
Max Strikes: {MAX_STRIKES}
Suspension: {SUSPEND_DURATION//3600} hour(s)
Double-check: {DOUBLE_CHECK_DELETE}
Scan: {SCAN_TIME}s

⏸️ SUSPENDED USERS ({len(suspended)}):"""
    
    for row in suspended:
        tg, until = row['tg'], row['suspended_until']
        time_left = ""
        if until:
            until_dt = datetime.strptime(until, '%Y-%m-%d %H:%M:%S')
            sec_left = (until_dt - datetime.now()).seconds
            hours = sec_left // 3600
            minutes = (sec_left % 3600) // 60
            time_left = f" ({hours}h {minutes}m left)"
        admin_text += f"\n• {tg}{time_left}"
    
    admin_text += f"\n\n🗑️ RECENT DELETIONS (last 10):"
    for row in recent_deletions:
        admin_text += f"\n• {row['tg']} ({row['ids_count']} IDs) at {row['deleted_at']}"
    
    admin_text += f"\n\n🔗 ENDPOINTS:\nRAW: /\nEXPORT: /export?key={ADMIN_KEY}"
    
    return Response(admin_text, mimetype='text/plain')

@app.route("/export")
def admin_export():
    """Admin export with metadata"""
    key = request.args.get("key")
    if key != ADMIN_KEY:
        return Response("Unauthorized", mimetype='text/plain', status=403)
    
    ids = get_all_ids()
    total = len(ids)
    
    export_text = f"""# VISHAL X BOT EXPORT - ENTERPRISE EDITION v2.2
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# Total IDs: {total}
# Channel: {CHANNEL}
# Protection: {MAX_STRIKES}-strike system
# Double-check: {DOUBLE_CHECK_DELETE}
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
        "version": "2.2",
        "protection": "enterprise_grade",
        "max_strikes": MAX_STRIKES,
        "suspension_hours": SUSPEND_DURATION//3600,
        "double_check": DOUBLE_CHECK_DELETE,
        "scan_interval": SCAN_TIME,
        "total_ids": len(get_all_ids()),
        "database_threads": len(db_manager.connections)
    })

# ================= CLEANUP ==================================
import atexit

@atexit.register
def cleanup():
    """Cleanup resources on exit"""
    print("🔄 Cleaning up resources...")
    db_manager.close_all()
    print("✅ Cleanup completed")

# ================= RUN ======================================
if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 VISHAL X BOT - ENTERPRISE PROTECTION v2.2")
    print("="*70)
    print(f"✅ CRITICAL FIXES APPLIED:")
    print(f"   1️⃣ ensure_user_state() - All users in monitor")
    print(f"   2️⃣ status='deleted' set before actual delete")
    print(f"   3️⃣ Thread-safe database connections")
    print(f"   4️⃣ last_check updated even on API errors")
    print(f"📊 CONFIG: {MAX_STRIKES} strikes | {SUSPEND_DURATION//3600} hour suspension")
    print(f"📡 SCAN INTERVAL: {SCAN_TIME} seconds")
    print(f"🌐 PUBLIC ENDPOINT: http://localhost:{PORT}/")
    print(f"📊 STATS: http://localhost:{PORT}/stats")
    print("="*70)
    print("✅ FINAL PROTECTION FLOW:")
    print("1. /start → ensure_user_state() → user_states entry created")
    print("2. Active users only in monitor")
    print("3. API error → last_check updated, no strike")
    print("4. Leave → strike++ → warning (once)")
    print("5. 3 strikes → suspend → notification (once)")
    print("6. 1 hour → double-check → status='deleted' → delete → log")
    print("7. Rejoin anytime → full restore")
    print("="*70 + "\n")
    
    # Start monitor and poller in threads
    threading.Thread(target=monitor, daemon=True).start()
    threading.Thread(target=poller, daemon=True).start()
    
    # Start Flask app
    app.run(host="0.0.0.0", port=PORT, debug=False)