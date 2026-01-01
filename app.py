#!/usr/bin/env python3
# ============================================================
#     VISHAL X BOT - PRODUCTION FINAL v6.0 (2026 MODERN UI)
#     Instant Leave Delete | Auto Restore | Reply Fix
#     409 Fix | No Webhook Conflict | Stable Poller Engine
# ============================================================

import os, time, requests, threading, sqlite3
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string

# ===================== CONFIG ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN","8504965473:AAE0yYTi4DWvpdopOBkjA0AucJf0tknHDJE")
CHANNEL   = os.getenv("CHANNEL","@vishalxnetwork4")
ADMIN_KEY = os.getenv("ADMIN_KEY","VISHAL2026")
API       = f"https://api.telegram.org/bot{BOT_TOKEN}"
PORT      = int(os.getenv("PORT",8080))
SCAN_TIME = 1
RESTORE_AFTER_JOIN = True

# ============================================================
# ===================== DATABASE FIXED =======================
# ============================================================
os.makedirs("database",exist_ok=True)
db = sqlite3.connect("database/data.db",check_same_thread=False)
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

def add_id(tg,uid):
    cur.execute("INSERT OR IGNORE INTO users VALUES(?,?,?,datetime('now'))",(tg,uid,"active"))
    db.commit()

def delete_ids(tg):
    cur.execute("DELETE FROM users WHERE tg=?",(tg,))
    db.commit()

def restore_ids(tg):
    cur.execute("UPDATE users SET status='active', joined=datetime('now') WHERE tg=?",(tg,))
    db.commit()

def user_list():
    return cur.execute("SELECT DISTINCT tg FROM users").fetchall()

def get_stats():
    total = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    users = cur.execute("SELECT COUNT(DISTINCT tg) FROM users").fetchone()[0]
    today = cur.execute("SELECT COUNT(*) FROM users WHERE date(joined)=date('now')").fetchone()[0]
    return total, users, today

# ============================================================
# ================= TELEGRAM API FUNCTIONS ===================
# ============================================================
def send(tg,msg):
    try:
        r = requests.post(f"{API}/sendMessage",
        json={"chat_id":tg,"text":msg,"parse_mode":"HTML"},timeout=5)
        return r.status_code
    except Exception as e:
        print("SEND ERROR:",e)
        return False

def member(tg):
    try:
        r = requests.post(f"{API}/getChatMember",
        json={"chat_id":CHANNEL,"user_id":tg},timeout=5).json()
        status = r.get("result",{}).get("status","left")
        return status in ["member","administrator","creator"]
    except:
        return False

# ============================================================
# ================= INSTANT MONITOR ENGINE ===================
# ============================================================
def monitor():
    print("🛡 Anti-Leave Monitor Started")
    while True:
        for (tg,) in user_list():
            if not member(tg):
                delete_ids(tg)
                send(tg,
                f"🚫 <b>ACCESS REVOKED</b>\n\n"
                f"📛 Channel Left: {CHANNEL}\n"
                f"🗑️ All IDs deleted instantly\n\n"
                f"🔓 <b>Rejoin and use /start to restore</b>")
                print(f"[REMOVE] {tg} LEFT → IDs Deleted")
        time.sleep(SCAN_TIME)

# ============================================================
# ===================== MESSAGE HANDLER ======================
# ============================================================
def handler(update):
    msg = update.get("message")
    if not msg: return

    tg = msg["from"]["id"]
    txt = msg.get("text","")
    if txt is None: return

    # START COMMAND
    if txt == "/start":
        if not member(tg):
            return send(tg,
            f"🔐 <b>ACCESS DENIED</b>\n\n"
            f"Join required channel first:\n"
            f"👉 {CHANNEL}\n\n"
            f"After joining, send /start again")

        restore_ids(tg)
        return send(tg,
        "🎉 <b>ACCESS RESTORED</b>\n\n"
        "✅ All previous IDs recovered\n"
        "📝 Now send your ID to save\n\n"
        "<i>Bot will auto-delete IDs if you leave channel</i>")

    # ADD ID
    if txt and not txt.startswith("/"):
        if not member(tg):
            return send(tg,
            f"❌ <b>CHANNEL LEFT</b>\n\n"
            f"You left {CHANNEL}\n"
            f"Rejoin and send /start")
        add_id(tg,txt)
        return send(tg,
        f"💾 <b>ID SAVED SUCCESSFULLY</b>\n\n"
        f"📄 Your ID: <code>{txt}</code>\n\n"
        f"🛡️ Protected by anti-leave system")

# ============================================================
# ======================== POLLER FIX ========================
# ============================================================
def poller():
    offset = 0
    print("🔄 Removing webhook (409 fix)...")
    requests.post(f"{API}/deleteWebhook",json={"drop_pending_updates":True})

    print("🤖 Bot Poller Started")
    while True:
        try:
            updates = requests.post(f"{API}/getUpdates",
            json={"offset":offset,"timeout":30}).json()

            for upd in updates.get("result",[]):
                offset = upd["update_id"] + 1
                handler(upd)

        except Exception as e:
            print("Poller Error:",e)
            time.sleep(2)

