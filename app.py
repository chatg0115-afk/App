import os
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
import traceback

# ==========================
# CONFIGURATION
# ==========================
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8504965473:AAE9dn_5_ZhEQKdekcgi3chIBHRsJNfC-Ms')
CHANNEL = os.environ.get('CHANNEL', '@Vishalxnetwork4')
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
PORT = int(os.environ.get('PORT', 10000))
ADMIN_USERNAME = "@vishalxtg45"
ADMIN_IDS = [int(x) for x in os.environ.get('ADMIN_IDS', '6493515910').split(',')]

# ==========================
# LOGGING SETUP
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger()

# ==========================
# DATABASE - ENHANCED
# ==========================
class EnhancedDatabase:
    """Enhanced database with performance monitoring"""
    
    def __init__(self):
        self.db_path = '/tmp/auth_bot.db' if 'RENDER' in os.environ else 'auth_bot.db'
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_tables()
        self.query_count = 0
        self.start_time = time.time()
    
    def init_tables(self):
        """Initialize all tables with enhanced features"""
        cursor = self.conn.cursor()
        
        # Enhanced authorized_ids table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS authorized_ids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            display_name TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP DEFAULT (datetime('now', '+30 days')),
            status TEXT DEFAULT 'active',
            flags INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            UNIQUE(user_id, telegram_id)
        )
        ''')
        
        # Enhanced channel_members table (FIXED: removed problematic column)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS channel_members (
            telegram_id INTEGER PRIMARY KEY,
            is_member BOOLEAN DEFAULT 0,
            status TEXT DEFAULT 'left',
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            check_count INTEGER DEFAULT 0
        )
        ''')
        
        # Enhanced removal_log table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS removal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            reason TEXT,
            ids_removed INTEGER DEFAULT 0,
            removed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            auto_rejoin BOOLEAN DEFAULT 0
        )
        ''')
        
        # Statistics table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric TEXT NOT NULL,
            value INTEGER DEFAULT 0,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # User activity log
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Bot performance metrics
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        self.conn.commit()
        logger.info("✅ Enhanced database initialized")
    
    def execute(self, query, params=()):
        """Track and execute queries"""
        self.query_count += 1
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return cursor
        except sqlite3.Error as e:
            logger.error(f"Database error in query '{query[:50]}...': {e}")
            # Try to reconnect
            self.reconnect()
            try:
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                return cursor
            except:
                return None
        except Exception as e:
            logger.error(f"Database error: {e}")
            return None
    
    def reconnect(self):
        """Reconnect to database"""
        try:
            self.conn.close()
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            logger.info("Database reconnected")
        except Exception as e:
            logger.error(f"Failed to reconnect: {e}")
    
    def commit(self):
        try:
            self.conn.commit()
        except:
            self.reconnect()
    
    def close(self):
        try:
            self.conn.close()
        except:
            pass
    
    def get_performance_stats(self):
        """Get database performance statistics"""
        uptime = time.time() - self.start_time
        qps = self.query_count / uptime if uptime > 0 else 0
        db_size = 0
        if os.path.exists(self.db_path):
            db_size = os.path.getsize(self.db_path)
        
        return {
            'query_count': self.query_count,
            'uptime_seconds': int(uptime),
            'queries_per_second': round(qps, 2),
            'database_size': db_size
        }

# Initialize database
db = EnhancedDatabase()

# ==========================
# FLASK APP
# ==========================
app = Flask(__name__)

# ==========================
# REAL-TIME MONITORING SYSTEM
# ==========================
class RealTimeMonitor:
    """Real-time monitoring with background refresh"""
    
    def __init__(self):
        self.last_check = {}
        self.user_status = {}
        self.alert_queue = []
        self.metrics = {
            'api_calls': 0,
            'membership_checks': 0,
            'ids_added': 0,
            'ids_removed': 0,
            'errors': 0,
            'messages_sent': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        self.start_time = time.time()
    
    def record_metric(self, metric, value=1):
        """Record performance metric"""
        if metric in self.metrics:
            self.metrics[metric] += value
        else:
            self.metrics[metric] = value
    
    def get_uptime(self):
        """Get formatted uptime"""
        uptime = time.time() - self.start_time
        days = int(uptime // 86400)
        hours = int((uptime % 86400) // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        else:
            return f"{minutes}m {seconds}s"
    
    def get_system_health(self):
        """Get system health score"""
        if self.metrics['api_calls'] == 0:
            return 100.0
        
        error_rate = self.metrics['errors'] / max(self.metrics['api_calls'], 1)
        health_score = max(0, 100 - (error_rate * 100))
        return min(100, health_score)
    
    def get_cache_efficiency(self):
        """Get cache hit rate"""
        total_cache = self.metrics.get('cache_hits', 0) + self.metrics.get('cache_misses', 0)
        if total_cache == 0:
            return 0.0
        return (self.metrics.get('cache_hits', 0) / total_cache) * 100

monitor = RealTimeMonitor()

# ==========================
# TELEGRAM API - ENHANCED
# ==========================
def telegram_request(method: str, data: Dict = None, retries: int = 3) -> Optional[Dict]:
    """Enhanced Telegram API request with retry logic"""
    for attempt in range(retries):
        try:
            monitor.record_metric('api_calls')
            url = f"{API}/{method}"
            response = requests.post(url, json=data or {}, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return result
                else:
                    logger.warning(f"API not OK: {result.get('description', 'Unknown error')}")
                    monitor.record_metric('errors')
            elif response.status_code == 429:  # Rate limited
                retry_after = int(response.headers.get('Retry-After', 30))
                logger.warning(f"Rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                continue
            else:
                logger.error(f"API error {response.status_code}: {method}")
                monitor.record_metric('errors')
                
        except requests.exceptions.Timeout:
            logger.warning(f"API timeout: {method} (attempt {attempt + 1}/{retries})")
            time.sleep(2 ** attempt)  # Exponential backoff
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error: {method}")
            time.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"API request failed: {e}")
            monitor.record_metric('errors')
            time.sleep(1)
    
    return None

def send_enhanced_message(chat_id: int, text: str, **kwargs) -> bool:
    """Send message with enhanced features"""
    try:
        # Add typing action
        telegram_request("sendChatAction", {
            "chat_id": chat_id,
            "action": "typing"
        })
        
        # Prepare message data
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "disable_notification": kwargs.get('silent', False)
        }
        
        # Add reply markup if provided
        if 'reply_markup' in kwargs:
            data['reply_markup'] = json.dumps(kwargs['reply_markup'])
        
        # Send message
        result = telegram_request("sendMessage", data)
        if result and result.get("ok"):
            monitor.record_metric('messages_sent')
            return True
        return False
    except Exception as e:
        logger.error(f"Send message error: {e}")
        return False

# ==========================
# CHANNEL CHECKING - REAL-TIME (1 SECOND)
# ==========================
@lru_cache(maxsize=1000)
def check_membership_cached(telegram_id: int) -> tuple:
    """Cached membership check for performance"""
    monitor.record_metric('membership_checks')
    
    # Check database cache first (cache for 5 seconds)
    cursor = db.execute(
        """SELECT is_member, status FROM channel_members 
           WHERE telegram_id = ? AND last_seen > datetime('now', '-5 seconds')""",
        (telegram_id,)
    )
    
    if cursor:
        row = cursor.fetchone()
        if row:
            monitor.record_metric('cache_hits')
            return bool(row['is_member']), row['status']
    
    monitor.record_metric('cache_misses')
    
    # Fresh API check
    result = telegram_request("getChatMember", {
        "chat_id": CHANNEL,
        "user_id": telegram_id
    })
    
    if result and result.get("ok"):
        status = result["result"].get("status", "left")
        is_member = status in ["member", "administrator", "creator"]
        
        # Update database (FIXED: Simplified query)
        try:
            db.execute(
                """INSERT OR REPLACE INTO channel_members 
                   (telegram_id, is_member, status, last_seen, check_count) 
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP, 
                   COALESCE((SELECT check_count FROM channel_members WHERE telegram_id = ?), 0) + 1)""",
                (telegram_id, 1 if is_member else 0, status, telegram_id)
            )
            db.commit()
        except Exception as e:
            logger.error(f"Error updating membership: {e}")
        
        return is_member, status
    
    return False, "error"

# ==========================
# ULTRA-FAST BACKGROUND MONITOR (1 SECOND)
# ==========================
class UltraFastMonitor:
    """1-second interval monitoring system"""
    
    @staticmethod
    def real_time_refresh():
        """Real-time refresh every second"""
        logger.info("🔄 Starting ultra-fast refresh system (1s interval)")
        refresh_count = 0
        
        while True:
            try:
                refresh_count += 1
                
                # Clear cache every minute to prevent stale data
                if refresh_count % 60 == 0:
                    check_membership_cached.cache_clear()
                    logger.debug("🧹 Cache cleared")
                
                # Sleep for exactly 1 second
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Refresh error: {e}")
                time.sleep(5)
    
    @staticmethod
    def anti_leave_monitor():
        """1-second anti-leave monitor"""
        logger.info("🛡️ Starting 1-second anti-leave monitor")
        
        while True:
            try:
                start_time = time.time()
                
                # Get all active users
                cursor = db.execute(
                    "SELECT DISTINCT telegram_id FROM authorized_ids WHERE status = 'active'"
                )
                
                if cursor:
                    users = [row['telegram_id'] for row in cursor.fetchall()]
                    
                    if users:
                        # Check each user in parallel threads for speed
                        threads = []
                        for telegram_id in users[:50]:  # Limit to 50 users per batch
                            thread = threading.Thread(
                                target=UltraFastMonitor.check_single_user,
                                args=(telegram_id,),
                                daemon=True
                            )
                            threads.append(thread)
                            thread.start()
                        
                        # Wait for all checks to complete
                        for thread in threads:
                            thread.join(timeout=2)
                
                # Calculate exact sleep time to maintain 1-second interval
                elapsed = time.time() - start_time
                sleep_time = max(0.1, 1.0 - elapsed)  # Never sleep less than 0.1s
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(5)
    
    @staticmethod
    def check_single_user(telegram_id: int):
        """Check single user's membership (thread-safe)"""
        try:
            is_member, status = check_membership_cached(telegram_id)
            
            if not is_member:
                # Count IDs to remove
                count_cursor = db.execute(
                    "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'active'",
                    (telegram_id,)
                )
                count_row = count_cursor.fetchone() if count_cursor else None
                count = count_row['count'] if count_row else 0
                
                if count > 0:
                    # Remove IDs
                    db.execute(
                        "UPDATE authorized_ids SET status = 'removed' WHERE telegram_id = ? AND status = 'active'",
                        (telegram_id,)
                    )
                    
                    # Log removal
                    db.execute(
                        """INSERT INTO removal_log (telegram_id, reason, ids_removed) 
                           VALUES (?, ?, ?)""",
                        (telegram_id, f"anti_leave_{status}", count)
                    )
                    
                    # Update statistics
                    db.execute(
                        "INSERT INTO statistics (metric, value) VALUES (?, ?)",
                        ("ids_removed", count)
                    )
                    
                    db.commit()
                    monitor.record_metric('ids_removed', count)
                    
                    logger.warning(f"🚫 Removed {count} IDs for user {telegram_id} (status: {status})")
                    
                    # Send notification (non-blocking)
                    threading.Thread(
                        target=send_enhanced_message,
                        args=(telegram_id, 
                              f"⚠️ <b>ACCESS REVOKED</b>\n\n"
                              f"Your {count} authorized ID(s) have been removed.\n"
                              f"Reason: Left {CHANNEL}\n"
                              f"Status: {status}\n\n"
                              f"Rejoin and use /start to re-authorize."),
                        daemon=True
                    ).start()
                    
        except Exception as e:
            logger.error(f"User check error {telegram_id}: {e}")

# ==========================
# BOT HANDLERS - OPTIMIZED
# ==========================
def handle_enhanced_start(telegram_id: int, user_name: str, username: str = None):
    """Enhanced start handler with real-time check"""
    # Immediate 1-second check
    is_member, status = check_membership_cached(telegram_id)
    
    # Log activity
    db.execute(
        "INSERT INTO user_activity (telegram_id, action, details) VALUES (?, ?, ?)",
        (telegram_id, "start", json.dumps({
            "is_member": is_member,
            "status": status,
            "username": username,
            "user_name": user_name
        }))
    )
    db.commit()
    
    if is_member:
        # Get user stats
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'active'",
            (telegram_id,)
        )
        row = cursor.fetchone() if cursor else None
        user_ids = row['count'] if row else 0
        
        # Create interactive keyboard
        keyboard = {
            "inline_keyboard": [
                [{"text": "➕ Add ID", "callback_data": "add_id"}],
                [{"text": "🔄 Check Now", "callback_data": "check_now"}],
                [{"text": "📊 My Stats", "callback_data": "my_stats"}]
            ]
        }
        
        message = f"""✅ <b>ACCESS GRANTED</b>

👤 Welcome, {html.escape(user_name)}!
🛡️ Channel Status: <b>{status.upper()}</b>
📊 Your IDs: {user_ids} active

⚡ <b>Real-time Protection Active:</b>
• 1-second monitoring
• Anti-leave system: ENABLED
• Cache: FRESH

<code>🕐 {datetime.now().strftime('%H:%M:%S')}</code>

<i>Send any ID to add it instantly!</i>"""
        
        send_enhanced_message(telegram_id, message, reply_markup=keyboard)
    else:
        keyboard = {
            "inline_keyboard": [
                [{"text": "✅ Join Channel", "url": f"https://t.me/{CHANNEL[1:]}"}],
                [{"text": "🔄 Check Again", "callback_data": "check_again"}]
            ]
        }
        
        message = f"""🔒 <b>ACCESS REQUIRED</b>

Hello {html.escape(user_name)}!

📢 <b>Required Channel:</b> {CHANNEL}
⚠️ <b>Current Status:</b> {status.upper()}

📋 <b>Steps:</b>
1. Join {CHANNEL}
2. Tap '🔄 Check Again'
3. Send /start

⚡ <b>Features after joining:</b>
• Instant ID authorization
• 1-second real-time monitoring
• Anti-leave protection
• Priority support

<code>Checked at: {datetime.now().strftime('%H:%M:%S')}</code>"""
        
        send_enhanced_message(telegram_id, message, reply_markup=keyboard)

def handle_id_addition(telegram_id: int, user_name: str, user_id: str, username: str = None):
    """Fast ID addition with 1-second validation"""
    # Step 1: Validation
    user_id = user_id.strip()
    if not user_id or len(user_id) < 3 or len(user_id) > 100:
        send_enhanced_message(telegram_id, "❌ <b>Invalid ID</b>\n\nID must be 3-100 characters.")
        return
    
    # Step 2: Real-time 1-second check
    send_enhanced_message(telegram_id, "🔄 <i>Real-time verification...</i>")
    is_member, status = check_membership_cached(telegram_id)
    
    if not is_member:
        send_enhanced_message(
            telegram_id,
            f"❌ <b>ACCESS DENIED</b>\n\n"
            f"Join {CHANNEL} to add IDs.\n"
            f"Status: <b>{status.upper()}</b>"
        )
        return
    
    # Step 3: Check for duplicates
    cursor = db.execute(
        "SELECT user_id FROM authorized_ids WHERE user_id = ? AND status = 'active'",
        (user_id,)
    )
    if cursor and cursor.fetchone():
        send_enhanced_message(
            telegram_id,
            f"⚠️ <b>ID Exists</b>\n\n"
            f"<code>{html.escape(user_id)}</code> is already authorized."
        )
        return
    
    # Step 4: Add to database
    try:
        db.execute(
            """INSERT INTO authorized_ids (user_id, telegram_id, username, display_name) 
               VALUES (?, ?, ?, ?)""",
            (user_id, telegram_id, username, user_name)
        )
        db.commit()
        monitor.record_metric('ids_added')
        
        # Get updated counts
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'active'",
            (telegram_id,)
        )
        row = cursor.fetchone() if cursor else None
        user_total = row['count'] if row else 0
        
        success_msg = f"""✅ <b>ID AUTHORIZED!</b>

🎯 <b>ID:</b> <code>{html.escape(user_id)}</code>
👤 <b>User:</b> {html.escape(user_name)}
📊 <b>Your Total IDs:</b> {user_total}
⚡ <b>Status:</b> ACTIVE
🛡️ <b>Protection:</b> Real-time monitoring ENABLED

<code>⏱️ Processed in under 1 second</code>

<i>Stay in {CHANNEL} to keep your IDs active!</i>"""
        
        send_enhanced_message(telegram_id, success_msg)
        
    except sqlite3.IntegrityError:
        send_enhanced_message(
            telegram_id,
            f"⚠️ <b>ID Already Exists</b>\n\n"
            f"<code>{html.escape(user_id)}</code> is already in the system."
        )
    except Exception as e:
        logger.error(f"ID addition error: {e}")
        send_enhanced_message(telegram_id, "❌ <b>Database Error</b>\n\nPlease try again.")

# ==========================
# BOT POLLING - ULTRA FAST
# ==========================
def ultra_fast_bot_polling():
    """Ultra-fast bot polling with 1-second response"""
    offset = 0
    logger.info("🤖 Starting ultra-fast bot polling...")
    
    while True:
        try:
            result = telegram_request("getUpdates", {
                "offset": offset,
                "timeout": 1,  # 1-second timeout
                "allowed_updates": ["message", "callback_query"]
            })
            
            if result and result.get("ok"):
                updates = result.get("result", [])
                
                for update in updates:
                    offset = update["update_id"] + 1
                    
                    # Handle messages
                    if "message" in update:
                        msg = update["message"]
                        telegram_id = msg.get("from", {}).get("id")
                        user_name = msg.get("from", {}).get("first_name", "User")
                        username = msg.get("from", {}).get("username")
                        text = msg.get("text", "").strip()
                        
                        if not telegram_id:
                            continue
                        
                        logger.info(f"📨 Message from {telegram_id} ({user_name}): {text[:50]}")
                        
                        if text == "/start":
                            threading.Thread(
                                target=handle_enhanced_start,
                                args=(telegram_id, user_name, username),
                                daemon=True
                            ).start()
                        elif text == "/stats":
                            send_user_stats(telegram_id, user_name)
                        elif text and not text.startswith('/'):
                            threading.Thread(
                                target=handle_id_addition,
                                args=(telegram_id, user_name, text, username),
                                daemon=True
                            ).start()
                    
                    # Handle callback queries
                    elif "callback_query" in update:
                        callback = update["callback_query"]
                        callback_data = callback.get("data")
                        telegram_id = callback.get("from", {}).get("id")
                        user_name = callback.get("from", {}).get("first_name", "User")
                        
                        if telegram_id and callback_data:
                            telegram_request("answerCallbackQuery", {
                                "callback_query_id": callback["id"]
                            })
                            
                            if callback_data == "check_again":
                                threading.Thread(
                                    target=handle_enhanced_start,
                                    args=(telegram_id, user_name),
                                    daemon=True
                                ).start()
                            elif callback_data == "check_now":
                                is_member, status = check_membership_cached(telegram_id)
                                send_enhanced_message(
                                    telegram_id,
                                    f"🔄 <b>REAL-TIME CHECK</b>\n\n"
                                    f"Status: <b>{status.upper()}</b>\n"
                                    f"Member: {'✅ YES' if is_member else '❌ NO'}\n\n"
                                    f"<code>Checked at: {datetime.now().strftime('%H:%M:%S')}</code>"
                                )
            
            time.sleep(0.1)  # Ultra-fast polling
            
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(1)

def send_user_stats(telegram_id: int, user_name: str):
    """Send user statistics"""
    try:
        # Get user's IDs
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'active'",
            (telegram_id,)
        )
        row = cursor.fetchone() if cursor else None
        user_ids = row['count'] if row else 0
        
        # Get membership status (1-second check)
        is_member, status = check_membership_cached(telegram_id)
        
        # Get system stats
        cursor = db.execute("SELECT COUNT(*) as total FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        total_ids = row['total'] if row else 0
        
        cursor = db.execute("SELECT COUNT(DISTINCT telegram_id) as users FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        unique_users = row['users'] if row else 0
        
        message = f"""📊 <b>YOUR STATISTICS</b>

👤 <b>Profile:</b>
• Name: {html.escape(user_name)}
• Telegram ID: <code>{telegram_id}</code>
• Channel Status: {status.upper()} {'✅' if is_member else '❌'}

📈 <b>Your Data:</b>
• Authorized IDs: {user_ids}
• Last Check: {datetime.now().strftime('%H:%M:%S')}

🌐 <b>System Stats:</b>
• Total IDs: {total_ids}
• Active Users: {unique_users}
• Uptime: {monitor.get_uptime()}

⚡ <b>Performance:</b>
• Refresh Rate: 1 second
• Health Score: {monitor.get_system_health():.1f}%
• Real-time: ACTIVE

<code>🔄 Updated every second</code>"""
        
        send_enhanced_message(telegram_id, message)
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        send_enhanced_message(telegram_id, "❌ <b>Error fetching statistics</b>")

# ==========================
# FLASK ROUTES - SIMPLIFIED
# ==========================
@app.route('/')
def premium_dashboard():
    """Simple professional dashboard"""
    try:
        # Get stats
        cursor = db.execute("SELECT COUNT(*) as total FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        total_ids = row['total'] if row else 0
        
        cursor = db.execute("SELECT COUNT(DISTINCT telegram_id) as users FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        unique_users = row['users'] if row else 0
        
        html_template = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>🛡️ Vishal Auth System PRO</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    margin: 0;
                    padding: 20px;
                    min-height: 100vh;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    text-align: center;
                    padding: 40px 0;
                    background: rgba(255,255,255,0.1);
                    border-radius: 20px;
                    margin-bottom: 30px;
                    backdrop-filter: blur(10px);
                }}
                .header h1 {{
                    font-size: 3rem;
                    margin: 0;
                    color: white;
                }}
                .header p {{
                    font-size: 1.2rem;
                    opacity: 0.9;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 40px;
                }}
                .stat-card {{
                    background: rgba(255,255,255,0.1);
                    padding: 30px;
                    border-radius: 15px;
                    text-align: center;
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255,255,255,0.2);
                    transition: transform 0.3s;
                }}
                .stat-card:hover {{
                    transform: translateY(-5px);
                }}
                .stat-value {{
                    font-size: 3rem;
                    font-weight: bold;
                    margin: 10px 0;
                }}
                .stat-label {{
                    font-size: 1rem;
                    opacity: 0.9;
                }}
                .live-status {{
                    background: rgba(16, 185, 129, 0.2);
                    padding: 20px;
                    border-radius: 15px;
                    margin-bottom: 30px;
                    text-align: center;
                    border: 2px solid rgba(16, 185, 129, 0.3);
                }}
                .status-dot {{
                    width: 12px;
                    height: 12px;
                    background: #10b981;
                    border-radius: 50%;
                    display: inline-block;
                    margin-right: 10px;
                    animation: pulse 1.5s infinite;
                }}
                @keyframes pulse {{
                    0% {{ opacity: 1; }}
                    50% {{ opacity: 0.5; }}
                    100% {{ opacity: 1; }}
                }}
                .api-links {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                }}
                .api-link {{
                    display: block;
                    background: rgba(255,255,255,0.1);
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    color: white;
                    text-decoration: none;
                    transition: background 0.3s;
                }}
                .api-link:hover {{
                    background: rgba(255,255,255,0.2);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🛡️ Vishal Auth System PRO</h1>
                    <p>Ultimate Protection • 1-Second Monitoring • Real-time Anti-Leave</p>
                </div>
                
                <div class="live-status">
                    <div class="status-dot"></div>
                    <strong>LIVE • 1-SECOND REFRESH • {monitor.get_uptime()} UPTIME</strong>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">{total_ids}</div>
                        <div class="stat-label">Authorized IDs</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{unique_users}</div>
                        <div class="stat-label">Active Users</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{monitor.metrics.get('api_calls', 0)}</div>
                        <div class="stat-label">API Calls</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{monitor.get_system_health():.1f}%</div>
                        <div class="stat-label">Health Score</div>
                    </div>
                </div>
                
                <div class="api-links">
                    <a href="/auth" target="_blank" class="api-link">📋 All Authorized IDs</a>
                    <a href="/stats" target="_blank" class="api-link">📊 System Statistics</a>
                    <a href="/health" target="_blank" class="api-link">❤️ Health Check</a>
                </div>
                
                <div style="margin-top: 40px; text-align: center; opacity: 0.8;">
                    <p>Channel: <strong>{CHANNEL}</strong> • Admin: <strong>{ADMIN_USERNAME}</strong></p>
                    <p>⚡ Real-time 1-second monitoring • 🛡️ Anti-leave protection • 🔄 Auto-refresh</p>
                </div>
            </div>
            
            <script>
                // Auto-refresh stats every 5 seconds
                setInterval(() => {{
                    location.reload();
                }}, 5000);
            </script>
        </body>
        </html>
        '''
        return render_template_string(html_template)
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/auth')
def get_auth():
    """Get all authorized IDs"""
    try:
        cursor = db.execute(
            "SELECT user_id, telegram_id, added_at FROM authorized_ids WHERE status = 'active' ORDER BY added_at DESC"
        )
        if cursor:
            ids = [dict(row) for row in cursor.fetchall()]
            return jsonify(ids)
        return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stats')
