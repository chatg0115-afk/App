import os, requests, threading, time, json, re, sqlite3
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
import html

# ==========================
# CONFIGURATION
# ==========================
BOT_TOKEN = "8504965473:AAFV_ciorWHwRZo_K6FpETDWTINtmbgUetc"
CHANNEL = "@Vishalxnetwork4"  # Your channel username
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
PORT = 8080
ADMIN_IDS = [6493515910]  # Add your Telegram ID here
API_TIMEOUT = 30

# ==========================
# LOGGING SETUP
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('auth_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger()

# ==========================
# DATABASE SETUP
# ==========================
class Database:
    """Database with proper channel membership tracking"""
    def __init__(self):
        self.conn = sqlite3.connect('auth_bot.db', check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_tables()

    def init_tables(self):
        """Initialize database tables"""
        cursor = self.conn.cursor()

        # Drop existing tables
        cursor.execute('DROP TABLE IF EXISTS authorized_ids')
        cursor.execute('DROP TABLE IF EXISTS channel_members')
        cursor.execute('DROP TABLE IF EXISTS user_sessions')
        cursor.execute('DROP TABLE IF EXISTS removal_log')

        # Create tables
        cursor.execute('''
            CREATE TABLE authorized_ids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                flags INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE channel_members (
                telegram_id INTEGER PRIMARY KEY,
                is_member BOOLEAN DEFAULT 0,
                status TEXT DEFAULT 'left',
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                check_count INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE user_sessions (
                telegram_id INTEGER PRIMARY KEY,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                total_ids_added INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE removal_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                reason TEXT,
                ids_removed INTEGER DEFAULT 0,
                removed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX idx_auth_telegram ON authorized_ids(telegram_id)')
        cursor.execute('CREATE INDEX idx_auth_status ON authorized_ids(status)')
        cursor.execute('CREATE INDEX idx_members_status ON channel_members(status)')
        cursor.execute('CREATE INDEX idx_members_checked ON channel_members(checked_at)')

        self.conn.commit()
        logger.info("✅ Database tables created successfully")

    def execute(self, query, params=()):
        """Execute SQL query"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return cursor
        except Exception as e:
            logger.error(f"Database error: {e}")
            return None

    def commit(self):
        """Commit transaction"""
        self.conn.commit()

    def close(self):
        """Close database connection"""
        self.conn.close()

# Initialize database
db = Database()

# ==========================
# FLASK APP
# ==========================
app = Flask(__name__)

# ==========================
# TELEGRAM API FUNCTIONS - FIXED
# ==========================
def telegram_api_request(method: str, data: Dict = None) -> Optional[Dict]:
    """Make request to Telegram API"""
    try:
        url = f"{API}/{method}"
        response = requests.post(
            url,
            json=data or {},
            timeout=API_TIMEOUT
        )

        if response.status_code == 200:
            return response.json()

        logger.error(f"API Error {method}: {response.status_code}")
        return None

    except requests.exceptions.Timeout:
        logger.error(f"API Timeout: {method}")
        return None
    except Exception as e:
        logger.error(f"API Request failed: {e}")
        return None

def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Send message to user"""
    try:
        # First send typing action
        telegram_api_request("sendChatAction", {
            "chat_id": chat_id,
            "action": "typing"
        })

        # Small delay for natural feel
        time.sleep(0.5)

        # Send the message
        result = telegram_api_request("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        })

        return bool(result and result.get("ok"))

    except Exception as e:
        logger.error(f"Send message error: {e}")
        return False

# ==========================
# CHANNEL MEMBERSHIP CHECKING - COMPLETELY FIXED
# ==========================
def check_channel_membership(telegram_id: int, force_fresh: bool = False) -> Tuple[bool, str]:
    """
    Check if user is a member of the channel
    Returns: (is_member, status)
    Status can be: 'member', 'administrator', 'creator', 'left', 'kicked', 'restricted', 'error'
    """
    try:
        # First check database cache if not forcing fresh check
        if not force_fresh:
            cursor = db.execute(
                """SELECT is_member, status FROM channel_members
                   WHERE telegram_id = ? AND checked_at > datetime('now', '-5 minutes')""",
                (telegram_id,)
            )
            if cursor:
                row = cursor.fetchone()
                if row:
                    logger.info(f"Cache hit for user {telegram_id}: {row['status']}")
                    return bool(row['is_member']), row['status']

        # Make fresh API call to Telegram
        logger.info(f"Making fresh API call for user {telegram_id}")
        result = telegram_api_request("getChatMember", {
            "chat_id": CHANNEL,  # Channel username or ID
            "user_id": telegram_id
        })

        if not result or not result.get("ok"):
            logger.error(f"Failed to get chat member for {telegram_id}")
            return False, "api_error"

        member_data = result["result"]
        status = member_data.get("status", "left")

        # Determine if user is a member
        is_member = status in ["member", "administrator", "creator"]

        # Update database cache
        db.execute(
            """INSERT OR REPLACE INTO channel_members
               (telegram_id, is_member, status, checked_at, last_seen, check_count)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                       COALESCE((SELECT check_count FROM channel_members WHERE telegram_id = ?), 0) + 1)""",
            (telegram_id, is_member, status, telegram_id)
        )
        db.commit()

        logger.info(f"User {telegram_id} status: {status} (member: {is_member})")
        return is_member, status

    except Exception as e:
        logger.error(f"Membership check error for {telegram_id}: {e}")
        return False, "error"

def is_user_in_channel(telegram_id: int) -> bool:
    """Simple wrapper to check if user is in channel"""
    is_member, _ = check_channel_membership(telegram_id)
    return is_member

# ==========================
# ID VALIDATION
# ==========================
def validate_user_id(user_id: str) -> Tuple[bool, str]:
    """Validate user ID format"""
    if not user_id or len(user_id.strip()) < 3:
        return False, "ID must be at least 3 characters"

    user_id = user_id.strip()

    if len(user_id) > 100:
        return False, "ID cannot exceed 100 characters"

    if not re.match(r'^[a-zA-Z0-9_\-\.@]+$', user_id):
        return False, "Only letters, numbers, _, -, ., @ allowed"

    return True, "Valid ID"

# ==========================
# DATA MANAGEMENT - FIXED
# ==========================
def add_authorized_id(telegram_id: int, user_id: str, username: str = None, display_name: str = None) -> Tuple[bool, str]:
    """Add authorized ID to database"""
    try:
        # First check if user is in channel
        is_member, status = check_channel_membership(telegram_id, force_fresh=True)
        if not is_member:
            return False, f"You must join {CHANNEL} first! Current status: {status}"

        # Validate ID format
        is_valid, error_msg = validate_user_id(user_id)
        if not is_valid:
            return False, error_msg

        # Check for duplicates
        cursor = db.execute(
            "SELECT user_id FROM authorized_ids WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        if cursor and cursor.fetchone():
            return False, "⚠️ This ID already exists in the system"

        # Add to database
        db.execute(
            """INSERT INTO authorized_ids
               (user_id, telegram_id, username, display_name, last_verified, status)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'active')""",
            (user_id, telegram_id, username, display_name)
        )

        # Update user session stats
        db.execute(
            """INSERT OR REPLACE INTO user_sessions
               (telegram_id, last_active, total_ids_added)
               VALUES (?, CURRENT_TIMESTAMP,
                       COALESCE((SELECT total_ids_added FROM user_sessions WHERE telegram_id = ?), 0) + 1)""",
            (telegram_id, telegram_id)
        )

        db.commit()
        logger.info(f"Added ID {user_id} for user {telegram_id}")

        return True, "✅ ID added successfully!"

    except Exception as e:
        logger.error(f"Error adding ID: {e}")
        return False, "❌ Database error, please try again"

def get_user_authorized_ids(telegram_id: int) -> List[str]:
    """Get all active IDs for a user"""
    try:
        cursor = db.execute(
            "SELECT user_id FROM authorized_ids WHERE telegram_id = ? AND status = 'active' ORDER BY added_at DESC",
            (telegram_id,)
        )
        if cursor:
            return [row['user_id'] for row in cursor.fetchall()]
        return []
    except:
        return []

def get_all_authorized_ids() -> List[str]:
    """Get all active IDs in system"""
    try:
        cursor = db.execute(
            "SELECT user_id FROM authorized_ids WHERE status = 'active' ORDER BY added_at DESC"
        )
        if cursor:
            return [row['user_id'] for row in cursor.fetchall()]
        return []
    except:
        return []

def remove_user_authorizations(telegram_id: int, reason: str = "left_channel") -> Tuple[bool, int]:
    """Remove all authorizations for a user"""
    try:
        # Count how many IDs will be removed
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM authorized_ids WHERE telegram_id = ? AND status = 'active'",
            (telegram_id,)
        )
        count_row = cursor.fetchone() if cursor else None
        ids_count = count_row['count'] if count_row else 0

        if ids_count == 0:
            return True, 0

        # Update status to 'removed'
        db.execute(
            "UPDATE authorized_ids SET status = 'removed' WHERE telegram_id = ? AND status = 'active'",
            (telegram_id,)
        )

        # Log the removal
        db.execute(
            "INSERT INTO removal_log (telegram_id, reason, ids_removed) VALUES (?, ?, ?)",
            (telegram_id, reason, ids_count)
        )

        # Update channel member status
        db.execute(
            "UPDATE channel_members SET is_member = 0, status = 'left' WHERE telegram_id = ?",
            (telegram_id,)
        )

        db.commit()
        logger.info(f"Removed {ids_count} IDs for user {telegram_id} (reason: {reason})")

        return True, ids_count

    except Exception as e:
        logger.error(f"Error removing authorizations: {e}")
        return False, 0

# ==========================
# ANTI-LEAVE MONITOR - COMPLETELY FIXED
# ==========================
def anti_leave_monitor():
    """
    Main anti-leave monitoring function
    Checks all users with active IDs and removes them if they left the channel
    """
    logger.info("🚀 Starting Anti-Leave Monitor...")

    while True:
        try:
            # Get all unique users with active IDs
            cursor = db.execute(
                "SELECT DISTINCT telegram_id FROM authorized_ids WHERE status = 'active'"
            )

            if not cursor:
                logger.warning("No users found in database")
                time.sleep(60)
                continue

            users = [row['telegram_id'] for row in cursor.fetchall()]
            total_users = len(users)

            if total_users == 0:
                logger.info("No active users to monitor")
                time.sleep(60)
                continue

            logger.info(f"🔍 Checking {total_users} users for channel membership...")

            removed_count = 0
            active_count = 0

            for telegram_id in users:
                try:
                    # Check channel membership (force fresh check)
                    is_member, status = check_channel_membership(telegram_id, force_fresh=True)

                    if not is_member:
                        # User is not in channel, remove their IDs
                        success, ids_removed = remove_user_authorizations(telegram_id, f"anti_leave_{status}")
                        if success and ids_removed > 0:
                            removed_count += 1
                            logger.warning(f"🚨 Removed {ids_removed} IDs for user {telegram_id} (status: {status})")

                            # Send notification to user if they're still reachable
                            try:
                                send_message(
                                    telegram_id,
                                    f"⚠️ <b>Access Revoked</b>\n\n"
                                    f"Your authorization has been removed because you left {CHANNEL}\n\n"
                                    f"<i>Rejoin the channel and add your IDs again.</i>"
                                )
                            except:
                                pass  # User might have blocked the bot
                    else:
                        active_count += 1

                    # Update last verification time for active IDs
                    if is_member:
                        db.execute(
                            "UPDATE authorized_ids SET last_verified = CURRENT_TIMESTAMP WHERE telegram_id = ? AND status = 'active'",
                            (telegram_id,)
                        )
                        db.commit()

                    # Small delay to avoid rate limiting
                    time.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error processing user {telegram_id}: {e}")
                    continue

            logger.info(f"✅ Anti-leave check completed: {active_count} active, {removed_count} removed")

            # Sleep before next check (adjust based on your needs)
            sleep_time = 60  # Check every 60 seconds
            logger.info(f"💤 Sleeping for {sleep_time} seconds...")
            time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Anti-leave monitor error: {e}")
            time.sleep(30)  # Shorter sleep on error

# ==========================
# PERIODIC CLEANUP
# ==========================
def periodic_cleanup():
    """Clean up old data and optimize database"""
    while True:
        try:
            logger.info("🧹 Running periodic cleanup...")

            # Remove old channel member records (older than 7 days)
            db.execute(
                "DELETE FROM channel_members WHERE checked_at < datetime('now', '-7 days')"
            )

            # Remove old removal logs (older than 30 days)
            db.execute(
                "DELETE FROM removal_log WHERE removed_at < datetime('now', '-30 days')"
            )

            # Remove old user sessions (inactive for 30 days)
            db.execute(
                "DELETE FROM user_sessions WHERE last_active < datetime('now', '-30 days')"
            )

            # Optimize database
            db.execute("VACUUM")

            db.commit()
            logger.info("✅ Cleanup completed")

            # Run every 6 hours
            time.sleep(6 * 3600)

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            time.sleep(3600)

# ==========================
# BOT HANDLERS - FIXED
# ==========================
def handle_start_command(telegram_id: int, user_name: str, username: str = None):
    """Handle /start command"""
    try:
        # Check channel membership
        is_member, status = check_channel_membership(telegram_id)

        if is_member:
            # User is in channel
            user_ids = get_user_authorized_ids(telegram_id)

            message = f"""
✨ <b>Welcome, {html.escape(user_name)}!</b> ✨

✅ <b>Channel Verified</b>
Status: {status.upper()}

📊 <b>Your Stats:</b>
• Active IDs: {len(user_ids)}
• Last Active: Now
• Anti-Leave: ACTIVE

🚀 <b>How to add IDs:</b>
Just send any ID as a message!
Format: 3-100 characters
Allowed: A-Z, 0-9, _, -, ., @

📋 <b>Your IDs:</b>
"""

            if user_ids:
                for i, uid in enumerate(user_ids[:5], 1):
                    message += f"{i}. <code>{html.escape(uid)}</code>\n"
                if len(user_ids) > 5:
                    message += f"... and {len(user_ids) - 5} more\n"
            else:
                message += "<i>No IDs added yet</i>\n"

            message += f"\n🔒 <b>Important:</b> Stay in {CHANNEL} to keep your IDs active!"

        else:
            # User is not in channel
            message = f"""
🔒 <b>Access Required</b>

Hello {html.escape(user_name)}!

📢 <b>Channel:</b> {CHANNEL}

⚠️ <b>You must join to:</b>
• Add authorization IDs
• Access all features
• Use the system

⚡ <b>After joining:</b>
Send /start again to verify

🛡️ <b>Anti-Leave System:</b>
Your IDs will be automatically removed if you leave the channel.

<i>Current status: {status.upper()}</i>
"""

        send_message(telegram_id, message)

    except Exception as e:
        logger.error(f"Start command error: {e}")
        send_message(telegram_id, "❌ An error occurred. Please try again.")

def handle_id_input(telegram_id: int, user_name: str, user_id: str, username: str = None):
    """Handle ID input from user"""
    try:
        # Step 1: Validate ID
        is_valid, error_msg = validate_user_id(user_id)
        if not is_valid:
            send_message(telegram_id, f"❌ <b>Invalid ID</b>\n\n{error_msg}")
            return

        # Step 2: Check channel membership (FRESH CHECK)
        send_message(telegram_id, "🔍 <i>Verifying channel membership...</i>")
        is_member, status = check_channel_membership(telegram_id, force_fresh=True)

        if not is_member:
            send_message(
                telegram_id,
                f"❌ <b>Access Denied</b>\n\n"
                f"You must join {CHANNEL} first!\n"
                f"Current status: <b>{status.upper()}</b>\n\n"
                f"<i>After joining, send /start to verify.</i>"
            )
            return

        # Step 3: Add ID to database
        send_message(telegram_id, "📝 <i>Adding to database...</i>")
        success, result_msg = add_authorized_id(telegram_id, user_id, username, user_name)

        if success:
            # Get updated counts
            user_ids = get_user_authorized_ids(telegram_id)
            all_ids = get_all_authorized_ids()

            # Success message
            success_message = f"""
🎉 <b>SUCCESS!</b>

✅ <b>ID Added:</b> <code>{html.escape(user_id)}</code>
👤 <b>User:</b> {html.escape(user_name)}
📊 <b>Your IDs:</b> {len(user_ids)}
🌐 <b>Total IDs:</b> {len(all_ids)}
🕒 <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}

🔒 <b>Security Status:</b>
• Channel: ✅ VERIFIED
• Anti-leave: ✅ ACTIVE
• Monitoring: ✅ 24/7

⚠️ <b>Important:</b>
Stay in {CHANNEL} to keep your IDs active!
Leaving will auto-remove all your IDs.
"""
            send_message(telegram_id, success_message)
        else:
            send_message(telegram_id, result_msg)

    except Exception as e:
        logger.error(f"ID input error: {e}")
        send_message(telegram_id, "❌ An error occurred. Please try again.")

def handle_stats_command(telegram_id: int, user_name: str):
    """Handle /stats command"""
    try:
        # Get user's stats
        user_ids = get_user_authorized_ids(telegram_id)
        all_ids = get_all_authorized_ids()

        # Get channel status
        is_member, status = check_channel_membership(telegram_id)

        # Get system stats
        cursor = db.execute("SELECT COUNT(DISTINCT telegram_id) as users FROM authorized_ids WHERE status = 'active'")
        unique_users = cursor.fetchone()['users'] if cursor else 0

        cursor = db.execute("SELECT COUNT(*) as removed FROM removal_log WHERE removed_at > datetime('now', '-1 day')")
        daily_removals = cursor.fetchone()['removed'] if cursor else 0

        message = f"""
📊 <b>SYSTEM STATISTICS</b>

👤 <b>Your Profile:</b>
• Name: {html.escape(user_name)}
• Your IDs: {len(user_ids)}
• Channel: {status.upper()} {'✅' if is_member else '❌'}

🌐 <b>Global Stats:</b>
• Total IDs: {len(all_ids)}
• Unique Users: {unique_users}
• Daily Removals: {daily_removals}

⚡ <b>Anti-Leave System:</b>
• Status: ACTIVE
• Checks: Every 60 seconds
• Protection: MAXIMUM

🔒 <b>Security:</b>
• Real-time verification
• Automatic cleanup
• Activity logging

<code>🔄 Updated: {datetime.now().strftime('%H:%M:%S')}</code>
"""

        send_message(telegram_id, message)

    except Exception as e:
        logger.error(f"Stats error: {e}")
        send_message(telegram_id, "❌ Could not fetch statistics.")

# ==========================
# BOT POLLING - FIXED
# ==========================
def bot_polling():
    """Main bot polling loop"""
    offset = 0
    error_count = 0

    logger.info("🤖 Starting bot polling...")

    while True:
        try:
            # Get updates from Telegram
            result = telegram_api_request("getUpdates", {
                "offset": offset,
                "timeout": 30,
                "allowed_updates": ["message"]
            })

            if result and result.get("ok"):
                updates = result.get("result", [])

                for update in updates:
                    offset = update["update_id"] + 1

                    if "message" in update:
                        msg = update["message"]
                        telegram_id = msg.get("from", {}).get("id")
                        user_name = msg.get("from", {}).get("first_name", "User")
                        username = msg.get("from", {}).get("username")
                        text = msg.get("text", "").strip()

                        if not telegram_id or not text:
                            continue

                        logger.info(f"📨 Message from {telegram_id}: {text[:50]}")

                        # Handle commands
                        if text == "/start":
                            threading.Thread(
                                target=handle_start_command,
                                args=(telegram_id, user_name, username),
                                daemon=True
                            ).start()

                        elif text == "/stats":
                            threading.Thread(
                                target=handle_stats_command,
                                args=(telegram_id, user_name),
                                daemon=True
                            ).start()

                        elif text == "/help":
                            help_msg = """
🆘 <b>HELP GUIDE</b>

<b>Commands:</b>
/start - Start bot & check membership
/stats - View your statistics
/help - Show this help

<b>How to use:</b>
1. Join the required channel
2. Send /start to verify
3. Send any ID to add it
4. Stay in channel to keep IDs active

<b>ID Format:</b>
• 3-100 characters
• Letters, numbers, _, -, ., @
• Case sensitive

<b>Anti-Leave System:</b>
• Automatically removes IDs if you leave
• Checks every 60 seconds
• Notifications sent on removal
• Must rejoin to re-add IDs

<b>Need help?</b>
Contact the channel admin.
"""
                            send_message(telegram_id, help_msg)

                        elif text.startswith('/'):
                            send_message(telegram_id, "❌ Unknown command. Use /help for available commands.")

                        else:
                            # Regular message - treat as ID input
                            threading.Thread(
                                target=handle_id_input,
                                args=(telegram_id, user_name, text, username),
                                daemon=True
                            ).start()

                error_count = 0

            else:
                error_count += 1
                if error_count > 5:
                    logger.warning("Multiple API errors, waiting 30 seconds...")
                    time.sleep(30)
                    error_count = 0

            time.sleep(0.5)

        except Exception as e:
            error_count += 1
            logger.error(f"Polling error: {e}")

            if error_count > 10:
                logger.critical("Critical error count, waiting 60 seconds...")
                time.sleep(60)
                error_count = 0
            else:
                time.sleep(5)

# ==========================
# FLASK ROUTES
# ==========================
@app.route('/')
def dashboard():
    """Dashboard page"""
    stats = get_system_stats()

    html_template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>🔐 Vishal Auth System</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                max-width: 1000px;
                width: 100%;
            }
            h1 {
                color: #333;
                text-align: center;
                margin-bottom: 10px;
            }
            .subtitle {
                text-align: center;
                color: #666;
                margin-bottom: 40px;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 40px;
            }
            .stat-card {
                background: #f8f9fa;
                padding: 25px;
                border-radius: 15px;
                text-align: center;
                border-left: 5px solid #667eea;
                transition: transform 0.3s;
            }
            .stat-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.1);
            }
            .stat-value {
                font-size: 2.5rem;
                font-weight: bold;
                color: #667eea;
                margin: 10px 0;
            }
            .stat-label {
                color: #666;
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .status-badge {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                background: #10b981;
                color: white;
                padding: 10px 20px;
                border-radius: 50px;
                font-weight: bold;
                margin: 20px 0;
            }
            .live-dot {
                width: 10px;
                height: 10px;
                background: white;
                border-radius: 50%;
                animation: pulse 1.5s infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            .endpoints {
                background: #f8f9fa;
                padding: 30px;
                border-radius: 15px;
                margin-top: 30px;
            }
            .endpoint {
                background: white;
                padding: 20px;
                margin: 15px 0;
                border-radius: 10px;
                border-left: 4px solid #667eea;
            }
            .endpoint-url {
                font-family: monospace;
                background: #f1f3f4;
                padding: 10px;
                border-radius: 5px;
                margin: 10px 0;
                word-break: break-all;
            }
            .btn {
                display: inline-block;
                padding: 12px 24px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-weight: bold;
                transition: background 0.3s;
                border: none;
                cursor: pointer;
                margin: 5px;
            }
            .btn:hover {
                background: #5a67d8;
            }
            .btn-secondary {
                background: transparent;
                border: 2px solid #667eea;
                color: #667eea;
            }
            .btn-secondary:hover {
                background: #667eea;
                color: white;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Vishal Authorization System</h1>
            <p class="subtitle">Professional ID Management with Anti-Leave Protection</p>

            <div style="text-align: center;">
                <div class="status-badge">
                    <div class="live-dot"></div>
                    <span>ANTI-LEAVE SYSTEM: ACTIVE</span>
                </div>
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total IDs</div>
                    <div class="stat-value" id="totalIds">''' + str(stats.get('total_ids', 0)) + '''</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Active Users</div>
                    <div class="stat-value" id="activeUsers">''' + str(stats.get('unique_users', 0)) + '''</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Daily Checks</div>
                    <div class="stat-value" id="dailyChecks">''' + str(stats.get('hourly_checks', 0) * 24) + '''</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Removals (24h)</div>
                    <div class="stat-value" id="dailyRemovals">''' + str(stats.get('daily_removals', 0)) + '''</div>
                </div>
            </div>

            <div class="endpoints">
                <h3>📡 API Endpoints</h3>

                <div class="endpoint">
                    <strong>GET /auth</strong><br>
                    <small>Get all authorized IDs (one per line)</small>
                    <div class="endpoint-url" id="authUrl">/auth</div>
                    <button class="btn" onclick="copyUrl('authUrl')">Copy URL</button>
                    <a href="/auth" target="_blank" class="btn btn-secondary">Open</a>
                </div>

                <div class="endpoint">
                    <strong>GET /stats</strong><br>
                    <small>Get system statistics (JSON)</small>
                    <div class="endpoint-url" id="statsUrl">/stats</div>
                    <button class="btn" onclick="copyUrl('statsUrl')">Copy URL</button>
                    <a href="/stats" target="_blank" class="btn btn-secondary">Open</a>
                </div>

                <div class="endpoint">
                    <strong>GET /verify/{user_id}</strong><br>
                    <small>Check if ID is authorized</small>
                    <div class="endpoint-url" id="verifyUrl">/verify/{user_id}</div>
                    <button class="btn" onclick="copyUrl('verifyUrl')">Copy URL</button>
                    <button class="btn btn-secondary" onclick="showDemo()">Try Demo</button>
                </div>
            </div>

            <div style="margin-top: 40px; text-align: center; color: #666;">
                <p><strong>Channel:</strong> ''' + CHANNEL + '''</p>
                <p><strong>Status:</strong> <span style="color: green;">●</span> Operational</p>
                <p><strong>Anti-Leave:</strong> Checks every 60 seconds</p>
                <p id="updateTime"><strong>Updated:</strong> ''' + datetime.now().strftime('%H:%M:%S') + '''</p>
            </div>
        </div>

        <script>
            function copyUrl(elementId) {
                const text = document.getElementById(elementId).textContent;
                const fullUrl = window.location.origin + text;
                navigator.clipboard.writeText(fullUrl).then(() => {
                    alert('URL copied to clipboard!');
                });
            }

            function showDemo() {
                const id = prompt('Enter ID to verify (or use "test123"):', 'test123');
                if (id) {
                    window.open('/verify/' + encodeURIComponent(id), '_blank');
                }
            }

            // Auto-update stats every 10 seconds
            async function updateStats() {
                try {
                    const response = await fetch('/stats');
                    const data = await response.json();

                    document.getElementById('totalIds').textContent = data.total_ids || 0;
                    document.getElementById('activeUsers').textContent = data.unique_users || 0;
                    document.getElementById('dailyChecks').textContent = (data.hourly_checks || 0) * 24;
                    document.getElementById('dailyRemovals').textContent = data.daily_removals || 0;
                    document.getElementById('updateTime').innerHTML = '<strong>Updated:</strong> ' +
                        new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
                } catch (error) {
                    console.error('Failed to update stats:', error);
                }
            }

            setInterval(updateStats, 10000);
            updateStats();
        </script>
    </body>
    </html>
    '''

    return render_template_string(html_template, stats=stats)

@app.route('/auth')
def get_auth_data():
    """Get all authorized IDs"""
    try:
        format_type = request.args.get('format', 'text')
        ids = get_all_authorized_ids()

        if format_type == 'json':
            return jsonify({
                'success': True,
                'count': len(ids),
                'data': ids,
                'timestamp': datetime.now().isoformat(),
                'anti_leave': 'active'
            })
        else:
            response = "\n".join(ids)
            return response, 200, {
                'Content-Type': 'text/plain; charset=utf-8',
                'Cache-Control': 'no-cache',
                'X-Total-Count': str(len(ids))
            }
    except Exception as e:
        logger.error(f"Auth endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/stats')
def get_system_stats():
    """Get system statistics"""
    try:
        ids = get_all_authorized_ids()

        cursor = db.execute("SELECT COUNT(DISTINCT telegram_id) as users FROM authorized_ids WHERE status = 'active'")
        unique_users = cursor.fetchone()['users'] if cursor else 0

        cursor = db.execute("SELECT COUNT(*) as checks FROM channel_members WHERE checked_at > datetime('now', '-1 hour')")
        hourly_checks = cursor.fetchone()['checks'] if cursor else 0

        cursor = db.execute("SELECT COUNT(*) as removed FROM removal_log WHERE removed_at > datetime('now', '-1 day')")
        daily_removals = cursor.fetchone()['removed'] if cursor else 0

        cursor = db.execute("SELECT COUNT(*) as active FROM channel_members WHERE is_member = 1")
        active_members = cursor.fetchone()['active'] if cursor else 0

        cursor = db.execute("SELECT user_id, added_at FROM authorized_ids WHERE status = 'active' ORDER BY added_at DESC LIMIT 1")
        last_row = cursor.fetchone() if cursor else None

        return jsonify({
            'total_ids': len(ids),
            'unique_users': unique_users,
            'hourly_checks': hourly_checks,
            'daily_removals': daily_removals,
            'active_members': active_members,
            'last_added': last_row['user_id'] if last_row else None,
            'last_added_time': last_row['added_at'] if last_row else None,
            'timestamp': datetime.now().isoformat(),
            'status': 'operational',
            'channel': CHANNEL,
            'anti_leave': 'active',
            'check_interval': '60 seconds'
        })
    except Exception as e:
        logger.error(f"Stats endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/verify/<user_id>')
def verify_user_id(user_id):
    """Verify if user ID is authorized"""
    try:
        cursor = db.execute(
            "SELECT telegram_id, display_name, added_at FROM authorized_ids WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        row = cursor.fetchone() if cursor else None

        if row:
            telegram_id = row['telegram_id']
            is_member, status = check_channel_membership(telegram_id)

            return jsonify({
                'authorized': True,
                'user_id': user_id,
                'user_name': row['display_name'],
                'channel_member': is_member,
                'channel_status': status,
                'added_at': row['added_at'],
                'anti_leave_status': 'protected' if is_member else 'will_be_removed',
                'message': 'ID is authorized' + ('' if is_member else ' but user left channel (will be removed)')
            })
        else:
            return jsonify({
                'authorized': False,
                'user_id': user_id,
                'message': 'ID not found in database'
            })
    except Exception as e:
        logger.error(f"Verify endpoint error: {e}")
        return jsonify({'error': str(e)}), 500

# ==========================
# STARTUP
# ==========================
def startup():
    """Start all services"""
    print("\n" + "="*70)
    print("🚀 VISHAL AUTHORIZATION SYSTEM - ANTI-LEAVE EDITION".center(70))
    print("="*70)

    print("\n✅ Database initialized")
    print("✅ Channel: " + CHANNEL)
    print("✅ Anti-leave system ready")
    print("✅ Bot polling started")
    print(f"✅ Web server on port {PORT}")

    print("\n🔧 Services started:")
    print("   • Bot message handler")
    print("   • Anti-leave monitor (60s checks)")
    print("   • Periodic cleanup")
    print("   • Web dashboard")

    print("\n📡 Endpoints:")
    print(f"   • Dashboard: http://0.0.0.0:{PORT}/")
    print(f"   • Raw IDs: http://0.0.0.0:{PORT}/auth")
    print(f"   • JSON IDs: http://0.0.0.0:{PORT}/auth?format=json")
    print(f"   • Stats: http://0.0.0.0:{PORT}/stats")
    print(f"   • Verify: http://0.0.0.0:{PORT}/verify/{{id}}")

    print("\n⚡ Anti-Leave Features:")
    print("   • Real-time membership checks")
    print("   • Automatic ID removal on leave")
    print("   • 60-second check intervals")
    print("   • User notifications")
    print("   • Comprehensive logging")

    print("\n🔒 Security:")
    print("   • Fresh API checks for each operation")
    print("   • Database caching for performance")
    print("   • Input validation")
    print("   • Error recovery")

    print("="*70)
    print("🎯 SYSTEM READY - ANTI-LEAVE PROTECTION ACTIVE")
    print("="*70 + "\n")

# ==========================
# MAIN ENTRY POINT
# ==========================
if __name__ == "__main__":
    try:
        # Start background services
        threading.Thread(target=bot_polling, daemon=True).start()
        threading.Thread(target=anti_leave_monitor, daemon=True).start()
        threading.Thread(target=periodic_cleanup, daemon=True).start()

        # Run startup sequence
        startup()

        # Run Flask app
        app.run(
            host="0.0.0.0",
            port=PORT,
            debug=False,
            threaded=True,
            use_reloader=False
        )

    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
        db.close()
        print("✅ Database closed")
        print("🎯 System stopped")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        traceback.print_exc()