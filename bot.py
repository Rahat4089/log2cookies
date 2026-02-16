import os
import sys
import re
import zipfile
import shutil
import hashlib
import time
import random
import string
import subprocess
import asyncio
import platform
import psutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional, Tuple

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified, FloodWait

# Third-party extraction tools
import rarfile
import py7zr

# ==============================================================================
#                            BOT CONFIGURATION
# ==============================================================================

API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]

# ==============================================================================
#                            SYSTEM / TOOL DETECTION
# ==============================================================================

MAX_WORKERS = 100
BUFFER_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}
SYSTEM = platform.system().lower()

class ToolDetector:
    @staticmethod
    def check_unrar() -> bool:
        try:
            if SYSTEM == 'windows':
                paths = ['C:\\Program Files\\WinRAR\\UnRAR.exe', 'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe', 'unrar.exe']
                for path in paths:
                    if os.path.exists(path): return True
                return subprocess.run(['unrar'], capture_output=True, shell=True).returncode != 127
            else:
                return subprocess.run(['which', 'unrar'], capture_output=True, text=True).returncode == 0
        except: return False

    @staticmethod
    def check_7z() -> bool:
        try:
            if SYSTEM == 'windows':
                paths = ['C:\\Program Files\\7-Zip\\7z.exe', 'C:\\Program Files (x86)\\7-Zip\\7z.exe', '7z.exe']
                for path in paths:
                    if os.path.exists(path): return True
                return subprocess.run(['7z'], capture_output=True, shell=True).returncode != 127
            else:
                if subprocess.run(['which', '7z'], capture_output=True, text=True).returncode == 0: return True
                return subprocess.run(['which', '7zz'], capture_output=True, text=True).returncode == 0
        except: return False

    @staticmethod
    def get_tool_path(tool_name: str) -> Optional[str]:
        if tool_name == 'unrar':
            if SYSTEM == 'windows':
                for path in ['C:\\Program Files\\WinRAR\\UnRAR.exe', 'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe']:
                    if os.path.exists(path): return path
                return 'unrar.exe'
            else:
                res = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
                return res.stdout.strip() if res.returncode == 0 else 'unrar'
        elif tool_name == '7z':
            if SYSTEM == 'windows':
                for path in ['C:\\Program Files\\7-Zip\\7z.exe', 'C:\\Program Files (x86)\\7-Zip\\7z.exe']:
                    if os.path.exists(path): return path
                return '7z.exe'
            else:
                for cmd in ['7z', '7zz']:
                    res = subprocess.run(['which', cmd], capture_output=True, text=True)
                    if res.returncode == 0: return res.stdout.strip()
                return '7z'

TOOL_STATUS = {'unrar': ToolDetector.check_unrar(), '7z': ToolDetector.check_7z()}
TOOL_PATHS = {'unrar': ToolDetector.get_tool_path('unrar') if TOOL_STATUS['unrar'] else None, '7z': ToolDetector.get_tool_path('7z') if TOOL_STATUS['7z'] else None}

# ==============================================================================
#                            UTILITY FUNCTIONS
# ==============================================================================