def get_stats():
    """Get system statistics"""
    try:
        cursor = db.execute("SELECT COUNT(*) as total FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        total_ids = row['total'] if row else 0
        
        cursor = db.execute("SELECT COUNT(DISTINCT telegram_id) as users FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        unique_users = row['users'] if row else 0
        
        return jsonify({
            'total_ids': total_ids,
            'unique_users': unique_users,
            'uptime': monitor.get_uptime(),
            'health_score': monitor.get_system_health(),
            'api_calls': monitor.metrics.get('api_calls', 0),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime': monitor.get_uptime(),
        'monitoring': '1-second real-time',
        'anti_leave': 'active'
    })

# ==========================
# STARTUP AND BACKGROUND SERVICES
# ==========================
def startup_sequence():
    """Start all background services"""
    print("\n" + "="*70)
    print("🚀 VISHAL AUTH SYSTEM PRO - ULTIMATE EDITION".center(70))
    print("="*70)
    
    # Test database connection
    try:
        cursor = db.execute("SELECT 1")
        print("✅ Database connection: OK")
    except Exception as e:
        print(f"❌ Database connection: FAILED - {e}")
        return
    
    # Test Telegram API
    try:
        result = telegram_request("getMe")
        if result and result.get("ok"):
            bot_name = result["result"].get("first_name", "Unknown")
            print(f"✅ Telegram API: OK (Bot: {bot_name})")
        else:
            print("❌ Telegram API: FAILED - Check BOT_TOKEN")
            return
    except Exception as e:
        print(f"❌ Telegram API: FAILED - {e}")
        return
    
    # Start ultra-fast background threads
    threads = [
        threading.Thread(target=ultra_fast_bot_polling, daemon=True, name="UltraFastBot"),
        threading.Thread(target=UltraFastMonitor.real_time_refresh, daemon=True, name="1sRefresh"),
        threading.Thread(target=UltraFastMonitor.anti_leave_monitor, daemon=True, name="1sAntiLeave")
    ]
    
    for thread in threads:
        thread.start()
        time.sleep(0.1)  # Stagger startup
    
    print("✅ All services started:")
    print("   • Ultra-fast bot polling (1s)")
    print("   • 1-second real-time refresh")
    print("   • 1-second anti-leave monitor")
    print(f"\n🌐 Web Dashboard: http://localhost:{PORT}")
    print(f"📊 Stats API: /stats")
    print(f"🔐 Auth Data: /auth")
    print(f"❤️ Health: /health")
    print("\n⚡ Premium Features:")
    print("   • 1-second real-time monitoring")
    print("   • Instant anti-leave protection")
    print("   • Professional dashboard")
    print("   • Performance optimized")
    print("="*70)
    print("🎯 SYSTEM READY - 1-SECOND MONITORING ACTIVE")
    print("="*70 + "\n")

# Cleanup on exit
def cleanup():
    """Cleanup on exit"""
    logger.info("Cleaning up...")
    db.close()

atexit.register(cleanup)

# ==========================
# MAIN ENTRY POINT
# ==========================
if __name__ == "__main__":
    try:
        startup_sequence()
        app.run(
            host='0.0.0.0',
            port=PORT,
            debug=False,
            threaded=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down gracefully...")
        cleanup()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
        cleanup()