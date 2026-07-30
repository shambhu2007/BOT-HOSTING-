# -*- coding: utf-8 -*-
#Toxic  Host Bot — Credit: @lII_KING_IIl
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import hashlib
import mimetypes
import struct

# --- Flask Keep Alive ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "💀Toxic Host Bot — Online"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")
# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    raise RuntimeError("❌ BOT_TOKEN environment variable not set! Add it in Render → Environment.")
OWNER_ID = 8219440183
ADMIN_ID  = 8219440183
YOUR_USERNAME = '@lII_KING_IIl'
UPDATE_CHANNEL = '@NovaBotz_Offical'
FORCE_JOIN_CHANNELS = ['@NovaBotz_Offical', '@Nova_ChatKing']   # user must join ALL of these
BOT_NAME = "Free Hosting"
CREDIT = "@lII_KING_IIl"

# Welcome banner image (fixed image sent to every new user)
WELCOME_IMAGE_URL = 'https://i.ibb.co/HpfHV4jX/Chat-GPT-Image-Apr-20-2026-11-08-21-AM.png'

# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# File upload limits
FREE_USER_LIMIT = 10
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# --- Malware Detection Configuration ---
MALWARE_SIGNATURES = [
    b'MZ', b'\x7fELF', b'\xfe\xed\xfa', b'\xce\xfa\xed\xfe', b'PK', b'Rar!',
]
ENCRYPTED_FILE_INDICATORS = [
    b'openssl', b'encrypted', b'cipher', b'AES', b'DES', b'RSA', b'GPG', b'PGP',
]
SUSPICIOUS_KEYWORDS = [
    b'ransomware', b'trojan', b'virus', b'malware', b'backdoor',
    b'exploit', b'payload', b'botnet', b'keylogger', b'rootkit',
]

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
#  BUTTON LAYOUTS
# ═══════════════════════════════════════════════════════
COMMAND_BUTTONS_LAYOUT_USER = [
    ["📤 Upload File", "📂 My Files"],
    ["⚡ Speed Test",  "📊 Statistics"],
    ["📤 Send Command","📞 Contact Owner"],
]
COMMAND_BUTTONS_LAYOUT_ADMIN = [
    ["📤 Upload File",  "📂 My Files"],
    ["⚡ Speed Test",   "📊 Statistics"],
    ["💳 Subscriptions","📢 Broadcast"],
    ["🔒 Lock Bot",     "🟢 Run All Scripts"],
    ["📤 Send Command", "👑 Admin Panel"],
    ["📞 Contact Owner"],
]