# ============================================================
# ==================== MODERN DASHBOARD UI ===================
# ============================================================
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VISHAL X BOT - ADMIN PANEL</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        }
        
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #10b981;
            --danger: #ef4444;
            --dark: #1f2937;
            --light: #f9fafb;
            --gray: #9ca3af;
            --border: #e5e7eb;
        }
        
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 25px;
        }
        
        .logo-icon {
            width: 60px;
            height: 60px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            border-radius: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 28px;
        }
        
        .logo-text h1 {
            font-size: 32px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
        }
        
        .logo-text p {
            color: var(--gray);
            font-size: 14px;
            margin-top: 5px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
            border-left: 4px solid var(--primary);
            transition: transform 0.3s ease;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-card.total { border-left-color: var(--primary); }
        .stat-card.users { border-left-color: var(--secondary); }
        .stat-card.today { border-left-color: #f59e0b; }
        
        .stat-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 15px;
        }
        
        .stat-icon {
            width: 48px;
            height: 48px;
            background: var(--primary);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 20px;
        }
        
        .stat-icon.total { background: var(--primary); }
        .stat-icon.users { background: var(--secondary); }
        .stat-icon.today { background: #f59e0b; }
        
        .stat-value {
            font-size: 36px;
            font-weight: 700;
            color: var(--dark);
            margin-bottom: 5px;
        }
        
        .stat-label {
            color: var(--gray);
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .content-box {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .box-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 2px solid var(--border);
        }
        
        .box-title {
            font-size: 24px;
            font-weight: 600;
            color: var(--dark);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .export-btn {
            background: var(--primary);
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 10px;
            cursor: pointer;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
            text-decoration: none;
        }
        
        .export-btn:hover {
            background: var(--primary-dark);
            transform: translateY(-2px);
        }
        
        .ids-container {
            background: var(--light);
            border-radius: 15px;
            padding: 20px;
            max-height: 500px;
            overflow-y: auto;
            font-family: 'Monaco', 'Courier New', monospace;
            line-height: 1.8;
            font-size: 14px;
            border: 1px solid var(--border);
        }
        
        .id-item {
            padding: 10px 15px;
            margin: 5px 0;
            background: white;
            border-radius: 8px;
            border-left: 3px solid var(--primary);
            display: flex;
            align-items: center;
            gap: 10px;
            transition: all 0.2s ease;
        }
        
        .id-item:hover {
            background: #f3f4f6;
            transform: translateX(5px);
        }
        
        .id-number {
            color: var(--primary);
            font-weight: 600;
            min-width: 30px;
        }
        
        .footer {
            text-align: center;
            margin-top: 30px;
            padding: 20px;
            color: rgba(255, 255, 255, 0.8);
            font-size: 14px;
        }
        
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #dcfce7;
            color: #166534;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .pulse {
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }
        
        @media (max-width: 768px) {
            .header, .content-box {
                padding: 20px;
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
            }
            
            .box-header {
                flex-direction: column;
                gap: 15px;
                align-items: flex-start;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <div class="logo-icon">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="logo-text">
                    <h1>VISHAL X BOT</h1>
                    <p>v6.0 • 2026 READY • ANTI-LEAVE PROTECTION</p>
                </div>
            </div>
            
            <div class="status-badge">
                <i class="fas fa-circle pulse" style="color: #10b981; font-size: 8px;"></i>
                SYSTEM ACTIVE • MONITORING {{ stats[1] }} USERS
            </div>
            
            <div class="stats-grid">
                <div class="stat-card total">
                    <div class="stat-header">
                        <div class="stat-icon total">
                            <i class="fas fa-database"></i>
                        </div>
                        <div>
                            <div class="stat-value">{{ stats[0] }}</div>
                            <div class="stat-label">Total IDs Stored</div>
                        </div>
                    </div>
                </div>
                
                <div class="stat-card users">
                    <div class="stat-header">
                        <div class="stat-icon users">
                            <i class="fas fa-users"></i>
                        </div>
                        <div>
                            <div class="stat-value">{{ stats[1] }}</div>
                            <div class="stat-label">Active Users</div>
                        </div>
                    </div>
                </div>
                
                <div class="stat-card today">
                    <div class="stat-header">
                        <div class="stat-icon today">
                            <i class="fas fa-calendar-day"></i>
                        </div>
                        <div>
                            <div class="stat-value">{{ stats[2] }}</div>
                            <div class="stat-label">Today's Adds</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="content-box">
            <div class="box-header">
                <div class="box-title">
                    <i class="fas fa-key" style="color: var(--primary);"></i>
                    STORED IDENTIFIERS
                </div>
                <a href="/export?key={{ key }}" class="export-btn">
                    <i class="fas fa-download"></i>
                    EXPORT ALL
                </a>
            </div>
            
            <div class="ids-container">
                {% if data %}
                    {% for id in data %}
                    <div class="id-item">
                        <span class="id-number">{{ loop.index }}</span>
                        <span>{{ id[0] }}</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <div style="text-align: center; padding: 40px; color: var(--gray);">
                        <i class="fas fa-inbox" style="font-size: 48px; margin-bottom: 20px; opacity: 0.5;"></i>
                        <p>No IDs stored yet</p>
                    </div>
                {% endif %}
            </div>
        </div>
        
        <div class="footer">
            <p>© 2026 VISHAL X BOT • Protected by Instant Anti-Leave System</p>
            <p style="margin-top: 5px; font-size: 12px; opacity: 0.7;">
                Last updated: {{ timestamp }} | Auto-scan every {{ scan_time }}s
            </p>
        </div>
    </div>
    
    <script>
        // Auto refresh every 30 seconds
        setTimeout(() => {
            window.location.reload();
        }, 30000);
        
        // Smooth scroll to top
        document.querySelector('.export-btn').addEventListener('click', function(e) {
            if(this.getAttribute('href') !== '#') {
                window.scrollTo({top: 0, behavior: 'smooth'});
            }
        });
        
        // Add copy functionality
        document.querySelectorAll('.id-item').forEach(item => {
            item.addEventListener('click', function() {
                const id = this.querySelector('span:last-child').textContent;
                navigator.clipboard.writeText(id).then(() => {
                    const original = this.innerHTML;
                    this.innerHTML = '<i class="fas fa-check"></i> Copied!';
                    setTimeout(() => {
                        this.innerHTML = original;
                    }, 2000);
                });
            });
        });
    </script>
</body>
</html>
"""

@app.route("/")
def panel():
    key = request.args.get("key")
    if key != ADMIN_KEY:
        return '''
        <div style="display: flex; justify-content: center; align-items: center; height: 100vh; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <div style="background: white; padding: 40px; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.2); text-align: center;">
                <div style="color: #ef4444; font-size: 48px; margin-bottom: 20px;">
                    <i class="fas fa-lock"></i>
                </div>
                <h2 style="color: #1f2937; margin-bottom: 10px;">ACCESS DENIED</h2>
                <p style="color: #6b7280; margin-bottom: 25px;">Invalid or missing admin key</p>
                <div style="color: #9ca3af; font-size: 12px;">
                    VISHAL X BOT ADMIN PANEL v6.0
                </div>
            </div>
        </div>
        ''', 401
    
    data = cur.execute("SELECT uid FROM users").fetchall()
    stats = get_stats()
    
    return render_template_string(HTML_TEMPLATE, 
        data=data, 
        key=key, 
        stats=stats,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        scan_time=SCAN_TIME
    )

@app.route("/export")
def export():
    if request.args.get("key") != ADMIN_KEY:
        return "❌ UNAUTHORIZED", 401
    
    data = cur.execute("SELECT uid FROM users").fetchall()
    raw = "\n".join([x[0] for x in data])
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Export IDs - VISHAL X BOT</title>
        <style>
            body {{
                font-family: monospace;
                background: #1a1a1a;
                color: #00ff00;
                padding: 20px;
                margin: 0;
            }}
            pre {{
                background: #000;
                padding: 20px;
                border-radius: 10px;
                border: 1px solid #333;
                max-height: 80vh;
                overflow: auto;
            }}
            .header {{
                text-align: center;
                margin-bottom: 20px;
                color: #fff;
                font-size: 24px;
            }}
        </style>
    </head>
    <body>
        <div class="header">📁 EXPORTED IDs • {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
        <pre>{raw}</pre>
        <script>
            // Auto select all text
            document.addEventListener('DOMContentLoaded', function() {{
                const pre = document.querySelector('pre');
                const range = document.createRange();
                range.selectNodeContents(pre);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
            }});
        </script>
    </body>
    </html>
    """

@app.route("/health")
def health():
    return jsonify({
        "status": "running",
        "version": "v6.0",
        "timestamp": datetime.now().isoformat(),
        "users": len(user_list()),
        "total_ids": get_stats()[0],
        "uptime": time.time()
    })

# ============================================================
# ========================== RUN =============================
# ============================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 VISHAL X BOT - v6.0 (2026 MODERN UI) STARTED")
    print("📊 Dashboard: http://localhost:{}/?key={}".format(PORT, ADMIN_KEY))
    print("🛡️ Anti-Leave Monitor: ACTIVE")
    print("🤖 Poller Engine: RUNNING")
    print("="*60 + "\n")
    
    threading.Thread(target=monitor,daemon=True).start()
    threading.Thread(target=poller,daemon=True).start()
    app.run(host="0.0.0.0",port=PORT)