def sanitize_filename(filename: str) -> str:
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_random_string(length: int = 6) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def format_size(size_bytes: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0: return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def format_time(seconds: float) -> str:
    if seconds < 60: return f"{seconds:.1f}s"
    elif seconds < 3600: return f"{seconds/60:.1f}m"
    else: return f"{seconds/3600:.1f}h"

def get_file_hash_fast(filepath: str) -> str:
    try:
        with open(filepath, 'rb', buffering=BUFFER_SIZE) as f:
            first = f.read(1024)
            f.seek(-1024, 2)
            last = f.read(1024)
            return hashlib.md5(first + last).hexdigest()[:8]
    except: return str(os.path.getmtime(filepath))

def delete_entire_folder(folder_path: str) -> bool:
    if not os.path.exists(folder_path): return True
    try:
        import gc; gc.collect()
        shutil.rmtree(folder_path, ignore_errors=True)
        time.sleep(0.5)
        if os.path.exists(folder_path):
            os.system(f'rmdir /s /q "{folder_path}"' if SYSTEM == 'windows' else f'rm -rf "{folder_path}"')
        return not os.path.exists(folder_path)
    except: return False

# ==============================================================================
#                            EXTRACTOR CLASSES (Adapted)
# ==============================================================================

class UltimateArchiveExtractor:
    def __init__(self, password: Optional[str] = None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = asyncio.Lock()
        self.extracted_count = 0
        self.stop_extraction = False
    
    # Keeping extract methods synchronous as they use subprocess/blocking modules
    def extract_single(self, archive_path: str, extract_dir: str) -> List[str]:
        if self.stop_extraction: return []
        ext = os.path.splitext(archive_path)[1].lower()
        try:
            if ext == '.7z' and TOOL_STATUS['7z']:
                cmd = [TOOL_PATHS['7z'], 'x', '-y']
                if self.password: cmd.append(f'-p{self.password}')
                cmd.extend([f'-o{extract_dir}', archive_path])
                subprocess.run(cmd, capture_output=True, timeout=300)
            elif ext == '.rar' and TOOL_STATUS['unrar']:
                cmd = [TOOL_PATHS['unrar'], 'x', '-y', f'-p{self.password}' if self.password else '-p-', archive_path, extract_dir + ('\\' if SYSTEM == 'windows' else '/')]
                subprocess.run(cmd, capture_output=True, timeout=300)
            elif ext == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(extract_dir, pwd=self.password.encode() if self.password else None)
            elif ext in ['.tar', '.gz', '.bz2', '.xz']:
                import tarfile
                with tarfile.open(archive_path, 'r:*') as tf: tf.extractall(extract_dir)
            else:
                return []
            
            # Find extracted files
            files = []
            for root, _, filenames in os.walk(extract_dir):
                for f in filenames:
                    files.append(os.path.relpath(os.path.join(root, f), extract_dir))
            return files
        except: return []

    def find_archives_fast(self, directory: str) -> List[str]:
        archives = []
        for root, _, files in os.walk(directory):
            for file in files:
                if os.path.splitext(file)[1].lower() in SUPPORTED_ARCHIVES:
                    archives.append(os.path.join(root, file))
        return archives

    def extract_all_nested(self, root_archive: str, base_dir: str):
        current_level = {root_archive}
        level = 0
        while current_level and not self.stop_extraction:
            next_level = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)
            
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(current_level) or 1)) as executor:
                futures = {}
                for archive in current_level:
                    if archive in self.processed_files or self.stop_extraction: continue
                    archive_name = sanitize_filename(os.path.splitext(os.path.basename(archive))[0])[:50]
                    extract_subdir = os.path.join(level_dir, archive_name)
                    os.makedirs(extract_subdir, exist_ok=True)
                    futures[executor.submit(self.extract_single, archive, extract_subdir)] = (archive, extract_subdir)
                
                for future in as_completed(futures):
                    if self.stop_extraction: break
                    archive, extract_subdir = futures[future]
                    try:
                        future.result(timeout=60)
                        self.processed_files.add(archive)
                        new_archives = self.find_archives_fast(extract_subdir)
                        next_level.update(new_archives)
                    except: pass
            current_level = next_level
            level += 1
        return base_dir

