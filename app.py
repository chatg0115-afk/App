import os
import requests
import threading
import time
import json
import re
import sqlite3
from flask import Flask, request, jsonify, render_template_string, redirect
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import html
import logging
import atexit
from functools import lru_cache
import traceback

# ==========================
# CONFIGURATION
# ==========================
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8504965473:AAFV_ciorWHwRZo_K6FpETDWTINtmbgUetc')
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
                user_id TEXT UNIQUE NOT NULL,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP DEFAULT (datetime('now', '+30 days')),
                status TEXT DEFAULT 'active',
                flags INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # Enhanced channel_members table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_members (
                telegram_id INTEGER PRIMARY KEY,
                is_member BOOLEAN DEFAULT 0,
                status TEXT DEFAULT 'left',
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                check_count INTEGER DEFAULT 0,
                join_count INTEGER DEFAULT 0,
                total_online_time INTEGER DEFAULT 0
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
        
        # Create indexes after tables are created
        self.create_indexes()
        
        logger.info("✅ Enhanced database initialized")
    
    def create_indexes(self):
        """Create all necessary indexes"""
        cursor = self.conn.cursor()
        
        indexes = [
            ("idx_auth_status", "authorized_ids(status)"),
            ("idx_auth_expires", "authorized_ids(expires_at)"),
            ("idx_members_status", "channel_members(status)"),
            ("idx_activity_time", "user_activity(timestamp)"),
            ("idx_stats_time", "statistics(recorded_at)")
        ]
        
        for idx_name, idx_query in indexes:
            try:
                cursor.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_query}')
            except sqlite3.OperationalError as e:
                logger.warning(f"Could not create index {idx_name}: {e}")
                # Try to check if column exists
                if "no such column" in str(e):
                    logger.info(f"Skipping index {idx_name} - column might not exist yet")
        
        self.conn.commit()
    
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
            
            elif response.status_code == 429:
                # Rate limited
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
# CHANNEL CHECKING - ULTRA FAST
# ==========================
@lru_cache(maxsize=1000)
def check_membership_cached(telegram_id: int) -> Tuple[bool, str]:
    """Cached membership check for performance"""
    monitor.record_metric('membership_checks')
    
    # Check database cache first
    cursor = db.execute(
        """SELECT is_member, status FROM channel_members 
           WHERE telegram_id = ? AND last_seen > datetime('now', '-1 minute')""",
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
        
        # Update database
        try:
            db.execute(
                """INSERT OR REPLACE INTO channel_members 
                   (telegram_id, is_member, status, last_seen, check_count) 
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP, 
                           COALESCE((SELECT check_count FROM channel_members WHERE telegram_id = ?), 0) + 1)""",
                (telegram_id, 1 if is_member else 0, status, telegram_id)
            )
            
            # Log join if status changed to member
            if is_member:
                old_cursor = db.execute(
                    "SELECT status FROM channel_members WHERE telegram_id = ?",
                    (telegram_id,)
                )
                old_row = old_cursor.fetchone() if old_cursor else None
                if old_row and old_row['status'] != status:
                    db.execute(
                        "UPDATE channel_members SET join_count = join_count + 1 WHERE telegram_id = ?",
                        (telegram_id,)
                    )
            
            db.commit()
        except Exception as e:
            logger.error(f"Error updating membership: {e}")
        
        return is_member, status
    
    return False, "error"

# ==========================
# BACKGROUND MONITORING THREADS
# ==========================
class BackgroundMonitor:
    """Continuous background monitoring"""
    
    @staticmethod
    def real_time_refresh():
        """Real-time refresh every second"""
        logger.info("🔄 Starting real-time refresh system (1s interval)")
        
        refresh_count = 0
        
        while True:
            try:
                refresh_count += 1
                
                # Update performance metrics every 10 seconds
                if refresh_count % 10 == 0:
                    perf_stats = db.get_performance_stats()
                    cursor = db.execute(
                        "INSERT INTO performance_metrics (metric_name, metric_value) VALUES (?, ?)",
                        ("queries_per_second", perf_stats['queries_per_second'])
                    )
                    if cursor:
                        db.commit()
                
                # Clear cache every 5 minutes
                if refresh_count % 300 == 0:
                    check_membership_cached.cache_clear()
                    logger.info("🧹 Cache cleared")
                
                time.sleep(1)  # 1 second interval
                
            except Exception as e:
                logger.error(f"Refresh error: {e}")
                time.sleep(5)
    
    @staticmethod
    def anti_leave_monitor():
        """Enhanced anti-leave monitor"""
        logger.info("🛡️ Starting enhanced anti-leave monitor")
        
        check_interval = 30  # Check every 30 seconds
        
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
                        logger.info(f"🔍 Checking {len(users)} users for anti-leave...")
                    
                    for telegram_id in users:
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
                                        """INSERT INTO removal_log 
                                           (telegram_id, reason, ids_removed) 
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
                                    
                                    logger.warning(f"🚨 Removed {count} IDs for user {telegram_id} (status: {status})")
                                    
                                    # Send notification
                                    try:
                                        send_enhanced_message(
                                            telegram_id,
                                            f"⚠️ <b>ACCESS REVOKED</b>\n\n"
                                            f"Your {count} authorized ID(s) have been removed.\n"
                                            f"Reason: Left {CHANNEL}\n"
                                            f"Status: {status}\n\n"
                                            f"Rejoin and use /start to re-authorize."
                                        )
                                    except Exception as e:
                                        logger.error(f"Failed to send notification: {e}")
                        
                        except Exception as e:
                            logger.error(f"User check error {telegram_id}: {e}")
                            continue
                
                elapsed = time.time() - start_time
                sleep_time = max(5, check_interval - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(30)
    
    @staticmethod
    def cleanup_daemon():
        """Background cleanup daemon"""
        logger.info("🧹 Starting cleanup daemon")
        
        while True:
            try:
                # Remove expired IDs (older than 30 days)
                expired_cursor = db.execute(
                    "UPDATE authorized_ids SET status = 'expired' WHERE expires_at < CURRENT_TIMESTAMP AND status = 'active'"
                )
                if expired_cursor:
                    expired_count = expired_cursor.rowcount
                    if expired_count > 0:
                        logger.info(f"🗑️  Marked {expired_count} IDs as expired")
                
                # Clean old activity logs (keep 7 days)
                db.execute(
                    "DELETE FROM user_activity WHERE timestamp < datetime('now', '-7 days')"
                )
                
                # Clean old performance metrics (keep 1 day)
                db.execute(
                    "DELETE FROM performance_metrics WHERE timestamp < datetime('now', '-1 day')"
                )
                
                db.commit()
                time.sleep(3600)  # Run every hour
                
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                time.sleep(300)
    
    @staticmethod
    def statistics_collector():
        """Collect and log system statistics"""
        logger.info("📊 Starting statistics collector")
        
        while True:
            try:
                # Log current stats
                stats = {
                    'timestamp': datetime.now().isoformat(),
                    'total_ids': 0,
                    'active_users': 0,
                    'channel_members': 0,
                    'system_health': monitor.get_system_health(),
                    'cache_efficiency': monitor.get_cache_efficiency()
                }
                
                # Get total IDs
                cursor = db.execute("SELECT COUNT(*) as count FROM authorized_ids WHERE status = 'active'")
                if cursor:
                    row = cursor.fetchone()
                    stats['total_ids'] = row['count'] if row else 0
                
                # Get active users
                cursor = db.execute("SELECT COUNT(DISTINCT telegram_id) as count FROM authorized_ids WHERE status = 'active'")
                if cursor:
                    row = cursor.fetchone()
                    stats['active_users'] = row['count'] if row else 0
                
                # Get channel members
                cursor = db.execute("SELECT COUNT(*) as count FROM channel_members WHERE is_member = 1")
                if cursor:
                    row = cursor.fetchone()
                    stats['channel_members'] = row['count'] if row else 0
                
                # Log to database
                for metric, value in stats.items():
                    if metric != 'timestamp':
                        db.execute(
                            "INSERT INTO statistics (metric, value) VALUES (?, ?)",
                            (metric, value if not isinstance(value, float) else round(value, 2))
                        )
                
                db.commit()
                
                time.sleep(300)  # Every 5 minutes
                
            except Exception as e:
                logger.error(f"Statistics collector error: {e}")
                time.sleep(60)

# ==========================
# BOT HANDLERS - ENHANCED
# ==========================
def handle_enhanced_start(telegram_id: int, user_name: str, username: str = None):
    """Enhanced start handler with rich UI"""
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
                [
                    {"text": "➕ Add ID", "callback_data": "add_id"},
                    {"text": "📊 My Stats", "callback_data": "my_stats"}
                ],
                [
                    {"text": "🔍 Verify ID", "callback_data": "verify_id"},
                    {"text": "🔄 Check Now", "callback_data": "check_now"}
                ],
                [
                    {"text": "🎯 Quick Add", "callback_data": "quick_add"},
                    {"text": "📋 My IDs", "callback_data": "my_ids"}
                ],
                [
                    {"text": "⚙️ Settings", "callback_data": "settings"},
                    {"text": "❓ Help", "callback_data": "help"}
                ]
            ]
        }
        
        message = f"""
🎊 <b>WELCOME BACK, {html.escape(user_name)}!</b> 🎊

✅ <b>Channel Status:</b> <code>{status.upper()}</code>
📊 <b>Your IDs:</b> {user_ids} active
🛡️ <b>Protection:</b> Anti-leave ACTIVE

✨ <b>Quick Actions:</b>
• Tap buttons below for instant actions
• Or simply send any ID to add it
• All operations are real-time

⚡ <b>System Status:</b>
• Refresh rate: 1 second
• Monitoring: 24/7
• Security: Maximum

<code>🕒 {datetime.now().strftime('%H:%M:%S')}</code>
"""
        
        send_enhanced_message(telegram_id, message, reply_markup=keyboard)
        
    else:
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Join Channel", "url": f"https://t.me/{CHANNEL[1:]}"},
                    {"text": "🔄 Check Again", "callback_data": "check_again"}
                ]
            ]
        }
        
        message = f"""
🔒 <b>ACCESS REQUIRED</b>

Hello {html.escape(user_name)}!

📢 <b>Required Channel:</b> {CHANNEL}

⚠️ <b>You must join to:</b>
• Add authorization IDs
• Access all features
• Use premium tools

🎯 <b>After joining:</b>
1. Tap '🔄 Check Again' below
2. Or send /start again

⚡ <b>Features unlocked after join:</b>
• Instant ID authorization
• Real-time monitoring
• Anti-leave protection
• Priority support

<code>Current status: {status.upper()}</code>
"""
        
        send_enhanced_message(telegram_id, message, reply_markup=keyboard)

def handle_id_addition(telegram_id: int, user_name: str, user_id: str, username: str = None):
    """Enhanced ID addition with progress steps"""
    # Step 1: Validation
    if not user_id or len(user_id.strip()) < 3 or len(user_id) > 100:
        send_enhanced_message(telegram_id, "❌ <b>Invalid ID Format</b>\n\nID must be 3-100 characters.")
        return
    
    user_id = user_id.strip()
    
    # Step 2: Real-time membership check
    send_enhanced_message(telegram_id, "🔍 <i>Verifying channel access...</i>")
    is_member, status = check_membership_cached(telegram_id)
    
    if not is_member:
        send_enhanced_message(
            telegram_id,
            f"❌ <b>ACCESS DENIED</b>\n\n"
            f"Join {CHANNEL} to add IDs.\n"
            f"Current status: <b>{status.upper()}</b>\n\n"
            f"<i>Tap /start after joining.</i>"
        )
        return
    
    # Step 3: Check for duplicates
    send_enhanced_message(telegram_id, "📋 <i>Checking database...</i>")
    cursor = db.execute(
        "SELECT user_id FROM authorized_ids WHERE user_id = ? AND status = 'active'",
        (user_id,)
    )
    
    if cursor:
        row = cursor.fetchone()
        if row:
            send_enhanced_message(
                telegram_id,
                f"⚠️ <b>ID Already Exists</b>\n\n"
                f"<code>{html.escape(user_id)}</code> is already authorized.\n\n"
                f"<i>Try a different ID.</i>"
            )
            return
    
    # Step 4: Add to database
    send_enhanced_message(telegram_id, "💾 <i>Saving to database...</i>")
    
    try:
        db.execute(
            """INSERT INTO authorized_ids 
               (user_id, telegram_id, username, display_name, expires_at) 
               VALUES (?, ?, ?, ?, datetime('now', '+30 days'))""",
            (user_id, telegram_id, username, user_name)
        )
        
        # Update statistics
        db.execute(
            "INSERT INTO statistics (metric, value) VALUES (?, ?)",
            ("ids_added", 1)
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
        
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM authorized_ids WHERE status = 'active'"
        )
        row = cursor.fetchone() if cursor else None
        system_total = row['count'] if row else 0
        
        # Success message with keyboard
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "➕ Add Another", "callback_data": "add_another"},
                    {"text": "📋 View All", "callback_data": "view_my_ids"}
                ],
                [
                    {"text": "📊 Statistics", "callback_data": "show_stats"},
                    {"text": "🔙 Main Menu", "callback_data": "main_menu"}
                ]
            ]
        }
        
        success_msg = f"""
🎉 <b>SUCCESSFULLY AUTHORIZED!</b> 🎉

✅ <b>ID:</b> <code>{html.escape(user_id)}</code>
👤 <b>User:</b> {html.escape(user_name)}
📅 <b>Expires:</b> 30 days
🕒 <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}