# ═══════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════
def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"⚠️ Invalid expiry for user {user_id}: {expiry}")
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(uid for (uid,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(uid for (uid,) in c.fetchall())
        conn.close()
        logger.info(f"Loaded: {len(active_users)} users, {len(user_subscriptions)} subs, {len(admin_ids)} admins.")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

init_db()
load_data()

# ═══════════════════════════════════════════════════════
#  FORCE JOIN CHECK
# ═══════════════════════════════════════════════════════
def get_unjoined_channels(user_id: int) -> list:
    """Return the list of FORCE_JOIN_CHANNELS the user has NOT joined."""
    if user_id in admin_ids:
        return []
    unjoined = []
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']:
                unjoined.append(channel)
        except Exception as e:
            logger.warning(f"Force-join check failed for {user_id} on {channel}: {e}")
            # fail-open per-channel to avoid locking out everyone on API error
    return unjoined

def is_member(user_id: int) -> bool:
    """Return True if the user is a member of ALL FORCE_JOIN_CHANNELS."""
    return len(get_unjoined_channels(user_id)) == 0

def require_join(func):
    """Decorator: gate any handler behind force-join."""
    def wrapper(message, *args, **kwargs):
        uid = message.from_user.id if hasattr(message, 'from_user') else None
        if uid:
            unjoined = get_unjoined_channels(uid)
            if unjoined:
                markup = types.InlineKeyboardMarkup()
                for channel in unjoined:
                    markup.add(types.InlineKeyboardButton(
                        f"✅ Join {channel}", url=f"https://t.me/{channel.lstrip('@')}"))
                markup.add(types.InlineKeyboardButton("🔄 I Joined — Verify", callback_data='verify_join'))
                channel_list = "\n".join(f"📣 {c}" for c in FORCE_JOIN_CHANNELS)
                bot.reply_to(message,
                    f"⚠️ *You must join our channels to use {BOT_NAME}!*\n\n"
                    f"1️⃣ Click the buttons below to join.\n"
                    f"2️⃣ Then tap **I Joined — Verify**.\n\n"
                    f"{channel_list}",
                    reply_markup=markup, parse_mode='Markdown')
                return
        return func(message, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# ═══════════════════════════════════════════════════════
#  MALWARE DETECTION
# ═══════════════════════════════════════════════════════
def get_file_type(file_content):
    signatures = {
        b'\x7fELF': 'application/x-executable',
        b'MZ':      'application/x-dosexec',
        b'\xfe\xed\xfa': 'application/x-mach-binary',
        b'\xce\xfa\xed\xfe': 'application/x-mach-binary',
        b'PK':  'application/zip',
        b'Rar!': 'application/x-rar',
    }
    for sig, mime in signatures.items():
        if file_content.startswith(sig):
            return mime
    return 'application/octet-stream'

def is_suspicious_file(file_content, file_name):
    file_lower = file_name.lower()
    suspicious_ext = ['.exe','.dll','.bat','.cmd','.scr','.com','.pif','.application','.gadget',
                      '.msi','.msp','.hta','.cpl','.msc','.jar','.bin','.deb','.rpm',
                      '.apk','.app','.dmg','.iso','.img']
    if any(file_lower.endswith(e) for e in suspicious_ext):
        return True, f"Suspicious file extension: {file_name}"
    for sig in MALWARE_SIGNATURES:
        if file_content.startswith(sig):
            return True, f"Malware signature detected"
    sample = file_content[:4096]
    for ind in ENCRYPTED_FILE_INDICATORS:
        if ind in sample:
            return True, f"Encrypted file indicator: {ind.decode('utf-8', errors='ignore')}"
    sample_text = sample.decode('utf-8', errors='ignore').lower()
    for kw in SUSPICIOUS_KEYWORDS:
        if kw.decode('utf-8').lower() in sample_text:
            return True, f"Suspicious keyword: {kw.decode('utf-8')}"
    try:
        ftype = get_file_type(sample)
        if ftype in ['application/x-dosexec','application/x-executable','application/x-mach-binary']:
            return True, f"Executable file type: {ftype}"
    except Exception as e:
        logger.warning(f"Could not determine file type: {e}")
    return False, "File appears safe"

def scan_file_for_malware(file_content, file_name, user_id):
    if user_id == OWNER_ID:
        return True, "Owner bypassed security check"
    is_sus, reason = is_suspicious_file(file_content, file_name)
    if is_sus:
        logger.warning(f"🚨 Malware in {file_name} from {user_id}: {reason}")
        return False, f"Security violation: {reason}"
    return True, "File passed security check"

# ═══════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════
def get_user_folder(user_id):
    folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(folder, exist_ok=True)
    return folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(owner_id, file_name):
    key = f"{owner_id}_{file_name}"
    info = bot_scripts.get(key)
    if info and info.get('process'):
        try:
            proc = psutil.Process(info['process'].pid)
            running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not running:
                _close_log(info)
                bot_scripts.pop(key, None)
            return running
        except psutil.NoSuchProcess:
            _close_log(info)
            bot_scripts.pop(key, None)
        except Exception as e:
            logger.error(f"Error checking process {key}: {e}")
    return False

def _close_log(info):
    lf = info.get('log_file')
    if lf and hasattr(lf, 'close') and not lf.closed:
        try: lf.close()
        except: pass

def kill_process_tree(process_info):
    key = process_info.get('script_key', 'N/A')
    _close_log(process_info)
    proc = process_info.get('process')
    if not proc or not hasattr(proc, 'pid') or not proc.pid:
        return
    try:
        parent = psutil.Process(proc.pid)
        kids = parent.children(recursive=True)
        for kid in kids:
            try: kid.terminate()
            except: pass
        psutil.wait_procs(kids, timeout=1)
        for kid in kids:
            try: kid.kill()
            except: pass
        try:
            parent.terminate()
            parent.wait(timeout=1)
        except psutil.TimeoutExpired:
            try: parent.kill()
            except: pass
        except psutil.NoSuchProcess:
            pass
    except psutil.NoSuchProcess:
        pass
    except Exception as e:
        logger.error(f"Error killing tree {key}: {e}", exc_info=True)

# ═══════════════════════════════════════════════════════
#  AUTO PACKAGE INSTALLATION
# ═══════════════════════════════════════════════════════
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI','telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot','aiogram': 'aiogram',
    'pyrogram': 'pyrogram','telethon': 'telethon','telethon.sync': 'telethon',
    'telepot': 'telepot','tgcrypto': 'tgcrypto','bs4': 'beautifulsoup4',
    'requests': 'requests','pillow': 'Pillow','cv2': 'opencv-python',
    'yaml': 'PyYAML','dotenv': 'python-dotenv','dateutil': 'python-dateutil',
    'pandas': 'pandas','numpy': 'numpy','flask': 'Flask','django': 'Django',
    'sqlalchemy': 'SQLAlchemy','psutil': 'psutil',
    'asyncio': None,'json': None,'datetime': None,'os': None,'sys': None,
    're': None,'time': None,'math': None,'random': None,'logging': None,
    'threading': None,'subprocess': None,'zipfile': None,'tempfile': None,
    'shutil': None,'sqlite3': None,'atexit': None,
}

def attempt_install_pip(module_name, message):
    pkg = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if pkg is None: return False
    try:
        bot.reply_to(message, f"🐍 Installing `{pkg}`...", parse_mode='Markdown')
        r = subprocess.run([sys.executable, '-m', 'pip', 'install', pkg],
                           capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if r.returncode == 0:
            bot.reply_to(message, f"✅ `{pkg}` installed.", parse_mode='Markdown')
            return True
        else:
            err = (r.stderr or r.stdout)[:2000]
            bot.reply_to(message, f"❌ Failed to install `{pkg}`:\n```\n{err}\n```", parse_mode='Markdown')
            return False
    except Exception as e:
        bot.reply_to(message, f"❌ Error installing `{pkg}`: {e}")
        return False

def attempt_install_npm(module_name, user_folder, message):
    try:
        bot.reply_to(message, f"🟠 Installing node pkg `{module_name}`...", parse_mode='Markdown')
        r = subprocess.run(['npm', 'install', module_name],
                           capture_output=True, text=True, cwd=user_folder, encoding='utf-8', errors='ignore')
        if r.returncode == 0:
            bot.reply_to(message, f"✅ Node pkg `{module_name}` installed.", parse_mode='Markdown')
            return True
        else:
            err = (r.stderr or r.stdout)[:2000]
            bot.reply_to(message, f"❌ Failed npm install `{module_name}`:\n```\n{err}\n```", parse_mode='Markdown')
            return False
    except FileNotFoundError:
        bot.reply_to(message, "❌ 'npm' not found. Install Node.js first.")
        return False
    except Exception as e:
        bot.reply_to(message, f"❌ npm error: {e}")
        return False

def run_script(script_path, owner_id, user_folder, file_name, msg_obj, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(msg_obj, f"❌ Failed to run `{file_name}` after {max_attempts} attempts.")
        return
    key = f"{owner_id}_{file_name}"
    try:
        if not os.path.exists(script_path):
            bot.reply_to(msg_obj, f"❌ Script `{file_name}` not found!"); return

        if attempt == 1:
            check_proc = None
            try:
                check_proc = subprocess.Popen([sys.executable, script_path], cwd=user_folder,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, encoding='utf-8', errors='ignore')
                _, stderr = check_proc.communicate(timeout=5)
                if check_proc.returncode != 0 and stderr:
                    m = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if m:
                        mod = m.group(1).strip().strip("'\"")
                        if attempt_install_pip(mod, msg_obj):
                            bot.reply_to(msg_obj, f"🔄 Retrying `{file_name}`...")
                            time.sleep(2)
                            threading.Thread(target=run_script,
                                args=(script_path, owner_id, user_folder, file_name, msg_obj, attempt+1)).start()
                        else:
                            bot.reply_to(msg_obj, f"❌ Install failed. Cannot run `{file_name}`.")
                        return
                    else:
                        bot.reply_to(msg_obj, f"❌ Script error:\n```\n{stderr[:500]}\n```", parse_mode='Markdown')
                        return
            except subprocess.TimeoutExpired:
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                bot.reply_to(msg_obj, f"❌ Python interpreter not found."); return
            except Exception as e:
                bot.reply_to(msg_obj, f"❌ Pre-check error: {e}"); return
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill(); check_proc.communicate()

        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None
        try:
            log_file = open(log_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(msg_obj, f"❌ Cannot open log file: {e}"); return
        try:
            si = None; cf = 0
            if os.name == 'nt':
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder,
                stdout=log_file, stderr=log_file, stdin=subprocess.PIPE,
                startupinfo=si, creationflags=cf, encoding='utf-8', errors='ignore')
            bot_scripts[key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': msg_obj.chat.id, 'script_owner_id': owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder,
                'type': 'py', 'script_key': key
            }
            bot.reply_to(msg_obj, f"✅ `{file_name}` started! (PID: {process.pid})", parse_mode='Markdown')
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            bot.reply_to(msg_obj, f"❌ Error starting `{file_name}`: {e}")
            if key in bot_scripts: del bot_scripts[key]
    except Exception as e:
        bot.reply_to(msg_obj, f"❌ Unexpected error: {e}")
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key]); del bot_scripts[key]

def run_js_script(script_path, owner_id, user_folder, file_name, msg_obj, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(msg_obj, f"❌ Failed to run `{file_name}` after {max_attempts} attempts.")
        return
    key = f"{owner_id}_{file_name}"
    try:
        if not os.path.exists(script_path):
            bot.reply_to(msg_obj, f"❌ Script `{file_name}` not found!"); return

        if attempt == 1:
            check_proc = None
            try:
                check_proc = subprocess.Popen(['node', script_path], cwd=user_folder,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, encoding='utf-8', errors='ignore')
                _, stderr = check_proc.communicate(timeout=5)
                if check_proc.returncode != 0 and stderr:
                    m = re.search(r"Cannot find module '(.+?)'", stderr)
                    if m:
                        mod = m.group(1).strip().strip("'\"")
                        if not mod.startswith('.') and not mod.startswith('/'):
                            if attempt_install_npm(mod, user_folder, msg_obj):
                                bot.reply_to(msg_obj, f"🔄 Retrying `{file_name}`...")
                                time.sleep(2)
                                threading.Thread(target=run_js_script,
                                    args=(script_path, owner_id, user_folder, file_name, msg_obj, attempt+1)).start()
                            else:
                                bot.reply_to(msg_obj, f"❌ NPM install failed.")
                            return
                    bot.reply_to(msg_obj, f"❌ JS error:\n```\n{stderr[:500]}\n```", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
            except FileNotFoundError:
                bot.reply_to(msg_obj, "❌ 'node' not found. Install Node.js."); return
            except Exception as e:
                bot.reply_to(msg_obj, f"❌ JS pre-check error: {e}"); return
            finally:
                if check_proc and check_proc.poll() is None:
                    check_proc.kill(); check_proc.communicate()

        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None
        try:
            log_file = open(log_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(msg_obj, f"❌ Cannot open log file: {e}"); return
        try:
            si = None
            if os.name == 'nt':
                si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder,
                stdout=log_file, stderr=log_file, stdin=subprocess.PIPE,
                startupinfo=si, encoding='utf-8', errors='ignore')
            bot_scripts[key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': msg_obj.chat.id, 'script_owner_id': owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder,
                'type': 'js', 'script_key': key
            }
            bot.reply_to(msg_obj, f"✅ `{file_name}` started! (PID: {process.pid})", parse_mode='Markdown')
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            bot.reply_to(msg_obj, f"❌ Error starting `{file_name}`: {e}")
            if key in bot_scripts: del bot_scripts[key]
    except Exception as e:
        bot.reply_to(msg_obj, f"❌ Unexpected JS error: {e}")
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key]); del bot_scripts[key]

# ═══════════════════════════════════════════════════════
#  DATABASE OPERATIONS
# ═══════════════════════════════════════════════════════
DB_LOCK = threading.Lock()

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files VALUES (?,?,?)', (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn,ft) for fn,ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
        except Exception as e: logger.error(f"❌ save_user_file: {e}")
        finally: conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id=? AND file_name=?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]: del user_files[user_id]
        except Exception as e: logger.error(f"❌ remove_user_file_db: {e}")
        finally: conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users VALUES (?)', (user_id,))
            conn.commit()
        except Exception as e: logger.error(f"❌ add_active_user: {e}")
        finally: conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO subscriptions VALUES (?,?)', (user_id, expiry.isoformat()))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
        except Exception as e: logger.error(f"❌ save_subscription: {e}")
        finally: conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id=?', (user_id,))
            conn.commit()
            user_subscriptions.pop(user_id, None)
        except Exception as e: logger.error(f"❌ remove_subscription_db: {e}")
        finally: conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins VALUES (?)', (admin_id,))
            conn.commit()
            admin_ids.add(admin_id)
        except Exception as e: logger.error(f"❌ add_admin_db: {e}")
        finally: conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID: return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        removed = False
        try:
            c.execute('DELETE FROM admins WHERE user_id=?', (admin_id,))
            conn.commit()
            removed = c.rowcount > 0
            if removed: admin_ids.discard(admin_id)
        except Exception as e: logger.error(f"❌ remove_admin_db: {e}")
        finally: conn.close()
        return removed

# ═══════════════════════════════════════════════════════
#  MENU BUILDERS
# ═══════════════════════════════════════════════════════
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if user_id in admin_ids:
        markup.add(
            types.InlineKeyboardButton('📤 Upload File',  callback_data='upload'),
            types.InlineKeyboardButton('📂 My Files',     callback_data='check_files'),
        )
        markup.add(
            types.InlineKeyboardButton('⚡ Speed Test',   callback_data='speed'),
            types.InlineKeyboardButton('📊 Statistics',   callback_data='stats'),
        )
        markup.add(
            types.InlineKeyboardButton('💳 Subscriptions',callback_data='subscription'),
            types.InlineKeyboardButton('📢 Broadcast',    callback_data='broadcast'),
        )
        markup.add(
            types.InlineKeyboardButton('🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot',
                callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('🟢 Run All Scripts', callback_data='run_all_scripts'),
        )
        markup.add(
            types.InlineKeyboardButton('📤 Send Command', callback_data='send_command'),
            types.InlineKeyboardButton('👑 Admin Panel',  callback_data='admin_panel'),
        )
    else:
        markup.add(
            types.InlineKeyboardButton('📤 Upload File',  callback_data='upload'),
            types.InlineKeyboardButton('📂 My Files',     callback_data='check_files'),
        )
        markup.add(
            types.InlineKeyboardButton('⚡ Speed Test',   callback_data='speed'),
            types.InlineKeyboardButton('📊 Statistics',   callback_data='stats'),
        )
        markup.add(
            types.InlineKeyboardButton('📤 Send Command', callback_data='send_command'),
        )
    markup.add(
        types.InlineKeyboardButton(f'📞 Contact — {CREDIT}',
            url=f'https://t.me/{YOUR_USERNAME.lstrip("@")}')
    )
    return markup

def create_reply_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout = COMMAND_BUTTONS_LAYOUT_ADMIN if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER
    for row in layout:
        markup.add(*[types.KeyboardButton(t) for t in row])
    return markup

def create_control_buttons(owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop",    callback_data=f'stop_{owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{owner_id}_{file_name}'),
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete",  callback_data=f'delete_{owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs",    callback_data=f'logs_{owner_id}_{file_name}'),
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start",  callback_data=f'start_{owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{owner_id}_{file_name}'),
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{owner_id}_{file_name}'),
        )
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin',    callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin'),
    )
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Sub',    callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Sub', callback_data='remove_subscription'),
    )
    markup.row(types.InlineKeyboardButton('🔍 Check Sub', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

def create_send_command_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('📝 Send to Process', callback_data='send_to_process'),
        types.InlineKeyboardButton('🗂️ View All Logs',   callback_data='view_all_logs'),
    )
    markup.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return markup

# ═══════════════════════════════════════════════════════
#  FILE HANDLING
# ═══════════════════════════════════════════════════════
def handle_zip_file(content, zip_name, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    tmp = None
    if user_id != OWNER_ID:
        ok, reason = scan_file_for_malware(content, zip_name, user_id)
        if not ok:
            bot.reply_to(message, f"🚨 Security Alert: {reason}"); return
    try:
        tmp = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        zip_path = os.path.join(tmp, zip_name)
        with open(zip_path, 'wb') as f: f.write(content)
        with zipfile.ZipFile(zip_path, 'r') as zr:
            if user_id != OWNER_ID:
                sus_ext = ['.exe','.dll','.bat','.cmd','.scr','.com']
                for m in zr.infolist():
                    if any(m.filename.lower().endswith(e) for e in sus_ext):
                        bot.reply_to(message, f"🚨 ZIP contains suspicious file: {m.filename}"); return
                    mp = os.path.abspath(os.path.join(tmp, m.filename))
                    if not mp.startswith(os.path.abspath(tmp)):
                        raise zipfile.BadZipFile(f"Unsafe path: {m.filename}")
            zr.extractall(tmp)

        target = tmp
        root_files = os.listdir(target)
        if not any(f.endswith(('.py','.js')) for f in root_files):
            for root, dirs, files in os.walk(tmp):
                dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('__')]
                if any(f.endswith(('.py','.js')) for f in files):
                    target = root; break
        if target != tmp:
            for item in os.listdir(target):
                s = os.path.join(target, item); d = os.path.join(tmp, item)
                if os.path.exists(d):
                    shutil.rmtree(d) if os.path.isdir(d) else os.remove(d)
                shutil.move(s, d)

        items = os.listdir(tmp)
        py_files = [f for f in items if f.endswith('.py')]
        js_files = [f for f in items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in items else None
        pkg_json = 'package.json'     if 'package.json'      in items else None

        if req_file:
            bot.reply_to(message, "🔄 Installing Python deps...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', os.path.join(tmp, req_file)],
                               check=True, capture_output=True, encoding='utf-8', errors='ignore')
                bot.reply_to(message, "✅ Python deps installed.")
            except subprocess.CalledProcessError as e:
                bot.reply_to(message, f"❌ pip install failed:\n```\n{(e.stderr or e.stdout)[:1500]}\n```", parse_mode='Markdown'); return

        if pkg_json:
            bot.reply_to(message, "🔄 Installing Node deps...")
            try:
                subprocess.run(['npm', 'install'], check=True, capture_output=True, cwd=tmp, encoding='utf-8', errors='ignore')
                bot.reply_to(message, "✅ Node deps installed.")
            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                bot.reply_to(message, f"❌ npm install failed: {e}"); return

        main_script = None; file_type = None
        for p in ['main.py','bot.py','app.py']:
            if p in py_files: main_script = p; file_type = 'py'; break
        if not main_script:
            for p in ['index.js','main.js','bot.js','app.js']:
                if p in js_files: main_script = p; file_type = 'js'; break
        if not main_script:
            if py_files: main_script = py_files[0]; file_type = 'py'
            elif js_files: main_script = js_files[0]; file_type = 'js'
        if not main_script:
            bot.reply_to(message, "❌ No `.py` or `.js` found in archive!"); return

        for item in os.listdir(tmp):
            if item == zip_name: continue
            s = os.path.join(tmp, item); d = os.path.join(user_folder, item)
            if os.path.exists(d):
                shutil.rmtree(d) if os.path.isdir(d) else os.remove(d)
            shutil.move(s, d)

        save_user_file(user_id, main_script, file_type)
        main_path = os.path.join(user_folder, main_script)
        bot.reply_to(message, f"✅ Extracted. Starting `{main_script}`...", parse_mode='Markdown')
        fn = run_script if file_type == 'py' else run_js_script
        threading.Thread(target=fn, args=(main_path, user_id, user_folder, main_script, message)).start()
    except zipfile.BadZipFile as e:
        bot.reply_to(message, f"❌ Bad ZIP: {e}")
    except Exception as e:
        logger.error(f"❌ ZIP error for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Error processing zip: {e}")
    finally:
        if tmp and os.path.exists(tmp):
            try: shutil.rmtree(tmp)
            except: pass

def handle_js_file(path, owner_id, folder, name, msg):
    save_user_file(owner_id, name, 'js')
    threading.Thread(target=run_js_script, args=(path, owner_id, folder, name, msg)).start()

def handle_py_file(path, owner_id, folder, name, msg):
    save_user_file(owner_id, name, 'py')
    threading.Thread(target=run_script, args=(path, owner_id, folder, name, msg)).start()

# ═══════════════════════════════════════════════════════
#  SEND COMMAND / LOGS HELPERS
# ═══════════════════════════════════════════════════════
def send_to_process_init(message):
    user_id = message.from_user.id
    running = [(k, v) for k, v in bot_scripts.items()
               if (user_id == v['script_owner_id'] or user_id in admin_ids)
               and is_bot_running(v['script_owner_id'], v['file_name'])]
    if not running:
        bot.reply_to(message, "❌ No running scripts found."); return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, info in running:
        markup.add(types.InlineKeyboardButton(
            f"{info['file_name']} (UID: {info['script_owner_id']})",
            callback_data=f'sendcmd_select_{key}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='send_command'))
    bot.reply_to(message, "📝 Select script:", reply_markup=markup)

def process_send_command(message, script_key):
    if script_key not in bot_scripts:
        bot.reply_to(message, "❌ Script no longer running."); return
    info = bot_scripts[script_key]
    try:
        proc = info['process']
        if proc and proc.poll() is None:
            proc.stdin.write(message.text + '\n')
            proc.stdin.flush()
            bot.reply_to(message, f"✅ Sent to `{info['file_name']}`:\n`{message.text}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"❌ `{info['file_name']}` is not running.", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

def view_all_logs(message):
    user_id = message.from_user.id
    folder = get_user_folder(user_id)
    logs = []
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.endswith('.log'):
                p = os.path.join(folder, f)
                logs.append((f, os.path.getsize(p), p))
    if not logs:
        bot.reply_to(message, "📜 No log files found."); return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for lf, sz, _ in sorted(logs):
        markup.add(types.InlineKeyboardButton(f"{lf} ({sz/1024:.1f} KB)",
                                              callback_data=f'viewlog_{user_id}_{lf}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='send_command'))
    bot.reply_to(message, "📜 Log files:", reply_markup=markup)

def send_log_file(message, log_path, log_filename):
    try:
        if os.path.getsize(log_path) > 50 * 1024 * 1024:
            bot.reply_to(message, "❌ Log too large (>50 MB)."); return
        with open(log_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"📜 {log_filename}")
    except Exception as e:
        bot.reply_to(message, f"❌ Error sending log: {e}")

# ═══════════════════════════════════════════════════════
#  LOGIC FUNCTIONS
# ═══════════════════════════════════════════════════════
def _logic_send_welcome(message):
    user_id  = message.from_user.id
    chat_id  = message.chat.id
    name     = message.from_user.first_name
    username = message.from_user.username

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot is currently locked by admin. Try later."); return

    # Force-join gate
    unjoined = get_unjoined_channels(user_id)
    if unjoined:
        markup = types.InlineKeyboardMarkup()
        for channel in unjoined:
            markup.add(types.InlineKeyboardButton(f"✅ Join {channel}",
                url=f"https://t.me/{channel.lstrip('@')}"))
        markup.add(types.InlineKeyboardButton("🔄 I Joined — Verify", callback_data='verify_join'))
        channel_list = "\n".join(f"📣 {c}" for c in FORCE_JOIN_CHANNELS)
        bot.send_message(chat_id,
            f"👋 Welcome to *{BOT_NAME}*!\n\n"
            f"⚠️ You must join our channels first to continue.\n\n"
            f"{channel_list}",
            reply_markup=markup, parse_mode='Markdown')
        return

    # New user notification to admin (name, ID, time only — no profile photo)
    if user_id not in active_users:
        add_active_user(user_id)
        join_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            bot.send_message(OWNER_ID,
                f"🆕 *New User Joined!*\n\n"
                f"👤 Name: {name}\n"
                f"✳️ Username: @{username or 'N/A'}\n"
                f"🆔 ID: `{user_id}`\n"
                f"🕐 Time: {join_time}",
                parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Could not notify owner: {e}")

    file_limit   = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str    = str(file_limit) if file_limit != float('inf') else "∞"
    expiry_info  = ""

    if user_id == OWNER_ID:        user_status = "👑 Owner"
    elif user_id in admin_ids:     user_status = "🛡️ Admin"
    elif user_id in user_subscriptions:
        exp = user_subscriptions[user_id].get('expiry')
        if exp and exp > datetime.now():
            days = (exp - datetime.now()).days
            user_status  = "⭐ Premium"
            expiry_info  = f"\n⏳ Expires in: {days} day(s)"
        else:
            user_status = "🆓 Free User"
            remove_subscription_db(user_id)
    else:
        user_status = "🆓 Free User"

    welcome_text = (
        f"💀 *{BOT_NAME}*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👋 Hello, {name}!\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Username: `@{username or 'Not set'}`\n"
        f"🔰 Status: {user_status}{expiry_info}\n"
        f"📁 Files: {current_files} / {limit_str}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Host & run Python or JS scripts.\n"
        f"Upload `.py`, `.js`, or `.zip` archives.\n\n"
        f"👇 Use the menu below to get started.\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"✨ Credit: {CREDIT}"
    )

    reply_kb = create_reply_keyboard(user_id)
    try:
        bot.send_photo(chat_id, WELCOME_IMAGE_URL,
                       caption=welcome_text,
                       reply_markup=reply_kb,
                       parse_mode='Markdown')
    except Exception:
        # Fallback: send text only if image fails
        bot.send_message(chat_id, welcome_text, reply_markup=reply_kb, parse_mode='Markdown')

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked. Cannot accept files."); return
    limit = get_user_file_limit(user_id)
    count = get_user_file_count(user_id)
    if count >= limit:
        ls = str(limit) if limit != float('inf') else "∞"
        bot.reply_to(message, f"⚠️ File limit reached ({count}/{ls}). Delete a file first.")
        return
    bot.reply_to(message, "📤 Send your `.py`, `.js`, or `.zip` file now.", parse_mode='Markdown')

def _logic_check_files(message):
    user_id = message.from_user.id
    files   = user_files.get(user_id, [])
    if not files:
        bot.reply_to(message, "📂 You have no files uploaded yet."); return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn, ft in sorted(files):
        running = is_bot_running(user_id, fn)
        icon    = "🟢" if running else "🔴"
        markup.add(types.InlineKeyboardButton(f"{icon} {fn} [{ft}]",
                                              callback_data=f'file_{user_id}_{fn}'))
    bot.reply_to(message, "📂 *Your Files* — tap to manage:", reply_markup=markup, parse_mode='Markdown')

def _logic_bot_speed(message):
    t0   = time.time()
    wait = bot.reply_to(message, "⏱️ Testing...")
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        ms = round((time.time() - t0) * 1000, 2)
        uid = message.from_user.id
        if uid == OWNER_ID:     lvl = "👑 Owner"
        elif uid in admin_ids:  lvl = "🛡️ Admin"
        elif uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
            lvl = "⭐ Premium"
        else: lvl = "🆓 Free"
        text = (f"⚡ *Speed Report*\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📶 Ping: `{ms} ms`\n"
                f"🚦 Bot: {'🔒 Locked' if bot_locked else '🟢 Online'}\n"
                f"👤 You: {lvl}")
        bot.edit_message_text(text, message.chat.id, wait.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Speed test failed: {e}", message.chat.id, wait.message_id)

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f'💬 Contact {CREDIT}',
               url=f'https://t.me/{YOUR_USERNAME.lstrip("@")}'))
    bot.reply_to(message, "📞 Tap to contact the owner/developer:", reply_markup=markup)

def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "💳 *Subscription Manager*", reply_markup=create_subscription_menu(), parse_mode='Markdown')

def _logic_statistics(message):
    user_id = message.from_user.id
    running_total = sum(1 for k, v in bot_scripts.items()
                        if is_bot_running(v['script_owner_id'], v['file_name']))
    user_running  = sum(1 for k, v in bot_scripts.items()
                        if v['script_owner_id'] == user_id
                        and is_bot_running(user_id, v['file_name']))
    text = (f"📊 *Statistics*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👥 Total Users: {len(active_users)}\n"
            f"📁 File Records: {sum(len(v) for v in user_files.values())}\n"
            f"🟢 Active Scripts: {running_total}\n"
            f"🤖 Your Scripts: {user_running}\n")
    if user_id in admin_ids:
        text += f"🔒 Bot: {'Locked' if bot_locked else 'Unlocked'}\n"
    text += f"━━━━━━━━━━━━━━━\n✨ {CREDIT}"
    bot.reply_to(message, text, parse_mode='Markdown')

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    msg = bot.reply_to(message, "📢 Send your broadcast message. /cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    global bot_locked
    bot_locked = not bot_locked
    status = "🔒 Locked" if bot_locked else "🟢 Unlocked"
    bot.reply_to(message, f"Bot is now {status}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "👑 *Admin Panel*", reply_markup=create_admin_panel(), parse_mode='Markdown')

def _logic_run_all_scripts(moc):
    if isinstance(moc, types.Message):
        uid = moc.from_user.id; cid = moc.chat.id
        reply = lambda t, **kw: bot.reply_to(moc, t, **kw)
        msg_for_script = moc
    else:  # CallbackQuery
        uid = moc.from_user.id; cid = moc.message.chat.id
        bot.answer_callback_query(moc.id)
        reply = lambda t, **kw: bot.send_message(cid, t, **kw)
        msg_for_script = moc.message
    if uid not in admin_ids:
        reply("⚠️ Admin only."); return
    reply("⏳ Starting all stopped scripts...")
    started = 0; skipped = 0
    for tuid, files in dict(user_files).items():
        folder = get_user_folder(tuid)
        for fname, ftype in files:
            if is_bot_running(tuid, fname): continue
            fpath = os.path.join(folder, fname)
            if not os.path.exists(fpath): skipped += 1; continue
            try:
                fn = run_script if ftype == 'py' else run_js_script
                threading.Thread(target=fn, args=(fpath, tuid, folder, fname, msg_for_script)).start()
                started += 1; time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error starting {fname} for {tuid}: {e}"); skipped += 1
    reply(f"✅ Done! Started: {started} | Skipped: {skipped}")

def _logic_send_command(message):
    if bot_locked and message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked."); return
    bot.reply_to(message, "📤 *Send Command*", reply_markup=create_send_command_menu(), parse_mode='Markdown')

# ═══════════════════════════════════════════════════════
#  BUTTON TEXT MAP
# ═══════════════════════════════════════════════════════
BUTTON_MAP = {
    "📤 Upload File":    _logic_upload_file,
    "📂 My Files":       _logic_check_files,
    "⚡ Speed Test":     _logic_bot_speed,
    "📊 Statistics":     _logic_statistics,
    "📤 Send Command":   _logic_send_command,
    "📞 Contact Owner":  _logic_contact_owner,
    "💳 Subscriptions":  _logic_subscriptions_panel,
    "📢 Broadcast":      _logic_broadcast_init,
    "🔒 Lock Bot":       _logic_toggle_lock_bot,
    "🟢 Run All Scripts":_logic_run_all_scripts,
    "👑 Admin Panel":    _logic_admin_panel,
}

# ═══════════════════════════════════════════════════════
#  COMMAND & TEXT HANDLERS
# ═══════════════════════════════════════════════════════
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message): _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def cmd_status(message): _logic_statistics(message)

@bot.message_handler(commands=['ping'])
def cmd_ping(message):
    t0  = time.time()
    msg = bot.reply_to(message, "🏓 Pong!")
    lat = round((time.time() - t0) * 1000, 2)
    bot.edit_message_text(f"🏓 Pong! `{lat} ms`", message.chat.id, msg.message_id, parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text in BUTTON_MAP)
def handle_buttons(message):
    fn = BUTTON_MAP.get(message.text)
    if fn: fn(message)

@bot.message_handler(commands=['uploadfile'])
def cmd_upload(m): _logic_upload_file(m)
@bot.message_handler(commands=['checkfiles'])
def cmd_check(m):  _logic_check_files(m)
@bot.message_handler(commands=['speed'])
def cmd_speed(m):  _logic_bot_speed(m)
@bot.message_handler(commands=['stats'])
def cmd_stats(m):  _logic_statistics(m)
@bot.message_handler(commands=['sendcommand'])
def cmd_sendcmd(m): _logic_send_command(m)
@bot.message_handler(commands=['contact'])
def cmd_contact(m): _logic_contact_owner(m)
@bot.message_handler(commands=['lock'])
def cmd_lock(m):   _logic_toggle_lock_bot(m)
@bot.message_handler(commands=['runall'])
def cmd_runall(m): _logic_run_all_scripts(m)
@bot.message_handler(commands=['admin'])
def cmd_admin(m):  _logic_admin_panel(m)

# ═══════════════════════════════════════════════════════
#  DOCUMENT (FILE UPLOAD) HANDLER
# ═══════════════════════════════════════════════════════
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    doc     = message.document

    unjoined = get_unjoined_channels(user_id)
    if unjoined:
        markup = types.InlineKeyboardMarkup()
        for channel in unjoined:
            markup.add(types.InlineKeyboardButton(f"✅ Join {channel}",
                url=f"https://t.me/{channel.lstrip('@')}"))
        markup.add(types.InlineKeyboardButton("🔄 I Joined — Verify", callback_data='verify_join'))
        channel_list = ", ".join(FORCE_JOIN_CHANNELS)
        bot.reply_to(message, f"⚠️ Join {channel_list} first!",
                     reply_markup=markup); return

    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked."); return

    limit = get_user_file_limit(user_id)
    count = get_user_file_count(user_id)
    if count >= limit:
        ls = str(limit) if limit != float('inf') else "∞"
        bot.reply_to(message, f"⚠️ File limit ({count}/{ls}) reached."); return

    fname = doc.file_name
    if not fname:
        bot.reply_to(message, "⚠️ File has no name."); return
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Only `.py`, `.js`, `.zip` allowed."); return
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "⚠️ File too large (max 20 MB)."); return

    try:
        try:
            bot.forward_message(OWNER_ID, message.chat.id, message.message_id)
            bot.send_message(OWNER_ID,
                f"📁 File `{fname}` from {message.from_user.first_name} (`{user_id}`)",
                parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Could not forward to owner: {e}")

        wait = bot.reply_to(message, f"⏳ Downloading `{fname}`...", parse_mode='Markdown')
        finfo   = bot.get_file(doc.file_id)
        content = bot.download_file(finfo.file_path)

        if user_id != OWNER_ID:
            ok, reason = scan_file_for_malware(content, fname, user_id)
            if not ok:
                bot.edit_message_text(f"🚨 Security Alert: {reason}",
                                      message.chat.id, wait.message_id); return

        bot.edit_message_text(f"✅ Downloaded `{fname}`. Processing...",
                              message.chat.id, wait.message_id, parse_mode='Markdown')
        user_folder = get_user_folder(user_id)

        if ext == '.zip':
            handle_zip_file(content, fname, message)
        else:
            fpath = os.path.join(user_folder, fname)
            with open(fpath, 'wb') as f: f.write(content)
            if ext == '.js': handle_js_file(fpath, user_id, user_folder, fname, message)
            else:            handle_py_file(fpath, user_id, user_folder, fname, message)

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"Telegram API error for {user_id}: {e}")
        bot.reply_to(message, f"❌ Telegram API error: {e}")
    except Exception as e:
        logger.error(f"File upload error for {user_id}: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Unexpected error: {e}")

# ═══════════════════════════════════════════════════════
#  CALLBACK QUERY ROUTER
# ═══════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data    = call.data

    # Force-join verify
    if data == 'verify_join':
        if is_member(user_id):
            bot.answer_callback_query(call.id, "✅ Verified! Use /start to continue.")
            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            _logic_send_welcome(call.message)
        else:
            channel_list = ", ".join(FORCE_JOIN_CHANNELS)
            bot.answer_callback_query(call.id,
                f"❌ You haven't joined {channel_list} yet!", show_alert=True)
        return

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main','speed','stats']:
        bot.answer_callback_query(call.id, "⚠️ Bot locked.", show_alert=True); return

    try:
        if   data == 'upload':           upload_callback(call)
        elif data == 'check_files':      check_files_callback(call)
        elif data.startswith('file_'):   file_control_callback(call)
        elif data.startswith('start_'):  start_bot_callback(call)
        elif data.startswith('stop_'):   stop_bot_callback(call)
        elif data.startswith('restart_'):restart_bot_callback(call)
        elif data.startswith('delete_'): delete_bot_callback(call)
        elif data.startswith('logs_'):   logs_bot_callback(call)
        elif data == 'speed':            speed_callback(call)
        elif data == 'back_to_main':     back_to_main_callback(call)
        elif data == 'send_command':     send_command_callback(call)
        elif data == 'send_to_process':  send_to_process_callback(call)
        elif data.startswith('sendcmd_select_'): sendcmd_select_callback(call)
        elif data == 'view_all_logs':    view_all_logs_callback(call)
        elif data.startswith('viewlog_'):viewlog_callback(call)
        elif data == 'subscription':     _admin_cb(call, subscription_management_callback)
        elif data == 'stats':            stats_callback(call)
        elif data == 'lock_bot':         _admin_cb(call, lock_bot_callback)
        elif data == 'unlock_bot':       _admin_cb(call, unlock_bot_callback)
        elif data == 'run_all_scripts':  _admin_cb(call, run_all_scripts_callback)
        elif data == 'broadcast':        _admin_cb(call, broadcast_init_callback)
        elif data == 'admin_panel':      _admin_cb(call, admin_panel_callback)
        elif data == 'add_admin':        _owner_cb(call, add_admin_init_callback)
        elif data == 'remove_admin':     _owner_cb(call, remove_admin_init_callback)
        elif data == 'list_admins':      _admin_cb(call, list_admins_callback)
        elif data == 'add_subscription': _admin_cb(call, add_subscription_init_callback)
        elif data == 'remove_subscription': _admin_cb(call, remove_subscription_init_callback)
        elif data == 'check_subscription':  _admin_cb(call, check_subscription_init_callback)
        elif data.startswith('confirm_broadcast_'): handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast': handle_cancel_broadcast(call)
        else:
            bot.answer_callback_query(call.id, "Unknown action.")
    except Exception as e:
        logger.error(f"Callback error '{data}' for {user_id}: {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Error processing.", show_alert=True)
        except: pass

def _admin_cb(call, fn):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    fn(call)

def _owner_cb(call, fn):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True); return
    fn(call)

# ═══════════════════════════════════════════════════════
#  CALLBACK IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════
def upload_callback(call):
    user_id = call.from_user.id
    limit = get_user_file_limit(user_id); count = get_user_file_count(user_id)
    if count >= limit:
        ls = str(limit) if limit != float('inf') else "∞"
        bot.answer_callback_query(call.id, f"⚠️ File limit ({count}/{ls}) reached.", show_alert=True); return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📤 Send your `.py`, `.js`, or `.zip` file.", parse_mode='Markdown')

def check_files_callback(call):
    user_id = call.from_user.id
    files   = user_files.get(user_id, [])
    if not files:
        bot.answer_callback_query(call.id, "⚠️ No files uploaded.", show_alert=True)
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
            bot.edit_message_text("📂 No files yet.", call.message.chat.id, call.message.message_id, reply_markup=markup)
        except: pass
        return
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    for fn, ft in sorted(files):
        icon = "🟢" if is_bot_running(user_id, fn) else "🔴"
        markup.add(types.InlineKeyboardButton(f"{icon} {fn} [{ft}]", callback_data=f'file_{user_id}_{fn}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    try:
        bot.edit_message_text("📂 *Your Files*:", call.message.chat.id, call.message.message_id,
                              reply_markup=markup, parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
        if "not modified" not in str(e): logger.error(f"check_files_callback edit error: {e}")

def file_control_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        files = user_files.get(oid, [])
        if not any(f[0] == fname for f in files):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); return
        bot.answer_callback_query(call.id)
        running = is_bot_running(oid, fname)
        ft = next((f[1] for f in files if f[0] == fname), '?')
        status = "🟢 Running" if running else "🔴 Stopped"
        try:
            bot.edit_message_text(
                f"⚙️ *{fname}* `[{ft}]`\nOwner: `{oid}` | Status: {status}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(oid, fname, running), parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
            if "not modified" not in str(e): raise
    except Exception as e:
        logger.error(f"file_control_callback: {e}")
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def start_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        files = user_files.get(oid, [])
        fi = next((f for f in files if f[0] == fname), None)
        if not fi:
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); return
        ft = fi[1]; folder = get_user_folder(oid); fpath = os.path.join(folder, fname)
        if not os.path.exists(fpath):
            bot.answer_callback_query(call.id, f"⚠️ File missing. Re-upload.", show_alert=True)
            remove_user_file_db(oid, fname); return
        if is_bot_running(oid, fname):
            bot.answer_callback_query(call.id, "⚠️ Already running.", show_alert=True); return
        bot.answer_callback_query(call.id, f"▶️ Starting {fname}...")
        fn = run_script if ft == 'py' else run_js_script
        threading.Thread(target=fn, args=(fpath, oid, folder, fname, call.message)).start()
        time.sleep(1.5)
        running = is_bot_running(oid, fname)
        status  = "🟢 Running" if running else "🟡 Starting..."
        try:
            bot.edit_message_text(f"⚙️ *{fname}* `[{ft}]`\nStatus: {status}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(oid, fname, running), parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
            if "not modified" not in str(e): raise
    except Exception as e:
        logger.error(f"start_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error starting.", show_alert=True)

def stop_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        files = user_files.get(oid, [])
        fi = next((f for f in files if f[0] == fname), None)
        if not fi:
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); return
        ft = fi[1]; key = f"{oid}_{fname}"
        if not is_bot_running(oid, fname):
            bot.answer_callback_query(call.id, "⚠️ Not running.", show_alert=True); return
        bot.answer_callback_query(call.id, f"⏹️ Stopping {fname}...")
        info = bot_scripts.get(key)
        if info: kill_process_tree(info)
        bot_scripts.pop(key, None)
        try:
            bot.edit_message_text(f"⚙️ *{fname}* `[{ft}]`\nStatus: 🔴 Stopped",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(oid, fname, False), parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
            if "not modified" not in str(e): raise
    except Exception as e:
        logger.error(f"stop_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error stopping.", show_alert=True)

def restart_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        files = user_files.get(oid, [])
        fi = next((f for f in files if f[0] == fname), None)
        if not fi:
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); return
        ft = fi[1]; folder = get_user_folder(oid); fpath = os.path.join(folder, fname)
        if not os.path.exists(fpath):
            bot.answer_callback_query(call.id, "⚠️ File missing. Re-upload.", show_alert=True)
            remove_user_file_db(oid, fname); return
        bot.answer_callback_query(call.id, f"🔄 Restarting {fname}...")
        key = f"{oid}_{fname}"
        if is_bot_running(oid, fname):
            info = bot_scripts.get(key)
            if info: kill_process_tree(info)
            bot_scripts.pop(key, None)
            time.sleep(1.5)
        fn = run_script if ft == 'py' else run_js_script
        threading.Thread(target=fn, args=(fpath, oid, folder, fname, call.message)).start()
        time.sleep(1.5)
        running = is_bot_running(oid, fname)
        status  = "🟢 Running" if running else "🟡 Starting..."
        try:
            bot.edit_message_text(f"⚙️ *{fname}* `[{ft}]`\nStatus: {status}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(oid, fname, running), parse_mode='Markdown')
        except telebot.apihelper.ApiTelegramException as e:
            if "not modified" not in str(e): raise
    except Exception as e:
        logger.error(f"restart_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error restarting.", show_alert=True)

def delete_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        if not any(f[0] == fname for f in user_files.get(oid, [])):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); return
        bot.answer_callback_query(call.id, f"🗑️ Deleting {fname}...")
        key = f"{oid}_{fname}"
        if is_bot_running(oid, fname):
            info = bot_scripts.get(key)
            if info: kill_process_tree(info)
            bot_scripts.pop(key, None)
        folder = get_user_folder(oid)
        for p in [os.path.join(folder, fname),
                  os.path.join(folder, f"{os.path.splitext(fname)[0]}.log")]:
            try:
                if os.path.exists(p): os.remove(p)
            except OSError as e: logger.error(f"Delete error {p}: {e}")
        remove_user_file_db(oid, fname)
        try:
            bot.edit_message_text(f"🗑️ `{fname}` deleted successfully!",
                call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        except: pass
    except Exception as e:
        logger.error(f"delete_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error deleting.", show_alert=True)

def logs_bot_callback(call):
    try:
        _, oid_str, fname = call.data.split('_', 2)
        oid = int(oid_str); uid = call.from_user.id
        if not (uid == oid or uid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        if not any(f[0] == fname for f in user_files.get(oid, [])):
            bot.answer_callback_query(call.id, "⚠️ File not found.", show_alert=True); return
        log_path = os.path.join(get_user_folder(oid), f"{os.path.splitext(fname)[0]}.log")
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, "⚠️ No logs yet.", show_alert=True); return
        bot.answer_callback_query(call.id)
        size = os.path.getsize(log_path)
        if size == 0: content = "(Log is empty)"
        elif size > 100 * 1024:
            with open(log_path, 'rb') as f:
                f.seek(-100*1024, os.SEEK_END); raw = f.read()
            content = "(Last 100 KB)\n...\n" + raw.decode('utf-8', errors='ignore')
        else:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        if len(content) > 4000: content = "...\n" + content[-3900:]
        if not content.strip(): content = "(Empty)"
        bot.send_message(call.message.chat.id,
            f"📜 *Logs* — `{fname}`:\n```\n{content}\n```", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"logs_bot_callback: {e}")
        bot.answer_callback_query(call.id, "Error fetching logs.", show_alert=True)

def speed_callback(call):
    uid = call.from_user.id; cid = call.message.chat.id
    t0  = time.time()
    try:
        bot.edit_message_text("⏱️ Testing...", cid, call.message.message_id)
        bot.send_chat_action(cid, 'typing')
        ms = round((time.time() - t0) * 1000, 2)
        if uid == OWNER_ID:    lvl = "👑 Owner"
        elif uid in admin_ids: lvl = "🛡️ Admin"
        elif uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
            lvl = "⭐ Premium"
        else: lvl = "🆓 Free"
        text = (f"⚡ *Speed Report*\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📶 Ping: `{ms} ms`\n"
                f"🚦 Bot: {'🔒 Locked' if bot_locked else '🟢 Online'}\n"
                f"👤 You: {lvl}\n"
                f"━━━━━━━━━━━━━━━")
        bot.answer_callback_query(call.id)
        bot.edit_message_text(text, cid, call.message.message_id,
                              reply_markup=create_main_menu_inline(uid), parse_mode='Markdown')
    except Exception as e:
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def back_to_main_callback(call):
    uid = call.from_user.id
    limit = get_user_file_limit(uid); count = get_user_file_count(uid)
    ls = str(limit) if limit != float('inf') else "∞"
    if uid == OWNER_ID:    st = "👑 Owner"
    elif uid in admin_ids: st = "🛡️ Admin"
    elif uid in user_subscriptions:
        exp = user_subscriptions[uid].get('expiry')
        st  = "⭐ Premium" if exp and exp > datetime.now() else "🆓 Free"
    else: st = "🆓 Free"
    text = (f"💀 *{BOT_NAME}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👋 {call.from_user.first_name}\n"
            f"🆔 `{uid}` | 🔰 {st}\n"
            f"📁 Files: {count}/{ls}\n"
            f"━━━━━━━━━━━━━━━")
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=create_main_menu_inline(uid), parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
        if "not modified" not in str(e): logger.error(f"back_to_main error: {e}")

def send_command_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("📤 *Send Command*", call.message.chat.id, call.message.message_id,
                              reply_markup=create_send_command_menu(), parse_mode='Markdown')
    except Exception as e: logger.error(f"send_command_callback: {e}")

def send_to_process_callback(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    running = [(k, v) for k, v in bot_scripts.items()
               if (user_id == v['script_owner_id'] or user_id in admin_ids)
               and is_bot_running(v['script_owner_id'], v['file_name'])]
    if not running:
        bot.answer_callback_query(call.id, "❌ No running scripts found.", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, info in running:
        markup.add(types.InlineKeyboardButton(
            f"{info['file_name']} (UID: {info['script_owner_id']})",
            callback_data=f'sendcmd_select_{key}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='send_command'))
    try:
        bot.edit_message_text("📝 Select script:", call.message.chat.id, call.message.message_id,
                              reply_markup=markup)
    except Exception as e:
        logger.error(f"send_to_process_callback: {e}")

def sendcmd_select_callback(call):
    key = call.data.replace('sendcmd_select_', '')
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='send_command'))
    try:
        bot.edit_message_text(f"📝 Enter command for `{key}`:", call.message.chat.id, call.message.message_id,
                              reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"sendcmd_select_callback: {e}")
    bot.register_next_step_handler(call.message, lambda m: process_send_command(m, key))

def view_all_logs_callback(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    folder = get_user_folder(user_id)
    logs = []
    if os.path.exists(folder):
        for f in os.listdir(folder):
            if f.endswith('.log'):
                p = os.path.join(folder, f)
                logs.append((f, os.path.getsize(p), p))
    if not logs:
        bot.answer_callback_query(call.id, "📜 No log files found.", show_alert=True)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for lf, sz, _ in sorted(logs):
        markup.add(types.InlineKeyboardButton(f"{lf} ({sz/1024:.1f} KB)",
                                              callback_data=f'viewlog_{user_id}_{lf}'))
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='send_command'))
    try:
        bot.edit_message_text("📜 Log files:", call.message.chat.id, call.message.message_id,
                              reply_markup=markup)
    except Exception as e:
        logger.error(f"view_all_logs_callback: {e}")

def viewlog_callback(call):
    try:
        _, uid_str, lf = call.data.split('_', 2)
        uid = int(uid_str); req = call.from_user.id
        if not (req == uid or req in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True); return
        lpath = os.path.join(get_user_folder(uid), lf)
        if not os.path.exists(lpath):
            bot.answer_callback_query(call.id, "❌ Log not found.", show_alert=True); return
        bot.answer_callback_query(call.id, "📜 Sending...")
        send_log_file(call.message, lpath, lf)
    except Exception as e:
        logger.error(f"viewlog_callback: {e}")
        bot.answer_callback_query(call.id, "Error.", show_alert=True)

def stats_callback(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message)

def subscription_management_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("💳 *Subscription Manager*",
            call.message.chat.id, call.message.message_id,
            reply_markup=create_subscription_menu(), parse_mode='Markdown')
    except Exception as e: logger.error(f"sub menu error: {e}")

def lock_bot_callback(call):
    global bot_locked; bot_locked = True
    bot.answer_callback_query(call.id, "🔒 Bot locked.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                       reply_markup=create_main_menu_inline(call.from_user.id))
    except: pass

def unlock_bot_callback(call):
    global bot_locked; bot_locked = False
    bot.answer_callback_query(call.id, "🟢 Bot unlocked.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                       reply_markup=create_main_menu_inline(call.from_user.id))
    except: pass

def run_all_scripts_callback(call): _logic_run_all_scripts(call)
def broadcast_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 Send broadcast message. /cancel to abort.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def admin_panel_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("👑 *Admin Panel*", call.message.chat.id, call.message.message_id,
                              reply_markup=create_admin_panel(), parse_mode='Markdown')
    except Exception as e: logger.error(f"admin panel error: {e}")

def add_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Enter User ID to promote. /cancel to abort.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID: bot.reply_to(message, "⚠️ Owner only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        nid = int(message.text.strip())
        if nid == OWNER_ID: bot.reply_to(message, "⚠️ Already owner."); return
        if nid in admin_ids: bot.reply_to(message, f"⚠️ `{nid}` is already admin."); return
        add_admin_db(nid)
        bot.reply_to(message, f"✅ User `{nid}` is now Admin.", parse_mode='Markdown')
        try: bot.send_message(nid, "🎉 You are now an Admin!")
        except: pass
    except ValueError:
        msg = bot.reply_to(message, "⚠️ Invalid ID. Try again or /cancel.")
        bot.register_next_step_handler(msg, process_add_admin_id)

def remove_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Enter Admin ID to demote. /cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID: bot.reply_to(message, "⚠️ Owner only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        rid = int(message.text.strip())
        if rid == OWNER_ID: bot.reply_to(message, "⚠️ Cannot remove owner."); return
        if rid not in admin_ids: bot.reply_to(message, f"⚠️ `{rid}` is not an admin."); return
        if remove_admin_db(rid):
            bot.reply_to(message, f"✅ Admin `{rid}` removed.", parse_mode='Markdown')
            try: bot.send_message(rid, "ℹ️ You are no longer an Admin.")
            except: pass
        else:
            bot.reply_to(message, f"❌ Failed to remove `{rid}`.", parse_mode='Markdown')
    except ValueError:
        msg = bot.reply_to(message, "⚠️ Invalid ID. Try again or /cancel.")
        bot.register_next_step_handler(msg, process_remove_admin_id)

def list_admins_callback(call):
    bot.answer_callback_query(call.id)
    lines = "\n".join(f"• `{a}` {'👑' if a == OWNER_ID else ''}" for a in sorted(admin_ids))
    try:
        bot.edit_message_text(f"👑 *Admin List*:\n\n{lines or '(none)'}",
            call.message.chat.id, call.message.message_id,
            reply_markup=create_admin_panel(), parse_mode='Markdown')
    except Exception as e: logger.error(f"list_admins: {e}")

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter: `USER_ID DAYS`\n/cancel to abort.", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_add_subscription_details)

def process_add_subscription_details(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Admin only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        parts = message.text.split()
        if len(parts) != 2: raise ValueError("Format: USER_ID DAYS")
        uid = int(parts[0]); days = int(parts[1])
        if uid <= 0 or days <= 0: raise ValueError("Values must be positive")
        base = user_subscriptions.get(uid, {}).get('expiry', datetime.now())
        if base < datetime.now(): base = datetime.now()
        exp = base + timedelta(days=days)
        save_subscription(uid, exp)
        bot.reply_to(message, f"✅ Sub for `{uid}` extended by {days} days. Expires: `{exp:%Y-%m-%d}`", parse_mode='Markdown')
        try: bot.send_message(uid, f"🎉 Sub activated! Expires: {exp:%Y-%m-%d}")
        except: pass
    except ValueError as e:
        msg = bot.reply_to(message, f"⚠️ {e}. Try again or /cancel.")
        bot.register_next_step_handler(msg, process_add_subscription_details)

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to remove sub. /cancel to abort.")
    bot.register_next_step_handler(msg, process_remove_subscription_id)

def process_remove_subscription_id(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Admin only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        uid = int(message.text.strip())
        if uid not in user_subscriptions:
            bot.reply_to(message, f"⚠️ No sub found for `{uid}`.", parse_mode='Markdown'); return
        remove_subscription_db(uid)
        bot.reply_to(message, f"✅ Sub for `{uid}` removed.", parse_mode='Markdown')
        try: bot.send_message(uid, "ℹ️ Your subscription was removed by admin.")
        except: pass
    except ValueError:
        msg = bot.reply_to(message, "⚠️ Invalid ID. /cancel to abort.")
        bot.register_next_step_handler(msg, process_remove_subscription_id)

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to check. /cancel to abort.")
    bot.register_next_step_handler(msg, process_check_subscription_id)

def process_check_subscription_id(message):
    if message.from_user.id not in admin_ids: bot.reply_to(message, "⚠️ Admin only."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Cancelled."); return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            exp = user_subscriptions[uid].get('expiry')
            if exp and exp > datetime.now():
                days = (exp - datetime.now()).days
                bot.reply_to(message,
                    f"✅ `{uid}` has active sub.\nExpires: `{exp:%Y-%m-%d}` ({days} days left)", parse_mode='Markdown')
            else:
                bot.reply_to(message, f"⚠️ `{uid}` sub expired.", parse_mode='Markdown')
                remove_subscription_db(uid)
        else:
            bot.reply_to(message, f"ℹ️ `{uid}` has no subscription.", parse_mode='Markdown')
    except ValueError:
        msg = bot.reply_to(message, "⚠️ Invalid ID. /cancel to abort.")
        bot.register_next_step_handler(msg, process_check_subscription_id)

# ═══════════════════════════════════════════════════════
#  BROADCAST
# ═══════════════════════════════════════════════════════
def process_broadcast_message(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "Broadcast cancelled."); return
    if not message.text and not (message.photo or message.video or message.document):
        msg = bot.reply_to(message, "⚠️ Empty message. Send content or /cancel.")
        bot.register_next_step_handler(msg, process_broadcast_message); return
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_broadcast_{message.message_id}"),
        types.InlineKeyboardButton("❌ Cancel",  callback_data="cancel_broadcast")
    )
    preview = (message.text or "(media)")[:800]
    bot.reply_to(message,
        f"📢 Broadcast to *{len(active_users)}* users?\n\nPreview:\n```\n{preview}\n```",
        reply_markup=markup, parse_mode='Markdown')

def handle_confirm_broadcast(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    try:
        orig = call.message.reply_to_message
        if not orig: raise ValueError("Original message not found.")
        text = photo = video = caption = None
        if orig.text:    text  = orig.text
        elif orig.photo: photo = orig.photo[-1].file_id; caption = orig.caption
        elif orig.video: video = orig.video.file_id;     caption = orig.caption
        else: raise ValueError("Unsupported media type.")
        bot.answer_callback_query(call.id, "🚀 Broadcasting...")
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)} users...",
                              call.message.chat.id, call.message.message_id)
        threading.Thread(target=execute_broadcast,
            args=(text, photo, video, caption, call.message.chat.id)).start()
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", call.message.chat.id, call.message.message_id)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "Broadcast cancelled.")
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

def execute_broadcast(text, photo, video, caption, admin_cid):
    sent = failed = blocked = 0
    users = list(active_users)
    for i, uid in enumerate(users):
        try:
            if text:  bot.send_message(uid, text, parse_mode='Markdown')
            elif photo: bot.send_photo(uid, photo, caption=caption, parse_mode='Markdown' if caption else None)
            elif video: bot.send_video(uid, video, caption=caption, parse_mode='Markdown' if caption else None)
            sent += 1
        except telebot.apihelper.ApiTelegramException as e:
            s = str(e).lower()
            if any(x in s for x in ["blocked","deactivated","not found","kicked"]):
                blocked += 1
            elif "flood" in s or "too many" in s:
                m = re.search(r"retry after (\d+)", s)
                wait = int(m.group(1)) + 1 if m else 5
                time.sleep(wait)
                try:
                    if text:  bot.send_message(uid, text, parse_mode='Markdown')
                    elif photo: bot.send_photo(uid, photo, caption=caption)
                    elif video: bot.send_video(uid, video, caption=caption)
                    sent += 1
                except: failed += 1
            else: failed += 1
        except Exception: failed += 1
        if (i+1) % 25 == 0: time.sleep(1.5)
        elif i % 5 == 0:    time.sleep(0.2)
    result = (f"📢 *Broadcast Done!*\n"
              f"✅ Sent: {sent} | ❌ Failed: {failed} | 🚫 Blocked: {blocked}\n"
              f"👥 Total: {len(users)}")
    try: bot.send_message(admin_cid, result, parse_mode='Markdown')
    except Exception as e: logger.error(f"Broadcast result send error: {e}")

# ═══════════════════════════════════════════════════════
#  CLEANUP & MAIN
# ═══════════════════════════════════════════════════════
def cleanup():
    logger.warning("Shutting down — killing all scripts...")
    for key in list(bot_scripts.keys()):
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
    logger.warning("Cleanup done.")

atexit.register(cleanup)

if __name__ == '__main__':
    logger.info(
        f"\n{'='*45}\n"
        f"  💀 {BOT_NAME}\n"
        f"  Credit : {CREDIT}\n"
        f"  Owner  : {OWNER_ID}\n"
        f"  Python : {sys.version.split()[0]}\n"
        f"{'='*45}"
    )
    keep_alive()
    logger.info("🚀 Bot polling started...")
    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("ReadTimeout — restarting in 5s..."); time.sleep(5)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"ConnectionError: {e} — retry in 15s..."); time.sleep(15)
        except Exception as e:
            logger.critical(f"💥 Polling crashed: {e}", exc_info=True)
            time.sleep(30)
        finally:
            time.sleep(1)