class UltimateCookieExtractor:
    def __init__(self, target_sites: List[str]):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.site_files: Dict[str, Dict[str, str]] = {site: {} for site in self.target_sites}
        self.global_seen: Set[str] = set()
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.total_found = 0
        self.files_processed = 0
        self.stop_processing = False
        self.site_patterns = {site: re.compile(site.encode()) for site in self.target_sites}
        
    def get_unique_filename(self, site: str, orig_name: str) -> str:
        base, ext = os.path.splitext(orig_name)
        if orig_name not in self.used_filenames[site]:
            self.used_filenames[site].add(orig_name)
            return orig_name
        
        new_name = f"{base}_{generate_random_string()}{ext}"
        while new_name in self.used_filenames[site]:
            new_name = f"{base}_{generate_random_string()}{ext}"
        self.used_filenames[site].add(new_name)
        return new_name

    def process_file(self, file_path: str, orig_name: str, extract_dir: str):
        if self.stop_processing: return
        try:
            lines = []
            with open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
                for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
                    lines.extend(chunk.split(b'\n'))
            
            file_hash = get_file_hash_fast(file_path)
            site_matches = {site: [] for site in self.target_sites}
            
            for line_num, line_bytes in enumerate(lines):
                if not line_bytes or line_bytes.startswith(b'#'): continue
                line_lower = line_bytes.lower()
                line_str = line_bytes.decode('utf-8', errors='ignore').rstrip('\n\r')
                
                for site in self.target_sites:
                    if self.site_patterns[site].search(line_lower):
                        unique_id = f"{site}|{file_hash}|{line_num}"
                        if unique_id not in self.global_seen:
                            self.global_seen.add(unique_id)
                            site_matches[site].append((line_num, line_str))
                            self.total_found += 1
            
            for site, matches in site_matches.items():
                if matches:
                    matches.sort(key=lambda x: x[0])
                    site_dir = os.path.join(extract_dir, "cookies", site)
                    os.makedirs(site_dir, exist_ok=True)
                    unique_name = self.get_unique_filename(site, orig_name)
                    out_path = os.path.join(site_dir, unique_name)
                    with open(out_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join([line for _, line in matches]))
                    self.site_files[site][out_path] = unique_name
            self.files_processed += 1
        except: pass

    def process_all(self, extract_dir: str):
        cookie_files = []
        for root, _, files in os.walk(extract_dir):
            if any(folder in root for folder in COOKIE_FOLDERS):
                for file in files:
                    if file.endswith(('.txt', '.txt.bak')):
                        cookie_files.append((os.path.join(root, file), file))
                        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for fp, name in cookie_files:
                if self.stop_processing: break
                futures.append(executor.submit(self.process_file, fp, name, extract_dir))
            for future in as_completed(futures):
                if self.stop_processing: break

    def create_site_zips(self, result_folder: str) -> Dict[str, str]:
        created_zips = {}
        for site, files_dict in self.site_files.items():
            if not files_dict or self.stop_processing: continue
            zip_path = os.path.join(result_folder, f"{sanitize_filename(site)}_{datetime.now().strftime('%H%M%S')}.zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                for file_path, unique_name in files_dict.items():
                    if os.path.exists(file_path): zf.write(file_path, unique_name)
            created_zips[site] = zip_path
        return created_zips


# ==============================================================================
#                            BOT STATE & QUEUE SYSTEM
# ==============================================================================

app = Client("ultimate_cookie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Stores state: user_id -> {'state': str, 'file_msg': Message, 'password': str, 'domains': list, 'size': int}
user_sessions = {}
# Queue handling: user_id list to track waiting jobs
task_queue = []
# Tracks active user tasks and their extractors
active_tasks = {}
user_extractors = {}  # user_id -> {'arc': UltimateArchiveExtractor, 'cook': UltimateCookieExtractor}
# System boot time
BOOT_TIME = time.time()

# States
STATE_WAIT_DOC = "WAITING_DOC"
STATE_WAIT_PWD = "WAITING_PWD"
STATE_WAIT_DOMAINS = "WAITING_DOMAINS"
STATE_IN_QUEUE = "IN_QUEUE"
STATE_PROCESSING = "PROCESSING"

async def async_progress(current, total, message, start_time, action, user_id):
    if user_id in active_tasks and active_tasks[user_id].get("cancelled"):
        raise asyncio.CancelledError()
        
    now = time.time()
    diff = now - start_time
    if diff < 1: diff = 1
    speed = current / diff
    eta = round((total - current) / speed) if speed > 0 else 0
    percent = round((current / total) * 100, 1) if total else 0
    
    # Fill progress bar blocks
    filled_blocks = int(percent / 5)
    bar = "█" * filled_blocks + "░" * (20 - filled_blocks)

    if round(now) % 3 == 0 or current == total:
        text = f"**⚙️ {action}...**\n\n"
        text += f"[{bar}] {percent}%\n\n"
        text += f"📦 **Size:** {format_size(current)} / {format_size(total)}\n"
        text += f"⚡ **Speed:** {format_size(speed)}/s\n"
        text += f"⏳ **ETA:** {format_time(eta)}\n"
        text += f"⏱ **Elapsed:** {format_time(diff)}"
        
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Cancel", callback_data="cancel_task")]])
        try: await message.edit_text(text, reply_markup=reply_markup)
        except MessageNotModified: pass
        except FloodWait as e: await asyncio.sleep(e.value)

# ==============================================================================
#                            COMMAND HANDLERS
# ==============================================================================

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    user_sessions.pop(message.from_user.id, None)
    text = (
        "🚀 **RUTE Cookie Extractor Bot - Ultimate Speed**\n\n"
        "Welcome! Send me any archive (`.zip`, `.rar`, `.7z`) to begin.\n"
        "I will extract nested archives, filter domains, and repackage them for you.\n\n"
        "👑 **Owner Credits:** @still_alivenow\n\n"
        "Commands:\n"
        "» /stats - View System Dashboard\n"
        "» /queue - View current queue\n"
        "» /cancel - Cancel any current operation"
    )
    await message.reply_text(text)

@app.on_message(filters.command("stats") & filters.private)
async def stats_cmd(client, message: Message):
    disk = psutil.disk_usage('/')
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_cores = psutil.cpu_count(logical=True)
    
    process = psutil.Process(os.getpid())
    bot_cpu = process.cpu_percent()
    bot_mem = process.memory_info()
    
    net = psutil.net_io_counters()
    
    uptime_sec = time.time() - BOOT_TIME
    uptime_str = f"{int(uptime_sec//3600):02}h {int((uptime_sec%3600)//60):02}m {int(uptime_sec%60):02}s"
    
    # Calculate Ping
    start_ping = time.time()
    msg = await message.reply_text("Calculating...")
    end_ping = time.time()
    ping_ms = (end_ping - start_ping) * 1000

    stats_text = (
        "🖥️ **System Statistics Dashboard**\n\n"
        "💾 **Disk Storage**\n"
        f"├ Total: {format_size(disk.total)}\n"
        f"├ Used: {format_size(disk.used)} ({disk.percent}%)\n"
        f"└ Free: {format_size(disk.free)}\n\n"
        "🧠 **RAM (Memory)**\n"
        f"├ Total: {format_size(mem.total)}\n"
        f"├ Used: {format_size(mem.used)} ({mem.percent}%)\n"
        f"└ Free: {format_size(mem.available)}\n\n"
        "⚡ **CPU**\n"
        f"├ Cores: {cpu_cores}\n"
        f"└ Usage: {cpu_percent}%\n\n"
        "🔌 **Bot Process**\n"
        f" ├ CPU: {bot_cpu}%\n"
        f" ├ RAM (RSS): {format_size(bot_mem.rss)}\n"
        f" └ RAM (VMS): {format_size(bot_mem.vms)}\n\n"
        "🌐 **Network**\n"
        f"├ Upload: {format_size(net.bytes_sent)}\n"
        f"├ Download: {format_size(net.bytes_recv)}\n"
        f"└ Total I/O: {format_size(net.bytes_sent + net.bytes_recv)}\n\n"
        "📟 **System Info**\n"
        f"├ OS: {platform.system()}\n"
        f"├ OS Version: {platform.release()}\n"
        f"├ Python: {platform.python_version()}\n"
        f"└ Uptime: {uptime_str}\n\n"
        "⏱️ **Performance**\n"
        f"└ Current Ping: {ping_ms:.3f} ms\n\n"
        "👑 **Owner Credits:** @still_alivenow"
    )
    await msg.edit_text(stats_text)

@app.on_message(filters.command("queue") & filters.private)
async def queue_cmd(client, message: Message):
    if not active_tasks and not task_queue:
        return await message.reply_text("The queue is currently empty. ✅")
    
    text = "**📊 Current Queue List:**\n\n"
    for user_id, task_data in active_tasks.items():
        text += f"🔄 **User:** `{user_id}` | Size: {format_size(task_data.get('size', 0))} | **Status:** PROCESSING\n"
    
    if task_queue:
        text += "\n**⏳ Waiting:**\n"
        for idx, user_id in enumerate(task_queue, 1):
            sess = user_sessions.get(user_id, {})
            text += f"{idx}. **User:** `{user_id}` | Size: {format_size(sess.get('size', 0))}\n"
    
    await message.reply_text(text)

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client, message: Message):
    user_id = message.from_user.id
    await cancel_logic(client, user_id, message)

@app.on_callback_query(filters.regex("cancel_task"))
async def cancel_cb(client, query: CallbackQuery):
    await query.answer("Cancelling task...")
    await cancel_logic(client, query.from_user.id, query.message, is_callback=True)

async def cancel_logic(client, user_id, message, is_callback=False):
    # Stop processing logic
    if user_id in active_tasks:
        active_tasks[user_id]["cancelled"] = True
        if user_id in user_extractors:
            if 'arc' in user_extractors[user_id]: user_extractors[user_id]['arc'].stop_extraction = True
            if 'cook' in user_extractors[user_id]: user_extractors[user_id]['cook'].stop_processing = True
    
    # Remove from queue if waiting
    if user_id in task_queue:
        task_queue.remove(user_id)
        
    # Clear session data
    user_sessions.pop(user_id, None)
    text = "🛑 Operation cancelled successfully. Send a new file to start over."
    
    if is_callback:
        await message.edit_text(text)
    else:
        await message.reply_text(text)

# ==============================================================================
#                            CORE WORKER / LOGIC
# ==============================================================================

@app.on_message(filters.document & filters.private)
async def handle_document(client, message: Message):
    user_id = message.from_user.id
    
    if user_id in active_tasks or user_id in task_queue:
        return await message.reply_text("⚠️ You already have a task in the queue or processing! One file per user. Use /cancel to stop it.")
    
    doc = message.document
    ext = os.path.splitext(doc.file_name)[1].lower() if doc.file_name else ""
    
    if ext not in SUPPORTED_ARCHIVES:
        return await message.reply_text(f"⚠️ Unsupported format. Supported: {', '.join(SUPPORTED_ARCHIVES)}")
    
    user_sessions[user_id] = {
        'state': STATE_WAIT_PWD,
        'file_msg': message,
        'size': doc.file_size
    }
    
    await message.reply_text("🔑 **Enter the archive password:**\n\n*(If there is no password, just reply with `none` or `no`)*")

@app.on_message(filters.text & filters.private & ~filters.command(["start", "stats", "queue", "cancel"]))
async def handle_text(client, message: Message):
    user_id = message.from_user.id
    session = user_sessions.get(user_id)
    
    if not session:
        return await message.reply_text("Send me an archive file first!")
    
    if session['state'] == STATE_WAIT_PWD:
        pwd = message.text.strip()
        session['password'] = None if pwd.lower() in ["none", "no"] else pwd
        session['state'] = STATE_WAIT_DOMAINS
        await message.reply_text("🎯 **Enter domains to filter:**\n\n*(Separate multiple domains with commas, e.g., `netflix.com, roblox.com`)*")
    
    elif session['state'] == STATE_WAIT_DOMAINS:
        domains = [d.strip().lower() for d in message.text.split(",") if d.strip()]
        if not domains:
            return await message.reply_text("❌ You must provide at least one domain.")
        
        session['domains'] = domains
        session['state'] = STATE_IN_QUEUE
        task_queue.append(user_id)
        
        await message.reply_text(f"✅ **Task added to queue!**\n\nYour position: {len(task_queue)}\nYou will be notified when processing begins.")
        
        # Trigger worker pool (Non-blocking)
        asyncio.create_task(process_queue())

async def process_queue():
    # Only allow max 5 concurrent global extractions to avoid server crashes
    if len(active_tasks) >= 5: 
        return
        
    if not task_queue: return
    
    user_id = task_queue.pop(0)
    session = user_sessions.get(user_id)
    if not session: return # Was cancelled
    
    active_tasks[user_id] = {"cancelled": False, "size": session['size']}
    
    # Run the worker for this user
    asyncio.create_task(user_worker(user_id, session))
    
    # Try popping another if slots available
    asyncio.create_task(process_queue())

async def user_worker(user_id: int, session: dict):
    client = app
    msg = session['file_msg']
    password = session['password']
    target_sites = session['domains']
    
    base_dir = f"./temp_work/{user_id}_{int(time.time())}"
    dl_path = os.path.join(base_dir, "downloaded_archive")
    extract_folder = os.path.join(base_dir, "extracted")
    results_folder = os.path.join(base_dir, "results")
    
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(extract_folder, exist_ok=True)
    os.makedirs(results_folder, exist_ok=True)
    
    status_msg = await msg.reply_text("⏳ Processing started...")
    start_time = time.time()
    
    try:
        # 1. Download File
        try:
            downloaded_file = await client.download_media(
                msg.document.file_id, 
                file_name=dl_path + "/", 
                progress=async_progress, 
                progress_args=(status_msg, start_time, "Downloading Archive", user_id)
            )
        except asyncio.CancelledError:
            raise Exception("Cancelled by user.")
            
        if active_tasks[user_id].get("cancelled"): raise Exception("Cancelled by user.")
        
        # Log: Silently forward incoming archive to LOG_CHANNEL
        if SEND_LOGS:
            await msg.forward(LOG_CHANNEL)
        
        await status_msg.edit_text("📦 **Extracting Archives...**\n\n*(This might take a while for large files)*")
        
        # 2. Extract Archive
        arc_extractor = UltimateArchiveExtractor(password)
        cook_extractor = UltimateCookieExtractor(target_sites)
        user_extractors[user_id] = {'arc': arc_extractor, 'cook': cook_extractor}
        
        loop = asyncio.get_running_loop()
        extracted_dir = await loop.run_in_executor(None, arc_extractor.extract_all_nested, downloaded_file, extract_folder)
        
        if active_tasks[user_id].get("cancelled"): raise Exception("Cancelled by user.")
        
        await status_msg.edit_text("🔍 **Filtering Cookies...**\n\n*(Searching for domains)*")
        
        # 3. Filter Cookies
        await loop.run_in_executor(None, cook_extractor.process_all, extracted_dir)
        
        if active_tasks[user_id].get("cancelled"): raise Exception("Cancelled by user.")
        
        # 4. Create ZIPs
        created_zips = await loop.run_in_executor(None, cook_extractor.create_site_zips, results_folder)
        
        if not created_zips:
            await status_msg.edit_text("⚠️ **No matching cookies found** for the provided domains.")
        else:
            await status_msg.edit_text(f"✅ Found {cook_extractor.total_found} entries. Uploading files...")
            
            # 5. Upload ZIPs
            for site, zip_file_path in created_zips.items():
                if active_tasks[user_id].get("cancelled"): break
                
                upload_start = time.time()
                try:
                    sent_doc = await client.send_document(
                        chat_id=user_id,
                        document=zip_file_path,
                        caption=f"✅ **Extracted:** {site}\n👑 @still_alivenow",
                        progress=async_progress,
                        progress_args=(status_msg, upload_start, f"Uploading {site}.zip", user_id)
                    )
                    # Forward the generated ZIP to Log channel silently
                    if SEND_LOGS:
                        await sent_doc.forward(LOG_CHANNEL)
                except asyncio.CancelledError:
                    raise Exception("Cancelled by user.")
            
            await status_msg.edit_text(
                f"🎉 **Extraction Complete!**\n\n"
                f"⏱ **Time Taken:** {format_time(time.time() - start_time)}\n"
                f"🔍 **Found Entries:** {cook_extractor.total_found}\n"
                f"📁 **Zips created:** {len(created_zips)}\n\n"
                f"👑 Owner Credits: @still_alivenow"
            )

    except Exception as e:
        err_msg = str(e)
        if "Cancelled" in err_msg:
            try: await status_msg.edit_text("🛑 **Operation Cancelled.**")
            except: pass
        else:
            try: await status_msg.edit_text(f"❌ **Error occurred:**\n`{err_msg}`")
            except: pass
    
    finally:
        # Cleanup State
        user_sessions.pop(user_id, None)
        active_tasks.pop(user_id, None)
        user_extractors.pop(user_id, None)
        
        # Cleanup Disk Storage
        delete_entire_folder(base_dir)
        
        # Pick the next user in queue
        asyncio.create_task(process_queue())

if __name__ == "__main__":
    app.run()