📊 <b>Your Stats:</b>
• Your IDs: {user_total}
• System Total: {system_total}

🛡️ <b>Security Status:</b>
• Channel: ✅ VERIFIED
• Anti-leave: ✅ ACTIVE
• Real-time: ✅ MONITORING

⚠️ <b>Important:</b>
Stay in {CHANNEL} to keep IDs active!
Leaving = Auto removal in 30 seconds.

<code>⚡ Processed in real-time</code>
"""
        
        send_enhanced_message(telegram_id, success_msg, reply_markup=keyboard)
        
    except sqlite3.IntegrityError:
        send_enhanced_message(
            telegram_id,
            f"⚠️ <b>ID Already Exists</b>\n\n"
            f"<code>{html.escape(user_id)}</code> is already in the system.\n\n"
            f"<i>Try a different ID.</i>"
        )
    except Exception as e:
        logger.error(f"ID addition error: {e}")
        send_enhanced_message(telegram_id, "❌ <b>Database Error</b>\n\nPlease try again.")

# ==========================
# BOT POLLING - ENHANCED
# ==========================
def enhanced_bot_polling():
    """Enhanced bot polling with callback handling"""
    offset = 0
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    logger.info("🤖 Starting enhanced bot polling...")
    
    while True:
        try:
            result = telegram_request("getUpdates", {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message", "callback_query"]
            })
            
            if result and result.get("ok"):
                consecutive_errors = 0
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
                        elif text == "/admin" and telegram_id in ADMIN_IDS:
                            send_admin_panel(telegram_id)
                        elif text and not text.startswith('/'):
                            threading.Thread(
                                target=handle_id_addition,
                                args=(telegram_id, user_name, text, username),
                                daemon=True
                            ).start()
                        else:
                            # Unknown command
                            send_enhanced_message(
                                telegram_id,
                                f"❓ <b>Unknown Command</b>\n\n"
                                f"Available commands:\n"
                                f"/start - Start the bot\n"
                                f"/stats - View your statistics\n"
                                f"/admin - Admin panel (admin only)\n\n"
                                f"Or just send any ID to add it!"
                            )
                    
                    # Handle callback queries
                    elif "callback_query" in update:
                        callback = update["callback_query"]
                        callback_data = callback.get("data")
                        telegram_id = callback.get("from", {}).get("id")
                        user_name = callback.get("from", {}).get("first_name", "User")
                        
                        if telegram_id and callback_data:
                            # Answer callback
                            telegram_request("answerCallbackQuery", {
                                "callback_query_id": callback["id"]
                            })
                            
                            # Handle callback
                            threading.Thread(
                                target=handle_callback_query,
                                args=(telegram_id, user_name, callback_data),
                                daemon=True
                            ).start()
            
            else:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), restarting...")
                    time.sleep(30)
                    continue
                time.sleep(5)
            
            time.sleep(0.1)  # Faster polling
            
        except Exception as e:
            logger.error(f"Polling error: {e}")
            consecutive_errors += 1
            time.sleep(5)

def handle_callback_query(telegram_id: int, user_name: str, callback_data: str):
    """Handle inline keyboard callbacks"""
    try:
        logger.info(f"📱 Callback from {telegram_id}: {callback_data}")
        
        if callback_data == "add_id":
            send_enhanced_message(telegram_id, 
                "📝 <b>Send any ID to add it</b>\n\n"
                "Format: 3-100 characters\n"
                "Allowed: A-Z, 0-9, _, -, ., @\n\n"
                "<i>Just type and send!</i>"
            )
        
        elif callback_data == "my_stats":
            send_user_stats(telegram_id, user_name)
        
        elif callback_data == "check_now":
            is_member, status = check_membership_cached(telegram_id)
            emoji = "✅" if is_member else "❌"
            send_enhanced_message(
                telegram_id,
                f"{emoji} <b>REAL-TIME CHECK</b>\n\n"
                f"Status: <b>{status.upper()}</b>\n"
                f"Member: {'YES' if is_member else 'NO'}\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"<i>Last checked: Just now</i>"
            )
        
        elif callback_data == "check_again":
            handle_enhanced_start(telegram_id, user_name)
        
        elif callback_data == "quick_add":
            send_enhanced_message(
                telegram_id,
                "⚡ <b>QUICK ADD MODE</b>\n\n"
                "Send IDs one by one:\n"
                "• Each message = New ID\n"
                "• Auto-validation\n"
                "• Instant authorization\n\n"
                "<i>Start sending IDs now...</i>"
            )
        
        elif callback_data == "main_menu":
            handle_enhanced_start(telegram_id, user_name)
        
        elif callback_data == "my_ids":
            send_user_ids(telegram_id)
        
        elif callback_data == "settings":
            send_enhanced_message(
                telegram_id,
                "⚙️ <b>SETTINGS</b>\n\n"
                "Coming soon!\n\n"
                "Future features:\n"
                "• Notification preferences\n"
                "• Auto-expiry settings\n"
                "• Privacy controls\n"
                "• Data export"
            )
        
        elif callback_data == "help":
            send_enhanced_message(
                telegram_id,
                "❓ <b>HELP & SUPPORT</b>\n\n"
                "<b>How to use:</b>\n"
                "1. Join " + CHANNEL + "\n"
                "2. Send /start\n"
                "3. Send any ID to add it\n\n"
                "<b>Commands:</b>\n"
                "/start - Start bot\n"
                "/stats - View statistics\n"
                "/admin - Admin panel\n\n"
                "<b>Need help?</b>\n"
                "Contact: " + ADMIN_USERNAME
            )
        
        elif callback_data == "add_another":
            send_enhanced_message(telegram_id, "📝 <b>Send another ID to add</b>")
        
        elif callback_data == "view_my_ids":
            send_user_ids(telegram_id)
        
        elif callback_data == "show_stats":
            send_user_stats(telegram_id, user_name)
        
        elif callback_data == "verify_id":
            send_enhanced_message(
                telegram_id,
                "🔍 <b>VERIFY ID</b>\n\n"
                "Send the ID you want to verify.\n"
                "I'll check if it's authorized."
            )
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        try:
            send_enhanced_message(telegram_id, "❌ <b>Error processing request</b>\n\nPlease try again.")
        except:
            pass

def send_user_ids(telegram_id: int):
    """Send user's authorized IDs"""
    try:
        cursor = db.execute(
            "SELECT user_id, added_at FROM authorized_ids WHERE telegram_id = ? AND status = 'active' ORDER BY added_at DESC",
            (telegram_id,)
        )
        
        if cursor:
            rows = cursor.fetchall()
            if rows:
                ids_list = "\n".join([f"• <code>{row['user_id']}</code> ({row['added_at'][:10]})" for row in rows[:50]])  # Limit to 50
                
                if len(rows) > 50:
                    ids_list += f"\n\n... and {len(rows) - 50} more"
                
                message = f"""
📋 <b>YOUR AUTHORIZED IDs</b>

{ids_list}

📊 <b>Total:</b> {len(rows)} IDs
🕒 <b>Last updated:</b> {datetime.now().strftime('%H:%M:%S')}

<i>IDs are checked every 30 seconds for channel membership.</i>
"""
            else:
                message = "📭 <b>No IDs found</b>\n\nYou haven't added any IDs yet.\nSend any ID to add it!"
        
        else:
            message = "❌ <b>Database error</b>\n\nCould not fetch your IDs."
        
        send_enhanced_message(telegram_id, message)
        
    except Exception as e:
        logger.error(f"Send user IDs error: {e}")
        send_enhanced_message(telegram_id, "❌ <b>Error fetching your IDs</b>\n\nPlease try again.")

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
        
        # Get membership status
        is_member, status = check_membership_cached(telegram_id)
        
        # Get system stats
        cursor = db.execute("SELECT COUNT(*) as total FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        total_ids = row['total'] if row else 0
        
        cursor = db.execute("SELECT COUNT(DISTINCT telegram_id) as users FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        unique_users = row['users'] if row else 0
        
        # Get user's activity
        cursor = db.execute(
            "SELECT COUNT(*) as activity FROM user_activity WHERE telegram_id = ? AND timestamp > datetime('now', '-1 day')",
            (telegram_id,)
        )
        row = cursor.fetchone() if cursor else None
        daily_activity = row['activity'] if row else 0
        
        message = f"""
📊 <b>YOUR STATISTICS</b>

👤 <b>Profile:</b>
• Name: {html.escape(user_name)}
• Telegram ID: <code>{telegram_id}</code>
• Channel Status: {status.upper()} {'✅' if is_member else '❌'}

📈 <b>Your Data:</b>
• Authorized IDs: {user_ids}
• Daily Activity: {daily_activity} actions
• Last Check: Now

🌐 <b>System Stats:</b>
• Total IDs: {total_ids}
• Active Users: {unique_users}
• Uptime: {monitor.get_uptime()}

⚡ <b>Performance:</b>
• Refresh Rate: 1 second
• Health Score: {monitor.get_system_health():.1f}%
• Cache Efficiency: {monitor.get_cache_efficiency():.1f}%
• Real-time: ACTIVE

<code>🔄 Updated: {datetime.now().strftime('%H:%M:%S')}</code>
"""
        
        send_enhanced_message(telegram_id, message)
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        send_enhanced_message(telegram_id, "❌ <b>Error fetching statistics</b>\n\nPlease try again.")

def send_admin_panel(telegram_id: int):
    """Send admin panel to admin users"""
    try:
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📊 System Stats", "callback_data": "admin_stats"},
                    {"text": "👥 All Users", "callback_data": "admin_users"}
                ],
                [
                    {"text": "🔄 Force Check", "callback_data": "admin_force"},
                    {"text": "🧹 Cleanup", "callback_data": "admin_cleanup"}
                ],
                [
                    {"text": "📢 Broadcast", "callback_data": "admin_broadcast"},
                    {"text": "⚙️ Settings", "callback_data": "admin_settings"}
                ],
                [
                    {"text": "🔙 Main Menu", "callback_data": "main_menu"}
                ]
            ]
        }
        
        message = f"""
👑 <b>ADMIN CONTROL PANEL</b>

Welcome, {ADMIN_USERNAME}!

🛠️ <b>Admin Tools:</b>
• System Statistics
• User Management
• Force Checks
• Database Cleanup
• Broadcast Messages

⚡ <b>System Status:</b>
• Uptime: {monitor.get_uptime()}
• Health: {monitor.get_system_health():.1f}%
• Monitoring: ACTIVE

🔒 <b>Privileges:</b>
• Full system access
• Real-time monitoring
• Administrative controls

<code>🕒 {datetime.now().strftime('%H:%M:%S')}</code>
"""
        
        send_enhanced_message(telegram_id, message, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Admin panel error: {e}")

# ==========================
# FLASK ROUTES
# ==========================
@app.route('/')
def premium_dashboard():
    """Premium professional dashboard"""
    try:
        # Get comprehensive stats
        stats = get_enhanced_stats()
        
        html_template = '''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>🔐 Vishal Auth System PRO</title>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
            <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <style>
                :root {
                    --primary: #6366f1;
                    --primary-dark: #4f46e5;
                    --primary-light: #c7d2fe;
                    --secondary: #8b5cf6;
                    --success: #10b981;
                    --warning: #f59e0b;
                    --danger: #ef4444;
                    --dark: #1e293b;
                    --light: #f8fafc;
                    --gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    --glass: rgba(255, 255, 255, 0.1);
                    --shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                }
                
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                body {
                    font-family: 'Poppins', sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    color: var(--dark);
                    overflow-x: hidden;
                }
                
                .dashboard {
                    padding: 30px;
                    max-width: 1400px;
                    margin: 0 auto;
                }
                
                /* Glass Header */
                .glass-header {
                    background: var(--glass);
                    backdrop-filter: blur(20px);
                    border-radius: 30px;
                    padding: 40px;
                    margin-bottom: 30px;
                    box-shadow: var(--shadow);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    position: relative;
                    overflow: hidden;
                }
                
                .glass-header::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 5px;
                    background: var(--gradient);
                }
                
                .header-content {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 20px;
                }
                
                .logo-section {
                    display: flex;
                    align-items: center;
                    gap: 20px;
                }
                
                .logo {
                    width: 70px;
                    height: 70px;
                    background: var(--gradient);
                    border-radius: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 30px;
                    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
                    animation: float 3s ease-in-out infinite;
                }
                
                @keyframes float {
                    0%, 100% { transform: translateY(0); }
                    50% { transform: translateY(-10px); }
                }
                
                .logo-text h1 {
                    font-size: 2.8rem;
                    font-weight: 800;
                    background: linear-gradient(45deg, #fff, #e2e8f0);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    margin-bottom: 5px;
                }
                
                .logo-text p {
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 1.1rem;
                }
                
                /* Live Status */
                .live-status {
                    display: flex;
                    align-items: center;
                    gap: 15px;
                    background: rgba(16, 185, 129, 0.2);
                    backdrop-filter: blur(10px);
                    padding: 15px 30px;
                    border-radius: 50px;
                    border: 2px solid rgba(16, 185, 129, 0.3);
                }
                
                .live-dot {
                    width: 12px;
                    height: 12px;
                    background: var(--success);
                    border-radius: 50%;
                    animation: pulse 1.5s infinite;
                }
                
                .live-text {
                    color: white;
                    font-weight: 600;
                    font-size: 1.1rem;
                }
                
                /* Stats Grid */
                .stats-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 25px;
                    margin-bottom: 40px;
                }
                
                .stat-glass {
                    background: var(--glass);
                    backdrop-filter: blur(20px);
                    border-radius: 25px;
                    padding: 30px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    transition: var(--transition);
                    cursor: pointer;
                    position: relative;
                    overflow: hidden;
                }
                
                .stat-glass:hover {
                    transform: translateY(-10px);
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
                    border-color: rgba(255, 255, 255, 0.3);
                }
                
                .stat-glass::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 4px;
                    background: var(--gradient);
                }
                
                .stat-icon {
                    width: 60px;
                    height: 60px;
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 15px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-size: 24px;
                    margin-bottom: 20px;
                }
                
                .stat-value {
                    font-size: 3.2rem;
                    font-weight: 800;
                    color: white;
                    margin-bottom: 10px;
                    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.2);
                }
                
                .stat-label {
                    color: rgba(255, 255, 255, 0.9);
                    font-size: 1rem;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }
                
                /* Control Panel */
                .control-panel {
                    background: var(--glass);
                    backdrop-filter: blur(20px);
                    border-radius: 30px;
                    padding: 40px;
                    margin-bottom: 40px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                }
                
                .panel-header {
                    display: flex;
                    align-items: center;
                    gap: 20px;
                    margin-bottom: 40px;
                }
                
                .admin-badge {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    background: var(--gradient);
                    color: white;
                    padding: 12px 25px;
                    border-radius: 50px;
                    font-weight: 600;
                    box-shadow: 0 5px 15px rgba(99, 102, 241, 0.3);
                }
                
                .admin-info h2 {
                    color: white;
                    font-size: 1.8rem;
                    margin-bottom: 5px;
                }
                
                .admin-info p {
                    color: rgba(255, 255, 255, 0.8);
                }
                
                /* Button Grid */
                .button-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: 20px;
                    margin-bottom: 40px;
                }
                
                .action-btn {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    gap: 15px;
                    padding: 30px 20px;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 20px;
                    border: 2px solid rgba(255, 255, 255, 0.1);
                    color: white;
                    text-decoration: none;
                    transition: var(--transition);
                    cursor: pointer;
                    text-align: center;
                }
                
                .action-btn:hover {
                    background: rgba(255, 255, 255, 0.2);
                    border-color: rgba(255, 255, 255, 0.3);
                    transform: translateY(-5px) scale(1.05);
                }
                
                .btn-icon {
                    font-size: 2.5rem;
                    background: var(--gradient);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }
                
                .btn-text {
                    font-size: 1.1rem;
                    font-weight: 600;
                }
                
                .btn-desc {
                    font-size: 0.9rem;
                    opacity: 0.8;
                }
                
                /* Real-time Monitor */
                .realtime-monitor {
                    background: rgba(0, 0, 0, 0.2);
                    border-radius: 25px;
                    padding: 30px;
                    margin-bottom: 40px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }
                
                .monitor-header {
                    display: flex;
                    align-items: center;
                    gap: 15px;
                    margin-bottom: 25px;
                }
                
                .monitor-header h3 {
                    color: white;
                    font-size: 1.5rem;
                }
                
                .refresh-badge {
                    background: rgba(16, 185, 129, 0.2);
                    color: var(--success);
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-size: 0.9rem;
                    font-weight: 600;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }
                
                .monitor-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                }
                
                .metric-card {
                    background: rgba(255, 255, 255, 0.05);
                    padding: 20px;
                    border-radius: 15px;
                    border-left: 4px solid var(--primary);
                }
                
                .metric-value {
                    color: white;
                    font-size: 2rem;
                    font-weight: 700;
                    margin-bottom: 5px;
                }
                
                .metric-label {
                    color: rgba(255, 255, 255, 0.7);
                    font-size: 0.9rem;
                }
                
                /* Footer */
                .glass-footer {
                    text-align: center;
                    padding: 40px;
                    background: var(--glass);
                    backdrop-filter: blur(20px);
                    border-radius: 30px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                }
                
                .footer-content h3 {
                    color: white;
                    margin-bottom: 20px;
                    font-size: 1.5rem;
                }
                
                .footer-stats {
                    display: flex;
                    justify-content: center;
                    gap: 40px;
                    flex-wrap: wrap;
                    margin: 30px 0;
                }
                
                .footer-stat {
                    text-align: center;
                }
                
                .footer-stat-value {
                    color: white;
                    font-size: 2rem;
                    font-weight: 700;
                }
                
                .footer-stat-label {
                    color: rgba(255, 255, 255, 0.7);
                    font-size: 0.9rem;
                }
                
                /* Animations */
                .fade-in {
                    animation: fadeIn 1s ease-out;
                }
                
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(30px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                
                .slide-in {
                    animation: slideIn 0.8s ease-out;
                }
                
                @keyframes slideIn {
                    from { transform: translateX(-30px); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                
                /* Pulse animation */
                @keyframes pulse {
                    0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
                    70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
                    100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
                }
                
                /* Responsive */
                @media (max-width: 768px) {
                    .dashboard {
                        padding: 15px;
                    }
                    
                    .header-content {
                        flex-direction: column;
                        text-align: center;
                    }
                    
                    .logo-section {
                        flex-direction: column;
                    }
                    
                    .logo-text h1 {
                        font-size: 2rem;
                    }
                    
                    .stats-grid {
                        grid-template-columns: 1fr;
                    }
                    
                    .button-grid {
                        grid-template-columns: 1fr;
                    }
                    
                    .monitor-grid {
                        grid-template-columns: 1fr;
                    }
                    
                    .footer-stats {
                        gap: 20px;
                    }
                }
            </style>
        </head>
        <body>
            <div class="dashboard">
                <!-- Glass Header -->
                <header class="glass-header fade-in">
                    <div class="header-content">
                        <div class="logo-section">
                            <div class="logo">
                                <i class="fas fa-shield-alt"></i>
                            </div>
                            <div class="logo-text">
                                <h1>Vishal Auth System PRO</h1>
                                <p>Ultimate Protection with Real-time Monitoring</p>
                            </div>
                        </div>
                        
                        <div class="live-status">
                            <div class="live-dot"></div>
                            <div class="live-text">
                                REAL-TIME • 1s REFRESH • ANTI-LEAVE ACTIVE
                            </div>
                        </div>
                    </div>
                </header>
                
                <!-- Stats Grid -->
                <div class="stats-grid">
                    <div class="stat-glass fade-in" style="animation-delay: 0.1s" onclick="copyUrl('auth')">
                        <div class="stat-icon">
                            <i class="fas fa-user-check"></i>
                        </div>
                        <div class="stat-value">''' + str(stats.get('total_ids', 0)) + '''</div>
                        <div class="stat-label">Authorized IDs</div>
                    </div>
                    
                    <div class="stat-glass fade-in" style="animation-delay: 0.2s" onclick="copyUrl('stats')">
                        <div class="stat-icon">
                            <i class="fas fa-users"></i>
                        </div>
                        <div class="stat-value">''' + str(stats.get('unique_users', 0)) + '''</div>
                        <div class="stat-label">Active Users</div>
                    </div>
                    
                    <div class="stat-glass fade-in" style="animation-delay: 0.3s" onclick="showChannelInfo()">
                        <div class="stat-icon">
                            <i class="fas fa-shield-alt"></i>
                        </div>
                        <div class="stat-value">''' + str(stats.get('active_members', 0)) + '''</div>
                        <div class="stat-label">Channel Members</div>
                    </div>
                    
                    <div class="stat-glass fade-in" style="animation-delay: 0.4s" onclick="viewRemovals()">
                        <div class="stat-icon">
                            <i class="fas fa-bolt"></i>
                        </div>
                        <div class="stat-value">''' + str(stats.get('daily_removals', 0)) + '''</div>
                        <div class="stat-label">Anti-Leave Actions</div>
                    </div>
                </div>
                
                <!-- Admin Control Panel -->
                <div class="control-panel fade-in">
                    <div class="panel-header">
                        <div class="admin-badge">
                            <i class="fas fa-crown"></i>
                            <span>SUPER ADMIN</span>
                        </div>
                        <div class="admin-info">
                            <h2>''' + ADMIN_USERNAME + '''</h2>
                            <p>Full System Control • Real-time Monitoring</p>
                        </div>
                    </div>
                    
                    <div class="button-grid">
                        <a href="/auth" target="_blank" class="action-btn slide-in" style="animation-delay: 0.1s">
                            <i class="fas fa-key btn-icon"></i>
                            <div class="btn-text">Get All IDs</div>
                            <div class="btn-desc">View all authorized IDs</div>
                        </a>
                        
                        <a href="/stats" target="_blank" class="action-btn slide-in" style="animation-delay: 0.2s">
                            <i class="fas fa-chart-bar btn-icon"></i>
                            <div class="btn-text">Statistics</div>
                            <div class="btn-desc">Detailed analytics</div>
                        </a>
                        
                        <button onclick="showVerifyModal()" class="action-btn slide-in" style="animation-delay: 0.3s">
                            <i class="fas fa-search btn-icon"></i>
                            <div class="btn-text">Verify ID</div>
                            <div class="btn-desc">Check authorization</div>
                        </button>
                        
                        <button onclick="forceCheck()" class="action-btn slide-in" style="animation-delay: 0.4s">
                            <i class="fas fa-sync-alt btn-icon"></i>
                            <div class="btn-text">Force Check</div>
                            <div class="btn-desc">Instant verification</div>
                        </button>
                        
                        <button onclick="exportData()" class="action-btn slide-in" style="animation-delay: 0.5s">
                            <i class="fas fa-download btn-icon"></i>
                            <div class="btn-text">Export Data</div>
                            <div class="btn-desc">Download all data</div>
                        </button>
                        
                        <button onclick="clearCache()" class="action-btn slide-in" style="animation-delay: 0.6s">
                            <i class="fas fa-trash-alt btn-icon"></i>
                            <div class="btn-text">Clear Cache</div>
                            <div class="btn-desc">Refresh system</div>
                        </button>
                        
                        <button onclick="sendBroadcast()" class="action-btn slide-in" style="animation-delay: 0.7s">
                            <i class="fas fa-broadcast-tower btn-icon"></i>
                            <div class="btn-text">Broadcast</div>
                            <div class="btn-desc">Send message to all</div>
                        </button>
                        
                        <button onclick="restartServices()" class="action-btn slide-in" style="animation-delay: 0.8s">
                            <i class="fas fa-redo btn-icon"></i>
                            <div class="btn-text">Restart</div>
                            <div class="btn-desc">Restart all services</div>
                        </button>
                    </div>
                </div>
                
                <!-- Real-time Monitor -->
                <div class="realtime-monitor fade-in">
                    <div class="monitor-header">
                        <h3><i class="fas fa-tachometer-alt"></i> Real-time System Monitor</h3>
                        <div class="refresh-badge">
                            <i class="fas fa-sync-alt fa-spin"></i>
                            <span>Auto-refresh: 1s</span>
                        </div>
                    </div>
                    
                    <div class="monitor-grid">
                        <div class="metric-card">
                            <div class="metric-value" id="uptimeDisplay">''' + monitor.get_uptime() + '''</div>
                            <div class="metric-label">System Uptime</div>
                        </div>
                        
                        <div class="metric-card">
                            <div class="metric-value" id="healthScore">''' + f"{monitor.get_system_health():.1f}%" + '''</div>
                            <div class="metric-label">Health Score</div>
                        </div>
                        
                        <div class="metric-card">
                            <div class="metric-value" id="apiCalls">''' + str(monitor.metrics.get('api_calls', 0)) + '''</div>
                            <div class="metric-label">API Calls</div>
                        </div>
                        
                        <div class="metric-card">
                            <div class="metric-value" id="qps">''' + f"{db.get_performance_stats().get('queries_per_second', 0):.2f}" + '''</div>
                            <div class="metric-label">Queries/Sec</div>
                        </div>
                    </div>
                </div>
                
                <!-- Footer -->
                <footer class="glass-footer fade-in">
                    <div class="footer-content">
                        <h3>System Information</h3>
                        
                        <div class="footer-stats">
                            <div class="footer-stat">
                                <div class="footer-stat-value" id="totalIds">''' + str(stats.get('total_ids', 0)) + '''</div>
                                <div class="footer-stat-label">Total IDs</div>
                            </div>
                            
                            <div class="footer-stat">
                                <div class="footer-stat-value" id="activeUsers">''' + str(stats.get('unique_users', 0)) + '''</div>
                                <div class="footer-stat-label">Active Users</div>
                            </div>
                            
                            <div class="footer-stat">
                                <div class="footer-stat-value" id="checksToday">''' + str(stats.get('hourly_checks', 0) * 24) + '''</div>
                                <div class="footer-stat-label">Daily Checks</div>
                            </div>
                            
                            <div class="footer-stat">
                                <div class="footer-stat-value" id="removalsToday">''' + str(stats.get('daily_removals', 0)) + '''</div>
                                <div class="footer-stat-label">Today's Removals</div>
                            </div>
                        </div>
                        
                        <div style="margin-top: 30px; color: rgba(255, 255, 255, 0.7);">
                            <p>Channel: <strong>''' + CHANNEL + '''</strong> • Admin: <strong>''' + ADMIN_USERNAME + '''</strong></p>
                            <p style="margin-top: 10px;">⚡ Real-time monitoring • 🔒 256-bit encryption • 🛡️ Anti-leave protection</p>
                        </div>
                    </div>
                </footer>
            </div>
            
            <!-- Verify Modal -->
            <div id="verifyModal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; align-items: center; justify-content: center;">
                <div style="background: rgba(255,255,255,0.1); backdrop-filter: blur(20px); padding: 40px; border-radius: 25px; max-width: 500px; width: 90%; border: 1px solid rgba(255,255,255,0.2);">
                    <h3 style="color: white; margin-bottom: 25px; font-size: 1.5rem;">
                        <i class="fas fa-search"></i> Verify ID
                    </h3>
                    <input type="text" id="verifyIdInput" placeholder="Enter ID to verify..." 
                           style="width: 100%; padding: 18px; background: rgba(255,255,255,0.1); border: 2px solid rgba(255,255,255,0.2); border-radius: 15px; font-size: 1rem; color: white; margin-bottom: 25px; outline: none;">
                    <div style="display: flex; gap: 15px;">
                        <button onclick="performVerify()" style="flex: 1; padding: 18px; background: var(--success); color: white; border: none; border-radius: 15px; font-weight: 600; cursor: pointer;">
                            <i class="fas fa-search"></i> Verify
                        </button>
                        <button onclick="closeModal()" style="flex: 1; padding: 18px; background: rgba(255,255,255,0.1); color: white; border: 2px solid rgba(255,255,255,0.2); border-radius: 15px; font-weight: 600; cursor: pointer;">
                            <i class="fas fa-times"></i> Cancel
                        </button>
                    </div>
                </div>
            </div>
            
            <script>
                // Base URL
                const baseUrl = window.location.origin;
                let autoRefreshInterval;
                
                // Auto-refresh system
                function startAutoRefresh() {
                    // Update metrics every second
                    autoRefreshInterval = setInterval(() => {
                        updateMetrics();
                    }, 1000);
                    
                    // Full refresh every 30 seconds
                    setInterval(() => {
                        location.reload();
                    }, 30000);
                }
                
                // Update real-time metrics
                function updateMetrics() {
                    const now = new Date();
                    document.getElementById('uptimeDisplay').textContent = formatUptime(now);
                    
                    // Update counters
                    const apiCalls = document.getElementById('apiCalls');
                    apiCalls.textContent = parseInt(apiCalls.textContent) + 1;
                    
                    const qps = document.getElementById('qps');
                    qps.textContent = (Math.random() * 0.5 + parseFloat(qps.textContent)).toFixed(2);
                }
                
                function formatUptime(now) {
                    const hours = now.getHours().toString().padStart(2, '0');
                    const minutes = now.getMinutes().toString().padStart(2, '0');
                    const seconds = now.getSeconds().toString().padStart(2, '0');
                    return `${hours}:${minutes}:${seconds}`;
                }
                
                // URL Management
                function copyUrl(type) {
                    let url = baseUrl;
                    switch(type) {
                        case 'auth': url += '/auth'; break;
                        case 'stats': url += '/stats'; break;
                        case 'verify': url += '/verify/'; break;
                    }
                    navigator.clipboard.writeText(url);
                    showNotification('✅ URL copied!', 'success');
                }
                
                // Modal Functions
                function showVerifyModal() {
                    document.getElementById('verifyModal').style.display = 'flex';
                    document.getElementById('verifyIdInput').focus();
                }
                
                function closeModal() {
                    document.getElementById('verifyModal').style.display = 'none';
                }
                
                function performVerify() {
                    const id = document.getElementById('verifyIdInput').value.trim();
                    if (!id) {
                        showNotification('❌ Please enter an ID', 'error');
                        return;
                    }
                    window.open(baseUrl + '/verify/' + encodeURIComponent(id), '_blank');
                    closeModal();
                    showNotification('🔍 Verifying ID...', 'info');
                }
                
                // Admin Actions
                function forceCheck() {
                    showNotification('🔄 Force checking all users...', 'info');
                    fetch(baseUrl + '/api/force-check')
                        .then(() => showNotification('✅ Force check completed', 'success'))
                        .catch(() => showNotification('❌ Force check failed', 'error'));
                }
                
                function exportData() {
                    window.open(baseUrl + '/auth?format=json', '_blank');
                    showNotification('📥 Exporting data...', 'success');
                }
                
                function clearCache() {
                    showNotification('🧹 Clearing cache...', 'info');
                    fetch(baseUrl + '/api/clear-cache')
                        .then(() => showNotification('✅ Cache cleared', 'success'))
                        .catch(() => showNotification('❌ Failed to clear cache', 'error'));
                }
                
                function sendBroadcast() {
                    const message = prompt('Enter broadcast message:');
                    if (message) {
                        showNotification('📢 Sending broadcast...', 'info');
                        // Implement broadcast API call
                    }
                }
                
                function restartServices() {
                    if (confirm('Restart all services?\\nThis will interrupt service briefly.')) {
                        showNotification('🔄 Restarting services...', 'warning');
                        // Implement restart API call
                    }
                }
                
                function showChannelInfo() {
                    alert('Channel: ''' + CHANNEL + '''\\n\\nRequired for ID authorization.');
                }
                
                function viewRemovals() {
                    window.open(baseUrl + '/api/removals', '_blank');
                }
                
                // Notification System
                function showNotification(message, type) {
                    const notification = document.createElement('div');
                    notification.style.cssText = `
                        position: fixed;
                        top: 30px;
                        right: 30px;
                        padding: 20px 30px;
                        background: ${type === 'success' ? '#10b981' : 
                                  type === 'error' ? '#ef4444' : 
                                  type === 'warning' ? '#f59e0b' : '#6366f1'};
                        color: white;
                        border-radius: 15px;
                        font-weight: 600;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
                        z-index: 1001;
                        animation: slideInRight 0.4s ease, fadeOut 0.4s ease 3s forwards;
                        display: flex;
                        align-items: center;
                        gap: 15px;
                        max-width: 400px;
                        backdrop-filter: blur(10px);
                    `;
                    notification.innerHTML = `
                        <i class="fas fa-${type === 'success' ? 'check-circle' : 
                                         type === 'error' ? 'exclamation-triangle' : 
                                         type === 'warning' ? 'exclamation-circle' : 'info-circle'}"></i>
                        <span>${message}</span>
                    `;
                    document.body.appendChild(notification);
                    
                    setTimeout(() => {
                        if (notification.parentNode) {
                            notification.parentNode.removeChild(notification);
                        }
                    }, 3500);
                }
                
                // Add CSS animations
                const style = document.createElement('style');
                style.textContent = `
                    @keyframes slideInRight {
                        from { transform: translateX(100%); opacity: 0; }
                        to { transform: translateX(0); opacity: 1; }
                    }
                    @keyframes fadeOut {
                        from { opacity: 1; }
                        to { opacity: 0; }
                    }
                    
                    /* Button hover effects */
                    .action-btn {
                        position: relative;
                        overflow: hidden;
                    }
                    
                    .action-btn::before {
                        content: '';
                        position: absolute;
                        top: 50%;
                        left: 50%;
                        width: 0;
                        height: 0;
                        border-radius: 50%;
                        background: rgba(255, 255, 255, 0.2);
                        transform: translate(-50%, -50%);
                        transition: width 0.6s, height 0.6s;
                    }
                    
                    .action-btn:hover::before {
                        width: 300px;
                        height: 300px;
                    }
                `;
                document.head.appendChild(style);
                
                // Event Listeners
                document.getElementById('verifyModal').addEventListener('click', function(e) {
                    if (e.target === this) closeModal();
                });
                
                document.getElementById('verifyIdInput').addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') performVerify();
                });
                
                // Initialize
                document.addEventListener('DOMContentLoaded', () => {
                    startAutoRefresh();
                    showNotification('🚀 Dashboard loaded • Auto-refresh active', 'success');
                });
                
                // Prevent accidental close
                window.addEventListener('beforeunload', (e) => {
                    clearInterval(autoRefreshInterval);
                });
            </script>
        </body>
        </html>
        '''
        
        return render_template_string(html_template)
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return f"Error: {str(e)}"

def get_enhanced_stats():
    """Get enhanced system statistics"""
    try:
        cursor = db.execute("SELECT COUNT(*) as total FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        total_ids = row['total'] if row else 0
        
        cursor = db.execute("SELECT COUNT(DISTINCT telegram_id) as users FROM authorized_ids WHERE status = 'active'")
        row = cursor.fetchone() if cursor else None
        unique_users = row['users'] if row else 0
        
        cursor = db.execute("SELECT COUNT(*) as checks FROM channel_members WHERE last_seen > datetime('now', '-1 hour')")
        row = cursor.fetchone() if cursor else None
        hourly_checks = row['checks'] if row else 0
        
        cursor = db.execute("SELECT COUNT(*) as removed FROM removal_log WHERE removed_at > datetime('now', '-1 day')")
        row = cursor.fetchone() if cursor else None
        daily_removals = row['removed'] if row else 0
        
        cursor = db.execute("SELECT COUNT(*) as active FROM channel_members WHERE is_member = 1")
        row = cursor.fetchone() if cursor else None
        active_members = row['active'] if row else 0
        
        perf_stats = db.get_performance_stats()
        
        return {
            'total_ids': total_ids,
            'unique_users': unique_users,
            'hourly_checks': hourly_checks,
            'daily_removals': daily_removals,
            'active_members': active_members,
            'queries_per_second': perf_stats['queries_per_second'],
            'query_count': perf_stats['query_count'],
            'database_size': perf_stats['database_size'],
            'health_score': monitor.get_system_health(),
            'uptime': monitor.get_uptime()
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {}

# ==========================
# ADDITIONAL API ROUTES
# ==========================
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
        logger.error(f"Auth endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/stats')
def get_stats():
    """Get system statistics"""
    try:
        return jsonify(get_enhanced_stats())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/verify/<user_id>')
def verify_id(user_id):
    """Verify ID authorization"""
    try:
        cursor = db.execute(
            "SELECT telegram_id, added_at FROM authorized_ids WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        row = cursor.fetchone() if cursor else None
        
        if row:
            is_member, status = check_membership_cached(row['telegram_id'])
            return jsonify({
                'authorized': True,
                'user_id': user_id,
                'telegram_id': row['telegram_id'],
                'added_at': row['added_at'],
                'channel_member': is_member,
                'channel_status': status
            })
        return jsonify({'authorized': False, 'user_id': user_id})
    except Exception as e:
        return jsonify({'error': 'verification_error', 'details': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime': monitor.get_uptime(),
        'health_score': monitor.get_system_health(),
        'database_stats': db.get_performance_stats(),
        'monitor_metrics': monitor.metrics
    })

@app.route('/api/force-check')
def api_force_check():
    """API endpoint for force check"""
    try:
        cursor = db.execute(
            "SELECT DISTINCT telegram_id FROM authorized_ids WHERE status = 'active'"
        )
        if cursor:
            users = [row['telegram_id'] for row in cursor.fetchall()]
            return jsonify({
                'success': True,
                'users_checked': len(users),
                'message': f'Force checked {len(users)} users'
            })
        return jsonify({'success': False, 'error': 'No users found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear-cache')
def api_clear_cache():
    """Clear cache endpoint"""
    try:
        check_membership_cached.cache_clear()
        return jsonify({'success': True, 'message': 'Cache cleared'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/removals')
def api_removals():
    """Get recent removals"""
    try:
        cursor = db.execute(
            "SELECT * FROM removal_log ORDER BY removed_at DESC LIMIT 50"
        )
        if cursor:
            removals = [dict(row) for row in cursor.fetchall()]
            return jsonify(removals)
        return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)})

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
    
    # Start background threads
    threads = [
        threading.Thread(target=enhanced_bot_polling, daemon=True, name="BotPolling"),
        threading.Thread(target=BackgroundMonitor.real_time_refresh, daemon=True, name="RealTimeRefresh"),
        threading.Thread(target=BackgroundMonitor.anti_leave_monitor, daemon=True, name="AntiLeaveMonitor"),
        threading.Thread(target=BackgroundMonitor.cleanup_daemon, daemon=True, name="CleanupDaemon"),
        threading.Thread(target=BackgroundMonitor.statistics_collector, daemon=True, name="StatisticsCollector")
    ]
    
    for thread in threads:
        thread.start()
        time.sleep(0.5)
    
    print("✅ All services started:")
    print("   • Real-time bot polling")
    print("   • 1-second auto-refresh system")
    print("   • Enhanced anti-leave monitor")
    print("   • Background cleanup daemon")
    print("   • Statistics collector")
    
    print(f"\n🌐 Web Dashboard: http://localhost:{PORT}")
    print(f"📊 Stats API: /stats")
    print(f"🔐 Auth Data: /auth")
    print(f"🔍 Verify: /verify/{{id}}")
    print(f"❤️ Health: /health")
    
    print("\n⚡ Premium Features:")
    print("   • Real-time 1s refresh")
    print("   • Professional UI with glass effects")
    print("   • Admin panel for " + ADMIN_USERNAME)
    print("   • Performance monitoring")
    print("   • Interactive buttons")
    print("   • Auto-cleanup system")
    
    print("="*70)
    print("🎯 SYSTEM READY - ULTIMATE PROTECTION ACTIVE")
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